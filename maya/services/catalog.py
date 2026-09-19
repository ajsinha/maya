"""
Shared catalog mechanics: reference lookup, effective definitions through
inheritance, definition hashing, change classification and definition
validation for features (§4, §5.1–§5.8).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import contextlib
import copy
from contextvars import ContextVar
from typing import Any, Iterator

from maya.core import djson
from maya.core.errors import NotApproved, NotFound, ValidationFailed
from maya.resolution import algebra, transforms
from maya.resolution.expr import compile_expr
from maya.resolution.quality import normalize_contract
from maya.resolution.rules import parse_rule
from maya.resolution.types import parse_type
from maya.services import refs

SUPPORTED_SOURCES = ("csv", "parquet", "json", "sql", "python", "delta", "derived")
DECLARED_UNSUPPORTED: dict[str, str] = {}
APPROVED_STATES = ("approved", "published")
MAX_DERIVATION_DEPTH = 16


# -- workspace overlay (§28.3) --------------------------------------------------
# (kind, object id) -> {"base_version_no", "definition"} while resolving inside a workspace
_OVERLAY: ContextVar[dict[tuple[str, str], dict[str, Any]]] = ContextVar("maya_overlay",
                                                                         default={})


@contextlib.contextmanager
def overlay(changes: dict[tuple[str, str], dict[str, Any]]) -> Iterator[None]:
    """Resolve with staged definitions in place of the versions they would replace."""
    token = _OVERLAY.set(changes)
    try:
        yield
    finally:
        _OVERLAY.reset(token)


def overlaid(kind: str, obj_id: str, version: dict[str, Any],
             requested_version: int | None) -> dict[str, Any]:
    """The version to resolve: the staged proposal when it replaces this one."""
    change = _OVERLAY.get().get((kind, obj_id))
    if change is None:
        return version
    if requested_version is not None and requested_version != change["base_version_no"]:
        return version          # a pinned reference to another version is untouched
    return {**version, "definition": change["definition"], "workspace": True}


# -- lookups ------------------------------------------------------------------
def find_object(uow: Any, table: str, kind: str, ref: refs.Ref) -> tuple[dict[str, Any],
                                                                        dict[str, Any]]:
    """The object and its namespace for a reference (namespace optional if unique)."""
    if ref.namespace:
        ns = uow.repo("namespaces").find_one(name=ref.namespace)
        if ns is None:
            raise NotFound(f"Namespace '{ref.namespace}' does not exist")
        obj = uow.repo(table).find_one(namespace_id=ns["id"], name=ref.name)
        if obj is None:
            raise NotFound(f"{kind} '{ref.namespace}/{ref.name}' does not exist", ref=str(ref))
        return obj, ns
    matches = uow.repo(table).list(name=ref.name)
    if not matches:
        raise NotFound(f"{kind} '{ref.name}' does not exist", ref=str(ref))
    if len(matches) > 1:
        raise ValidationFailed(f"'{ref.name}' exists in several namespaces; qualify it",
                               ref=str(ref))
    return matches[0], uow.repo("namespaces").require(matches[0]["namespace_id"])


def version_of(uow: Any, table: str, fk: str, obj: dict[str, Any],
               version_no: int | None) -> dict[str, Any]:
    """A specific version, or — for a bare reference — the latest approved one."""
    if version_no is not None:
        row = uow.repo(table).find_one(**{fk: obj["id"], "version_no": version_no})
        if row is None:
            raise NotFound(f"'{obj['name']}' has no version {version_no}")
        return row
    rows = uow.repo(table).list(**{fk: obj["id"], "state__in": APPROVED_STATES},
                                order_by=["-version_no"], limit=1)
    if not rows:
        raise NotApproved(f"'{obj['name']}' has no approved version; a bare reference "
                          "resolves only to the latest approved version")
    return rows[0]


def latest_version(uow: Any, table: str, fk: str, obj_id: str) -> dict[str, Any] | None:
    rows = uow.repo(table).list(**{fk: obj_id}, order_by=["-version_no"], limit=1)
    return rows[0] if rows else None


# -- effective definitions -------------------------------------------------------
def effective_feature_definition(uow: Any, definition: dict[str, Any], *,
                                 depth: int = 0) -> dict[str, Any]:
    """Resolve ``extends`` into a complete definition: parent, then the stored diff."""
    ext = definition.get("extends")
    if not ext:
        return definition
    if depth >= MAX_DERIVATION_DEPTH:
        raise ValidationFailed("Inheritance chain exceeds the depth cap")
    parent_ref = refs.parse(ext["parent"], "feature")
    feature, ns = find_object(uow, "features", "feature", parent_ref)
    parent_version = version_of(uow, "feature_versions", "feature_id", feature,
                                parent_ref.version)
    parent = effective_feature_definition(uow, parent_version["definition"], depth=depth + 1)
    # The child's rows are the parent's rows: inheritance reuses the source binding,
    # so the child reads the ingest log of the feature that actually holds the data.
    if (parent.get("source") or {}).get("type") != "derived":
        parent.setdefault("data_from", f"{ns['name']}/{feature['name']}")
        parent.setdefault("data_schema", [[c, parent["index_types"][c]] for c in parent["index"]]
                          + [[a["name"], a["type"]] for a in parent["schema"]])
    return apply_override(parent, ext.get("override") or {}, definition)


FROZEN_STATES = ("approved", "published", "deprecated")


def pinned_parent_errors(uow: Any, definition: dict[str, Any]) -> list[str]:
    """A pinned binding is immune to parent change only if the parent cannot change: it
    must name an approved version, never a draft that is still being edited."""
    ext = definition.get("extends")
    if not ext or ext.get("binding", "pinned") != "pinned":
        return []
    parent_ref = refs.parse(ext["parent"], "feature")
    feature, _ = find_object(uow, "features", "feature", parent_ref)
    parent = version_of(uow, "feature_versions", "feature_id", feature, parent_ref.version)
    if parent["state"] not in FROZEN_STATES:
        return [f"extends {ext['parent']}, which is {parent['state']}: a pinned parent must "
                "be an approved version, or the child would change when the draft does"]
    return []


def apply_override(parent: dict[str, Any], override: dict[str, Any],
                   child: dict[str, Any]) -> dict[str, Any]:
    """The child's stored diff applied to the parent (a diff, never a copy)."""
    out = copy.deepcopy(parent)
    out.pop("extends", None)
    res = out.setdefault("resolution", {})
    res.setdefault("rules", {}).update((override.get("resolution") or {}).get("rules", {}))
    for key in ("grid", "default"):
        if key in (override.get("resolution") or {}):
            res[key] = override["resolution"][key]
    if override.get("filter"):
        out["transform"] = [{"op": "filter", "expr": override["filter"]}] + \
            list(out.get("transform") or [])
    out["transform"] = list(out.get("transform") or []) + list(override.get("transform") or [])
    out["quality"] = list(out.get("quality") or []) + list(override.get("quality") or [])
    for attr in override.get("add_attributes") or []:
        out.setdefault("schema", []).append(attr)
    drop = set(override.get("drop_attributes") or [])
    out["schema"] = [a for a in out.get("schema", []) if a["name"] not in drop]
    for key in ("description",):
        if key in child:
            out[key] = child[key]
    return out


def definition_hash(effective: dict[str, Any], self_ref: str | None = None) -> str:
    """Canonical hash of what determines values; cosmetic fields excluded.

    The data source is part of it: two features with the same schema over
    different ingest logs are different definitions, not duplicates.
    """
    body = {k: effective.get(k) for k in ("index", "index_types", "schema", "source",
                                         "transform", "quality")}
    if (effective.get("source") or {}).get("type") != "derived":
        body["data_from"] = effective.get("data_from") or self_ref
    res = effective.get("resolution") or {}
    body["resolution"] = {
        "grid": res.get("grid", "as_is"),
        "rules": {a: parse_rule(r).canonical() for a, r in sorted((res.get("rules") or {}).items())},
        "default": parse_rule(res["default"]).canonical() if res.get("default") else None,
    }
    body["transform"] = transforms.canonical_pipeline(effective.get("transform") or [])
    src = dict(body["source"] or {})
    src.pop("freshness", None)
    if src.get("type") == "derived":
        d = src.get("derivation") or {}
        src["derivation"] = algebra.canonical_derivation(d.get("operator", ""), d.get("options"),
                                                         d.get("operands") or [])
    body["source"] = src
    return djson.canonical_hash(body)


def change_class(old: dict[str, Any] | None, new: dict[str, Any]) -> str | None:
    """breaking · behavioral · additive, against the previous version (§4)."""
    if old is None:
        return None
    if old.get("index") != new.get("index") or old.get("index_types") != new.get("index_types"):
        return "breaking"
    old_attrs = {a["name"]: a["type"] for a in old.get("schema", [])}
    new_attrs = {a["name"]: a["type"] for a in new.get("schema", [])}
    if any(n not in new_attrs or new_attrs[n] != t for n, t in old_attrs.items()):
        return "breaking"
    if set(new_attrs) - set(old_attrs):
        return "additive"
    return "behavioral"


# -- validation -------------------------------------------------------------------
def validate_feature_definition(d: dict[str, Any], *, production: bool = False) -> list[str]:
    """Every problem with a feature definition, at definition time (§5.8 typing)."""
    from maya.security.licence import validate as validate_licence
    errors: list[str] = [f"licence: {e}" for e in validate_licence(d.get("licence"))]
    index = d.get("index") or []
    index_types = d.get("index_types") or {}
    schema = d.get("schema") or []
    src = (d.get("source") or {}).get("type")
    if d.get("extends"):
        binding = d["extends"].get("binding", "pinned")
        if binding not in ("pinned", "tracking"):
            errors.append("extends.binding must be 'pinned' or 'tracking'")
        if binding == "tracking" and production:
            errors.append("'tracking' parent binding is blocked in production namespaces (D-7)")
        if binding == "pinned" and "@v" not in d["extends"].get("parent", ""):
            errors.append("a 'pinned' parent must name a version (…@vN)")
        return errors
    if src in DECLARED_UNSUPPORTED:
        errors.append(DECLARED_UNSUPPORTED[src])
    elif src not in SUPPORTED_SOURCES:
        errors.append(f"source.type must be one of {', '.join(SUPPORTED_SOURCES)}")
    elif src == "sql":
        from maya.services.sources import validate_sql_source
        errors += validate_sql_source(d.get("source") or {})
    elif src == "python":
        from maya.services.sources import validate_python_source
        errors += validate_python_source(d.get("source") or {})
    if src != "derived":
        errors += _validate_index(index, index_types)
    errors += _validate_schema(schema, index)
    errors += _validate_policy(d)
    for step in d.get("transform") or []:
        try:
            transforms.validate_step(step)
        except ValidationFailed as exc:
            errors.append(f"transform: {exc.message}")
    try:
        normalize_contract(d.get("quality") or [])
    except ValidationFailed as exc:
        errors.append(f"quality: {exc.message}")
    return errors


def _validate_index(index: list[str], index_types: dict[str, str]) -> list[str]:
    errors = []
    if not index:
        errors.append("an index is required: the event-time column first, e.g. (date, symbol)")
        return errors
    for col in index:
        if col not in index_types:
            errors.append(f"index column '{col}' has no declared type")
    if index and index_types.get(index[0]) not in ("date", "timestamp"):
        errors.append(f"the first index column '{index[0]}' is the event time and must be "
                      "of type date or timestamp (bitemporality, §5.1)")
    return errors


def _validate_schema(schema: list[dict[str, Any]], index: list[str]) -> list[str]:
    errors = []
    names = [a.get("name") for a in schema]
    if not schema:
        errors.append("the schema needs at least one value attribute")
    if len(set(names)) != len(names):
        errors.append("attribute names must be unique")
    for a in schema:
        if a.get("name") in index:
            errors.append(f"'{a['name']}' is both an index column and an attribute")
        try:
            parse_type(a.get("type", ""))
        except (ValidationFailed, ValueError) as exc:
            errors.append(f"attribute '{a.get('name')}': {exc}")
        if a.get("tag") == "price" and str(a.get("type", "")).startswith("float"):
            errors.append(f"warning: '{a['name']}' carries the price tag on a float; "
                          "decimal is mandatory for monetary attributes (§5.1)")
    return [e for e in errors]


def _validate_policy(d: dict[str, Any]) -> list[str]:
    errors = []
    res = d.get("resolution") or {}
    for attr, spec in (res.get("rules") or {}).items():
        try:
            parse_rule(spec)
        except ValidationFailed as exc:
            errors.append(f"resolution rule for '{attr}': {exc.message}")
    for step in d.get("transform") or []:
        if step.get("op") in ("filter", "derive") and step.get("expr"):
            try:
                compile_expr(step["expr"])
            except ValidationFailed as exc:
                errors.append(f"expression '{step['expr']}': {exc.message}")
    return errors


def blocking_errors(errors: list[str]) -> list[str]:
    return [e for e in errors if not e.startswith("warning:")]


def non_causal_rules(d: dict[str, Any]) -> list[str]:
    res = d.get("resolution") or {}
    out = [a for a, spec in (res.get("rules") or {}).items() if parse_rule(spec).non_causal]
    if res.get("default") and parse_rule(res["default"]).non_causal:
        out.append("*default*")
    return out
