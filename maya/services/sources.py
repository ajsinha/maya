"""
SQL sources (§5.2): administrator-managed connections, and the *pull* that
snapshots a feature's query into its bitemporal ingest log.

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
from maya.persistence.types import utcnow
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
        """Run the feature's reviewed query and append its rows to the ingest log."""
        with self.p.uow() as uow:
            feature, ns = catalog.find_object(uow, "features", "feature", refs.parse(ref, "feature"))
            self.p.access.require(uow, p, "update", "feature", feature)
            latest = catalog.latest_version(uow, "feature_versions", "feature_id", feature["id"])
            eff = catalog.effective_feature_definition(uow, latest["definition"])
            src = eff.get("source") or {}
            if src.get("type") != "sql":
                raise ValidationFailed("Only a feature whose source is 'sql' is pulled")
            conn = self._get(uow, src["connection"])
        errors = catalog.blocking_errors(catalog.validate_feature_definition(eff))
        if errors:
            raise ValidationFailed("Fix the definition before pulling: " + "; ".join(errors))
        frame = external.read_query(conn["url"], conn["password_env"], src["query"],
                                    bind_params(src.get("params")))
        known_at = knowledge_time or utcnow()
        table = self.p.feature_data.prepare_ingest(eff, frame, known_at)
        generation = f"{feature['name']}/{schema_generation(eff)}"
        prior = self.p.lake.read_raw(ns["name"], generation)
        from maya.services.features import _overlaps
        restatement = _overlaps(prior, table, eff["index"])
        version = self.p.lake.append_raw(ns["name"], generation, table)
        query_hash = hashlib.sha256(src["query"].encode()).hexdigest()
        with self.p.uow(p.username) as uow:
            row = uow.repo("feature_ingests").add({
                "feature_id": feature["id"], "blob_hash": None, "source_type": "sql",
                "knowledge_time": known_at, "rows": table.num_rows, "lake_version": version,
                "note": f"pulled from connection '{conn['name']}' (query {query_hash[:12]})",
                "restatement": restatement})
            uow.audit("feature.pulled", object_type="feature",
                      object_ref=refs.object_ref("feature", ns["name"], feature["name"]),
                      detail={"connection": conn["name"], "rows": table.num_rows,
                              "query_sha256": query_hash, "restatement": restatement})
        return row
