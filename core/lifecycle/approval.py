"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Version approval as a quorum.

The model *record* was already attested by several people; an individual version
was approved by one. That asymmetry was backwards. The record says what the model
is for and who owns it; the version says what will actually run. If anything
deserves more than one signature it is the second.

**The depth of control follows the tier**, which is the same adjunction (law
**L-5**) that decides every other control set here. A Tier 1 version needs the
second line and an independent validator; a Tier 4 version needs neither, and
saying so is better than pretending a scheduling heuristic and a capital model
deserve the same ceremony.

**A version whose model has no tier cannot be approved at all.** Not because the
tier is paperwork, but because the tier is what decides how many signatures this
approval needs — approving first and assessing afterwards would be a way of
choosing your own control depth, and it is the obvious way to game a rule like
this one.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.evidence import EvidenceEngine
from core.lifecycle.common import LifecycleError
from core.log import get_logger
from db import VersionApprovalRepository, VersionApprovalSignatureRepository

logger = get_logger(__name__)

APPROVE, DECLINE = "approve", "decline"
DECISIONS: Tuple[str, ...] = (APPROVE, DECLINE)

OPEN, APPROVED, DECLINED, WITHDRAWN = "open", "approved", "declined", "withdrawn"

# Who must sign, by tier. A tier absent from this map is approved by one
# authorised person, which is what tiers 3 and 4 have always been.
DEFAULT_QUORUM: Dict[int, Tuple[str, ...]] = {
    1: ("model_risk_manager", "validator"),
    2: ("model_risk_manager", "validator"),
}


class VersionApproval:
    """Opens version approvals, collects signatures, decides when enough is enough."""

    def __init__(self, approvals: VersionApprovalRepository,
                 signatures: VersionApprovalSignatureRepository,
                 registry, evidence: EvidenceEngine,
                 quorum: Optional[Dict[int, Sequence[str]]] = None):
        self.approvals, self.signatures = approvals, signatures
        self.registry, self.evidence = registry, evidence
        self.quorum = {int(k): tuple(v) for k, v in (quorum or DEFAULT_QUORUM).items()}

    # ------------------------------------------------------------ requirement
    def required_for(self, tier: Optional[int]) -> Tuple[str, ...]:
        """Which roles must sign for a version of a model at this tier."""
        return self.quorum.get(int(tier), ()) if tier is not None else ()

    def describes(self) -> List[Dict[str, Any]]:
        """The whole table, so nobody has to read the configuration to know."""
        return [{"tier": tier, "required_roles": list(roles),
                 "signatures": len(roles)}
                for tier, roles in sorted(self.quorum.items())] + [
            {"tier": tier, "required_roles": [], "signatures": 1}
            for tier in (3, 4) if tier not in self.quorum]

    def needed(self, urn: str, semver: str) -> Dict[str, Any]:
        """What this particular version's approval requires, and where it stands."""
        model, version = self._subject(urn, semver)
        roles = self.required_for(model.get("tier"))
        current = self.approvals.open_for(version["id"])
        return {
            "urn": urn, "semver": semver, "tier": model.get("tier"),
            "quorum_required": bool(roles), "required_roles": list(roles),
            "status": version["status"],
            "open_approval": current["id"] if current else None,
            "progress": self.progress(current["id"]) if current else None,
            "detail": self._requirement_detail(model, roles, version),
        }

    @staticmethod
    def _requirement_detail(model: Dict[str, Any], roles: Tuple[str, ...],
                            version: Dict[str, Any]) -> str:
        if model.get("tier") is None:
            return ("this model has no risk tier, so the depth of control its "
                    "versions owe is undecided; assess it before approving")
        if not roles:
            return (f"a tier {model['tier']} version is approved by one authorised "
                    f"person; no quorum is required")
        return (f"a tier {model['tier']} version needs {len(roles)} signatures: "
                f"{', '.join(roles)}")

    def refuse_without_quorum(self, urn: str, semver: str) -> None:
        """The registry's gate. Raises when a quorum applies and is not complete.

        A direct approval of a version whose tier demands a quorum is exactly
        what this feature exists to stop, so the refusal names the endpoint that
        does the right thing rather than only saying no.
        """
        model, version = self._subject(urn, semver)
        self._refuse_without_tier(model)
        roles = self.required_for(model["tier"])
        if not roles:
            return
        complete = [a for a in self.approvals.history(version["id"])
                    if a["status"] == APPROVED]
        if complete:
            return
        raise LifecycleError(
            "quorum_required",
            f"a tier {model['tier']} version is approved by a quorum of "
            f"{', '.join(roles)}, not by one signature",
            f"open an approval at POST /api/v1/models/.../versions/{semver}"
            f"/approval and have each required role sign it")

    # ------------------------------------------------------------------- open
    def open(self, urn: str, semver: str, statement: str = "",
             actor: str = "system") -> Dict[str, Any]:
        model, version = self._subject(urn, semver)
        self._refuse_without_tier(model)
        if version["status"] == "approved":
            raise LifecycleError("already_approved",
                                 f"version {semver} is already approved",
                                 "open an approval for a version that needs one")
        roles = self.required_for(model["tier"])
        if not roles:
            raise LifecycleError(
                "no_quorum_required",
                f"a tier {model['tier']} version is approved by one authorised "
                f"person, so there is no quorum to open",
                "approve it directly")
        if self.approvals.open_for(version["id"]):
            raise LifecycleError(
                "approval_open",
                f"an approval is already open for version {semver}",
                "complete or withdraw it before opening another")

        row = {"model_id": model["id"], "model_version_id": version["id"],
               "tier": model["tier"], "required_roles": list(roles),
               "status": OPEN, "statement": statement,
               "opened_by": actor, "opened_at": time.time(), "completed_at": None}
        self.approvals.add(row)
        self.evidence.append("version_approval_opened", "version", version["id"],
                             {"approval_id": row["id"], "semver": semver,
                              "tier": model["tier"], "required_roles": list(roles)},
                             actor=actor)
        logger.info("opened approval for %s@%s requiring %s", urn, semver, roles)
        return self.approvals.one(id=row["id"])

    @staticmethod
    def _refuse_without_tier(model: Dict[str, Any]) -> None:
        if model.get("tier") is None:
            raise LifecycleError(
                "no_tier",
                "this model has no risk tier, so how many signatures its version "
                "needs is undecided",
                "assess the model first; approving before assessing would be a "
                "way of choosing your own control depth")

    # ------------------------------------------------------------------- sign
    def sign(self, approval_id: str, principal: Dict[str, Any], role: str,
             decision: str = APPROVE, statement: str = "") -> Dict[str, Any]:
        """One signature. The same person may not sign twice under two hats."""
        approval = self.require(approval_id)
        username = principal.get("username", "")
        if approval["status"] != OPEN:
            raise LifecycleError("approval_closed",
                                 f"this approval is already '{approval['status']}'",
                                 "open a new one if another is needed")
        if decision not in DECISIONS:
            raise LifecycleError("unknown_decision",
                                 f"'{decision}' is not a decision; expected "
                                 f"{' or '.join(DECISIONS)}", "")
        if role not in approval["required_roles"]:
            raise LifecycleError(
                "role_not_required",
                f"'{role}' is not one of the roles this approval requires "
                f"({', '.join(approval['required_roles'])})",
                "sign for a required role")
        if role not in (principal.get("roles") or []):
            raise LifecycleError(
                "role_not_held", f"{username} does not hold the role '{role}'",
                "sign for a role you hold; an approval signed under a borrowed "
                "hat is not a quorum")
        if self.signatures.one(version_approval_id=approval_id, role=role):
            raise LifecycleError("already_signed",
                                 f"the '{role}' signature is already recorded",
                                 "each required role signs once")
        if any(s["principal"] == username
               for s in self.signatures.many(version_approval_id=approval_id)):
            raise LifecycleError(
                "already_signed_personally",
                f"{username} has already signed this approval under another role",
                "a quorum is a number of people, not a number of hats")

        self.signatures.add({"version_approval_id": approval_id,
                             "principal": username, "role": role,
                             "decision": decision, "statement": statement,
                             "signed_at": time.time()})
        self.evidence.append("version_approval_signed", "version",
                             approval["model_version_id"],
                             {"approval_id": approval_id, "role": role,
                              "decision": decision}, actor=username)
        return self._settle(approval_id)

    def _settle(self, approval_id: str) -> Dict[str, Any]:
        approval = self.require(approval_id)
        signatures = self.signatures.many(version_approval_id=approval_id)
        if any(s["decision"] == DECLINE for s in signatures):
            return self._close(approval, DECLINED)
        signed = {s["role"] for s in signatures if s["decision"] == APPROVE}
        if signed >= set(approval["required_roles"]):
            return self._close(approval, APPROVED)
        return self.progress(approval_id)

    def _close(self, approval: Dict[str, Any], status: str) -> Dict[str, Any]:
        self.approvals.set({"status": status, "completed_at": time.time()},
                           id=approval["id"])
        self.evidence.append(f"version_approval_{status}", "version",
                             approval["model_version_id"],
                             {"approval_id": approval["id"]}, actor="system")
        if status == APPROVED:
            # The quorum is the decision; the registry records its consequence.
            version = self.registry.version_by_id(approval["model_version_id"])
            self.registry.approve_version(version["urn"], version["semver"],
                                          actor="quorum", quorum_id=approval["id"])
        logger.info("version approval %s is now %s", approval["id"], status)
        return self.progress(approval["id"])

    def withdraw(self, approval_id: str, actor: str = "system") -> Dict[str, Any]:
        approval = self.require(approval_id)
        if approval["status"] != OPEN:
            raise LifecycleError("approval_closed",
                                 f"this approval is already '{approval['status']}'", "")
        return self._close(approval, WITHDRAWN)

    # ------------------------------------------------------------------ query
    def get(self, approval_id: str) -> Optional[Dict[str, Any]]:
        return self.approvals.one(id=approval_id)

    def require(self, approval_id: str) -> Dict[str, Any]:
        row = self.get(approval_id)
        if row is None:
            raise LifecycleError("no_approval",
                                 f"no version approval {approval_id}", "")
        return row

    def progress(self, approval_id: str) -> Dict[str, Any]:
        """Who has signed, who has not, and what is still needed."""
        approval = self.require(approval_id)
        signatures = self.signatures.many(version_approval_id=approval_id)
        signed = {s["role"]: s for s in signatures}
        outstanding = [r for r in approval["required_roles"] if r not in signed]
        return {
            **approval,
            "signatures": [{"role": s["role"], "principal": s["principal"],
                            "decision": s["decision"], "statement": s["statement"],
                            "signed_at": s["signed_at"]} for s in signatures],
            "outstanding_roles": outstanding,
            "detail": self._progress_detail(approval, signatures, outstanding),
        }

    @staticmethod
    def _progress_detail(approval: Dict[str, Any], signatures: List[Dict[str, Any]],
                         outstanding: List[str]) -> str:
        declined = [s for s in signatures if s["decision"] == DECLINE]
        if declined:
            return (f"declined by {declined[0]['principal']} as "
                    f"{declined[0]['role']}; one decline returns the version to "
                    f"its author")
        if approval["status"] == APPROVED:
            return (f"approved by {len(signatures)} signatures: "
                    f"{', '.join(sorted(s['role'] for s in signatures))}")
        if approval["status"] == WITHDRAWN:
            return "withdrawn before a quorum was reached"
        return (f"waiting on {', '.join(outstanding)}"
                if outstanding else "waiting")

    def history(self, urn: str, semver: str) -> List[Dict[str, Any]]:
        _, version = self._subject(urn, semver)
        return [self.progress(a["id"])
                for a in self.approvals.history(version["id"])]

    # ---------------------------------------------------------------- subject
    def _subject(self, urn: str, semver: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        model = self.registry.require(urn)
        version = self.registry.version(urn, semver)
        if version is None:
            raise LifecycleError("no_such_version",
                                 f"{urn} has no version {semver}", "")
        return model, version
