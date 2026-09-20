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
from maya.services import quota as quota_svc, refs
from maya.services import refs as refs_mod  # the same module under a name a parameter cannot shadow

SUPPORTED_SOURCES = ("csv", "parquet", "json", "sql", "python", "delta", "derived")
DECLARED_UNSUPPORTED: dict[str, str] = {}
APPROVED_STATES = ("approved", "published")
MAX_DERIVATION_DEPTH = 16


# -- workspace overlay (§28.3) --------------------------------------------------
# (kind, object id) -> {"base_version_no", "definition"} while resolving inside a workspace
_OVERLAY: ContextVar[dict[tuple[str, str], dict[str, Any]]] = ContextVar("maya_overlay", default={})


@contextlib.contextmanager
def overlay(changes: dict[tuple[str, str], dict[str, Any]]) -> Iterator[None]:
    """Resolve with staged definitions in place of the versions they would replace."""
    token = _OVERLAY.set(changes)
    try:
        yield
    finally:
        _OVERLAY.reset(token)


def overlaid(
    kind: str, obj_id: str, version: dict[str, Any], requested_version: int | None
) -> dict[str, Any]:
    """The version to resolve: the staged proposal when it replaces this one."""
    change = _OVERLAY.get().get((kind, obj_id))
    if change is None:
        return version
    if requested_version is not None and requested_version != change["base_version_no"]:
        return version  # a pinned reference to another version is untouched
    return {**version, "definition": change["definition"], "workspace": True}


# -- lookups ------------------------------------------------------------------
def find_object(
    uow: Any, table: str, kind: str, ref: refs.Ref
) -> tuple[dict[str, Any], dict[str, Any]]:
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
        raise ValidationFailed(
            f"'{ref.name}' exists in several namespaces; qualify it", ref=str(ref)
        )
    return matches[0], uow.repo("namespaces").require(matches[0]["namespace_id"])


def version_of(
    uow: Any, table: str, fk: str, obj: dict[str, Any], version_no: int | None
) -> dict[str, Any]:
    """A specific version, or — for a bare reference — the latest approved one."""
    if version_no is not None:
        row = uow.repo(table).find_one(**{fk: obj["id"], "version_no": version_no})
        if row is None:
            raise NotFound(f"'{obj['name']}' has no version {version_no}")
        return row
    rows = uow.repo(table).list(
        **{fk: obj["id"], "state__in": APPROVED_STATES}, order_by=["-version_no"], limit=1
    )
    if not rows:
        raise NotApproved(
            f"'{obj['name']}' has no approved version; a bare reference "
            "resolves only to the latest approved version"
        )
    return rows[0]


def latest_version(uow: Any, table: str, fk: str, obj_id: str) -> dict[str, Any] | None:
    rows = uow.repo(table).list(**{fk: obj_id}, order_by=["-version_no"], limit=1)
    return rows[0] if rows else None


def require_latest(uow: Any, table: str, fk: str, obj_id: str) -> dict[str, Any]:
    """The latest version, where the caller cannot go on without one: every catalog object
    is created with v1, so its absence is a named NotFound, never a TypeError later."""
    latest = latest_version(uow, table, fk, obj_id)
    if latest is None:
        raise NotFound(f"No version found in {table} for {obj_id}", id=str(obj_id))
    return latest


def in_state(uow: Any, table: str, fk: str, state: str | None, keep: Any) -> Any:
    """``keep``, narrowed to objects whose latest version is in ``state`` — one state or a
    comma-separated few ("draft,changes_requested"); ``keep`` itself when no state."""
    if not state:
        return keep
    ids = uow.repo(table).latest_in(fk, "state", [s.strip() for s in state.split(",")])
    return lambda uow, row: row["id"] in ids and keep(uow, row)


# -- effective definitions -------------------------------------------------------
def effective_feature_definition(
    uow: Any, definition: dict[str, Any], *, depth: int = 0
) -> dict[str, Any]:
    """Resolve ``extends`` into a complete definition: parent, then the stored diff."""
    ext = definition.get("extends")
    if not ext:
        return definition
    if depth >= MAX_DERIVATION_DEPTH:
        raise ValidationFailed("Inheritance chain exceeds the depth cap")
    parent_ref = refs.parse(ext["parent"], "feature")
    feature, ns = find_object(uow, "features", "feature", parent_ref)
    parent_version = version_of(uow, "feature_versions", "feature_id", feature, parent_ref.version)
    parent = effective_feature_definition(uow, parent_version["definition"], depth=depth + 1)
    # The child's rows are the parent's rows: inheritance reuses the source binding,
    # so the child reads the ingest log of the feature that actually holds the data.
    if (parent.get("source") or {}).get("type") != "derived":
        parent.setdefault("data_from", f"{ns['name']}/{feature['name']}")
        parent.setdefault(
            "data_schema",
            [[c, parent["index_types"][c]] for c in parent["index"]]
            + [[a["name"], a["type"]] for a in parent["schema"]],
        )
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
        return [
            f"extends {ext['parent']}, which is {parent['state']}: a pinned parent must "
            "be an approved version, or the child would change when the draft does"
        ]
    return []


def apply_override(
    parent: dict[str, Any], override: dict[str, Any], child: dict[str, Any]
) -> dict[str, Any]:
    """The child's stored diff applied to the parent (a diff, never a copy)."""
    out = copy.deepcopy(parent)
    out.pop("extends", None)
    res = out.setdefault("resolution", {})
    res.setdefault("rules", {}).update((override.get("resolution") or {}).get("rules", {}))
    for key in ("grid", "default"):
        if key in (override.get("resolution") or {}):
            res[key] = override["resolution"][key]
    if override.get("filter"):
        out["transform"] = [{"op": "filter", "expr": override["filter"]}] + list(
            out.get("transform") or []
        )
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


def override_count(override: dict[str, Any] | None) -> int:
    """How many things a child's ``extends`` diff changes — the number §16.3 draws on the
    inheritance edge.

    It counts changes, not JSON keys, because that is the sentence a reader wants: §6.8's
    own example ("overrides two resolution rules, drops an attribute it cannot see, and
    adds three of its own") should read as six. So a list counts its entries and a mapping
    of per-attribute rules its keys; ``resolution`` is opened one level, since its own
    entries are the overrides and it is not itself one.
    """

    def entries(value: Any) -> int:
        return len(value) if isinstance(value, (list, dict)) else 1

    total = 0
    for key, value in (override or {}).items():
        if key == "resolution" and isinstance(value, dict):
            total += sum(entries(v) for v in value.values())
        else:
            total += entries(value)
    return total


def definition_hash(effective: dict[str, Any], self_ref: str | None = None) -> str:
    """Canonical hash of what determines values; cosmetic fields excluded.

    The data source is part of it: two features with the same schema over
    different ingest logs are different definitions, not duplicates.
    """
    body = {
        k: effective.get(k)
        for k in ("index", "index_types", "schema", "source", "transform", "quality")
    }
    if (effective.get("source") or {}).get("type") != "derived":
        body["data_from"] = effective.get("data_from") or self_ref
    res = effective.get("resolution") or {}
    body["resolution"] = {
        "grid": res.get("grid", "as_is"),
        "rules": {
            a: parse_rule(r).canonical() for a, r in sorted((res.get("rules") or {}).items())
        },
        "default": parse_rule(res["default"]).canonical() if res.get("default") else None,
    }
    body["transform"] = transforms.canonical_pipeline(effective.get("transform") or [])
    src = dict(body["source"] or {})
    src.pop("freshness", None)
    if src.get("type") == "derived":
        d = src.get("derivation") or {}
        src["derivation"] = algebra.canonical_derivation(
            d.get("operator", ""), d.get("options"), d.get("operands") or []
        )
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
def validate_feature_definition(d: dict[str, Any], *, production: bool = False) -> list[str]:  # noqa: C901 - a checklist
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
        errors.append(
            f"the first index column '{index[0]}' is the event time and must be "
            "of type date or timestamp (bitemporality, §5.1)"
        )
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
            errors.append(
                f"warning: '{a['name']}' carries the price tag on a float; "
                "decimal is mandatory for monetary attributes (§5.1)"
            )
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


# -- semantic diff (§10.3) ---------------------------------------------------------
# A reviewer reads prose, not JSON. Every part of a definition has a renderer, and the
# diff names what changed in those words — "resolution rule for close: forward_fill(
# limit=3) → last_known()" — never two pretty-printed dicts side by side.
def _text(value: Any) -> str:
    """One line of plain text for a fragment of a definition."""
    if value is None or value == "" or value == [] or value == {}:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(_text(v) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k} {_text(v)}" for k, v in sorted(value.items()))
    return str(value)


def source_text(source: dict[str, Any] | None) -> str:
    """The source binding in words: where this feature's rows come from."""
    src = dict(source or {})
    kind = src.get("type") or "—"
    if kind == "derived":
        d = src.get("derivation") or {}
        operands = ", ".join(str(o) for o in (d.get("operands") or []))
        options = d.get("options") or {}
        return f"derived: {d.get('operator', '?')}({operands})" + (
            f" [{_text(options)}]" if options else ""
        )
    if kind == "sql":
        return f"sql on connection '{src.get('connection', '?')}': {src.get('query', '')}"
    if kind == "python":
        return f"python source, entry '{src.get('entrypoint') or 'build'}'"
    if kind == "delta":
        return f"delta table at {src.get('path', '?')}"
    extra = [f"{k}={_text(v)}" for k, v in sorted(src.items()) if k not in ("type", "freshness")]
    return f"{kind} upload" + (f" ({'; '.join(extra)})" if extra else "")


def attribute_text(attr: dict[str, Any]) -> str:
    """An attribute as its declaration reads: ``decimal(18,6) · tag price``."""
    bits = [str(attr.get("type") or "?")]
    for key in ("unit", "tag", "description"):
        if attr.get(key):
            bits.append(f"{key} {attr[key]}")
    if attr.get("withheld"):
        bits.append("withheld")
    return " · ".join(bits)


def step_text(step: dict[str, Any]) -> str:
    """One transform step, named and with its arguments spelled out."""
    op = step.get("op") or "?"
    args = {k: v for k, v in step.items() if k != "op"}
    return op + (
        " " + ", ".join(f"{k}={_text(v)}" for k, v in sorted(args.items())) if args else ""
    )


def check_text(check: dict[str, Any]) -> str:
    """One quality check: ``not_null(attr=close)``."""
    name = check.get("check") or "?"
    inside = ", ".join(f"{k}={_text(v)}" for k, v in sorted(check.items()) if k != "check")
    return f"{name}({inside})" if inside else name


def _entry(section: str, what: str, was: str, now: str) -> dict[str, Any]:
    change = "added" if was == "—" else "removed" if now == "—" else "changed"
    return {"section": section, "what": what, "was": was, "now": now, "change": change}


def _mapping_diff(
    section: str, label: str, old: dict[str, Any], new: dict[str, Any], render: Any
) -> list[dict[str, Any]]:
    """Every key in either side, rendered by ``render``, wherever the two differ."""
    out = []
    for key in sorted(set(old) | set(new)):
        was = render(old[key]) if key in old else "—"
        now = render(new[key]) if key in new else "—"
        if was != now:
            out.append(_entry(section, f"{label} {key}".strip(), was, now))
    return out


def _list_diff(
    section: str, label: str, old: list[Any], new: list[Any], render: Any
) -> list[dict[str, Any]]:
    """An ordered list compared position by position: a pipeline's order is meaning."""
    out = []
    was_all = [render(x) for x in old]
    now_all = [render(x) for x in new]
    for i in range(max(len(was_all), len(now_all))):
        was = was_all[i] if i < len(was_all) else "—"
        now = now_all[i] if i < len(now_all) else "—"
        if was != now:
            out.append(_entry(section, f"{label} {i + 1}", was, now))
    return out


def feature_diff(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    """Two effective feature definitions, section by section, in words (§10.3)."""
    out: list[dict[str, Any]] = []
    if (old.get("index") or []) != (new.get("index") or []):
        out.append(_entry("Index", "columns", _text(old.get("index")), _text(new.get("index"))))
    out += _mapping_diff(
        "Index", "type of", old.get("index_types") or {}, new.get("index_types") or {}, _text
    )
    out += _mapping_diff(
        "Schema",
        "attribute",
        {a["name"]: a for a in old.get("schema") or []},
        {a["name"]: a for a in new.get("schema") or []},
        attribute_text,
    )
    was_src, now_src = source_text(old.get("source")), source_text(new.get("source"))
    if was_src != now_src:
        out.append(_entry("Source", "binding", was_src, now_src))
    ores, nres = old.get("resolution") or {}, new.get("resolution") or {}
    if ores.get("grid", "as_is") != nres.get("grid", "as_is"):
        out.append(
            _entry(
                "Resolution",
                "grid",
                _text(ores.get("grid", "as_is")),
                _text(nres.get("grid", "as_is")),
            )
        )
    if _text(ores.get("default")) != _text(nres.get("default")):
        out.append(
            _entry(
                "Resolution", "default rule", _text(ores.get("default")), _text(nres.get("default"))
            )
        )
    out += _mapping_diff(
        "Resolution", "rule for", ores.get("rules") or {}, nres.get("rules") or {}, _text
    )
    out += _list_diff(
        "Transform", "step", old.get("transform") or [], new.get("transform") or [], step_text
    )
    out += _list_diff(
        "Quality", "check", old.get("quality") or [], new.get("quality") or [], check_text
    )
    if _text(old.get("licence")) != _text(new.get("licence")):
        out.append(_entry("Licence", "terms", _text(old.get("licence")), _text(new.get("licence"))))
    return out


def member_text(member: dict[str, Any]) -> str:
    """One feature-set member mapping, as the builder shows it."""
    bits = [f"{member.get('ref', '?')}.{member.get('source_attr', '?')}"]
    for key in ("cast", "rule", "alignment"):
        if member.get(key):
            bits.append(f"{key} {_text(member[key])}")
    if member.get("overrides"):
        bits.append(f"overrides {_text(member['overrides'])}")
    return " · ".join(bits)


def set_derivation_text(derivation: dict[str, Any] | None) -> str:
    """A derived feature set as its algebra reads: ``union(a, b) [collision=prefer_left]``."""
    if not derivation:
        return "—"
    operands = ", ".join(str(o) for o in (derivation.get("operands") or []))
    options = derivation.get("options") or {}
    return f"{derivation.get('operator', '?')}({operands})" + (
        f" [{_text(options)}]" if options else ""
    )


def featureset_diff(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    """Two effective feature-set definitions: the algebra of a derived set, or the
    members, alignment, filters, grid and policy of a mapped one (§6.7, §6.8)."""
    out: list[dict[str, Any]] = []
    if (old.get("index") or []) != (new.get("index") or []):
        out.append(_entry("Index", "columns", _text(old.get("index")), _text(new.get("index"))))
    was_alg, now_alg = (
        set_derivation_text(old.get("derivation")),
        set_derivation_text(new.get("derivation")),
    )
    if was_alg != now_alg:
        out.append(_entry("Algebra", "derivation", was_alg, now_alg))
    out += _mapping_diff(
        "Members",
        "attribute",
        {m["attr"]: m for m in old.get("members") or []},
        {m["attr"]: m for m in new.get("members") or []},
        member_text,
    )
    for section, key in (("Alignment", "alignment"), ("Filters", "filters"), ("Grid", "grid")):
        if _text(old.get(key)) != _text(new.get(key)):
            out.append(_entry(section, key, _text(old.get(key)), _text(new.get(key))))
    out += _mapping_diff(
        "Policy", "", old.get("global_policy") or {}, new.get("global_policy") or {}, _text
    )
    return out


def definition_diff(kind: str, old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    """The semantic diff for whichever kind of definition this is."""
    return featureset_diff(old, new) if kind == "featureset" else feature_diff(old, new)


# -- browse, facets, impact and the pin preview (§16.2, §16.4) ----------------------
# object type -> (table, access kind, version table, version foreign key)
BROWSE_TYPES: dict[str, tuple[str, str, str, str]] = {
    "feature": ("features", "feature", "feature_versions", "feature_id"),
    "featureset": ("feature_sets", "featureset", "feature_set_versions", "feature_set_id"),
    "model": ("models", "model", "model_versions", "model_id"),
}
# The freshness facet's windows, in days. For a feature, freshness is the knowledge time
# of its data; a feature set or a model has no ingest of its own, so it is when the
# object last changed. The UI names which of the two it is showing.
FRESHNESS_DAYS = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}
BROWSE_SORTS = {
    "name": "name",
    "-name": "-name",
    "updated": "updated_at",
    "-updated": "-updated_at",
    "created": "created_at",
    "-created": "-created_at",
}
PREVIEW_SAMPLE = 2000  # rows measured to estimate a pin's footprint
_ID_CHUNK = 500  # ids per IN clause, well under any backend's bound-parameter limit
NODE_LIMIT = 500  # references described in one nodes() call; a canvas draw asks for far fewer


def _chunked(items: list[str], size: int = _ID_CHUNK) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class CatalogService:
    """Browsing the catalog across its object types (§16.2) and the previews §16.4
    requires before anything irreversible: what a pin would cost, and what a change
    would break."""

    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- facets -------------------------------------------------------------------
    def facets(self, p: Any, *, type: str = "feature") -> dict[str, Any]:
        """The values each facet can take, for this object type: what the filter bar offers."""
        table, kind, _, _ = self._parts(type)
        with self.p.uow() as uow:
            users = {u["id"]: u["username"] for u in uow.repo("users").list()}
            owners = sorted(
                {
                    users[row["owner_id"]]
                    for row in uow.repo(table).slim(["owner_id"])
                    if row["owner_id"] in users
                }
            )
            statuses = sorted({row["status"] for row in uow.repo(table).slim(["status"])})
            tags = sorted(
                {
                    row["term"]
                    for row in uow.repo("search_terms").slim(["term"], kind=kind, field="tag")
                }
            )
            namespaces = [n["name"] for n in uow.repo("namespaces").list(order_by=["name"])]
        return {
            "types": sorted(BROWSE_TYPES),
            "type": type,
            "namespaces": namespaces,
            "owners": owners,
            "statuses": statuses,
            "tags": tags,
            "freshness": list(FRESHNESS_DAYS),
            "freshness_means": (
                "data known within the window"
                if type == "feature"
                else "the object changed within the window"
            ),
        }

    @staticmethod
    def _parts(type: str) -> tuple[str, str, str, str]:
        if type not in BROWSE_TYPES:
            raise ValidationFailed(
                f"type must be one of {', '.join(sorted(BROWSE_TYPES))}", type=type
            )
        return BROWSE_TYPES[type]

    # -- browse --------------------------------------------------------------------
    def browse_listing(  # noqa: C901 - one branch per facet, and the facets are the point
        self,
        uow: Any,
        p: Any,
        *,
        type: str = "feature",
        namespace: str | None = None,
        owner: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        freshness: str | None = None,
        state: str | None = None,
        q: str | None = None,
    ) -> Any:
        """'The objects of this type that ``p`` may read, narrowed by the facets' (§16.2).

        Namespace, owner and status are columns, so they narrow the query itself and the
        total is still counted by the database. Tag and freshness are not columns — a tag
        lives in the search index and a feature's freshness in its ingest log — so they
        narrow an identifier set, and the total is counted over that set alone.
        """
        from maya.services.paging import Listing

        table, kind, vtable, vkey = self._parts(type)
        filters: dict[str, Any] = {}
        if namespace:
            filters["namespace_id"] = self.p.access.namespace(uow, namespace)["id"]
        if status:
            filters["status"] = status
        if owner:
            user = uow.repo("users").find_one(username=owner)
            if user is None:
                raise NotFound(f"No user named '{owner}'", owner=owner)
            # ``owner_id__eq``, not ``owner_id``: the grouped counter takes the reader's own
            # id as a positional ``owner_id``, and a filter of that bare name would collide
            # with it. The explicit operator says the same thing and travels intact.
            filters["owner_id__eq"] = user["id"]
        narrow: set[str] | None = None
        if tag:
            narrow = self._tagged_ids(uow, kind, tag)
        if freshness:
            fresh = self._fresh_ids(uow, type, freshness, filters)
            narrow = fresh if narrow is None else (narrow & fresh)
        keep = in_state(uow, vtable, vkey, state, self.p.access.reader(uow, p, kind))
        if narrow is not None:
            keep = self._narrowed(keep, narrow, has_count=not state)
        names = {n["id"]: n["name"] for n in uow.repo("namespaces").list()}
        users = {u["id"]: u["username"] for u in uow.repo("users").list()}

        def enrich_many(uow: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            latest = uow.repo(vtable).latest_per(vkey, [r["id"] for r in rows])
            out = []
            for row in rows:
                v = latest.get(row["id"])
                ns = names.get(row["namespace_id"], "")
                out.append(
                    {
                        **row,
                        "type": type,
                        "namespace": ns,
                        "owner": users.get(row["owner_id"]),
                        "latest_version": v["version_no"] if v else None,
                        "latest_state": v["state"] if v else None,
                        "change_class": (v or {}).get("change_class"),
                        "needs_reapproval": (v or {}).get("needs_reapproval"),
                        "ref": refs.object_ref(kind, ns, row["name"]),
                        "url": self._url(type, ns, row["name"]),
                    }
                )
            return out

        scope = {"tag": tag, "freshness": freshness, "state": state}
        return Listing(
            table,
            BROWSE_SORTS,
            "name",
            filters,
            (["name", "description"], q or ""),
            keep=keep,
            enrich_many=enrich_many,
            scope={k: v for k, v in scope.items() if v},
        )

    @staticmethod
    def _url(type: str, namespace: str, name: str) -> str:
        """Where this object's page lives, so one browse row serves all three types."""
        stem = {"feature": "/catalog/features", "featureset": "/catalog/featuresets"}.get(
            type, "/models"
        )
        return f"{stem}/{namespace}/{name}"

    @staticmethod
    def _tagged_ids(uow: Any, kind: str, tag: str) -> set[str]:
        """The objects of ``kind`` carrying ``tag``, read from the search index, which is
        where a tag is already indexed term by term."""
        rows = uow.repo("search_terms").slim(
            ["object_id"], kind=kind, field="tag", term=tag.strip().lower()
        )
        return {r["object_id"] for r in rows}

    def _fresh_ids(self, uow: Any, type: str, freshness: str, filters: dict[str, Any]) -> set[str]:
        """The objects fresh within the window: for a feature, those whose ingest log
        holds rows known inside it; for anything else, those changed inside it."""
        import datetime as dt

        from maya.core.clock import utcnow

        if freshness not in FRESHNESS_DAYS:
            raise ValidationFailed(
                f"freshness must be one of {', '.join(FRESHNESS_DAYS)}", freshness=freshness
            )
        cutoff = utcnow() - dt.timedelta(days=FRESHNESS_DAYS[freshness])
        if type == "feature":
            rows = uow.repo("feature_ingests").slim(["feature_id"], knowledge_time__ge=cutoff)
            return {r["feature_id"] for r in rows}
        table = self._parts(type)[0]
        return {r["id"] for r in uow.repo(table).slim(["id"], updated_at__ge=cutoff, **filters)}

    @staticmethod
    def _narrowed(keep: Any, ids: set[str], *, has_count: bool) -> Any:
        """``keep``, restricted to ``ids``, counting the total over those ids alone."""
        kept = set(ids)

        def narrowed(uow: Any, row: dict[str, Any]) -> bool:
            return row["id"] in kept and bool(keep(uow, row))

        if has_count:

            def count(uow: Any, table: str, search: Any, filters: dict[str, Any]) -> int:
                repo = uow.repo(table)
                total = 0
                for chunk in _chunked(sorted(kept)):
                    rows = repo.slim(
                        ["id", "namespace_id", "owner_id"],
                        search=search,
                        id__in=chunk,
                        **filters,
                    )
                    total += sum(1 for r in rows if keep(uow, r))
                return total

            narrowed.count = count  # type: ignore[attr-defined]
        return narrowed

    def browse(self, p: Any, **facets: Any) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return self.browse_listing(uow, p, **facets).collect(uow)

    def browse_page(
        self,
        p: Any,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
        sort: str | None = None,
        total: bool = False,
        **facets: Any,
    ) -> dict[str, Any]:
        from maya.services.paging import run_page

        return run_page(
            self.p,
            lambda uow: self.browse_listing(uow, p, **facets),
            page_size=page_size,
            cursor=cursor,
            sort=sort,
            total=total,
        )

    # -- bulk node metadata, for a graph (§16.3) -------------------------------------
    def nodes(self, p: Any, refs: list[str]) -> dict[str, Any]:
        """What the caller needs to know about each of ``refs``, in one call.

        The lineage canvas used to get this by browsing the catalog once per (type,
        namespace) its graph touched, which is up to a dozen queries per draw and still
        the wrong answer twice over: the browse row carries the state of the object's
        *latest* version, while a graph node names a particular one, and it carries no
        idea of how fresh a feature's data is. Both overlays were therefore approximate
        in a way that looked exact.

        A reference the caller may not read comes back as ``{"hidden": True}`` and is
        never described. It is keyed by the reference the caller passed in, which they
        already knew; what does not come back is the namespace, the owner or the name of
        anything they cannot see, and there is deliberately no tally by namespace — a
        count per namespace is a directory of the namespaces you are shut out of. A
        reference to nothing at all answers the same way, for the same reason: "there is
        no such object" and "not for you" must be one answer, or the difference between
        them is a way to enumerate an estate.
        """
        wanted: list[tuple[str, Any]] = []
        for raw in refs[:NODE_LIMIT]:
            ref = refs_mod.parse(raw)
            if ref.kind not in BROWSE_TYPES:
                raise ValidationFailed(
                    f"'{raw}' is not a catalog object: nodes describes "
                    + ", ".join(sorted(BROWSE_TYPES)),
                    ref=raw,
                )
            if not ref.namespace:
                # Elsewhere an unqualified name is resolved when it is unique. Not here:
                # this answers about many objects at once, and the failure mode would be a
                # readable object reported as hidden, which reads as an access problem.
                raise ValidationFailed(
                    f"'{raw}' names no namespace; nodes describes qualified references",
                    ref=raw,
                )
            wanted.append((raw, ref))
        out: dict[str, Any] = {}
        with self.p.uow() as uow:
            names = {n["name"]: n["id"] for n in uow.repo("namespaces").list()}
            users = {u["id"]: u["username"] for u in uow.repo("users").list()}
            for kind in {r.kind for _, r in wanted}:
                group = [(raw, r) for raw, r in wanted if r.kind == kind]
                out.update(self._nodes_of_kind(uow, p, kind, group, names, users))
        for raw, _ in wanted:
            out.setdefault(raw, {"hidden": True})
        return out

    def _nodes_of_kind(
        self,
        uow: Any,
        p: Any,
        kind: str,
        group: list[tuple[str, Any]],
        names: dict[str, Any],
        users: dict[Any, str],
    ) -> dict[str, Any]:
        """One type's worth of node metadata: four queries, whatever the node count."""
        table, cap_kind, vtable, vkey = self._parts(kind)
        keep = self.p.access.reader(uow, p, cap_kind)
        rows = {
            (r["namespace_id"], r["name"]): r
            for r in uow.repo(table).list(name__in=[r.name for _, r in group])
            if keep(uow, r)
        }
        found = {
            raw: rows[(names[r.namespace], r.name)]
            for raw, r in group
            if r.namespace in names and (names[r.namespace], r.name) in rows
        }
        ids = [row["id"] for row in found.values()]
        latest = uow.repo(vtable).latest_per(vkey, ids)
        states = {
            (v[vkey], v["version_no"]): v["state"]
            for v in uow.repo(vtable).slim([vkey, "version_no", "state"], **{f"{vkey}__in": ids})
        }
        pinned = self._pinned_bytes(uow, kind, ids)
        fresh = self._data_freshness(uow, kind, ids)
        out: dict[str, Any] = {}
        for raw, ref in group:
            row = found.get(raw)
            if row is None:
                continue
            top = latest.get(row["id"]) or {}
            asked = ref.version if ref.version is not None else top.get("version_no")
            out[raw] = {
                "type": kind,
                "name": row["name"],
                "namespace": ref.namespace,
                "owner": users.get(row["owner_id"]),
                "version": asked,
                # The state of the version this node names, not of the newest one. A graph
                # drawn on v1 of something now at v4 must not borrow v4's approval.
                "state": states.get((row["id"], asked)),
                "latest_version": top.get("version_no"),
                "latest_state": top.get("state"),
                "change_class": top.get("change_class"),
                "needs_reapproval": top.get("needs_reapproval"),
                "updated_at": row.get("updated_at"),
                "data_freshness": fresh.get(row["id"]),
                "pinned_bytes": pinned.get(row["id"]),
                "description": row.get("description"),
                "url": self._url(kind, ref.namespace or "", row["name"]),
            }
        return out

    @staticmethod
    def _pinned_bytes(uow: Any, kind: str, ids: list[str]) -> dict[str, int]:
        """Bytes of sealed pins per object — exact, and one query per chunk. A model has
        no pins of its own, so it is priced as nothing rather than as zero."""
        pins = {
            "feature": ("feature_pins", "feature_id"),
            "featureset": ("feature_set_pins", "feature_set_id"),
        }
        if kind not in pins:
            return {}
        table, fk = pins[kind]
        totals: dict[str, int] = {}
        for chunk in _chunked(ids):
            for row in uow.repo(table).slim(
                [fk, "bytes_total"], state="sealed", **{f"{fk}__in": chunk}
            ):
                totals[row[fk]] = totals.get(row[fk], 0) + int(row["bytes_total"] or 0)
        return {oid: totals.get(oid, 0) for oid in ids}

    @staticmethod
    def _data_freshness(uow: Any, kind: str, ids: list[str]) -> dict[str, Any]:
        """When each feature's data was last known to be true (§5.2). A feature set or a
        model has no ingest of its own, so it has no data freshness — the canvas falls
        back to when the object itself last changed, and says which it is showing."""
        if kind != "feature" or not ids:
            return {}
        latest = uow.repo("feature_ingests").latest_per("feature_id", ids, order="knowledge_time")
        return {fid: row["knowledge_time"] for fid, row in latest.items()}

    # -- impact: what a change to this object would break (§16.4, §10.3) ------------
    def dependents(self, p: Any, ref: str, *, depth: int = 4) -> dict[str, Any]:
        """Every catalog object downstream of ``ref``, with its owner.

        A dependent the caller may not read is not named: it is counted in ``hidden``,
        the same rule the lineage graph follows.
        """
        with self.p.uow() as uow:
            return self.dependents_in(uow, p, [ref], depth=depth)

    def dependents_in(
        self, uow: Any, p: Any, roots: list[str], *, depth: int = 4
    ) -> dict[str, Any]:
        """``dependents`` inside a unit of work already open, over several roots."""
        found: dict[str, str] = {}  # object reference -> the edge that reached it
        for root in roots:
            for edge in uow.repo("lineage_edges").walk(root, direction="downstream", depth=depth):
                found.setdefault(edge["dst_ref"], edge["edge_type"])
        for root in roots:
            found.pop(root, None)
        readers = {
            kind: self.p.access.reader(uow, p, kind) for _, kind, _, _ in BROWSE_TYPES.values()
        }
        users = {u["id"]: u["username"] for u in uow.repo("users").list()}
        names = {n["id"]: n["name"] for n in uow.repo("namespaces").list()}
        items: list[dict[str, Any]] = []
        hidden = 0
        for dst, edge_type in sorted(found.items()):
            resolved = self._object_at(uow, dst)
            if resolved is None:
                continue  # an operator node, a pin or a warrant: not an owned catalog object
            type_name, obj = resolved
            _, kind, vtable, vkey = BROWSE_TYPES[type_name]
            if not readers[kind](uow, obj):
                hidden += 1
                continue
            latest = latest_version(uow, vtable, vkey, obj["id"])
            items.append(
                {
                    "ref": dst,
                    "type": type_name,
                    "namespace": names.get(obj["namespace_id"]),
                    "name": obj["name"],
                    "owner": users.get(obj["owner_id"]),
                    "edge": edge_type,
                    "state": (latest or {}).get("state"),
                    "change_class": (latest or {}).get("change_class"),
                    "url": self._url(type_name, names.get(obj["namespace_id"], ""), obj["name"]),
                }
            )
        return {"items": items, "hidden": hidden, "total": len(items)}

    @staticmethod
    def _object_at(uow: Any, ref: str) -> tuple[str, dict[str, Any]] | None:
        """The catalog object a lineage node names, or None when it names something else."""
        try:
            parsed = refs.parse(ref)
        except ValidationFailed:
            return None
        if parsed.kind not in BROWSE_TYPES or parsed.is_pin:
            return None
        table = BROWSE_TYPES[parsed.kind][0]
        try:
            obj, _ = find_object(uow, table, parsed.kind, parsed)
        except (NotFound, ValidationFailed):
            return None
        return parsed.kind, obj

    # -- the pin preview (§16.4) -----------------------------------------------------
    def pin_preview(
        self,
        p: Any,
        ref: str,
        *,
        version_no: int,
        as_of: Any,
        as_of_known: Any = None,
        pin_name: str = "",
    ) -> dict[str, Any]:
        """What pinning would produce, before the button becomes active (§16.4).

        Rows, the fill report, the quality contract's verdict and an estimate of the
        storage the pin would take, plus anything that would refuse the pin outright.
        Nothing is written, and the estimate is named as an estimate: it measures a
        sample and scales it, where the pin itself writes only fragments the store has
        never seen, so the pin's own new bytes are usually smaller.
        """
        from maya.resolution import quality

        with self.p.uow() as uow:
            feature, ns = find_object(uow, "features", "feature", refs.parse(ref, "feature"))
            self.p.access.require(uow, p, "read", "feature", feature)
            version = version_of(uow, "feature_versions", "feature_id", feature, version_no)
            eff = effective_feature_definition(uow, version["definition"])
            # the same two tests ``features.pin`` will make, in the same order: the pin
            # capability lives on ``feature_pin``, and the object check is made with that
            # capability type, so asking about "pin on feature" would answer a different
            # question from the one the button will ask.
            direct = p.has_capability("feature_pin", "P")
            may_pin = (direct or p.has_capability("feature_pin", "Q")) and self.p.access.allowed(
                uow,
                p,
                "pin" if direct else "request_pin",
                "feature",
                feature,
                cap_type="feature_pin",
            )
            clash = (
                uow.repo("feature_pins").find_one(
                    feature_id=feature["id"], pin_name=pin_name, as_of_date=as_of
                )
                if pin_name
                else None
            )
            # the enforcement's own figure: stored bytes, counted once per
            # content-addressed fragment. Summing logical sizes here would quote the
            # reader a number the refusal does not use.
            held = quota_svc.usage(uow, feature["namespace_id"])["stored_bytes"]
            quota = uow.repo("namespaces").require(feature["namespace_id"]).get("quota_bytes")
        blockers: list[str] = []
        if version["state"] not in APPROVED_STATES:
            blockers.append(
                f"v{version_no} is '{version['state']}': only an approved version can be pinned"
            )
        if not may_pin:
            blockers.append("you hold no pin or pin-request right on this feature")
        if clash is not None and clash["state"] != "failed":
            blockers.append(
                f"'{pin_name}' already has a pin as of {as_of} ({clash['state']}): "
                "a pin series never overwrites"
            )
        res = self.p.feature_data.resolve_definition(
            ns["name"],
            feature["name"],
            eff,
            as_of_known=as_of_known,
            end=as_of,
            label=f"{ref}@v{version_no} (pin preview)",
        )
        checks = quality.run_checks(
            res.df, eff.get("quality") or [], res.meta["index"], as_of=as_of
        )
        failed = [c for c in checks if not c["passed"]]
        if failed:
            blockers.append(
                "quality check(s) would fail: "
                + "; ".join(f"{c['check']}: {c['detail']}" for c in failed)
            )
        if res.df.empty:
            blockers.append("resolution produces no rows at this as-of")
        storage = self._estimate_bytes(res)
        if quota and held + storage["estimated_bytes"] > quota:
            blockers.append(
                f"the namespace holds {held} of {quota} bytes and this pin is estimated at "
                f"{storage['estimated_bytes']}: it would exceed the quota"
            )
        return {
            "ref": f"{ref}@v{version_no}",
            "as_of": as_of,
            "rows": int(len(res.df)),
            "columns": list(res.df.columns),
            "fill_report": res.fill_report,
            "plan": res.plan,
            "checks": checks,
            "storage": {
                **storage,
                "namespace": ns["name"],
                "quota_bytes": quota,
                "held_bytes": held,
            },
            "blockers": blockers,
            "may_pin": not blockers,
        }

    def _estimate_bytes(self, res: Any) -> dict[str, Any]:
        """Compressed size per row, measured on a sample and scaled to the whole frame.

        This is what the rows *are*, not what they will add: fragments this feature already
        holds cost nothing to pin again, so a re-pin of mostly unchanged data stores far
        less than this. It is the right number for "how big is this", and an upper bound on
        "what will it cost me".
        """
        import io

        import pyarrow.parquet as pq

        rows = int(len(res.df))
        if not rows:
            return {"estimated_bytes": 0, "bytes_per_row": 0.0, "sampled_rows": 0}
        sample = res.df.head(PREVIEW_SAMPLE)
        table = self.p.feature_data.to_table(
            type(res)(sample, res.meta, res.fill_report, res.inputs, res.plan)
        )
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="zstd")
        per_row = buf.tell() / max(table.num_rows, 1)
        return {
            "estimated_bytes": int(per_row * rows),
            "bytes_per_row": round(per_row, 2),
            "sampled_rows": int(table.num_rows),
        }
