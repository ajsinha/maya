"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Governed aliases — the most dangerous operation in the platform.

Consumers bind to an alias, never to a version. That is what lets a version move
without anyone redeploying, and it is exactly why moving one is not a judgement
call. Two proof obligations must discharge first:

  * L-7, refinement. The replacement's contract must refine the incumbent's:
    assume no more, guarantee no less. A contract that demands a narrower input
    range is not a drop-in, however much better it scores.
  * L-12, variance. Input schemas are contravariant and output schemas
    covariant, so a consumer written against the old version still type-checks
    against the new one.

When either fails the move is refused and the refusal names the clause, because
"incompatible" is not something anyone can act on.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.domain import substitutable
from core.evidence import EvidenceEngine
from core.registry.catalogue import ModelCatalogue
from core.registry.common import RegistryError
from core.registry.specs import contract_of, schema_of
from core.registry.versions import VersionService
from db import AliasHistoryRepository, AliasRepository

NO_INCUMBENT = "no incumbent"


class AliasService:
    """Moves, resolves and records the history of environment aliases."""

    def __init__(self, aliases: AliasRepository, history: AliasHistoryRepository,
                 catalogue: ModelCatalogue, versions: VersionService,
                 evidence: EvidenceEngine):
        self.aliases, self.history = aliases, history
        self.catalogue, self.versions, self.evidence = catalogue, versions, evidence

    # ------------------------------------------------------------------ proof
    @staticmethod
    def obligations(new: Dict[str, Any], old: Optional[Dict[str, Any]]) -> Dict[str, Dict]:
        """Discharge L-7 and L-12 against the incumbent, if there is one."""
        if old is None:
            return {"refinement": {"holds": True, "reason": NO_INCUMBENT},
                    "variance": {"ok": True, "reason": NO_INCUMBENT}}
        r = contract_of(new["contract"]).refines(contract_of(old["contract"]))
        v = substitutable(schema_of(new["input_schema"]), schema_of(new["output_schema"]),
                          schema_of(old["input_schema"]), schema_of(old["output_schema"]))
        return {"refinement": {"holds": r.holds, "reason": r.reason()},
                "variance": {"ok": v.ok, "reason": v.reason()}}

    # ------------------------------------------------------------------- move
    def move(self, urn: str, environment: str, name: str, to_semver: str,
             actor: str = "system", justification: str = "") -> Dict[str, Any]:
        """Governed version switch. Refusal names the exact clause that failed."""
        m = self.catalogue.require(urn)
        new = self.versions.require(urn, to_semver)
        if new["status"] != "approved":
            raise RegistryError(f"version {to_semver} is '{new['status']}', not approved; "
                                f"an alias may only point at an approved version")

        current = self.aliases.one(model_id=m["id"], environment=environment, name=name)
        incumbent = self.versions.by_id(current["version_id"]) if current else None
        proof = self.obligations(new, incumbent)
        if not (proof["refinement"]["holds"] and proof["variance"]["ok"]):
            raise RegistryError(f"alias move refused: {proof['refinement']['reason']} / "
                                f"{proof['variance']['reason']}")

        now = time.time()
        self.aliases.point(m["id"], environment, name, new["id"], now, actor)
        self.history.add({
            "model_id": m["id"], "environment": environment, "name": name,
            "from_version_id": current["version_id"] if current else None,
            "to_version_id": new["id"], **proof,
            "moved_at": now, "moved_by": actor, "justification": justification})
        self.evidence.append("alias_moved", "model", m["id"],
                             {"alias": name, "environment": environment,
                              "to": to_semver, **proof}, actor=actor)
        return {"model": urn, "environment": environment, "alias": name,
                "version": to_semver, **proof}

    # ---------------------------------------------------------------- resolve
    def resolve(self, urn: str, environment: str, name: str) -> Optional[Dict[str, Any]]:
        a = self.aliases.one(model_id=self.catalogue.require(urn)["id"],
                             environment=environment, name=name)
        return self.versions.by_id(a["version_id"]) if a else None

    def history_of(self, urn: str) -> List[Dict[str, Any]]:
        return self.history.many(model_id=self.catalogue.require(urn)["id"])
