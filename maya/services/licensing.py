"""
Effective licences (§29.6): what terms an object carries, computed from what it
is built of — its own declaration, the parent it extends, the operands it is
derived from, the members of a feature set, the feature set behind a warrant.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any

from maya.core.errors import LicenceBreach, NotApproved, NotFound
from maya.security import licence as lic
from maya.security.authz import Principal
from maya.services import catalog, refs

MAX_DEPTH = 32


class LicenceService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- computing -----------------------------------------------------------------
    def feature_sources(self, uow: Any, ref: str, depth: int = 0) -> list[tuple[str, Any]]:
        if depth > MAX_DEPTH:
            return []
        r = refs.parse(ref, "feature")
        try:
            feature, ns = catalog.find_object(uow, "features", "feature", r)
        except NotFound:
            return []
        if r.is_pin:
            pin = self.p.feature_data.find_pin(uow, feature, r)
            version = uow.repo("feature_versions").require(pin["feature_version_id"])
        else:
            version = catalog.version_of(uow, "feature_versions", "feature_id", feature,
                                         r.version)
        d = version["definition"]
        me = refs.version_ref("feature", ns["name"], feature["name"], version["version_no"])
        out: list[tuple[str, Any]] = [(me, d.get("licence"))]
        if d.get("extends"):
            out += self.feature_sources(uow, d["extends"]["parent"], depth + 1)
        src = d.get("source") or {}
        if src.get("type") == "derived":
            for operand in (src.get("derivation") or {}).get("operands") or []:
                out += self.feature_sources(uow, operand, depth + 1)
        return out

    def featureset_sources(self, uow: Any, ref: str, depth: int = 0) -> list[tuple[str, Any]]:
        r = refs.parse(ref, "featureset")
        fs, ns = catalog.find_object(uow, "feature_sets", "feature set", r)
        if r.is_pin:
            rows = uow.repo("feature_set_pins").list(feature_set_id=fs["id"], pin_name=r.series,
                                                     order_by=["-as_of_date"], limit=1)
            v = uow.repo("feature_set_versions").require(rows[0]["feature_set_version_id"]) \
                if rows else catalog.version_of(uow, "feature_set_versions", "feature_set_id",
                                                fs, None)
        else:
            v = catalog.version_of(uow, "feature_set_versions", "feature_set_id", fs, r.version)
        eff, _ = self.p.featuresets.effective(uow, v["definition"])
        me = refs.version_ref("featureset", ns["name"], fs["name"], v["version_no"])
        out: list[tuple[str, Any]] = [(me, v["definition"].get("licence"))]
        for m in eff.get("members", []):
            out += self.feature_sources(uow, m["ref"], depth + 1)
        return out

    def effective(self, kind: str, ref: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            sources = self.feature_sources(uow, ref) if kind == "feature" \
                else self.featureset_sources(uow, ref)
        return {**lic.combine(sources), "sources": [s for s, t in sources if t]}

    # -- enforcing -------------------------------------------------------------------
    def reader(self, p: Principal | None, kind: str, ref: str) -> dict[str, Any]:
        eff = self.effective(kind, ref)
        if p is not None:
            lic.check_reader(eff, p.username, p.groups, p.desk)
        return eff

    def export(self, p: Principal, kind: str, ref: str, audience: str = "internal"
               ) -> dict[str, Any]:
        eff = self.reader(p, kind, ref)
        try:
            lic.check_export(eff, audience)
        except LicenceBreach as exc:
            with self.p.uow(p.username) as uow:
                uow.audit("licence.refused", object_type=kind, object_ref=ref,
                          detail={"audience": audience, **exc.context}, durable=True)
            raise
        return eff

    def derivation(self, kind: str, refs_used: list[str], what: str) -> None:
        with self.p.uow() as uow:
            sources: list[tuple[str, Any]] = []
            for ref in refs_used:
                sources += self.feature_sources(uow, ref) if kind == "feature" \
                    else self.featureset_sources(uow, ref)
        lic.check_derivation(lic.combine(sources), what)

    def grantee(self, kind: str, ref: str, principal_type: str, principal_id: str,
                groups: list[str], desk: str | None) -> None:
        """A grant may not open data to people its licence excludes."""
        eff = self.effective(kind, ref)
        if eff["population"] is None:
            return
        if principal_type in ("everyone", "role"):
            raise lic._breach(eff, "population", f"a grant to {principal_type} "
                                                 f"'{principal_id}' would reach people outside "
                                                 "the licensed population")
        if principal_type == "group":
            groups = [principal_id]
        lic.check_reader(eff, f"{principal_type} '{principal_id}'", groups, desk)

    def show(self, p: Principal, kind: str, ref: str) -> dict[str, Any]:
        """The effective licence, for anyone who may read the object (terms are not secret)."""
        if kind not in ("feature", "featureset"):
            raise NotFound(f"No licences on '{kind}'")
        table, label = ("features", "feature") if kind == "feature" else \
            ("feature_sets", "feature set")
        with self.p.uow() as uow:
            obj, _ = catalog.find_object(uow, table, label, refs.parse(ref, kind))
            self.p.access.require(uow, p, "read", kind, obj)
        try:
            eff = self.effective(kind, ref)
        except (NotFound, NotApproved):                 # nothing approved yet
            eff = {**lic.combine([]), "sources": []}
        eff["you_may_receive"] = lic.in_population(eff, p.groups, p.desk)
        return eff
