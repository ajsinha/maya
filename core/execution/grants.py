"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Warrant grants and revocation.

A grant is the standing entitlement: this principal, in this environment, for
this declared use. A descriptor is a short-lived credential minted against one.
Separating them is what makes revocation meaningful — withdrawing the grant
stops future descriptors, and bumping the epoch invalidates the ones already out.

The revocation floor (adversarial review, finding C-1) is the rule that grace
never overrides. Grace extends how long a descriptor's AUTHORISATION stays
current when the platform is unreachable; it does not extend how long a consumer
may stay ignorant of a withdrawal it has already been told about.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.execution.errors import WarrantError
from core.log import get_logger
from core.execution.urn import DEFAULT_ALIAS, model_urn, parse_urn
from core.registry import ModelRegistry
from db import WarrantRepository

logger = get_logger(__name__)

DEFAULT_TTL = {1: 60, 2: 300, 3: 3600, 4: 3600}
DEFAULT_GRACE = {1: 0, 2: 0, 3: 900, 4: 900}


class WarrantGrants:
    """Issues standing entitlements and withdraws them."""

    def __init__(self, repo: WarrantRepository, registry: ModelRegistry,
                 evidence: EvidenceEngine,
                 ttl_by_tier: Optional[Dict[int, int]] = None,
                 grace_by_tier: Optional[Dict[int, int]] = None):
        self.repo, self.registry, self.evidence = repo, registry, evidence
        self.ttl = ttl_by_tier or dict(DEFAULT_TTL)
        self.grace = grace_by_tier or dict(DEFAULT_GRACE)
        # Seeded from what is stored, not from zero.
        #
        # The epoch is bumped by every revocation and stamped onto each grant,
        # so a descriptor carrying a stale epoch is one issued before somebody
        # withdrew authority. It lived only in this process and started at 0, so
        # a restart walked it back: revoke three times, restart, and the next
        # grant is issued at epoch 0 — indistinguishable from a grant predating
        # every one of those revocations. **A restart silently undid the effect
        # of revoking**, which is the one act that most needs to survive one.
        #
        # The column has been on `warrant` the whole time. Nothing read it back.
        self.epoch = self._highest_epoch()

    def _highest_epoch(self) -> int:
        """The furthest any grant has been stamped with, or zero if none have.

        Read once at construction rather than on every issue: the epoch only
        advances, and re-reading it per grant would make issuance depend on a
        query whose answer this object already owns.
        """
        row = self.repo.db.query_one(
            "SELECT MAX(epoch) AS highest FROM warrant")
        highest = (row or {}).get("highest")
        if highest:
            logger.info("revocation epoch resumed at %d from the register", highest)
        return int(highest or 0)

    def issue(self, urn: str, environment: str, principal: str, declared_use: str,
              flavour: str = "descriptor_only", actor: str = "system") -> Dict[str, Any]:
        name, semver, aliasname = parse_urn(urn)
        m = self.registry.require(model_urn(name))
        tier = m.get("tier") or 1
        if semver is None and aliasname is None:
            aliasname = DEFAULT_ALIAS
        row = {"model_id": m["id"], "environment": environment,
               "binding_kind": "pinned_version" if semver else "alias",
               "alias_name": aliasname, "version_id": None, "flavour": flavour,
               "principal": principal, "declared_use": declared_use,
               "ttl_seconds": self.ttl.get(tier, 300),
               "grace_seconds": self.grace.get(tier, 0),
               "revoked": False, "revoke_reason": None, "epoch": self.epoch,
               "created_at": time.time()}
        if semver:
            v = self.registry.version(m["urn"], semver)
            if not v:
                raise WarrantError("validation_failed", f"no version {semver} for {m['urn']}", "")
            row["version_id"] = v["id"]
        self.repo.add(row)
        self.evidence.append("warrant_issued", "model", m["id"],
                             {"urn": urn, "principal": principal, "use": declared_use,
                              "environment": environment}, actor=actor)
        return row

    def find(self, model_id: str, environment: str, principal: str) -> Optional[Dict[str, Any]]:
        return self.repo.one(model_id=model_id, environment=environment, principal=principal)

    def of_model(self, urn: str) -> List[Dict[str, Any]]:
        return self.repo.many(model_id=self.registry.require(urn)["id"])

    # ------------------------------------------------------------- revocation
    def revoke(self, warrant_id: str, reason: str, actor: str = "system") -> Dict[str, Any]:
        row = self.repo.one(id=warrant_id)
        if not row:
            raise WarrantError("not_found", f"no warrant {warrant_id}", "")
        self.epoch += 1
        self.repo.set({"revoked": True, "revoke_reason": reason, "epoch": self.epoch},
                      id=warrant_id)
        self.evidence.append("warrant_revoked", "model", row["model_id"],
                             {"warrant_id": warrant_id, "reason": reason}, actor=actor)
        return {"warrant_id": warrant_id, "revoked": True, "reason": reason, "epoch": self.epoch}

    def revoke_model(self, urn: str, reason: str, actor: str = "system") -> int:
        """Kill switch for every warrant on a model."""
        rows = self.of_model(urn)
        for r in rows:
            self.revoke(r["id"], reason, actor)
        return len(rows)
