"""
Feature use cases (§5): define, ingest, version, review, resolve, pin, download.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import builtins
import datetime as dt
from typing import Any

import pandas as pd

from maya.core.errors import ConflictError, NotApproved, PermissionDenied, ValidationFailed
from maya.core.clock import utcnow
from maya.resolution import algebra, shapes
from maya.resolution.types import cast_preview, infer_schema, schema_warnings
from maya.security.authz import Principal
from maya.services import catalog, refs
from maya.services.feature_data import schema_generation
from maya.workflow.engine import Subject

EDITABLE = ("draft", "changes_requested")
PINS_SHOWN = 100  # pins returned with a feature; the rest via pins_page
PREVIEW_ROWS = 200


class FeatureService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    @property
    def data(self) -> Any:
        return self.p.feature_data

    # -- read ---------------------------------------------------------------------
    def listing(
        self,
        uow: Any,
        p: Principal,
        *,
        namespace: str | None = None,
        q: str | None = None,
        status: str | None = None,
        state: str | None = None,
    ) -> Any:
        """What 'the features p may read' means, for the whole list or one page of it."""
        from maya.services.paging import Listing

        filters: dict[str, Any] = {}
        if namespace:
            filters["namespace_id"] = self.p.access.namespace(uow, namespace)["id"]
        if status:
            filters["status"] = status
        names = {n["id"]: n["name"] for n in uow.repo("namespaces").list()}
        users = {u["id"]: u["username"] for u in uow.repo("users").list()}

        def enrich_many(uow: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            ids = [f["id"] for f in rows]
            latest = uow.repo("feature_versions").latest_per("feature_id", ids)
            pins = uow.repo("feature_pins").count_per("feature_id", ids, state="sealed")
            out = []
            for f in rows:
                v = latest.get(f["id"])
                out.append(
                    {
                        **f,
                        "namespace": names.get(f["namespace_id"]),
                        "owner": users.get(f["owner_id"]),
                        "latest_version": v["version_no"] if v else None,
                        "latest_state": v["state"] if v else None,
                        "pins": pins.get(f["id"], 0),
                        "ref": refs.object_ref(
                            "feature", names.get(f["namespace_id"], ""), f["name"]
                        ),
                    }
                )
            return out

        return Listing(
            "features",
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
                "feature_versions",
                "feature_id",
                state,
                self.p.access.reader(uow, p, "feature"),
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
        status: str | None = None,
        state: str | None = None,
    ) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return self.listing(
                uow, p, namespace=namespace, q=q, status=status, state=state
            ).collect(uow)

    def page(
        self,
        p: Principal,
        *,
        namespace: str | None = None,
        q: str | None = None,
        status: str | None = None,
        state: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        sort: str | None = None,
        total: bool = False,
    ) -> dict[str, Any]:
        from maya.services.paging import run_page

        return run_page(
            self.p,
            lambda uow: self.listing(uow, p, namespace=namespace, q=q, status=status, state=state),
            page_size=page_size,
            cursor=cursor,
            sort=sort,
            total=total,
        )

    def get(self, p: Principal, ref: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            feature, ns = catalog.find_object(
                uow, "features", "feature", refs.parse(ref, "feature")
            )
            self.p.access.require(uow, p, "read", "feature", feature)
            versions = uow.repo("feature_versions").list(
                feature_id=feature["id"], order_by=["-version_no"]
            )
            # the most recent pins; a feature may have 100k — the rest are paged (pins_page)
            pins = uow.repo("feature_pins").list(
                feature_id=feature["id"], order_by=["-as_of_date", "pin_name"], limit=PINS_SHOWN
            )
            pins_total = uow.repo("feature_pins").count(feature_id=feature["id"])
            ingests = uow.repo("feature_ingests").list(
                feature_id=feature["id"], order_by=["-knowledge_time"]
            )
            vno = {v["id"]: v["version_no"] for v in versions}
            for pin in pins:
                pin["version_no"] = vno.get(pin["feature_version_id"])
                pin["ref"] = refs.pin_ref(
                    "feature", ns["name"], feature["name"], pin["pin_name"], pin["as_of_date"]
                )
            owner = uow.repo("users").get(feature["owner_id"])
            for v in versions:
                v["transitions"] = self._transitions(uow, feature, ns, v)
            return {
                **feature,
                "namespace": ns["name"],
                "namespace_row": ns,
                "owner": owner["username"] if owner else None,
                "versions": versions,
                "pins": pins,
                "pins_total": pins_total,
                "ingests": ingests,
                "ref": refs.object_ref("feature", ns["name"], feature["name"]),
                "grants": uow.repo("grants").list(object_type="feature", object_id=feature["id"]),
                "can_edit": self.p.access.allowed(uow, p, "update", "feature", feature),
                "can_pin": p.has_capability("feature_pin", "P")
                or p.has_capability("feature_pin", "Q"),
            }

    def pins_page(
        self,
        p: Principal,
        ref: str,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
        sort: str | None = None,
        total: bool = False,
    ) -> dict[str, Any]:
        """A feature's pins a page at a time, newest as-of first."""
        from maya.services.paging import Listing, run_page

        def build(uow: Any) -> Any:
            feature, ns = catalog.find_object(
                uow, "features", "feature", refs.parse(ref, "feature")
            )
            self.p.access.require(uow, p, "read", "feature", feature)
            vno = {
                v["id"]: v["version_no"]
                for v in uow.repo("feature_versions").list(feature_id=feature["id"])
            }

            def enrich(uow: Any, pin: dict[str, Any]) -> dict[str, Any]:
                return {
                    **pin,
                    "version_no": vno.get(pin["feature_version_id"]),
                    "ref": refs.pin_ref(
                        "feature", ns["name"], feature["name"], pin["pin_name"], pin["as_of_date"]
                    ),
                    "can_retire": p.is_admin,
                }

            return Listing(
                "feature_pins",
                {
                    "-as_of": "-as_of_date",
                    "as_of": "as_of_date",
                    "series": "pin_name",
                    "-series": "-pin_name",
                },
                "-as_of",
                {"feature_id": feature["id"]},
                None,
                enrich=enrich,
            )

        return run_page(self.p, build, page_size=page_size, cursor=cursor, sort=sort, total=total)

    def _transitions(
        self, uow: Any, feature: dict[str, Any], ns: dict[str, Any], v: dict[str, Any]
    ) -> builtins.list[str]:
        if ns["is_scratch"]:
            return ["submit"] if v["state"] in EDITABLE else []
        subject = self.subject(uow, feature, ns, v)
        return self.p.workflow.available(uow, subject)

    # -- create and edit ----------------------------------------------------------------
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
                uow, p, "create", "feature", {"id": "new", "namespace_id": ns["id"], "name": name}
            )
            if uow.repo("features").find_one(namespace_id=ns["id"], name=name):
                raise ConflictError(f"Feature '{namespace}/{name}' already exists")
            feature = uow.repo("features").add(
                {
                    "namespace_id": ns["id"],
                    "name": name,
                    "owner_id": p.user_id,
                    "description": description,
                    "tags": tags or [],
                    "index_spec": definition.get("index") or [],
                    "ungoverned": ns["is_scratch"],
                }
            )
            uow.repo("feature_versions").add(
                {
                    "feature_id": feature["id"],
                    "version_no": 1,
                    "state": "draft",
                    "definition": definition,
                }
            )
            uow.audit(
                "feature.created",
                object_type="feature",
                object_ref=refs.object_ref("feature", namespace, name),
            )
            return feature

    def update_draft(
        self,
        p: Principal,
        ref: str,
        definition: dict[str, Any],
        *,
        expected_version: int | None = None,
        description: str | None = None,
        tags: builtins.list[str] | None = None,
    ) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            feature, ns = catalog.find_object(
                uow, "features", "feature", refs.parse(ref, "feature")
            )
            self.p.access.require(uow, p, "update", "feature", feature)
            draft = catalog.latest_version(uow, "feature_versions", "feature_id", feature["id"])
            if draft is None or draft["state"] not in EDITABLE:
                raise NotApproved("There is no editable draft; start a new draft first")
            row = uow.repo("feature_versions").update(
                draft["id"], {"definition": definition}, expected_version=expected_version
            )
            changes: dict[str, Any] = {"index_spec": definition.get("index") or []}
            if description is not None:
                changes["description"] = description
            if tags is not None:
                changes["tags"] = tags
            uow.repo("features").update(feature["id"], changes)
            uow.audit(
                "feature.draft_updated",
                object_type="feature",
                object_ref=refs.object_ref("feature", ns["name"], feature["name"]),
            )
            return row

    def new_draft(self, p: Principal, ref: str) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            feature, ns = catalog.find_object(
                uow, "features", "feature", refs.parse(ref, "feature")
            )
            self.p.access.require(uow, p, "update", "feature", feature)
            latest = catalog.latest_version(uow, "feature_versions", "feature_id", feature["id"])
            if latest and latest["state"] in EDITABLE:
                return latest
            row = uow.repo("feature_versions").add(
                {
                    "feature_id": feature["id"],
                    "version_no": (latest["version_no"] + 1) if latest else 1,
                    "state": "draft",
                    "definition": latest["definition"] if latest else {},
                }
            )
            uow.audit(
                "feature.new_draft",
                object_type="feature",
                object_ref=refs.version_ref(
                    "feature", ns["name"], feature["name"], row["version_no"]
                ),
            )
            return row

    def clone(
        self,
        p: Principal,
        ref: str,
        *,
        name: str,
        namespace: str | None = None,
        extend: bool = False,
    ) -> dict[str, Any]:
        """Clone into a new draft, or ``extend`` it: store a diff over a pinned parent."""
        with self.p.uow() as uow:
            src, ns = catalog.find_object(uow, "features", "feature", refs.parse(ref, "feature"))
            self.p.access.require(uow, p, "read", "feature", src)
            latest = catalog.require_latest(uow, "feature_versions", "feature_id", src["id"])
            # extend the latest *approved* version: a draft can still change under the child
            parent = (
                catalog.version_of(uow, "feature_versions", "feature_id", src, None)
                if extend
                else None
            )
        target_ns = namespace or ns["name"]
        if parent is not None:  # extending: version_of never returns None
            definition = {
                "extends": {
                    "parent": refs.version_ref(
                        "feature", ns["name"], src["name"], parent["version_no"]
                    ),
                    "binding": "pinned",
                    "override": {},
                }
            }
        else:
            definition = dict(latest["definition"])
        return self.create(
            p,
            namespace=target_ns,
            name=name,
            definition=definition,
            description=f"Cloned from {ref}",
            tags=src["tags"],
        )

    # -- ingest ---------------------------------------------------------------------
    def infer(self, data: bytes, fmt: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        """Propose a schema from an upload. A proposal the designer confirms (§5.2)."""
        frame = self.data.parse_upload(data, fmt, options)
        schema = infer_schema(frame)
        index = [c for c in ("date", "as_of", "timestamp") if c in frame.columns][:1]
        index += [c for c in ("symbol", "ticker", "id") if c in frame.columns][:1]
        return {
            "schema": schema,
            "warnings": schema_warnings(schema),
            "rows": len(frame),
            "suggested_index": index,
            "preview": _records(frame.head(20)),
        }

    def cast_preview(self, data: bytes, fmt: str, attr: str, logical: str) -> dict[str, Any]:
        frame = self.data.parse_upload(data, fmt)
        if attr not in frame.columns:
            raise ValidationFailed(f"The upload has no column '{attr}'")
        return cast_preview(frame[attr], logical)

    def ingest(
        self,
        p: Principal,
        ref: str,
        data: bytes,
        *,
        fmt: str,
        filename: str = "",
        knowledge_time: dt.datetime | None = None,
        note: str = "",
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append a knowledge-time batch. A restatement never overwrites (§29.1)."""
        digest, existing = self._store_blob(p, data, filename, fmt)
        with self.p.uow() as uow:
            feature, ns = catalog.find_object(
                uow, "features", "feature", refs.parse(ref, "feature")
            )
            self.p.access.require(uow, p, "update", "feature", feature)
            latest = catalog.require_latest(uow, "feature_versions", "feature_id", feature["id"])
            eff = catalog.effective_feature_definition(uow, latest["definition"])
        if (eff.get("source") or {}).get("type") not in ("csv", "parquet", "json"):
            raise ValidationFailed("Only csv, parquet and json sources take uploads")
        if eff.get("data_from"):
            raise ValidationFailed(
                f"This feature extends another and reads its rows from "
                f"'{eff['data_from']}'; ingest there instead"
            )
        errors = catalog.blocking_errors(catalog.validate_feature_definition(eff))
        if errors:
            raise ValidationFailed("Fix the definition before ingesting: " + "; ".join(errors))
        known_at = knowledge_time or utcnow()
        frame = self.data.parse_upload(data, fmt, options or eff.get("source", {}).get("options"))
        table = self.data.prepare_ingest(eff, frame, known_at)
        prior = self.p.lake.read_raw(ns["name"], f"{feature['name']}/{schema_generation(eff)}")
        restatement = _overlaps(prior, table, eff["index"])
        version = self.p.lake.append_raw(
            ns["name"], f"{feature['name']}/{schema_generation(eff)}", table
        )
        with self.p.uow(p.username) as uow:
            row = uow.repo("feature_ingests").add(
                {
                    "feature_id": feature["id"],
                    "blob_hash": digest,
                    "source_type": fmt,
                    "knowledge_time": known_at,
                    "rows": table.num_rows,
                    "lake_version": version,
                    "note": note,
                    "restatement": restatement,
                }
            )
            uow.audit(
                "feature.ingested",
                object_type="feature",
                object_ref=refs.object_ref("feature", ns["name"], feature["name"]),
                detail={
                    "rows": table.num_rows,
                    "blob": digest,
                    "restatement": restatement,
                    "knowledge_time": known_at.isoformat(),
                },
            )
        return {**row, "duplicate_upload_of": existing}

    def _store_blob(
        self, p: Principal, data: bytes, filename: str, fmt: str
    ) -> tuple[str, str | None]:
        digest = self.p.blobs.put(data)
        with self.p.uow(p.username) as uow:
            blob = uow.repo("blobs").find_one(hash=digest)
            if blob is None:
                uow.repo("blobs").add(
                    {
                        "hash": digest,
                        "size": len(data),
                        "content_type": fmt,
                        "filename": filename[:500],
                        "created_at": utcnow(),
                        "created_by": p.username,
                    }
                )
                return digest, None
            return digest, blob["filename"]

    # -- workflow -------------------------------------------------------------------
    def subject(
        self, uow: Any, feature: dict[str, Any], ns: dict[str, Any], version: dict[str, Any]
    ) -> Subject:
        owner = uow.repo("users").get(feature["owner_id"])
        return Subject(
            object_type="feature_version",
            table="feature_versions",
            id=version["id"],
            ref=refs.version_ref("feature", ns["name"], feature["name"], version["version_no"]),
            cap_type="feature",
            row=version,
            namespace=ns,
            owner_id=feature["owner_id"],
            owner_name=owner["username"] if owner else None,
            grants=uow.repo("grants").list(object_type="feature", object_id=feature["id"]),
            context={"feature": feature},
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
            feature, ns = catalog.find_object(
                uow, "features", "feature", refs.parse(ref, "feature")
            )
            version = catalog.version_of(uow, "feature_versions", "feature_id", feature, version_no)
            if ns["is_scratch"] and name == "submit":
                return self._scratch_approve(uow, p, feature, ns, version)
            outcome = self.p.workflow.transition(
                uow,
                p,
                self.subject(uow, feature, ns, version),
                name,
                rationale=rationale,
                force=force,
            )
            if outcome.moved:
                uow.repo("features").update(feature["id"], {"status": outcome.state})
                if outcome.state == "approved":
                    self._lineage(uow, feature, ns, version)
            return outcome.__dict__

    def _scratch_approve(
        self,
        uow: Any,
        p: Principal,
        feature: dict[str, Any],
        ns: dict[str, Any],
        version: dict[str, Any],
    ) -> dict[str, Any]:
        """Scratch has zero ceremony: submit is approval, marked ungoverned (§28.1)."""
        if ns["owner_id"] != p.user_id:
            raise PermissionDenied("Only the owner acts in a scratch namespace")
        uow.repo("feature_versions").update(
            version["id"],
            {
                "state": "approved",
                "submitted_by": p.username,
                "submitted_at": utcnow(),
                "approved_by": p.username,
                "approved_at": utcnow(),
            },
        )
        uow.repo("features").update(feature["id"], {"status": "approved", "ungoverned": True})
        self._lineage(uow, feature, ns, version)
        uow.audit(
            "feature.scratch_approved",
            object_type="feature_version",
            object_ref=refs.version_ref(
                "feature", ns["name"], feature["name"], version["version_no"]
            ),
            detail={"ungoverned": True},
        )
        return {
            "moved": True,
            "state": "approved",
            "message": "scratch: approved, ungoverned",
            "checks": [],
            "approvals": {},
        }

    def _freeze(self, p: Principal, ref: str, version_no: int) -> None:
        """On submit: validate, typecheck the algebra, hash and classify (§5.6)."""
        with self.p.uow(p.username) as uow:
            feature, ns = catalog.find_object(
                uow, "features", "feature", refs.parse(ref, "feature")
            )
            version = catalog.version_of(uow, "feature_versions", "feature_id", feature, version_no)
            if version["state"] not in EDITABLE:
                return
            eff = catalog.effective_feature_definition(uow, version["definition"])
            errors = catalog.blocking_errors(
                catalog.validate_feature_definition(
                    version["definition"], production=ns["production"]
                )
            )
            errors += catalog.blocking_errors(catalog.validate_feature_definition(eff))
            errors += catalog.pinned_parent_errors(uow, version["definition"])
        if errors:
            raise ValidationFailed(
                "The definition is not valid: " + "; ".join(errors), errors=errors
            )
        non_causal = bool(catalog.non_causal_rules(eff))
        src = eff.get("source") or {}
        built_on = (
            list((src.get("derivation") or {}).get("operands") or [])
            if src.get("type") == "derived"
            else []
        )
        if version["definition"].get("extends"):
            built_on.append(version["definition"]["extends"]["parent"])
        if built_on:
            self.p.licences.derivation("feature", built_on, "building a derived feature")
        if src.get("type") == "derived":
            d = src["derivation"]
            metas = self.data.operand_metas(d)
            out = algebra.typecheck(d["operator"], d.get("options"), metas)
            non_causal = non_causal or bool(out.get("non_causal"))
        digest = catalog.definition_hash(eff, f"{ns['name']}/{feature['name']}")
        with self.p.uow(p.username) as uow:
            prev = uow.repo("feature_versions").list(
                feature_id=feature["id"],
                version_no__lt=version_no,
                order_by=["-version_no"],
                limit=1,
            )
            if prev and prev[0]["definition_hash"] == digest:
                raise ValidationFailed(
                    "Nothing changed: this definition hashes identically to "
                    f"v{prev[0]['version_no']} (cosmetic edits do not mint "
                    "a version)"
                )
            dup = uow.repo("feature_versions").find_one(
                definition_hash=digest, feature_id__ne=feature["id"]
            )
            prev_eff = (
                catalog.effective_feature_definition(uow, prev[0]["definition"]) if prev else None
            )
            uow.repo("feature_versions").update(
                version["id"],
                {
                    "definition_hash": digest,
                    "non_causal": non_causal,
                    "change_class": catalog.change_class(prev_eff, eff),
                    "needs_reapproval": None
                    if dup is None
                    else f"equivalent to an existing definition (feature id {dup['feature_id']})",
                },
            )
            self._record_structure(uow, version, eff, version["definition"])

    def _record_structure(
        self, uow: Any, version: dict[str, Any], eff: dict[str, Any], raw_def: dict[str, Any]
    ) -> None:
        src = eff.get("source") or {}
        uow.repo("derivations").delete_where(target_version_id=version["id"])
        if src.get("type") == "derived":
            d = src["derivation"]
            uow.repo("derivations").add(
                {
                    "target_type": "feature",
                    "target_version_id": version["id"],
                    "operator": d["operator"],
                    "operand_refs": d.get("operands") or [],
                    "options": d.get("options") or {},
                }
            )
        uow.repo("inheritance_links").delete_where(child_version_id=version["id"])
        if raw_def.get("extends"):
            e = raw_def["extends"]
            uow.repo("inheritance_links").add(
                {
                    "child_type": "feature",
                    "child_version_id": version["id"],
                    "parent_ref": e["parent"],
                    "binding": e.get("binding", "pinned"),
                    "override_diff": e.get("override") or {},
                }
            )

    def _lineage(
        self, uow: Any, feature: dict[str, Any], ns: dict[str, Any], version: dict[str, Any]
    ) -> None:
        me = refs.version_ref("feature", ns["name"], feature["name"], version["version_no"])
        d = version["definition"]
        if d.get("extends"):
            uow.repo("lineage_edges").link(d["extends"]["parent"], me, "extends")
        src = d.get("source") or {}
        if src.get("type") == "derived":
            op = src["derivation"]["operator"]
            op_node = f"maya://op/{op}/{version['id'][:8]}"
            for i, operand in enumerate(src["derivation"].get("operands") or []):
                uow.repo("lineage_edges").link(operand, op_node, "operand_of", str(i + 1))
            uow.repo("lineage_edges").link(op_node, me, "derived_from", op)

    # -- resolution, pins, download ----------------------------------------------------
    def preview(
        self,
        p: Principal,
        ref: str,
        *,
        as_of_known: Any = None,
        start: dt.date | None = None,
        end: dt.date | None = None,
        limit: int = PREVIEW_ROWS,
    ) -> dict[str, Any]:
        conditions = self._read_conditions(p, ref)
        self.p.licences.reader(p, "feature", ref)
        res = self.data.resolve_ref(ref, as_of_known=as_of_known, start=start, end=end)
        applied = self._condition(res, conditions, p)
        return {
            "rows": _records(res.df.head(limit)),
            "total_rows": len(res.df),
            "columns": list(res.df.columns),
            "fill_report": res.fill_report,
            "plan": res.plan,
            "non_causal": res.meta["non_causal"],
            "access_conditions": applied,
        }

    def _read_conditions(self, p: Principal, ref: str) -> dict[str, Any]:
        """Authorize the read and return the conditions it carries (§11.4)."""
        with self.p.uow() as uow:
            feature, _ = catalog.find_object(uow, "features", "feature", refs.parse(ref, "feature"))
            self.p.access.require(uow, p, "read", "feature", feature)
            return self.p.access.read_conditions(uow, p, "feature", feature)

    def _condition(self, res: Any, conditions: dict[str, Any], p: Principal) -> dict[str, Any]:
        from maya.security.conditions import apply

        res.df, applied = apply(
            res.df, conditions, event_col=res.meta["index"][0], user=self.p.access.user_context(p)
        )
        return applied

    def draft_preview(self, p: Principal, ref: str, *, as_of_known: Any = None) -> dict[str, Any]:
        """Live resolution of the editable draft, so a policy edit shows its fill report."""
        with self.p.uow() as uow:
            feature, ns = catalog.find_object(
                uow, "features", "feature", refs.parse(ref, "feature")
            )
            self.p.access.require(uow, p, "read", "feature", feature)
            latest = catalog.require_latest(uow, "feature_versions", "feature_id", feature["id"])
            eff = catalog.effective_feature_definition(uow, latest["definition"])
        res = self.data.resolve_definition(
            ns["name"], feature["name"], eff, as_of_known=as_of_known, label=f"{ref} (draft)"
        )
        return {
            "rows": _records(res.df.head(PREVIEW_ROWS)),
            "total_rows": len(res.df),
            "columns": list(res.df.columns),
            "fill_report": res.fill_report,
            "plan": res.plan,
        }

    def pin(
        self,
        p: Principal,
        ref: str,
        *,
        version_no: int,
        pin_name: str,
        as_of: dt.date,
        as_of_known: dt.datetime | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Request a pin; a P-holder's request is a job, a Q-holder's awaits approval."""
        if not pin_name.replace("_", "").replace("-", "").isalnum():
            raise ValidationFailed("Pin names use letters, digits, '_' and '-'")
        with self.p.uow(p.username) as uow:
            feature, ns = catalog.find_object(
                uow, "features", "feature", refs.parse(ref, "feature")
            )
            version = catalog.version_of(uow, "feature_versions", "feature_id", feature, version_no)
            if version["state"] not in catalog.APPROVED_STATES:
                raise NotApproved(
                    f"v{version_no} is '{version['state']}'; only an approved version can be pinned"
                )
            if ns["is_scratch"]:
                # Zero ceremony (§28.1): whoever may edit a scratch feature — its owner —
                # pins it directly. No role carries 'P' on 'feature' itself, so checking
                # "pin" there refused every scratch pin.
                direct = True
                self.p.access.require(uow, p, "update", "feature", feature)
            else:
                direct = p.has_capability("feature_pin", "P")
                self.p.access.require(
                    uow,
                    p,
                    "pin" if direct else "request_pin",
                    "feature",
                    feature,
                    cap_type="feature_pin",
                )
            # one request per series and date at a time (§15.3): a racer waits here, then
            # sees the winner's pin and is refused as a conflict
            uow.lock(f"pin:feature:{feature['id']}:{pin_name}:{as_of}")
            clash = uow.repo("feature_pins").find_one(
                feature_id=feature["id"], pin_name=pin_name, as_of_date=as_of
            )
            if clash and clash["state"] != "failed":
                raise ConflictError(f"Pin {pin_name}/{as_of} already exists ({clash['state']})")
            if clash:
                uow.repo("feature_pins").delete(clash["id"])
            pin = uow.repo("feature_pins").add(
                {
                    "feature_id": feature["id"],
                    "feature_version_id": version["id"],
                    "pin_name": pin_name,
                    "as_of_date": as_of,
                    "as_of_known": as_of_known or utcnow(),
                    "state": "materializing" if direct else "requested",
                    "provenance": {"as_of_known_defaulted": as_of_known is None},
                }
            )
            job = None
            if direct:
                job = self.p.jobs.submit(
                    uow,
                    "feature.pin",
                    {"pin_id": pin["id"]},
                    owner=p.username,
                    idempotency_key=idempotency_key,
                )
            uow.audit(
                "pin.requested",
                object_type="feature_pin",
                object_ref=refs.pin_ref("feature", ns["name"], feature["name"], pin_name, as_of),
                detail={"direct": direct},
            )
            return {"pin": pin, "job": job}

    def approve_pin_request(self, p: Principal, pin_id: str) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            pin = uow.repo("feature_pins").require(pin_id)
            feature = uow.repo("features").require(pin["feature_id"])
            if pin["state"] != "requested":
                raise NotApproved(f"Pin is '{pin['state']}', not awaiting approval")
            self.p.access.require(uow, p, "pin", "feature", feature, cap_type="feature_pin")
            if pin["created_by"] == p.username:
                raise PermissionDenied("Segregation of duties: you requested this pin")
            uow.repo("feature_pins").update(pin_id, {"state": "materializing"})
            job = self.p.jobs.submit(uow, "feature.pin", {"pin_id": pin_id}, owner=p.username)
            return {"pin_id": pin_id, "job": job}

    def run_pin_job(self, ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
        try:
            ctx.progress(10, "resolving")  # may raise JobCancelled: the pin fails too
            pin = self.data.materialize(params["pin_id"], ctx.actor)
        except Exception as exc:
            # A failure materialize did not itself record (a resolver or lake error) must
            # still leave the pin 'failed', never 'materializing': a stuck pin blocks that
            # name and date for good. A retry of the job may yet seal it.
            self.data.fail_if_unfinished(params["pin_id"], ctx.actor, exc)
            raise
        return {
            "pin_id": pin["id"],
            "content_hash": pin["content_hash"],
            "rows": pin["row_count"],
            "bytes_new": pin["bytes_new"],
        }

    def retire_pin(self, p: Principal, pin_id: str, reason: str) -> dict[str, Any]:
        if not p.is_admin:
            raise PermissionDenied("Only an administrator retires a pin")
        if not reason.strip():
            raise ValidationFailed("Retiring a pin requires a reason")
        with self.p.uow(p.username) as uow:
            pin = uow.repo("feature_pins").require(pin_id)
            if pin["state"] != "sealed":
                raise NotApproved("Only a sealed pin can be retired")
            row = uow.repo("feature_pins").update(
                pin_id, {"state": "retired", "retired_at": utcnow(), "retire_reason": reason}
            )
            uow.audit(
                "pin.retired",
                object_type="feature_pin",
                object_ref=pin_id,
                detail={"reason": reason},
            )
            return row

    def download(
        self,
        p: Principal,
        ref: str,
        *,
        fmt: str = "parquet",
        csv_encoding: str | None = None,
        as_of_known: Any = None,
    ) -> dict[str, Any]:
        """Bytes plus a manifest naming the version or pin, the hash and the time (§5.7)."""
        with self.p.uow() as uow:
            feature, _ = catalog.find_object(uow, "features", "feature", refs.parse(ref, "feature"))
            self.p.access.require(uow, p, "download", "feature", feature)
            conditions = self.p.access.read_conditions(uow, p, "feature", feature)
        licence = self.p.licences.export(p, "feature", ref, "internal")
        res = self.data.resolve_ref(ref, as_of_known=as_of_known)
        applied = self._condition(res, conditions, p)
        if any(how == "hash" for how in (conditions.get("column_mask") or {}).values()):
            # a hashed column is text now: describe it as such, so export types match values
            res.meta = {
                **res.meta,
                "schema": [
                    {**a, "type": "string"}
                    if conditions["column_mask"].get(a["name"]) == "hash"
                    else a
                    for a in res.meta["schema"]
                ],
            }
        table = self.data.to_table(res)
        _, runs = self.p.lake.plan_fragments(table)
        from maya.core import canonical

        schema_hex = canonical.schema_digest((f.name, str(f.type)) for f in table.schema)
        content = canonical.content_hash(schema_hex, [d for d, _, _ in runs])
        payload = shapes.export(res.df, res.full_schema, fmt, csv_encoding)
        manifest = {
            "ref": ref,
            "content_hash": content,
            "rows": len(res.df),
            "format": fmt,
            "csv_encoding": csv_encoding,
            "exported_at": utcnow().isoformat(),
            "exported_by": p.username,
            "as_of_known": str(as_of_known or "now"),
            "access_conditions": applied,
            "licence": {
                k: licence[k]
                for k in ("vendors", "redistribution", "derived_works", "retention_days")
            },
        }
        with self.p.uow(p.username) as uow:
            uow.audit("data.downloaded", object_type="feature", object_ref=ref, detail=manifest)
        return {"data": payload, "manifest": manifest}

    def compare(self, p: Principal, ref: str, v1: int, v2: int) -> dict[str, Any]:
        with self.p.uow() as uow:
            feature, _ = catalog.find_object(uow, "features", "feature", refs.parse(ref, "feature"))
            self.p.access.require(uow, p, "read", "feature", feature)
            a = catalog.version_of(uow, "feature_versions", "feature_id", feature, v1)
            b = catalog.version_of(uow, "feature_versions", "feature_id", feature, v2)
            ea = catalog.effective_feature_definition(uow, a["definition"])
            eb = catalog.effective_feature_definition(uow, b["definition"])
        return {"change_class": catalog.change_class(ea, eb), "diff": diff_definitions(ea, eb)}

    # -- scratch --------------------------------------------------------------------
    def quick(self, p: Principal, data: bytes, *, name: str, fmt: str = "csv") -> dict[str, Any]:
        """``maya feature quick``: a typed, resolvable, shareable feature in one call (§28.1)."""
        proposal = self.infer(data, fmt)
        index = proposal["suggested_index"]
        if not index:
            raise ValidationFailed(
                "Could not find an event-time column (date, as_of, "
                "timestamp); use the full designer"
            )
        types = {a["name"]: a["type"] for a in proposal["schema"]}
        if types.get(index[0]) not in ("date", "timestamp"):
            types[index[0]] = "date"
        definition = {
            "index": index,
            "index_types": {c: types[c] for c in index},
            "schema": [a for a in proposal["schema"] if a["name"] not in index],
            "source": {"type": fmt},
            "resolution": {"grid": "as_is", "rules": {}},
            "transform": [],
            "quality": [],
        }
        with self.p.uow(p.username) as uow:
            ns = self.p.access.ensure_scratch(uow, p)
        self.create(
            p,
            namespace=ns["name"],
            name=name,
            definition=definition,
            description="Created by 'maya feature quick' — ungoverned scratch",
        )
        ref = refs.object_ref("feature", ns["name"], name)
        ingest = self.ingest(p, ref, data, fmt=fmt, filename=f"{name}.{fmt}")
        self.transition(p, ref, 1, "submit")
        return {
            "ref": ref,
            "version": 1,
            "rows": ingest["rows"],
            "schema": definition,
            "warnings": proposal["warnings"],
        }


def diff_definitions(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    """Attribute-by-attribute comparison of two effective definitions."""
    out = []
    aa = {x["name"]: x for x in a.get("schema", [])}
    bb = {x["name"]: x for x in b.get("schema", [])}
    for name in sorted(set(aa) | set(bb)):
        if name not in bb:
            out.append({"what": f"attribute {name}", "change": "removed"})
        elif name not in aa:
            out.append({"what": f"attribute {name}", "change": f"added ({bb[name]['type']})"})
        elif aa[name] != bb[name]:
            out.append({"what": f"attribute {name}", "change": f"{aa[name]} → {bb[name]}"})
    for key in ("index", "index_types", "source", "resolution", "transform", "quality"):
        if a.get(key) != b.get(key):
            out.append({"what": key, "change": f"{a.get(key)} → {b.get(key)}"})
    return out


def _overlaps(prior: Any, table: Any, index: list[str]) -> bool:
    if prior is None or prior.num_rows == 0:
        return False
    old = prior.select(index).to_pandas().astype(str)
    new = table.select(index).to_pandas().astype(str)
    return bool(len(old.merge(new, on=index, how="inner")))


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for rec in df.to_dict("records"):
        out.append({k: _jsonable(v) for k, v in rec.items()})
    return out


def _jsonable(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and v != v:
        return None
    if isinstance(v, pd.Timestamp):
        return None if pd.isna(v) else v.isoformat()
    if hasattr(v, "tolist"):
        return v.tolist()
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v
