"""
Feature set use cases (§6): define, resolve, review, pin (with cascade), download.

A feature set stores no data of its own until it is pinned; its pin is
materialized by default (D-1) as content-addressed fragments like any pin.
A feature set refuses to pin unless every member is pinned; ``cascade``
pins the members under a shared name and as-of date in one job and rolls
the whole cascade back if any member fails (§6.6).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import builtins
import copy
import datetime as dt
import time
from typing import Any

import pandas as pd

from maya.core import djson
from maya.core.errors import ConflictError, NotApproved, ValidationFailed
from maya.core.clock import utcnow
from maya.resolution import algebra, shapes
from maya.resolution.featureset import resolve_featureset
from maya.resolution.resolver import KT
from maya.security.authz import Principal
from maya.services import catalog, quota, refs
from maya.services.feature_data import Resolved
from maya.services.features import _records
from maya.workflow.engine import Subject

EDITABLE = ("draft", "changes_requested")
MAX_SET_DEPTH = 8

# §6.8's operators over whole feature sets, and how many operands each takes. All but
# `override` are the feature algebra applied to sets, by the mapping below.
SET_OPERATORS: dict[str, tuple[int, int | None]] = {
    "union": (2, None),
    "intersect": (2, 2),
    "difference": (2, 2),
    "join": (2, None),
    "project": (1, 1),
    "override": (1, 1),
    "pivot": (1, 1),
    "unpivot": (1, 1),
    "sample": (1, 1),
}
# what each operator cannot be written without; the rest is typed when it resolves,
# because it depends on the operands' schemas
REQUIRED_OPTIONS: dict[str, tuple[str, ...]] = {
    "project": ("attrs",),
    "pivot": ("on", "value", "values"),
    "unpivot": ("into",),
}
ALGEBRA_FOR_SET = {
    "union": "union",
    "intersect": "intersect",
    "difference": "difference",
    "join": "compose",  # §6.2 alignment modes, as the feature algebra composes
    "project": "project",
    "pivot": "pivot",
    "unpivot": "unpivot",
    "sample": "sample",
}


class FeatureSetService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- definitions -------------------------------------------------------------
    def effective(
        self, uow: Any, definition: dict[str, Any], depth: int = 0
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Effective definition plus inherited policies, nearest ancestor first (§6.8)."""
        ext = definition.get("extends")
        if not ext:
            return definition, []
        if depth >= MAX_SET_DEPTH:
            raise ValidationFailed("Feature set inheritance exceeds the depth cap (8)")
        r = refs.parse(ext["parent"], "featureset")
        fs, _ = catalog.find_object(uow, "feature_sets", "feature set", r)
        pv = catalog.version_of(uow, "feature_set_versions", "feature_set_id", fs, r.version)
        parent, inherited = self.effective(uow, pv["definition"], depth + 1)
        o = ext.get("override") or {}
        out = copy.deepcopy(parent)
        out.pop("extends", None)
        drop = set(o.get("drop_attributes") or [])
        out["members"] = [m for m in out.get("members", []) if m["attr"] not in drop]
        out["members"] += list(o.get("add_members") or [])
        for m in out["members"]:
            if m["attr"] in (o.get("attribute_rules") or {}):
                m["rule"] = o["attribute_rules"][m["attr"]]
        for key in ("filters", "grid", "alignment"):
            if key in o:
                out[key] = o[key]
        out["global_policy"] = o.get("global_policy") or {}
        chain = [{"source": ext["parent"], **(parent.get("global_policy") or {})}] + inherited
        return out, chain

    def validate(self, d: dict[str, Any]) -> list[str]:
        if d.get("extends"):
            return [] if d["extends"].get("parent") else ["extends.parent is required"]
        if d.get("derivation"):
            return self._validate_derivation(d["derivation"])
        errors = []
        if not d.get("index"):
            errors.append("a feature set declares its index, e.g. [date, symbol]")
        members = d.get("members") or []
        if not members:
            errors.append("a feature set maps at least one attribute")
        names = [m.get("attr") for m in members]
        if len(names) != len(set(names)):
            errors.append("attribute names must be unique")
        for m in members:
            for key in ("attr", "ref", "source_attr"):
                if not m.get(key):
                    errors.append(f"member mapping {m} is missing '{key}'")
        mode = (d.get("alignment") or {}).get("mode", "inner")
        if mode not in ("inner", "outer", "left", "asof"):
            errors.append("alignment.mode must be inner, outer, left or asof")
        return errors

    def _validate_derivation(self, derivation: dict[str, Any]) -> builtins.list[str]:
        """A feature set built from other feature sets (§6.8): the operator, its operands
        and their number, checked while it is a definition — the types are checked when it
        resolves, because they depend on the operands' own schemas."""
        errors = []
        operator = derivation.get("operator")
        if operator not in SET_OPERATORS:
            return [f"derivation.operator must be one of {', '.join(sorted(SET_OPERATORS))}"]
        operands = derivation.get("operands") or []
        lo, hi = SET_OPERATORS[operator]
        if len(operands) < lo or (hi is not None and len(operands) > hi):
            want = f"{lo}" if hi == lo else f"{lo}..{hi or 'n'}"
            errors.append(f"'{operator}' takes {want} operand(s), got {len(operands)}")
        for operand in operands:
            if not isinstance(operand, str) or not operand:
                errors.append(f"derivation operand {operand!r} is not a feature set reference")
        options = derivation.get("options") or {}
        if operator == "override" and not options:
            errors.append("'override' declares what it overrides (options: {...})")
        for key in REQUIRED_OPTIONS.get(operator, ()):
            if options.get(key) in (None, [], {}):
                errors.append(f"'{operator}' requires option '{key}'")
        if operator == "sample" and not any(
            options.get(k) is not None for k in ("start", "end", "universe", "fraction")
        ):
            errors.append("'sample' declares at least one of start, end, universe, fraction")
        return errors

    # -- read --------------------------------------------------------------------
    def listing(
        self,
        uow: Any,
        p: Principal,
        *,
        namespace: str | None = None,
        q: str | None = None,
        state: str | None = None,
    ) -> Any:
        from maya.services.paging import Listing

        filters: dict[str, Any] = {}
        if namespace:
            filters["namespace_id"] = self.p.access.namespace(uow, namespace)["id"]
        names = {n["id"]: n["name"] for n in uow.repo("namespaces").list()}

        def enrich_many(uow: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            ids = [fs["id"] for fs in rows]
            latest = uow.repo("feature_set_versions").latest_per("feature_set_id", ids)
            pins = uow.repo("feature_set_pins").count_per("feature_set_id", ids, state="sealed")
            out = []
            for fs in rows:
                v = latest.get(fs["id"])
                out.append(
                    {
                        **fs,
                        "namespace": names.get(fs["namespace_id"]),
                        "latest_version": v["version_no"] if v else None,
                        "latest_state": v["state"] if v else None,
                        "members": len((v or {}).get("definition", {}).get("members", [])),
                        "pins": pins.get(fs["id"], 0),
                        "ref": refs.object_ref(
                            "featureset", names.get(fs["namespace_id"], ""), fs["name"]
                        ),
                    }
                )
            return out

        return Listing(
            "feature_sets",
            {
                "name": "name",
                "-name": "-name",
                "updated": "updated_at",
                "-updated": "-updated_at",
                "created": "created_at",
                "-created": "-created_at",
            },
            "name",
            filters,
            (["name", "description"], q or ""),
            keep=catalog.in_state(
                uow,
                "feature_set_versions",
                "feature_set_id",
                state,
                self.p.access.reader(uow, p, "featureset"),
            ),
            enrich_many=enrich_many,
            scope={"state": state} if state else {},
        )

    def list(
        self,
        p: Principal,
        *,
        namespace: str | None = None,
        q: str | None = None,
        state: str | None = None,
    ) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return self.listing(uow, p, namespace=namespace, q=q, state=state).collect(uow)

    def page(
        self,
        p: Principal,
        *,
        namespace: str | None = None,
        q: str | None = None,
        state: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        sort: str | None = None,
        total: bool = False,
    ) -> dict[str, Any]:
        from maya.services.paging import run_page

        return run_page(
            self.p,
            lambda uow: self.listing(uow, p, namespace=namespace, q=q, state=state),
            page_size=page_size,
            cursor=cursor,
            sort=sort,
            total=total,
        )

    def get(self, p: Principal, ref: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            fs, ns = catalog.find_object(
                uow, "feature_sets", "feature set", refs.parse(ref, "featureset")
            )
            self.p.access.require(uow, p, "read", "featureset", fs)
            versions = uow.repo("feature_set_versions").list(
                feature_set_id=fs["id"], order_by=["-version_no"]
            )
            for v in versions:
                v["transitions"] = self.p.workflow.available(uow, self.subject(uow, fs, ns, v))
                v["effective"], v["inherited"] = self.effective(uow, v["definition"])
            pins = uow.repo("feature_set_pins").list(
                feature_set_id=fs["id"], order_by=["pin_name", "-as_of_date"]
            )
            vno = {v["id"]: v["version_no"] for v in versions}
            for pin in pins:
                pin["version_no"] = vno.get(pin["feature_set_version_id"])
                pin["ref"] = refs.pin_ref(
                    "featureset", ns["name"], fs["name"], pin["pin_name"], pin["as_of_date"]
                )
            return {
                **fs,
                "namespace": ns["name"],
                "versions": versions,
                "pins": pins,
                "ref": refs.object_ref("featureset", ns["name"], fs["name"]),
                "can_edit": self.p.access.allowed(uow, p, "update", "featureset", fs),
            }

    # -- create and edit ----------------------------------------------------------
    def create(
        self,
        p: Principal,
        *,
        namespace: str,
        name: str,
        definition: dict[str, Any],
        description: str = "",
        tags: builtins.list[str] | None = None,
    ) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            ns = self.p.access.namespace(uow, namespace)
            self.p.access.require(
                uow,
                p,
                "create",
                "featureset",
                {"id": "new", "namespace_id": ns["id"], "name": name},
            )
            if uow.repo("feature_sets").find_one(namespace_id=ns["id"], name=name):
                raise ConflictError(f"Feature set '{namespace}/{name}' already exists")
            fs = uow.repo("feature_sets").add(
                {
                    "namespace_id": ns["id"],
                    "name": name,
                    "owner_id": p.user_id,
                    "description": description,
                    "tags": tags or [],
                }
            )
            uow.repo("feature_set_versions").add(
                {
                    "feature_set_id": fs["id"],
                    "version_no": 1,
                    "state": "draft",
                    "definition": definition,
                }
            )
            uow.audit(
                "featureset.created",
                object_type="featureset",
                object_ref=refs.object_ref("featureset", namespace, name),
            )
            return fs

    def update_draft(
        self,
        p: Principal,
        ref: str,
        definition: dict[str, Any],
        *,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            fs, ns = catalog.find_object(
                uow, "feature_sets", "feature set", refs.parse(ref, "featureset")
            )
            self.p.access.require(uow, p, "update", "featureset", fs)
            draft = catalog.latest_version(uow, "feature_set_versions", "feature_set_id", fs["id"])
            if draft is None or draft["state"] not in EDITABLE:
                raise NotApproved("There is no editable draft; start a new draft first")
            row = uow.repo("feature_set_versions").update(
                draft["id"], {"definition": definition}, expected_version=expected_version
            )
            uow.audit("featureset.draft_updated", object_type="featureset", object_ref=ref)
            return row

    def new_draft(self, p: Principal, ref: str) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            fs, _ = catalog.find_object(
                uow, "feature_sets", "feature set", refs.parse(ref, "featureset")
            )
            self.p.access.require(uow, p, "update", "featureset", fs)
            latest = catalog.require_latest(uow, "feature_set_versions", "feature_set_id", fs["id"])
            if latest["state"] in EDITABLE:
                return latest
            return uow.repo("feature_set_versions").add(
                {
                    "feature_set_id": fs["id"],
                    "version_no": latest["version_no"] + 1,
                    "state": "draft",
                    "definition": latest["definition"],
                }
            )

    def fork(
        self,
        p: Principal,
        ref: str,
        *,
        name: str,
        namespace: str | None = None,
        version_no: int | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """A new feature set that starts as a copy of this one's definition (§6.7).

        A fork is not an `extend`: it takes the definition and lets go. Use `extends` when
        the child should follow the parent's corrections, and a fork when a desk is taking
        the panel somewhere the firm's copy should not follow. The lineage records where it
        came from, so "where did this come from" stays answerable either way.
        """
        with self.p.uow(p.username) as uow:
            source, source_ns = catalog.find_object(
                uow, "feature_sets", "feature set", refs.parse(ref, "featureset")
            )
            self.p.access.require(uow, p, "read", "featureset", source)
            version = catalog.version_of(
                uow, "feature_set_versions", "feature_set_id", source, version_no
            )
        target_ns = namespace or source_ns["name"]
        # A fork declares where it came from. Without that it is byte-identical to its
        # source, and the near-copy guard (§6.8) refuses it — rightly, because an accidental
        # copy and a deliberate one look the same until one of them says so.
        forked = copy.deepcopy(version["definition"])
        forked["forked_from"] = refs.version_ref(
            "featureset", source_ns["name"], source["name"], version["version_no"]
        )
        out = self.create(
            p,
            namespace=target_ns,
            name=name,
            definition=forked,
            description=description
            or f"forked from {source_ns['name']}/{source['name']} v{version['version_no']}",
        )
        with self.p.uow(p.username) as uow:
            uow.repo("lineage_edges").link(
                refs.version_ref(
                    "featureset", source_ns["name"], source["name"], version["version_no"]
                ),
                f"maya://featureset/{target_ns}/{name}@v1",
                "forked_from",
            )
            uow.audit(
                "featureset.forked",
                object_type="featureset",
                object_ref=f"{target_ns}/{name}",
                detail={"from": f"{source_ns['name']}/{source['name']}@v{version['version_no']}"},
            )
        return {
            **out,
            "forked_from": f"{source_ns['name']}/{source['name']}@v{version['version_no']}",
        }

    def diff(self, p: Principal, ref: str, version_a: int, version_b: int) -> dict[str, Any]:
        """Two versions of a feature set, attribute by attribute (§6.7)."""
        with self.p.uow() as uow:
            fs, ns = catalog.find_object(
                uow, "feature_sets", "feature set", refs.parse(ref, "featureset")
            )
            self.p.access.require(uow, p, "read", "featureset", fs)
            a = catalog.version_of(uow, "feature_set_versions", "feature_set_id", fs, version_a)
            b = catalog.version_of(uow, "feature_set_versions", "feature_set_id", fs, version_b)
            eff_a, _ = self.effective(uow, a["definition"])
            eff_b, _ = self.effective(uow, b["definition"])
        return {
            "ref": f"{ns['name']}/{fs['name']}",
            "from": version_a,
            "to": version_b,
            "changes": diff_set_definitions(eff_a, eff_b),
        }

    # -- workflow -------------------------------------------------------------------
    def subject(
        self, uow: Any, fs: dict[str, Any], ns: dict[str, Any], v: dict[str, Any]
    ) -> Subject:
        owner = uow.repo("users").get(fs["owner_id"])
        return Subject(
            "featureset_version",
            "feature_set_versions",
            v["id"],
            refs.version_ref("featureset", ns["name"], fs["name"], v["version_no"]),
            "featureset",
            v,
            ns,
            fs["owner_id"],
            owner["username"] if owner else None,
            uow.repo("grants").list(object_type="featureset", object_id=fs["id"]),
            {"featureset": fs, "service": self},
        )

    def transition(
        self,
        p: Principal,
        ref: str,
        version_no: int,
        name: str,
        *,
        rationale: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        if name == "submit":
            self._freeze(p, ref, version_no)
        with self.p.uow(p.username) as uow:
            fs, ns = catalog.find_object(
                uow, "feature_sets", "feature set", refs.parse(ref, "featureset")
            )
            v = catalog.version_of(uow, "feature_set_versions", "feature_set_id", fs, version_no)
            out = self.p.workflow.transition(
                uow, p, self.subject(uow, fs, ns, v), name, rationale=rationale, force=force
            )
            if out.moved:
                uow.repo("feature_sets").update(fs["id"], {"status": out.state})
                if out.state == "approved":
                    eff, _ = self.effective(uow, v["definition"])
                    me = refs.version_ref("featureset", ns["name"], fs["name"], v["version_no"])
                    for m in eff.get("members", []):
                        uow.repo("lineage_edges").link(m["ref"], me, "member_of", m["attr"])
                    ext = v["definition"].get("extends")
                    if ext:
                        uow.repo("lineage_edges").link(
                            ext["parent"],
                            me,
                            "extends",
                            str(catalog.override_count(ext.get("override"))),
                        )
            return out.__dict__

    def _freeze(self, p: Principal, ref: str, version_no: int) -> None:
        with self.p.uow(p.username) as uow:
            fs, _ = catalog.find_object(
                uow, "feature_sets", "feature set", refs.parse(ref, "featureset")
            )
            v = catalog.version_of(uow, "feature_set_versions", "feature_set_id", fs, version_no)
            if v["state"] not in EDITABLE:
                return
            eff, inherited = self.effective(uow, v["definition"])
            # the written definition and its effective form are both checked; an error in
            # both is one error to the person reading it
            errors = list(dict.fromkeys(self.validate(v["definition"]) + self.validate(eff)))
            if errors:
                raise ValidationFailed(
                    "The feature set definition is not valid: " + "; ".join(errors), errors=errors
                )
            digest = djson.canonical_hash(equivalence_body(eff, inherited))
            dup = uow.repo("feature_set_versions").find_one(
                definition_hash=digest, feature_set_id__ne=fs["id"]
            )
            if dup:
                other = uow.repo("feature_sets").require(dup["feature_set_id"])
                raise ConflictError(
                    f"An equivalent feature set already exists: "
                    f"'{other['name']}' v{dup['version_no']}. Reuse it rather "
                    "than adding a near-copy (§6.8)",
                    existing=other["name"],
                )
            uow.repo("feature_set_versions").update(v["id"], {"definition_hash": digest})

    def members_approved(self, uow: Any, row: dict[str, Any]) -> tuple[bool, str]:
        eff, _ = self.effective(uow, row["definition"])
        bad = []
        for m in eff.get("members", []):
            r = refs.parse(m["ref"], "feature")
            if r.kind == "featureset":
                # §6.7: a member may be another feature set. The same rule applies to it —
                # approved, or pinned — read from its own table.
                try:
                    nested, _ = catalog.find_object(uow, "feature_sets", "feature set", r)
                    if r.version is not None:
                        version = catalog.version_of(
                            uow, "feature_set_versions", "feature_set_id", nested, r.version
                        )
                        if version["state"] not in catalog.APPROVED_STATES:
                            bad.append(f"{m['ref']} is {version['state']}")
                except Exception as exc:  # noqa: BLE001 - reported as the check detail
                    bad.append(f"{m['ref']}: {exc}")
                continue
            try:
                feature, _ = catalog.find_object(uow, "features", "feature", r)
                if not r.is_pin:
                    catalog.version_of(uow, "feature_versions", "feature_id", feature, r.version)
            except Exception as exc:  # noqa: BLE001 - reported as the check detail
                bad.append(f"{m['ref']}: {exc}")
                continue
            if r.version is not None:
                ver = catalog.version_of(uow, "feature_versions", "feature_id", feature, r.version)
                if ver["state"] not in catalog.APPROVED_STATES:
                    bad.append(f"{m['ref']} is {ver['state']}")
        return (not bad, "all members approved or pinned" if not bad else "; ".join(bad))

    # -- resolution -------------------------------------------------------------------
    def resolve_definition(
        self,
        p: Principal | None,
        eff: dict[str, Any],
        inherited: builtins.list[dict[str, Any]],
        *,
        as_of_known: Any = None,
        start: dt.date | None = None,
        end: dt.date | None = None,
        member_override: dict[str, str] | None = None,
    ) -> Resolved:
        """Resolve members (withholding what ``p`` cannot read), then assemble. A set built
        from other sets (§6.8) resolves its operands first and applies the operator."""
        if eff.get("derivation"):
            return self._resolve_derived(
                p, eff, as_of_known=as_of_known, start=start, end=end, depth=0
            )
        member_override = member_override or {}
        members: dict[str, Any] = {}
        inputs: builtins.list[str] = []
        plan: builtins.list[str] = []
        withheld: builtins.list[str] = []
        readable = self._readable_members(p, eff) if p is not None else None
        mapping = []
        for m in eff.get("members", []):
            ref = member_override.get(m["ref"], m["ref"])
            if readable is not None and m["ref"] not in readable:
                withheld.append(m["attr"])
                continue
            if ref not in members:
                # §6.7: a member may be another feature set, one level deep. Its rows are
                # resolved the same way and joined like any other member, so a desk panel
                # can be built from the firm panel without copying its definition.
                res = (
                    self.resolve_ref(p, ref, as_of_known=as_of_known)
                    if refs.parse(ref, "feature").kind == "featureset"
                    else self.p.feature_data.resolve_ref(
                        ref, as_of_known=as_of_known, start=start, end=end
                    )
                )
                members[ref] = (res.df, res.meta)
                inputs.append(ref)
                plan += res.plan
            mapping.append({**m, "member": ref})
        if not mapping:
            raise ValidationFailed(
                "You cannot read any member of this feature set", withheld=withheld
            )
        universe_rows = self._universe_rows(p, eff, as_of_known, start, end, plan)
        df, manifest = resolve_featureset(
            members,
            mapping,
            index=eff["index"],
            alignment=_aligned(eff, member_override),
            grid=eff.get("grid", "as_is"),
            global_policy=eff.get("global_policy"),
            group_policies=eff.get("group_policies"),
            inherited_policies=inherited,
            filters=eff.get("filters"),
            universe_rows=universe_rows,
        )
        for attr in withheld:
            df[attr] = None
        manifest["withheld"] = withheld
        schema = self._schema(eff, members, mapping)
        index_types = {}
        for ref, (_, meta) in members.items():
            index_types.update(
                {k: v for k, v in meta.get("index_types", {}).items() if k in eff["index"]}
            )
        meta = {
            "index": eff["index"],
            "index_types": index_types,
            "schema": schema,
            "non_causal": bool(manifest.get("non_causal")),
            "policy": {},
        }
        manifest["plan"] = plan + manifest.get("plan", [])
        return Resolved(df, meta, manifest, inputs, manifest["plan"])

    def _resolve_derived(
        self,
        p: Principal | None,
        eff: dict[str, Any],
        *,
        as_of_known: Any = None,
        start: dt.date | None = None,
        end: dt.date | None = None,
        depth: int = 0,
    ) -> Resolved:
        """One §6.8 operator over resolved operand sets.

        `union`, `intersect`, `difference`, `join`, `project`, `pivot`, `unpivot` and
        `sample` are the feature algebra applied to whole sets — the same executors, so a
        set operation and the equivalent feature operation cannot drift apart. `override`
        is different in kind: it re-resolves one operand under a different policy, filter
        or grid, which is why it takes options rather than a second operand.
        """
        if depth >= MAX_SET_DEPTH:
            raise ValidationFailed("Feature set derivation exceeds the depth cap (8)")
        derivation = eff["derivation"]
        operator = derivation["operator"]
        options = dict(derivation.get("options") or {})
        operands = [
            self.resolve_ref(p, ref, as_of_known=as_of_known) for ref in derivation["operands"]
        ]
        plan = [step for res in operands for step in res.plan]
        inputs = [ref for ref in derivation["operands"]]
        if operator == "override":
            return self._resolve_override(
                p, operands[0], inputs[0], options, as_of_known=as_of_known, start=start, end=end
            )
        frames = [res.df for res in operands]
        metas = [res.meta for res in operands]
        op = ALGEBRA_FOR_SET[operator]
        meta = algebra.typecheck(op, options, metas)
        df = algebra.execute(op, options, frames, metas)
        plan.append(
            f"set algebra: {algebra.OPERATORS[op].notation} over "
            + ", ".join(inputs)
            + f" -> {len(df)} rows"
        )
        manifest = {
            "derivation": algebra.canonical_derivation(op, options, inputs),
            "plan": plan,
            "non_causal": bool(meta.get("non_causal")),
            "change_class": meta.get("change_class"),
        }
        index_types = {}
        for res in operands:
            index_types.update(
                {k: v for k, v in (res.meta.get("index_types") or {}).items() if k in meta["index"]}
            )
        out_meta = {
            "index": meta["index"],
            "index_types": index_types,
            "schema": meta["schema"],
            "non_causal": bool(meta.get("non_causal")),
            "policy": {},
        }
        return Resolved(df, out_meta, manifest, inputs, plan)

    def _resolve_override(
        self,
        p: Principal | None,
        operand: Resolved,
        ref: str,
        options: dict[str, Any],
        *,
        as_of_known: Any = None,
        start: dt.date | None = None,
        end: dt.date | None = None,
    ) -> Resolved:
        """The same attributes under a different policy, filter or grid: the operand's own
        definition is re-resolved with the named parts replaced, so the override is applied
        where resolution happens rather than patched onto the result."""
        allowed = {"global_policy", "group_policies", "filters", "grid", "alignment"}
        unknown = sorted(set(options) - allowed)
        if unknown:
            raise ValidationFailed(
                f"override may replace {', '.join(sorted(allowed))}; not {', '.join(unknown)}",
                unknown=unknown,
            )
        del operand
        fs, ns, version, pin, eff, inherited = self.load(ref)
        del fs, ns, version, pin
        out = self.resolve_definition(
            p, {**eff, **options}, inherited, as_of_known=as_of_known, start=start, end=end
        )
        out.plan.append(f"set algebra: override[{', '.join(sorted(options))}]({ref})")
        out.fill_report["derivation"] = {
            "operator": "override",
            "operands": [ref],
            "options": options,
        }
        return out

    def _universe_rows(
        self,
        p: Principal | None,
        eff: dict[str, Any],
        as_of_known: Any,
        start: dt.date | None,
        end: dt.date | None,
        plan: builtins.list[str],
    ) -> Any:
        """The rows of a point-in-time universe feature, where the filters name one (§6.3).

        Resolved bitemporally like everything else, so "as of 2019" means the membership
        known then — which is the whole difference between a backtest and a story about
        one."""
        universe = ((eff.get("filters") or {}).get("universe")) or {}
        ref = universe.get("feature") if isinstance(universe, dict) else None
        if not ref:
            return None
        res = self.p.feature_data.resolve_ref(ref, as_of_known=as_of_known, start=start, end=end)
        if p is not None:
            plan.append(f"universe feature {ref}: {len(res.df)} row(s)")
        return res.df

    def _readable_members(self, p: Principal, eff: dict[str, Any]) -> set[str]:
        """The members ``p`` may read. A member is a feature or — §6.7 — another feature
        set, and each is checked against its own kind: a nested set's own read rule governs
        it, exactly as if it had been opened directly."""
        ok = set()
        with self.p.uow() as uow:
            for m in eff.get("members", []):
                r = refs.parse(m["ref"], "feature")
                table, kind = (
                    ("feature_sets", "featureset")
                    if r.kind == "featureset"
                    else ("features", "feature")
                )
                obj, _ = catalog.find_object(uow, table, kind, r)
                if self.p.access.allowed(uow, p, "read", kind, obj):
                    ok.add(m["ref"])
        return ok

    @staticmethod
    def _schema(
        eff: dict[str, Any], members: dict[str, Any], mapping: builtins.list[dict[str, Any]]
    ) -> builtins.list[dict[str, Any]]:
        out = []
        by_member = {
            ref: {a["name"]: a for a in meta["schema"]} for ref, (_, meta) in members.items()
        }
        for m in eff.get("members", []):
            entry = next((x for x in mapping if x["attr"] == m["attr"]), None)
            if entry is None:
                out.append(
                    {"name": m["attr"], "type": m.get("cast") or "float64", "withheld": True}
                )
                continue
            src = by_member[entry["member"]].get(m["source_attr"], {})
            out.append({**src, "name": m["attr"], "type": m.get("cast") or src.get("type")})
        return out

    def load(
        self, ref: str
    ) -> tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any] | None,
        dict[str, Any],
        builtins.list[Any],
    ]:
        """fs, namespace, version, pin (or None), effective definition, inherited."""
        r = refs.parse(ref, "featureset")
        with self.p.uow() as uow:
            fs, ns = catalog.find_object(uow, "feature_sets", "feature set", r)
            pin = None
            if r.is_pin:
                f = {"feature_set_id": fs["id"], "pin_name": r.series, "state": "sealed"}
                if r.as_of:
                    f["as_of_date"] = r.as_of
                rows = uow.repo("feature_set_pins").list(**f, order_by=["-as_of_date"], limit=1)
                if not rows:
                    from maya.core.errors import NotFound

                    raise NotFound(f"No sealed pin {r}")
                pin = rows[0]
                v = uow.repo("feature_set_versions").require(pin["feature_set_version_id"])
            else:
                v = catalog.overlaid(
                    "featureset",
                    fs["id"],
                    catalog.version_of(
                        uow, "feature_set_versions", "feature_set_id", fs, r.version
                    ),
                    r.version,
                )
            eff, inherited = self.effective(uow, v["definition"])
        return fs, ns, v, pin, eff, inherited

    def resolve_ref(self, p: Principal | None, ref: str, *, as_of_known: Any = None) -> Resolved:
        fs, ns, v, pin, eff, inherited = self.load(ref)
        if p is not None:
            with self.p.uow() as uow:
                self.p.access.require(uow, p, "read", "featureset", fs)
            self.p.licences.reader(p, "featureset", ref)
        if pin is not None:
            table = self.pin_table(pin, fs, ns, eff, inherited)
            meta = pin["manifest"].get("meta") or {}
            res = Resolved(
                table.to_pandas(), meta, dict(pin["manifest"]), [], [f"{ref}: sealed pin"]
            )
        else:
            res = self.resolve_definition(p, eff, inherited, as_of_known=as_of_known)
        if p is not None:
            res.fill_report["access_conditions"] = self.condition(p, fs, eff, res)
        return res

    @staticmethod
    def stored(pin: dict[str, Any]) -> bool:
        """Whether a pin's resolved output is in the lake (pins sealed before the policy
        existed carry no note, and were always written)."""
        return (pin.get("manifest") or {}).get("materialization", {}).get("stored", True)

    def pin_table(
        self,
        pin: dict[str, Any],
        fs: dict[str, Any],
        ns: dict[str, Any],
        eff: dict[str, Any],
        inherited: builtins.list[Any],
    ) -> Any:
        """A sealed pin's bytes: read from the lake, or — for a pin sealed under
        ``on_demand`` or ``never`` and not yet written — replayed from its member pins and
        accepted only if the replay reproduces the sealed content hash exactly. Under
        ``on_demand`` the first replay is written, and later reads come from the lake."""
        self.p.feature_data.note_read("feature_set_pins", pin["id"])
        if self.stored(pin):
            return self.p.lake.read_pin("fspins", ns["name"], fs["name"], pin["fragments"])
        table = self.replay(pin, eff, inherited)
        policy = pin["manifest"]["materialization"]["policy"]
        if policy == "on_demand":
            write, lake_table = self.p.feature_data._write_fragments(
                ns["name"], fs["name"], table, kind="fspins"
            )
            with self.p.uow("system") as uow:
                manifest = {
                    **pin["manifest"],
                    "materialization": {
                        "policy": policy,
                        "stored": True,
                        "stored_at": utcnow().isoformat(),
                    },
                }
                uow.repo("feature_set_pins").update(
                    pin["id"],
                    {"lake_table": lake_table, "manifest": manifest, "bytes_new": write.bytes_new},
                )
                uow.audit(
                    "pin.materialized",
                    object_type="featureset_pin",
                    object_ref=pin["id"],
                    principal_type="system",
                    detail={"content_hash": pin["content_hash"], "policy": policy},
                )
        return table

    def replay(
        self, pin: dict[str, Any], eff: dict[str, Any], inherited: builtins.list[Any]
    ) -> Any:
        """Resolve a pin again over its recorded member pins; refuse unless it is the same
        content, byte for byte by the canonical hash."""
        res = self.resolve_definition(
            None,
            eff,
            inherited,
            member_override=pin["manifest"]["member_pins"],
            end=pin["as_of_date"],
        )
        table = self.p.feature_data.to_table(res)
        again = self.p.lake.describe_pin(table)
        if again.content_hash != pin["content_hash"]:
            from maya.core.errors import IntegrityError

            raise IntegrityError(
                "Replaying this pin from its member pins did not reproduce its sealed "
                f"content (sealed {pin['content_hash'][:12]}, replayed "
                f"{again.content_hash[:12]}); it is not served",
                expected=pin["content_hash"],
                actual=again.content_hash,
            )
        return table

    def verify_pin(self, pin: dict[str, Any]) -> dict[str, Any]:
        """Integrity verification for a pin whose bytes are not stored: replay and hash."""
        with self.p.uow() as uow:
            v = uow.repo("feature_set_versions").require(pin["feature_set_version_id"])
            eff, inherited = self.effective(uow, v["definition"])
        from maya.core.errors import IntegrityError

        try:
            table = self.replay(pin, eff, inherited)
        except IntegrityError as exc:
            return {
                "ok": False,
                "expected": pin["content_hash"],
                "actual": exc.context.get("actual"),
                "replayed": True,
            }
        return {
            "ok": True,
            "expected": pin["content_hash"],
            "actual": pin["content_hash"],
            "rows": table.num_rows,
            "replayed": True,
        }

    def condition(
        self, p: Principal, fs: dict[str, Any], eff: dict[str, Any], res: Resolved
    ) -> builtins.list[dict[str, Any]]:
        """Apply every §11.4 condition that governs ``p``'s read, member by member, then
        the set's own — on live and pinned data alike, so no path escapes a mask."""
        from maya.security.conditions import apply, apply_mapped

        user = self.p.access.user_context(p)
        index = res.meta.get("index") or eff.get("index") or []
        applied: list[dict[str, Any]] = []
        with self.p.uow() as uow:
            by_member: dict[str, list[tuple[str, str]]] = {}
            for m in eff.get("members", []):
                by_member.setdefault(m["ref"], []).append((m["source_attr"], m["attr"]))
            for ref, pairs in sorted(by_member.items()):
                r = refs.parse(ref, "feature")
                # a member is a feature or (§6.7) another feature set; each carries its own
                # conditions, and a nested set's masks must reach through to this read
                table, kind = (
                    ("feature_sets", "featureset")
                    if r.kind == "featureset"
                    else ("features", "feature")
                )
                member, _ = catalog.find_object(uow, table, kind, r)
                cond = self.p.access.read_conditions(uow, p, kind, member)
                if cond:
                    res.df, report = apply_mapped(res.df, cond, pairs, index=index, user=user)
                    applied.append({"member": ref, **report})
            cond = self.p.access.read_conditions(uow, p, "featureset", fs)
        if cond:
            res.df, report = apply(res.df, cond, event_col=index[0] if index else None, user=user)
            applied.append({"featureset": fs["name"], **report})
        return applied

    def preview(self, p: Principal, ref: str, *, as_of_known: Any = None) -> dict[str, Any]:
        res = self.resolve_ref(p, ref, as_of_known=as_of_known)
        return {
            "rows": _records(res.df.head(200)),
            "total_rows": len(res.df),
            "columns": list(res.df.columns),
            "manifest": _jsonsafe(res.fill_report),
        }

    def draft_preview(self, p: Principal, ref: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            fs, _ = catalog.find_object(
                uow, "feature_sets", "feature set", refs.parse(ref, "featureset")
            )
            self.p.access.require(uow, p, "read", "featureset", fs)
            v = catalog.require_latest(uow, "feature_set_versions", "feature_set_id", fs["id"])
            eff, inherited = self.effective(uow, v["definition"])
        errors = self.validate(eff)
        if errors:
            raise ValidationFailed("; ".join(errors))
        res = self.resolve_definition(p, eff, inherited)
        return {
            "rows": _records(res.df.head(200)),
            "total_rows": len(res.df),
            "columns": list(res.df.columns),
            "manifest": _jsonsafe(res.fill_report),
        }

    # -- pinning -----------------------------------------------------------------------
    def pin(
        self,
        p: Principal,
        ref: str,
        *,
        version_no: int,
        pin_name: str,
        as_of: dt.date,
        as_of_known: dt.datetime | None = None,
        cascade: bool = False,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            fs, ns = catalog.find_object(
                uow, "feature_sets", "feature set", refs.parse(ref, "featureset")
            )
            v = catalog.version_of(uow, "feature_set_versions", "feature_set_id", fs, version_no)
            if v["state"] not in catalog.APPROVED_STATES:
                raise NotApproved(f"v{version_no} is '{v['state']}'; pin an approved version")
            self.p.access.require(
                uow, p, "update" if ns["is_scratch"] else "pin", "featureset", fs
            )  # scratch: its owner pins
            eff, _ = self.effective(uow, v["definition"])
            if eff.get("derivation"):
                # a derived set's inputs are whole feature sets, each pinnable in its own
                # right: it pins only over pinned operands, and there is no cascade to
                # give — pinning someone else's feature set is their decision, not a
                # side effect of pinning this one
                loose = [
                    ref
                    for ref in eff["derivation"]["operands"]
                    if not refs.parse(ref, "featureset").is_pin
                ]
                if loose:
                    raise NotApproved(
                        "A derived feature set pins over pinned operands. Pin these first, "
                        "then point this set at their pins: " + ", ".join(sorted(loose)),
                        unpinned=loose,
                    )
            unpinned = [m["ref"] for m in eff.get("members", []) if not refs.parse(m["ref"]).is_pin]
            if unpinned and not cascade:
                raise NotApproved(
                    "A feature set refuses to pin unless every member is pinned. "
                    "Unpinned: "
                    + ", ".join(sorted(set(unpinned)))
                    + ". Use cascade pin to pin them together.",
                    unpinned=unpinned,
                )
            # one request per series and date at a time (§15.3): a racer waits here, then
            # sees the winner's pin and is refused as a conflict
            uow.lock(f"pin:featureset:{fs['id']}:{pin_name}:{as_of}")
            clash = uow.repo("feature_set_pins").find_one(
                feature_set_id=fs["id"], pin_name=pin_name, as_of_date=as_of
            )
            if clash and clash["state"] != "failed":
                replay = catalog.replayed_pin(uow, idempotency_key, clash)
                if replay:
                    return replay
                raise ConflictError(f"Pin {pin_name}/{as_of} already exists ({clash['state']})")
            if clash:  # a failed pin never blocks its name and date
                uow.repo("feature_set_pins").delete(clash["id"])
            pin = uow.repo("feature_set_pins").add(
                {
                    "feature_set_id": fs["id"],
                    "feature_set_version_id": v["id"],
                    "pin_name": pin_name,
                    "as_of_date": as_of,
                    "as_of_known": as_of_known or utcnow(),
                    "state": "materializing",
                }
            )
            job = self.p.jobs.submit(
                uow,
                "featureset.pin",
                {"pin_id": pin["id"], "cascade": cascade},
                owner=p.username,
                idempotency_key=idempotency_key,
            )
            uow.audit(
                "featureset.pin_requested",
                object_type="featureset",
                object_ref=ref,
                detail={"pin": pin_name, "as_of": as_of.isoformat(), "cascade": cascade},
            )
            return {"pin": pin, "job": job}

    def run_pin_job(self, ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
        created: list[str] = []
        try:
            return self._materialize(ctx, params["pin_id"], params.get("cascade", False), created)
        except Exception as exc:
            self._rollback(ctx.actor, params["pin_id"], created, str(exc))
            raise

    def _materialize(
        self, ctx: Any, pin_id: str, cascade: bool, created: builtins.list[str]
    ) -> dict[str, Any]:
        with self.p.uow(ctx.actor) as uow:
            pin = uow.repo("feature_set_pins").require(pin_id)
            fs = uow.repo("feature_sets").require(pin["feature_set_id"])
            ns = uow.repo("namespaces").require(fs["namespace_id"])
            v = uow.repo("feature_set_versions").require(pin["feature_set_version_id"])
            eff, inherited = self.effective(uow, v["definition"])
        override, member_pins = self._pin_members(ctx, eff, pin, cascade, created)
        ctx.progress(60, "resolving the feature set over member pins")
        res = self.resolve_definition(
            None, eff, inherited, member_override=override, end=pin["as_of_date"]
        )
        table = self.p.feature_data.to_table(res)
        policy = ns.get("materialize_policy") or "always"
        if policy == "always":
            rel = self.p.lake.rel(self.p.lake.table_path("fspins", ns["name"], fs["name"]))
            with self.p.uow() as uow:
                known = {f["hash"] for f in uow.repo("fragments").list(lake_table=rel)}
                quota.check(uow, ns, self.p.lake.new_bytes(table, known), what="feature set pin")
            write, lake_table = self.p.feature_data._write_fragments(
                ns["name"], fs["name"], table, kind="fspins"
            )
            verify = self.p.lake.verify_pin(
                "fspins", ns["name"], fs["name"], write.fragments, write.content_hash, written=table
            )
            if not verify["ok"]:
                raise ValidationFailed("Feature set pin failed hash verification", **verify)
        else:  # sealed by its hash; the bytes are replayed from member pins when read
            write, lake_table = self.p.lake.describe_pin(table), None
        manifest = _jsonsafe(
            {
                **res.fill_report,
                "meta": res.meta,
                "member_pins": override,
                "materialization": {"policy": policy, "stored": policy == "always"},
            }
        )
        provenance = self.p.feature_data.provenance(v["definition_hash"], res, write, ctx.actor)
        with self.p.uow(ctx.actor) as uow:
            gone = sorted(
                ref
                for ref, pid in member_pins.items()
                if (uow.repo("feature_pins").get(pid) or {}).get("state") != "sealed"
            )
            if gone:  # never seal over a member pin that is no longer there
                raise ConflictError(
                    "Member pin(s) removed or unsealed while this pin was being "
                    "made: " + ", ".join(gone),
                    members=gone,
                )
            uow.repo("feature_set_pins").update(
                pin_id,
                {
                    "state": "sealed",
                    "member_pin_ids": member_pins,
                    "content_hash": write.content_hash,
                    "schema_digest": write.schema_digest,
                    "fragments": write.fragments,
                    "lake_table": lake_table,
                    "manifest": manifest,
                    "row_count": write.rows,
                    "bytes_total": write.bytes_total,
                    "bytes_new": write.bytes_new,
                    "provenance": provenance,
                    "sealed_at": utcnow(),
                },
            )
            me = refs.pin_ref(
                "featureset", ns["name"], fs["name"], pin["pin_name"], pin["as_of_date"]
            )
            uow.repo("lineage_edges").link(
                refs.version_ref("featureset", ns["name"], fs["name"], v["version_no"]),
                me,
                "pinned_as",
            )
            for mref in override.values():
                uow.repo("lineage_edges").link(mref, me, "member_of")
            from maya.observability.metrics import METRICS

            METRICS.inc("maya_pins_sealed_total", {"kind": "featureset"})
            METRICS.inc("maya_pin_new_bytes_total", value=float(write.bytes_new))
            uow.audit(
                "pin.sealed",
                object_type="featureset_pin",
                object_ref=me,
                detail={
                    "content_hash": write.content_hash,
                    "members": len(override),
                    "cascaded": len(created),
                },
            )
        return {
            "pin_id": pin_id,
            "content_hash": write.content_hash,
            "rows": write.rows,
            "cascaded_member_pins": len(created),
        }

    def _pin_members(
        self,
        ctx: Any,
        eff: dict[str, Any],
        pin: dict[str, Any],
        cascade: bool,
        created: builtins.list[str],
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Pin every unpinned member, in sorted feature-id order (no deadlock, §15.3)."""
        override: dict[str, str] = {}
        member_pins: dict[str, str] = {}
        todo = []
        with self.p.uow(ctx.actor) as uow:
            for ref in sorted({m["ref"] for m in eff.get("members", [])}):
                r = refs.parse(ref, "feature")
                feature, ns = catalog.find_object(uow, "features", "feature", r)
                if r.is_pin:
                    found = self.p.feature_data.find_pin(uow, feature, r)
                    override[ref] = refs.pin_ref(
                        "feature",
                        ns["name"],
                        feature["name"],
                        found["pin_name"],
                        found["as_of_date"],
                    )
                    member_pins[ref] = found["id"]
                    continue
                version = catalog.version_of(
                    uow, "feature_versions", "feature_id", feature, r.version
                )
                todo.append((feature["id"], ref, feature, ns, version))
        for i, (_, ref, feature, ns, version) in enumerate(sorted(todo, key=lambda t: t[0])):
            ctx.progress(10 + int(40 * i / max(len(todo), 1)), f"cascade: pinning {ref}")
            pid = self._cascade_one(ctx, feature, version, pin, created)
            override[ref] = refs.pin_ref(
                "feature", ns["name"], feature["name"], pin["pin_name"], pin["as_of_date"]
            )
            member_pins[ref] = pid
        return override, member_pins

    def _cascade_one(
        self,
        ctx: Any,
        feature: dict[str, Any],
        version: dict[str, Any],
        pin: dict[str, Any],
        created: builtins.list[str],
    ) -> str:
        """Pin one member for a cascade, or reuse the member pin that already exists.

        A member pin another cascade is still making — or has sealed while its own set pin
        is unsealed, and so may yet roll back — is waited for, never taken over or built on.
        Members are visited in sorted id order, so two cascades never wait on each other
        (§15.3); the wait is bounded and honours cancellation."""
        wait = float(self.p.settings.int("featuresets.cascade_wait_seconds", 120))
        deadline = time.monotonic() + wait
        while True:
            with self.p.uow(ctx.actor) as uow:
                uow.lock(f"pin:feature:{feature['id']}:{pin['pin_name']}:{pin['as_of_date']}")
                existing = uow.repo("feature_pins").find_one(
                    feature_id=feature["id"], pin_name=pin["pin_name"], as_of_date=pin["as_of_date"]
                )
                action = self._member_action(uow, existing, pin["id"])
                if action == "reuse":
                    return str(existing["id"])
                if action == "replace":
                    uow.repo("feature_pins").delete(existing["id"])
                if action != "wait":
                    row = uow.repo("feature_pins").add(
                        {
                            "feature_id": feature["id"],
                            "feature_version_id": version["id"],
                            "pin_name": pin["pin_name"],
                            "as_of_date": pin["as_of_date"],
                            "as_of_known": pin["as_of_known"],
                            "state": "materializing",
                            "provenance": {"cascade_of": pin["id"]},
                        }
                    )
                    break
            if time.monotonic() > deadline:
                raise ConflictError(
                    f"Member '{feature['name']}' is still being pinned by another "
                    f"cascade after {wait:.0f}s; retry this pin",
                    member=feature["name"],
                )
            ctx.check_cancel()
            time.sleep(0.05)
        created.append(row["id"])  # recorded first, so a failure here is rolled back too
        self.p.feature_data.materialize(row["id"], ctx.actor)
        return str(row["id"])

    @staticmethod
    def _member_action(uow: Any, existing: dict[str, Any] | None, own: str) -> str:
        """What a cascade does with a member's existing pin: create, reuse, replace, wait."""
        if existing is None:
            return "create"
        owner = (existing.get("provenance") or {}).get("cascade_of")
        other = uow.repo("feature_set_pins").get(owner) if owner and owner != own else None
        busy = other is not None and other["state"] == "materializing"
        if existing["state"] == "sealed":
            return "wait" if busy else "reuse"
        if existing["state"] == "materializing" and not owner:
            raise ConflictError(
                f"Member pin {existing['pin_name']}/{existing['as_of_date']} is "
                "being made by a direct pin request; retry when it finishes"
            )
        if existing["state"] == "materializing" and busy:
            return "wait"
        return "replace"  # failed, requested, or a leftover of a finished cascade

    def _rollback(self, actor: str, pin_id: str, created: builtins.list[str], why: str) -> None:
        """A failed cascade leaves nothing behind: its member pins are removed (§6.6)."""
        with self.p.uow(actor) as uow:
            for pid in created:
                uow.repo("feature_pins").delete(pid)
            uow.repo("feature_set_pins").update(pin_id, {"state": "failed", "failure": why[:2000]})
            uow.audit(
                "featureset.cascade_rolled_back",
                object_type="featureset_pin",
                object_ref=pin_id,
                detail={"member_pins_removed": len(created), "reason": why[:500]},
            )

    def download(
        self,
        p: Principal,
        ref: str,
        *,
        fmt: str = "parquet",
        shape: str = "tabular",
        csv_encoding: str | None = None,
    ) -> dict[str, Any]:
        if shape not in ("tabular", "wide"):
            raise ValidationFailed(
                f"A download is tabular or wide, not '{shape}'"
                + (
                    ": the tensor shape is an in-memory form with no file format; download "
                    "tabular and reshape with maya.resolution.shapes.to_shape"
                    if shape == "tensor"
                    else ""
                ),
                allowed=["tabular", "wide"],
            )
        self.p.licences.export(p, "featureset", ref, "internal")
        res = self.resolve_ref(p, ref)
        schema = self._full_schema(res)
        if shape == "wide":
            df, axis = shapes.to_shape(res.df, schema, "wide")
            # keep every declared type (a date index stays a date); infer only the
            # columns widening created
            known = {a["name"]: a for a in schema}
            inferred = {a["name"]: a for a in shapes_infer(df)}
            payload = shapes.export(
                df, [known.get(c) or inferred[c] for c in df.columns], fmt, csv_encoding
            )
        else:
            payload, axis = shapes.export(res.df, schema, fmt, csv_encoding), None
        manifest = {
            "ref": ref,
            "rows": len(res.df),
            "format": fmt,
            "shape": shape,
            "exported_at": utcnow().isoformat(),
            "exported_by": p.username,
            "withheld": res.fill_report.get("withheld", []),
            "axis": axis,
            "access_conditions": res.fill_report.get("access_conditions", []),
        }
        with self.p.uow(p.username) as uow:
            uow.audit(
                "data.downloaded",
                object_type="featureset",
                object_ref=ref,
                detail=_jsonsafe(manifest),
            )
        return {"data": payload, "manifest": _jsonsafe(manifest)}

    @staticmethod
    def _full_schema(res: Resolved) -> builtins.list[dict[str, Any]]:
        idx = [
            {"name": c, "type": res.meta.get("index_types", {}).get(c, "string")}
            for c in res.meta["index"]
        ]
        extra = [{"name": KT, "type": "timestamp"}] if KT in res.df.columns else []
        return idx + [a for a in res.meta["schema"] if a["name"] in res.df.columns] + extra


def _aligned(eff: dict[str, Any], member_override: dict[str, str]) -> Any:
    """The alignment, its driver member renamed as the members were (a pin resolves each
    member through its member pin, so the driver is known by that pin's ref)."""
    alignment = eff.get("alignment")
    driver = (alignment or {}).get("member")
    if alignment and driver in member_override:
        return {**alignment, "member": member_override[driver]}
    return alignment


def equivalence_body(eff: dict[str, Any], inherited: list[dict[str, Any]]) -> dict[str, Any]:
    """What a feature set *means*, for the near-copy check (§6.8).

    Defaults are spelled out, so an omitted key and its default hash alike; members are
    ordered by attribute; and an inherited layer counts by the policy it carries, not by
    the ancestor that supplied it — an ``extend`` whose parent adds no policy means the
    same as the directly written set, as ``project(extend(S, …), attrs)`` must."""
    body = {
        "index": eff.get("index"),
        "grid": eff.get("grid") or "as_is",
        "alignment": {"mode": "inner", **(eff.get("alignment") or {})},
        "filters": eff.get("filters") or [],
        "global_policy": eff.get("global_policy") or {},
        "group_policies": eff.get("group_policies") or {},
    }
    body["members"] = sorted(eff.get("members", []), key=lambda m: m["attr"])
    if eff.get("forked_from"):
        body["forked_from"] = eff["forked_from"]
    if eff.get("derivation"):
        # a derived set means its operator over its operands, so two derived sets are
        # near-copies only when both of those match (without this, every derived set
        # hashed alike, because none of them has members)
        derivation = eff["derivation"]
        body["derivation"] = {
            "operator": derivation.get("operator"),
            "operands": list(derivation.get("operands") or []),
            "options": derivation.get("options") or {},
        }
    layers = [{k: v for k, v in layer.items() if k != "source"} for layer in inherited]
    body["inherited"] = [layer for layer in layers if layer]
    return body


def shapes_infer(df: pd.DataFrame) -> list[dict[str, Any]]:
    from maya.resolution.types import infer_schema

    return infer_schema(df)


def _jsonsafe(obj: Any) -> Any:
    return djson.loads(djson.dumps(obj))


def diff_set_definitions(a: dict[str, Any], b: dict[str, Any]) -> builtins.list[dict[str, Any]]:
    """Two effective feature-set definitions, member by member and policy by policy."""
    out: builtins.list[dict[str, Any]] = []
    left = {m["attr"]: m for m in a.get("members", [])}
    right = {m["attr"]: m for m in b.get("members", [])}
    for attr in sorted(set(left) | set(right)):
        if attr not in right:
            out.append({"what": f"member {attr}", "change": "removed"})
        elif attr not in left:
            out.append({"what": f"member {attr}", "change": f"added from {right[attr]['ref']}"})
        elif left[attr] != right[attr]:
            changed = sorted(
                k
                for k in set(left[attr]) | set(right[attr])
                if left[attr].get(k) != right[attr].get(k)
            )
            out.append(
                {
                    "what": f"member {attr}",
                    "change": "; ".join(
                        f"{k}: {left[attr].get(k)} → {right[attr].get(k)}" for k in changed
                    ),
                }
            )
    for key in (
        "index",
        "grid",
        "alignment",
        "filters",
        "global_policy",
        "group_policies",
        "derivation",
        "extends",
    ):
        if a.get(key) != b.get(key):
            out.append({"what": key, "change": f"{a.get(key)} → {b.get(key)}"})
    return out
