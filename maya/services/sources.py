"""
SQL and Python sources (§5.2): administrator-managed connections, sandboxed
producer functions, and the *pull* that snapshots either into a feature's
bitemporal ingest log.

A ``python`` source is the specification's escape hatch: a function
``produce(params)`` in the definition, returning columns (``{name: [values]}``)
or records (``[{name: value}]``). Its code is part of the definition, so it is
hashed and reviewed at approval like a SQL query, and it runs only in the
sandbox — no network, no filesystem, capped CPU, memory and output — at the
verified tier, which every pull records. It computes; it cannot fetch.

A pull is an ingest like an upload: the rows land with a knowledge time (the
source's own publication column when the definition names one, else the moment
of the pull), a restatement appends rather than overwrites, and every pin made
afterwards is reproducible from the log. Reading the source live at each
resolution would absorb upstream restatements silently — the one thing
bitemporality exists to prevent — so MAYA never does.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

from maya.core.errors import ConflictError, NotFound, PermissionDenied, ValidationFailed
from maya.persistence import external
from maya.core.clock import utcnow
from maya.security.authz import Principal
from maya.services import catalog, refs
from maya.services.feature_data import schema_generation

PARAM_TYPES = ("string", "int", "float", "date", "bool")


def bind_params(spec: dict[str, Any] | None) -> dict[str, Any]:
    """Typed parameter values for binding: ``{name: {"type": …, "value": …}}``."""
    out: dict[str, Any] = {}
    for name, p in (spec or {}).items():
        if not name.isidentifier():
            raise ValidationFailed(f"Parameter name '{name}' is not an identifier")
        kind, value = (p.get("type", "string"), p.get("value")) if isinstance(p, dict) \
            else ("string", p)
        if kind not in PARAM_TYPES:
            raise ValidationFailed(f"Parameter '{name}': type must be one of {PARAM_TYPES}")
        try:
            out[name] = {"string": str, "int": int, "float": float,
                         "date": lambda v: dt.date.fromisoformat(str(v)),
                         "bool": lambda v: str(v).lower() in ("1", "true", "yes")}[kind](value)
        except (TypeError, ValueError) as exc:
            raise ValidationFailed(f"Parameter '{name}' is not a valid {kind}") from exc
    return out


def validate_python_source(src: dict[str, Any]) -> list[str]:
    """The artifact ladder's static rungs, applied to a producer function."""
    import ast

    from maya.formula.artifact import DEFAULT_ALLOWLIST, rung_allowlist, rung_static_ban
    code, entry = src.get("code") or "", src.get("entry") or "produce"
    if not code.strip():
        return ["a python source carries its code in source.code"]
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"python source: syntax error on line {exc.lineno}: {exc.msg}"]
    errors = []
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == entry), None)
    if fn is None:
        errors.append(f"python source: no function '{entry}' at module level")
    elif [a.arg for a in fn.args.args] != ["params"]:
        errors.append(f"python source: '{entry}' must take exactly one argument, params")
    allowed = DEFAULT_ALLOWLIST | {"datetime", "calendar"}   # producers build date series
    for ok, detail in (rung_allowlist(tree, allowed), rung_static_ban(tree)):
        if not ok:
            errors.append(f"python source: {detail}")
    try:
        bind_params(src.get("params"))
    except ValidationFailed as exc:
        errors.append(exc.message)
    return errors


def run_python_source(src: dict[str, Any], settings: Any) -> tuple[Any, dict[str, Any]]:
    """Run the producer in the sandbox; its rows as a DataFrame, and what ran where."""
    import pandas as pd

    from maya.security.sandbox import run_sandboxed
    params = {k: v.isoformat() if isinstance(v, dt.date) else v
              for k, v in bind_params(src.get("params")).items()}
    wrapper = src["code"] + ("\n\ndef _maya_source(X, params):\n"
                             f"    return {src.get('entry') or 'produce'}(params)\n")
    out = run_sandboxed(wrapper, "_maya_source", {"params": params},
                        cpu_seconds=settings.int("sources.python.cpu_seconds", 30),
                        memory_mb=settings.int("sources.python.memory_mb", 1024),
                        wall_seconds=settings.int("sources.python.wall_seconds", 60),
                        output_limit_bytes=settings.int("sources.python.max_output_mb", 20)
                        * 1024 * 1024, preload=("numpy", "pandas"))
    ran = {"tier": out.get("tier"), "duration": round(out.get("duration") or 0.0, 3)}
    if not out["ok"]:
        raise ValidationFailed(f"The python source failed in the sandbox: {out['error']}", **ran)
    result = out["result"]
    if isinstance(result, dict) and all(isinstance(v, list) for v in result.values()):
        frame = pd.DataFrame(result)
    elif isinstance(result, list) and all(isinstance(r, dict) for r in result):
        frame = pd.DataFrame.from_records(result)
    else:
        raise ValidationFailed("produce(params) must return {column: [values]} or a list of "
                               "{column: value} records", got=type(result).__name__)
    return frame, ran


def validate_sql_source(src: dict[str, Any]) -> list[str]:
    errors = []
    if not src.get("connection"):
        errors.append("an sql source names an administrator-managed connection")
    try:
        external.check_query(src.get("query", ""))
        bind_params(src.get("params"))
    except ValidationFailed as exc:
        errors.append(exc.message)
    return errors


class SourceService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- connections (admin) ---------------------------------------------------------
    @staticmethod
    def _admin(p: Principal) -> None:
        if not p.is_admin:
            raise PermissionDenied("Source connections are administered by 'admin'")

    def create(self, p: Principal, *, name: str, url: str, password_env: str | None = None,
               description: str = "") -> dict[str, Any]:
        self._admin(p)
        external.check_url(url)
        if password_env and not password_env.replace("_", "").isalnum():
            raise ValidationFailed("password_env must be an environment variable name")
        with self.p.uow(p.username) as uow:
            if uow.repo("sql_connections").find_one(name=name):
                raise ConflictError(f"Connection '{name}' already exists")
            row = uow.repo("sql_connections").add({"name": name, "url": url,
                                                   "password_env": password_env or None,
                                                   "description": description})
            uow.audit("source.connection_created", object_ref=f"connection:{name}",
                      detail={"url": url, "password_env": password_env})
            return row

    def list(self) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return uow.repo("sql_connections").list(order_by=["name"])

    def delete(self, p: Principal, name: str) -> None:
        self._admin(p)
        with self.p.uow(p.username) as uow:
            row = self._get(uow, name)
            uow.repo("sql_connections").delete(row["id"])
            uow.audit("source.connection_deleted", object_ref=f"connection:{name}")

    def test(self, p: Principal, name: str) -> dict[str, Any]:
        self._admin(p)
        with self.p.uow() as uow:
            row = self._get(uow, name)
        return external.test_connection(row["url"], row["password_env"])

    @staticmethod
    def _get(uow: Any, name: str) -> dict[str, Any]:
        row = uow.repo("sql_connections").find_one(name=name)
        if row is None:
            raise NotFound(f"Source connection '{name}' does not exist")
        return row

    # -- pull ------------------------------------------------------------------------------
    def pull(self, p: Principal, ref: str, *,
             knowledge_time: dt.datetime | None = None) -> dict[str, Any]:
        """Run the feature's reviewed query or producer; append its rows to the ingest log."""
        with self.p.uow() as uow:
            feature, ns = catalog.find_object(uow, "features", "feature", refs.parse(ref, "feature"))
            self.p.access.require(uow, p, "update", "feature", feature)
            latest = catalog.latest_version(uow, "feature_versions", "feature_id", feature["id"])
            eff = catalog.effective_feature_definition(uow, latest["definition"])
            src = eff.get("source") or {}
            if src.get("type") not in ("sql", "python"):
                raise ValidationFailed("Only a feature whose source is 'sql' or 'python' is "
                                       "pulled")
            conn = self._get(uow, src["connection"]) if src["type"] == "sql" else None
        errors = catalog.blocking_errors(catalog.validate_feature_definition(eff))
        if errors:
            raise ValidationFailed("Fix the definition before pulling: " + "; ".join(errors))
        if conn is not None:
            frame = external.read_query(conn["url"], conn["password_env"], src["query"],
                                        bind_params(src.get("params")))
            code = src["query"]
            origin = {"connection": conn["name"]}
            note = f"connection '{conn['name']}'"
        else:
            frame, ran = run_python_source(src, self.p.settings)
            code = src["code"]
            origin = {"entry": src.get("entry") or "produce", **ran}
            note = f"{origin['entry']}() in the {ran['tier']} sandbox"
        known_at = knowledge_time or utcnow()
        table = self.p.feature_data.prepare_ingest(eff, frame, known_at)
        generation = f"{feature['name']}/{schema_generation(eff)}"
        prior = self.p.lake.read_raw(ns["name"], generation)
        from maya.services.features import _overlaps
        restatement = _overlaps(prior, table, eff["index"])
        version = self.p.lake.append_raw(ns["name"], generation, table)
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        with self.p.uow(p.username) as uow:
            row = uow.repo("feature_ingests").add({
                "feature_id": feature["id"], "blob_hash": None, "source_type": src["type"],
                "knowledge_time": known_at, "rows": table.num_rows, "lake_version": version,
                "note": f"pulled from {note} (code {code_hash[:12]})",
                "restatement": restatement})
            uow.audit("feature.pulled", object_type="feature",
                      object_ref=refs.object_ref("feature", ns["name"], feature["name"]),
                      detail={**origin, "source": src["type"], "rows": table.num_rows,
                              "code_sha256": code_hash, "restatement": restatement})
        return row
