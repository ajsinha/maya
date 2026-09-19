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

import copy
import datetime as dt
from typing import Any

import pandas as pd

from maya.core import djson
from maya.core.errors import ConflictError, NotApproved, ValidationFailed
from maya.persistence.types import utcnow
from maya.resolution import shapes
from maya.resolution.featureset import resolve_featureset
from maya.resolution.resolver import KT
from maya.security.authz import Principal
from maya.services import catalog, refs
from maya.services.feature_data import Resolved
from maya.services.features import _records
from maya.workflow.engine import Subject

EDITABLE = ("draft", "changes_requested")
MAX_SET_DEPTH = 8


class FeatureSetService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- definitions -------------------------------------------------------------
    def effective(self, uow: Any, definition: dict[str, Any], depth: int = 0
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

    # -- read --------------------------------------------------------------------
    def list(self, p: Principal, *, namespace: str | None = None, q: str | None = None
             ) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            filters: dict[str, Any] = {}
            if namespace:
                filters["namespace_id"] = self.p.access.namespace(uow, namespace)["id"]
            rows = uow.repo("feature_sets").list(order_by=["name"],
                                                 search=(["name", "description"], q or ""),
                                                 **filters)
            names = {n["id"]: n["name"] for n in uow.repo("namespaces").list()}
            out = []
            for fs in rows:
                if not self.p.access.allowed(uow, p, "read", "featureset", fs):
                    continue
                latest = catalog.latest_version(uow, "feature_set_versions", "feature_set_id",
                                                fs["id"])
                out.append({**fs, "namespace": names.get(fs["namespace_id"]),
                            "latest_version": latest["version_no"] if latest else None,
                            "latest_state": latest["state"] if latest else None,
                            "members": len((latest or {}).get("definition", {}).get("members", [])),
                            "pins": uow.repo("feature_set_pins").count(feature_set_id=fs["id"],
                                                                       state="sealed"),
                            "ref": refs.object_ref("featureset", names.get(fs["namespace_id"], ""),
                                                   fs["name"])})
            return out

    def get(self, p: Principal, ref: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            fs, ns = catalog.find_object(uow, "feature_sets", "feature set",
                                         refs.parse(ref, "featureset"))
            self.p.access.require(uow, p, "read", "featureset", fs)
            versions = uow.repo("feature_set_versions").list(feature_set_id=fs["id"],
                                                             order_by=["-version_no"])
            for v in versions:
                v["transitions"] = self.p.workflow.available(uow, self.subject(uow, fs, ns, v))
                v["effective"], v["inherited"] = self.effective(uow, v["definition"])
            pins = uow.repo("feature_set_pins").list(feature_set_id=fs["id"],
                                                     order_by=["pin_name", "-as_of_date"])
            vno = {v["id"]: v["version_no"] for v in versions}
            for pin in pins:
                pin["version_no"] = vno.get(pin["feature_set_version_id"])
                pin["ref"] = refs.pin_ref("featureset", ns["name"], fs["name"], pin["pin_name"],
                                          pin["as_of_date"])
            return {**fs, "namespace": ns["name"], "versions": versions, "pins": pins,
                    "ref": refs.object_ref("featureset", ns["name"], fs["name"]),
                    "can_edit": self.p.access.allowed(uow, p, "update", "featureset", fs)}

    # -- create and edit ----------------------------------------------------------
    def create(self, p: Principal, *, namespace: str, name: str, definition: dict[str, Any],
               description: str = "", tags: list[str] | None = None) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            ns = self.p.access.namespace(uow, namespace)
            self.p.access.require(uow, p, "create", "featureset",
                                  {"id": "new", "namespace_id": ns["id"], "name": name})
            if uow.repo("feature_sets").find_one(namespace_id=ns["id"], name=name):
                raise ConflictError(f"Feature set '{namespace}/{name}' already exists")
            fs = uow.repo("feature_sets").add({"namespace_id": ns["id"], "name": name,
                                               "owner_id": p.user_id, "description": description,
                                               "tags": tags or []})
            uow.repo("feature_set_versions").add({"feature_set_id": fs["id"], "version_no": 1,
                                                  "state": "draft", "definition": definition})
            uow.audit("featureset.created", object_type="featureset",
                      object_ref=refs.object_ref("featureset", namespace, name))
            return fs

    def update_draft(self, p: Principal, ref: str, definition: dict[str, Any], *,
                     expected_version: int | None = None) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            fs, ns = catalog.find_object(uow, "feature_sets", "feature set",
                                         refs.parse(ref, "featureset"))
            self.p.access.require(uow, p, "update", "featureset", fs)
            draft = catalog.latest_version(uow, "feature_set_versions", "feature_set_id", fs["id"])
            if draft is None or draft["state"] not in EDITABLE:
                raise NotApproved("There is no editable draft; start a new draft first")
            row = uow.repo("feature_set_versions").update(draft["id"], {"definition": definition},
                                                          expected_version=expected_version)
            uow.audit("featureset.draft_updated", object_type="featureset", object_ref=ref)
            return row

    def new_draft(self, p: Principal, ref: str) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            fs, _ = catalog.find_object(uow, "feature_sets", "feature set",
                                        refs.parse(ref, "featureset"))
            self.p.access.require(uow, p, "update", "featureset", fs)
            latest = catalog.latest_version(uow, "feature_set_versions", "feature_set_id", fs["id"])
            if latest["state"] in EDITABLE:
                return latest
            return uow.repo("feature_set_versions").add({
                "feature_set_id": fs["id"], "version_no": latest["version_no"] + 1,
                "state": "draft", "definition": latest["definition"]})

    # -- workflow -------------------------------------------------------------------
    def subject(self, uow: Any, fs: dict[str, Any], ns: dict[str, Any],
                v: dict[str, Any]) -> Subject:
        owner = uow.repo("users").get(fs["owner_id"])
        return Subject("featureset_version", "feature_set_versions", v["id"],
                       refs.version_ref("featureset", ns["name"], fs["name"], v["version_no"]),
                       "featureset", v, ns, fs["owner_id"], owner["username"] if owner else None,
                       uow.repo("grants").list(object_type="featureset", object_id=fs["id"]),
                       {"featureset": fs, "service": self})

    def transition(self, p: Principal, ref: str, version_no: int, name: str, *,
                   rationale: str | None = None, force: bool = False) -> dict[str, Any]:
        if name == "submit":
            self._freeze(p, ref, version_no)
        with self.p.uow(p.username) as uow:
            fs, ns = catalog.find_object(uow, "feature_sets", "feature set",
                                         refs.parse(ref, "featureset"))
            v = catalog.version_of(uow, "feature_set_versions", "feature_set_id", fs, version_no)
            out = self.p.workflow.transition(uow, p, self.subject(uow, fs, ns, v), name,
                                             rationale=rationale, force=force)
            if out.moved:
                uow.repo("feature_sets").update(fs["id"], {"status": out.state})
                if out.state == "approved":
                    eff, _ = self.effective(uow, v["definition"])
                    me = refs.version_ref("featureset", ns["name"], fs["name"], v["version_no"])
                    for m in eff.get("members", []):
                        uow.repo("lineage_edges").link(m["ref"], me, "member_of", m["attr"])
                    if v["definition"].get("extends"):
                        uow.repo("lineage_edges").link(v["definition"]["extends"]["parent"], me,
                                                       "extends")
            return out.__dict__

    def _freeze(self, p: Principal, ref: str, version_no: int) -> None:
        with self.p.uow(p.username) as uow:
            fs, _ = catalog.find_object(uow, "feature_sets", "feature set",
                                        refs.parse(ref, "featureset"))
            v = catalog.version_of(uow, "feature_set_versions", "feature_set_id", fs, version_no)
            if v["state"] not in EDITABLE:
                return
            eff, inherited = self.effective(uow, v["definition"])
            errors = self.validate(v["definition"]) + self.validate(eff)
            if errors:
                raise ValidationFailed("The feature set definition is not valid: " +
                                       "; ".join(errors), errors=errors)
            body = {k: eff.get(k) for k in ("index", "grid", "alignment", "filters",
                                            "global_policy", "group_policies")}
            body["members"] = sorted(eff.get("members", []), key=lambda m: m["attr"])
            body["inherited"] = inherited
            digest = djson.canonical_hash(body)
            dup = uow.repo("feature_set_versions").find_one(definition_hash=digest,
                                                            feature_set_id__ne=fs["id"])
            if dup:
                other = uow.repo("feature_sets").require(dup["feature_set_id"])
                raise ConflictError(f"An equivalent feature set already exists: "
                                    f"'{other['name']}' v{dup['version_no']}. Reuse it rather "
                                    "than adding a near-copy (§6.8)", existing=other["name"])
            uow.repo("feature_set_versions").update(v["id"], {"definition_hash": digest})

    def members_approved(self, uow: Any, row: dict[str, Any]) -> tuple[bool, str]:
        eff, _ = self.effective(uow, row["definition"])
        bad = []
        for m in eff.get("members", []):
            r = refs.parse(m["ref"], "feature")
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
    def resolve_definition(self, p: Principal | None, eff: dict[str, Any],
                           inherited: list[dict[str, Any]], *, as_of_known: Any = None,
                           start: dt.date | None = None, end: dt.date | None = None,
                           member_override: dict[str, str] | None = None) -> Resolved:
        """Resolve members (withholding what ``p`` cannot read), then assemble."""
        member_override = member_override or {}
        members: dict[str, Any] = {}
        inputs, plan, withheld = [], [], []
        readable = self._readable_members(p, eff) if p is not None else None
        mapping = []
        for m in eff.get("members", []):
            ref = member_override.get(m["ref"], m["ref"])
            if readable is not None and m["ref"] not in readable:
                withheld.append(m["attr"])
                continue
            if ref not in members:
                res = self.p.feature_data.resolve_ref(ref, as_of_known=as_of_known,
                                                      start=start, end=end)
                members[ref] = (res.df, res.meta)
                inputs.append(ref)
                plan += res.plan
            mapping.append({**m, "member": ref})
        if not mapping:
            raise ValidationFailed("You cannot read any member of this feature set",
                                   withheld=withheld)
        df, manifest = resolve_featureset(
            members, mapping, index=eff["index"], alignment=eff.get("alignment"),
            grid=eff.get("grid", "as_is"), global_policy=eff.get("global_policy"),
            group_policies=eff.get("group_policies"), inherited_policies=inherited,
            filters=eff.get("filters"))
        for attr in withheld:
            df[attr] = None
        manifest["withheld"] = withheld
        schema = self._schema(eff, members, mapping)
        index_types = {}
        for ref, (_, meta) in members.items():
            index_types.update({k: v for k, v in meta.get("index_types", {}).items()
                                if k in eff["index"]})
        meta = {"index": eff["index"], "index_types": index_types, "schema": schema,
                "non_causal": bool(manifest.get("non_causal")), "policy": {}}
        manifest["plan"] = plan + manifest.get("plan", [])
        return Resolved(df, meta, manifest, inputs, manifest["plan"])

    def _readable_members(self, p: Principal, eff: dict[str, Any]) -> set[str]:
        ok = set()
        with self.p.uow() as uow:
            for m in eff.get("members", []):
                feature, _ = catalog.find_object(uow, "features", "feature",
                                                 refs.parse(m["ref"], "feature"))
                if self.p.access.allowed(uow, p, "read", "feature", feature):
                    ok.add(m["ref"])
        return ok

    @staticmethod
    def _schema(eff: dict[str, Any], members: dict[str, Any], mapping: list[dict[str, Any]]
                ) -> list[dict[str, Any]]:
        out = []
        by_member = {ref: {a["name"]: a for a in meta["schema"]}
                     for ref, (_, meta) in members.items()}
        for m in eff.get("members", []):
            entry = next((x for x in mapping if x["attr"] == m["attr"]), None)
            if entry is None:
                out.append({"name": m["attr"], "type": m.get("cast") or "float64",
                            "withheld": True})
                continue
            src = by_member[entry["member"]].get(m["source_attr"], {})
            out.append({**src, "name": m["attr"], "type": m.get("cast") or src.get("type")})
        return out

    def load(self, ref: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any],
                                      dict[str, Any] | None, dict[str, Any], list[Any]]:
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
                v = catalog.overlaid("featureset", fs["id"], catalog.version_of(
                    uow, "feature_set_versions", "feature_set_id", fs, r.version), r.version)
            eff, inherited = self.effective(uow, v["definition"])
        return fs, ns, v, pin, eff, inherited

    def resolve_ref(self, p: Principal | None, ref: str, *, as_of_known: Any = None) -> Resolved:
        fs, ns, v, pin, eff, inherited = self.load(ref)
        if p is not None:
            with self.p.uow() as uow:
                self.p.access.require(uow, p, "read", "featureset", fs)
            self.p.licences.reader(p, "featureset", ref)
        if pin is not None:
            table = self.p.lake.read_pin("fspins", ns["name"], fs["name"], pin["fragments"])
            meta = pin["manifest"].get("meta") or {}
            res = Resolved(table.to_pandas(), meta, dict(pin["manifest"]), [],
                           [f"{ref}: sealed pin"])
        else:
            res = self.resolve_definition(p, eff, inherited, as_of_known=as_of_known)
        if p is not None:
            res.fill_report["access_conditions"] = self.condition(p, fs, eff, res)
        return res

    def condition(self, p: Principal, fs: dict[str, Any], eff: dict[str, Any],
                  res: Resolved) -> list[dict[str, Any]]:
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
                feature, _ = catalog.find_object(uow, "features", "feature",
                                                 refs.parse(ref, "feature"))
                cond = self.p.access.read_conditions(uow, p, "feature", feature)
                if cond:
                    res.df, report = apply_mapped(res.df, cond, pairs, index=index, user=user)
                    applied.append({"member": ref, **report})
            cond = self.p.access.read_conditions(uow, p, "featureset", fs)
        if cond:
            res.df, report = apply(res.df, cond, event_col=index[0] if index else None,
                                   user=user)
            applied.append({"featureset": fs["name"], **report})
        return applied

    def preview(self, p: Principal, ref: str, *, as_of_known: Any = None) -> dict[str, Any]:
        res = self.resolve_ref(p, ref, as_of_known=as_of_known)
        return {"rows": _records(res.df.head(200)), "total_rows": len(res.df),
                "columns": list(res.df.columns), "manifest": _jsonsafe(res.fill_report)}

    def draft_preview(self, p: Principal, ref: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            fs, _ = catalog.find_object(uow, "feature_sets", "feature set",
                                        refs.parse(ref, "featureset"))
            self.p.access.require(uow, p, "read", "featureset", fs)
            v = catalog.latest_version(uow, "feature_set_versions", "feature_set_id", fs["id"])
            eff, inherited = self.effective(uow, v["definition"])
        errors = self.validate(eff)
        if errors:
            raise ValidationFailed("; ".join(errors))
        res = self.resolve_definition(p, eff, inherited)
        return {"rows": _records(res.df.head(200)), "total_rows": len(res.df),
                "columns": list(res.df.columns), "manifest": _jsonsafe(res.fill_report)}

    # -- pinning -----------------------------------------------------------------------
    def pin(self, p: Principal, ref: str, *, version_no: int, pin_name: str, as_of: dt.date,
            as_of_known: dt.datetime | None = None, cascade: bool = False,
            idempotency_key: str | None = None) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            fs, ns = catalog.find_object(uow, "feature_sets", "feature set",
                                         refs.parse(ref, "featureset"))
            v = catalog.version_of(uow, "feature_set_versions", "feature_set_id", fs, version_no)
            if v["state"] not in catalog.APPROVED_STATES:
                raise NotApproved(f"v{version_no} is '{v['state']}'; pin an approved version")
            self.p.access.require(uow, p, "pin", "featureset", fs)
            eff, _ = self.effective(uow, v["definition"])
            unpinned = [m["ref"] for m in eff["members"] if not refs.parse(m["ref"]).is_pin]
            if unpinned and not cascade:
                raise NotApproved("A feature set refuses to pin unless every member is pinned. "
                                  "Unpinned: " + ", ".join(sorted(set(unpinned))) +
                                  ". Use cascade pin to pin them together.", unpinned=unpinned)
            if uow.repo("feature_set_pins").find_one(feature_set_id=fs["id"], pin_name=pin_name,
                                                     as_of_date=as_of, state__ne="failed"):
                raise ConflictError(f"Pin {pin_name}/{as_of} already exists")
            pin = uow.repo("feature_set_pins").add({
                "feature_set_id": fs["id"], "feature_set_version_id": v["id"],
                "pin_name": pin_name, "as_of_date": as_of, "as_of_known": as_of_known or utcnow(),
                "state": "materializing"})
            job = self.p.jobs.submit(uow, "featureset.pin",
                                     {"pin_id": pin["id"], "cascade": cascade},
                                     owner=p.username, idempotency_key=idempotency_key)
            uow.audit("featureset.pin_requested", object_type="featureset", object_ref=ref,
                      detail={"pin": pin_name, "as_of": as_of.isoformat(), "cascade": cascade})
            return {"pin": pin, "job": job}

    def run_pin_job(self, ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
        created: list[str] = []
        try:
            return self._materialize(ctx, params["pin_id"], params.get("cascade", False), created)
        except Exception as exc:
            self._rollback(ctx.actor, params["pin_id"], created, str(exc))
            raise

    def _materialize(self, ctx: Any, pin_id: str, cascade: bool, created: list[str]
                     ) -> dict[str, Any]:
        with self.p.uow(ctx.actor) as uow:
            pin = uow.repo("feature_set_pins").require(pin_id)
            fs = uow.repo("feature_sets").require(pin["feature_set_id"])
            ns = uow.repo("namespaces").require(fs["namespace_id"])
            v = uow.repo("feature_set_versions").require(pin["feature_set_version_id"])
            eff, inherited = self.effective(uow, v["definition"])
        override, member_pins = self._pin_members(ctx, eff, pin, cascade, created)
        ctx.progress(60, "resolving the feature set over member pins")
        res = self.resolve_definition(None, eff, inherited, member_override=override,
                                      end=pin["as_of_date"])
        table = self.p.feature_data.to_table(res)
        write, lake_table = self.p.feature_data._write_fragments(ns["name"], fs["name"], table,
                                                                 kind="fspins")
        verify = self.p.lake.verify_pin("fspins", ns["name"], fs["name"], write.fragments,
                                        write.content_hash)
        if not verify["ok"]:
            raise ValidationFailed("Feature set pin failed hash verification", **verify)
        manifest = _jsonsafe({**res.fill_report, "meta": res.meta, "member_pins": override})
        provenance = self.p.feature_data.provenance(v["definition_hash"], res, write, ctx.actor)
        with self.p.uow(ctx.actor) as uow:
            uow.repo("feature_set_pins").update(pin_id, {
                "state": "sealed", "member_pin_ids": member_pins,
                "content_hash": write.content_hash, "schema_digest": write.schema_digest,
                "fragments": write.fragments, "lake_table": lake_table, "manifest": manifest,
                "row_count": write.rows, "bytes_total": write.bytes_total,
                "bytes_new": write.bytes_new, "provenance": provenance, "sealed_at": utcnow()})
            me = refs.pin_ref("featureset", ns["name"], fs["name"], pin["pin_name"],
                              pin["as_of_date"])
            uow.repo("lineage_edges").link(
                refs.version_ref("featureset", ns["name"], fs["name"], v["version_no"]), me,
                "pinned_as")
            for mref in override.values():
                uow.repo("lineage_edges").link(mref, me, "member_of")
            from maya.observability.metrics import METRICS
            METRICS.inc("maya_pins_sealed_total", {"kind": "featureset"})
            METRICS.inc("maya_pin_new_bytes_total", value=float(write.bytes_new))
            uow.audit("pin.sealed", object_type="featureset_pin", object_ref=me,
                      detail={"content_hash": write.content_hash, "members": len(override),
                              "cascaded": len(created)})
        return {"pin_id": pin_id, "content_hash": write.content_hash, "rows": write.rows,
                "cascaded_member_pins": len(created)}

    def _pin_members(self, ctx: Any, eff: dict[str, Any], pin: dict[str, Any], cascade: bool,
                     created: list[str]) -> tuple[dict[str, str], dict[str, str]]:
        """Pin every unpinned member, in sorted feature-id order (no deadlock, §15.3)."""
        override: dict[str, str] = {}
        member_pins: dict[str, str] = {}
        todo = []
        with self.p.uow(ctx.actor) as uow:
            for ref in sorted({m["ref"] for m in eff["members"]}):
                r = refs.parse(ref, "feature")
                feature, ns = catalog.find_object(uow, "features", "feature", r)
                if r.is_pin:
                    found = self.p.feature_data.find_pin(uow, feature, r)
                    override[ref] = refs.pin_ref("feature", ns["name"], feature["name"],
                                                 found["pin_name"], found["as_of_date"])
                    member_pins[ref] = found["id"]
                    continue
                version = catalog.version_of(uow, "feature_versions", "feature_id", feature,
                                             r.version)
                todo.append((feature["id"], ref, feature, ns, version))
        for i, (_, ref, feature, ns, version) in enumerate(sorted(todo, key=lambda t: t[0])):
            ctx.progress(10 + int(40 * i / max(len(todo), 1)), f"cascade: pinning {ref}")
            pid = self._cascade_one(ctx.actor, feature, ns, version, pin, created)
            override[ref] = refs.pin_ref("feature", ns["name"], feature["name"], pin["pin_name"],
                                         pin["as_of_date"])
            member_pins[ref] = pid
        return override, member_pins

    def _cascade_one(self, actor: str, feature: dict[str, Any], ns: dict[str, Any],
                     version: dict[str, Any], pin: dict[str, Any], created: list[str]) -> str:
        with self.p.uow(actor) as uow:
            existing = uow.repo("feature_pins").find_one(feature_id=feature["id"],
                                                         pin_name=pin["pin_name"],
                                                         as_of_date=pin["as_of_date"])
            if existing and existing["state"] == "sealed":
                return existing["id"]
            if existing:
                uow.repo("feature_pins").delete(existing["id"])
            row = uow.repo("feature_pins").add({
                "feature_id": feature["id"], "feature_version_id": version["id"],
                "pin_name": pin["pin_name"], "as_of_date": pin["as_of_date"],
                "as_of_known": pin["as_of_known"], "state": "materializing",
                "provenance": {"cascade_of": pin["id"]}})
        created.append(row["id"])      # recorded first, so a failure here is rolled back too
        self.p.feature_data.materialize(row["id"], actor)
        return row["id"]

    def _rollback(self, actor: str, pin_id: str, created: list[str], why: str) -> None:
        """A failed cascade leaves nothing behind: its member pins are removed (§6.6)."""
        with self.p.uow(actor) as uow:
            for pid in created:
                uow.repo("feature_pins").delete(pid)
            uow.repo("feature_set_pins").update(pin_id, {"state": "failed", "failure": why[:2000]})
            uow.audit("featureset.cascade_rolled_back", object_type="featureset_pin",
                      object_ref=pin_id, detail={"member_pins_removed": len(created),
                                                 "reason": why[:500]})

    def download(self, p: Principal, ref: str, *, fmt: str = "parquet", shape: str = "tabular",
                 csv_encoding: str | None = None) -> dict[str, Any]:
        if shape not in ("tabular", "wide"):
            raise ValidationFailed(
                f"A download is tabular or wide, not '{shape}'"
                + (": the tensor shape is an in-memory form with no file format; download "
                   "tabular and reshape with maya.resolution.shapes.to_shape" if shape == "tensor"
                   else ""), allowed=["tabular", "wide"])
        self.p.licences.export(p, "featureset", ref, "internal")
        res = self.resolve_ref(p, ref)
        schema = self._full_schema(res)
        if shape == "wide":
            df, axis = shapes.to_shape(res.df, schema, "wide")
            payload = shapes.export(df, shapes_infer(df), fmt, csv_encoding)
        else:
            payload, axis = shapes.export(res.df, schema, fmt, csv_encoding), None
        manifest = {"ref": ref, "rows": len(res.df), "format": fmt, "shape": shape,
                    "exported_at": utcnow().isoformat(), "exported_by": p.username,
                    "withheld": res.fill_report.get("withheld", []), "axis": axis,
                    "access_conditions": res.fill_report.get("access_conditions", [])}
        with self.p.uow(p.username) as uow:
            uow.audit("data.downloaded", object_type="featureset", object_ref=ref,
                      detail=_jsonsafe(manifest))
        return {"data": payload, "manifest": _jsonsafe(manifest)}

    @staticmethod
    def _full_schema(res: Resolved) -> list[dict[str, Any]]:
        idx = [{"name": c, "type": res.meta.get("index_types", {}).get(c, "string")}
               for c in res.meta["index"]]
        extra = [{"name": KT, "type": "timestamp"}] if KT in res.df.columns else []
        return idx + [a for a in res.meta["schema"] if a["name"] in res.df.columns] + extra


def shapes_infer(df: pd.DataFrame) -> list[dict[str, Any]]:
    from maya.resolution.types import infer_schema
    return infer_schema(df)


def _jsonsafe(obj: Any) -> Any:
    return djson.loads(djson.dumps(obj))
