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
from core.ports import BlockingSource
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
                 evidence: EvidenceEngine, blocking: Optional[BlockingSource] = None):
        self.aliases, self.history = aliases, history
        self.catalogue, self.versions, self.evidence = catalogue, versions, evidence
        self.blocking = blocking
        # A policy gate, consulted after the proofs above and only
        # ever to refuse. Policy tightens; these proofs are the floor.
        self.policy = None
        # Set at wiring time; see core/policy/wiring.py.
        self.facts = None

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

        self._check_not_blocked(m)
        current = self.aliases.one(model_id=m["id"], environment=environment, name=name)
        incumbent = self.versions.by_id(current["version_id"]) if current else None
        proof = self.obligations(new, incumbent)
        if not (proof["refinement"]["holds"] and proof["variance"]["ok"]):
            raise RegistryError(f"alias move refused: {proof['refinement']['reason']} / "
                                f"{proof['variance']['reason']}")

        if self.policy is not None:
            self.policy.check("alias:move", {
                "tier": m.get("tier"), "environment": environment, "alias": name,
                "to_status": new["status"],
                "refinement_holds": bool(proof["refinement"]["holds"]),
                "variance_ok": bool(proof["variance"]["ok"]),
                "attested": m.get("status") == "attested",
                **(self.facts.alias_move(m) if self.facts else {})},
                f"{urn} {environment}/{name}")

        now = time.time()
        # All three writes together, or none.
        #
        # An alias is what production reads. These ran as three separate
        # statements, so a crash between them left the alias moved with no
        # history row and no evidence node — a change to what the bank is
        # serving, with nothing recording that it happened or why. That is the
        # precise failure this platform exists to prevent, in the one act where
        # it matters most.
        #
        # `db.transaction()` is re-entrant and its own docstring names this use:
        # "a service can wrap a whole governance act without knowing what its
        # collaborators do." The evidence append opens its own and joins this
        # one rather than deadlocking against it.
        with self.aliases.db.transaction():
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

    def _check_not_blocked(self, model: Dict[str, Any]) -> None:
        """An open blocking finding stops promotion.

        Checked before the refinement and variance proofs, because "this model
        has an unresolved Critical finding" is a more useful refusal than a
        contract clause, and cheaper to establish.
        """
        if not self.blocking:
            return
        if open_findings := self.blocking.blocking_for(model["id"]):
            titles = "; ".join(f["title"] for f in open_findings)
            raise RegistryError(
                f"alias move refused: {len(open_findings)} blocking finding(s) open "
                f"against {model['urn']} ({titles}); close them or downgrade them "
                "before promoting a version")

    # ---------------------------------------------------------------- resolve
    def resolve(self, urn: str, environment: str, name: str) -> Optional[Dict[str, Any]]:
        a = self.aliases.one(model_id=self.catalogue.require(urn)["id"],
                             environment=environment, name=name)
        return self.versions.by_id(a["version_id"]) if a else None

    def history_of(self, urn: str) -> List[Dict[str, Any]]:
        return self.history.many(model_id=self.catalogue.require(urn)["id"])
