"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Attestation: a quorum, not a signature.

An attestation names the roles that must sign before a model is in force. Each
required role signs once; the model becomes attested only when every one of them
has. A single decline ends the attestation and sends the record back to be
worked on.

That is the difference between attestation and approval, and it is why both
exist. Approval is one authorised person saying the work is sound. Attestation
is the set of people who will be asked about this model in a supervisory
meeting each putting their name to it — the owner that the controls are
operating, the second line that challenge was effective. A button one person
presses is not that.

Signatures are one-per-role, and a principal may only sign for a role they
actually hold. Both are enforced rather than assumed: an attestation where the
same person signed twice under two hats is not a quorum -- one-per-role and
one-per-person are different rules, and this enforces both.
"""
from __future__ import annotations

import time

from sqlalchemy.exc import IntegrityError
from typing import Any, Dict, List, Optional, Sequence

from core.evidence import EvidenceEngine
from core.lifecycle.common import (DAY, DECISIONS, DEFAULT_REQUIRED_ROLES,
                                   DEFAULT_VALIDITY_DAYS, LifecycleError)
from core.log import get_logger, swallowed
from db import AttestationRepository, SignatureRepository

logger = get_logger(__name__)


class AttestationService:
    """Opens attestations, collects signatures, and decides when a quorum is met."""

    def __init__(self, attestations: AttestationRepository,
                 signatures: SignatureRepository, evidence: EvidenceEngine,
                 required_roles: Sequence[str] = DEFAULT_REQUIRED_ROLES,
                 validity_days: int = DEFAULT_VALIDITY_DAYS):
        self.attestations, self.signatures = attestations, signatures
        self.evidence = evidence
        self.required_roles = tuple(required_roles)
        self.validity_days = validity_days

    # ------------------------------------------------------------------ open
    def open(self, model_id: str, kind: str = "initial",
             amendment_id: Optional[str] = None, statement: str = "",
             required_roles: Optional[Sequence[str]] = None,
             actor: str = "system") -> Dict[str, Any]:
        if self.current(model_id):
            raise LifecycleError(
                "attestation_open",
                "an attestation is already open for this model",
                "complete or withdraw the open attestation before opening another")
        now = time.time()
        row = {"model_id": model_id, "amendment_id": amendment_id, "kind": kind,
               "required_roles": list(required_roles or self.required_roles),
               "status": "open", "statement": statement, "opened_by": actor,
               "opened_at": now, "completed_at": None,
               "expires_at": now + self.validity_days * DAY}
        self.attestations.add(row)
        self.evidence.append("attestation_opened", "model", model_id,
                             {"attestation_id": row["id"], "kind": kind,
                              "required_roles": row["required_roles"]}, actor=actor)
        return self.attestations.one(id=row["id"])

    # ------------------------------------------------------------------ sign
    def sign(self, attestation_id: str, principal: Dict[str, Any], role: str,
             decision: str = "attest", statement: str = "") -> Dict[str, Any]:
        """Record one signature. Returns the attestation with its progress."""
        att = self.require(attestation_id)
        username = principal.get("username", "")
        if att["status"] != "open":
            raise LifecycleError("attestation_closed",
                                 f"this attestation is already '{att['status']}'",
                                 "open a new attestation if another is needed")
        if decision not in DECISIONS:
            raise LifecycleError("unknown_decision",
                                 f"'{decision}' is not a decision; expected "
                                 f"{' or '.join(DECISIONS)}", "")
        if role not in att["required_roles"]:
            raise LifecycleError(
                "role_not_required",
                f"'{role}' is not one of the roles this attestation requires "
                f"({', '.join(att['required_roles'])})",
                "sign for a required role, or open an attestation that requires this one")
        if role not in (principal.get("roles") or []):
            raise LifecycleError(
                "role_not_held",
                f"{username} does not hold the role '{role}'",
                "sign for a role you hold; an attestation signed under a borrowed "
                "hat is not a quorum")
        if self.signatures.one(attestation_id=attestation_id, role=role):
            raise LifecycleError("already_signed",
                                 f"the '{role}' signature is already recorded",
                                 "each required role signs once")
        # One-per-ROLE is not one-per-PERSON, and this module's docstring
        # claimed both. It enforced only the first: a principal holding
        # `model_risk_manager` and `validator` -- a supported configuration,
        # since the first is a superset of the second -- signed for each in turn
        # and the model went into force on one person's judgement, with the
        # record and the evidence chain both calling it a quorum. Version
        # approval had carried this check since the quorum was built; the
        # attestation path never did, which is the harder half to notice
        # because the two read almost identically.
        if any(s["principal"] == username
               for s in self.signatures.many(attestation_id=attestation_id)):
            raise LifecycleError(
                "already_signed_personally",
                f"{username} has already signed this attestation under another role",
                "a quorum is a number of people, not a number of hats")

        # The read above and the write below are separate, so the database is
        # what settles a race between two requests from the same dual-hatted
        # principal. `UNIQUE (attestation_id, principal)` does that; losing the
        # race is not a different answer from being told you have already
        # signed, so it translates back into the same refusal.
        try:
            with self.signatures.db.transaction():
                self.signatures.add({"attestation_id": attestation_id,
                                     "principal": username, "role": role,
                                     "decision": decision, "statement": statement,
                                     "signed_at": time.time()})
                self.evidence.append("attestation_signed", "model", att["model_id"],
                                     {"attestation_id": attestation_id, "role": role,
                                      "decision": decision}, actor=username)
        except IntegrityError as exc:
            swallowed(logger, exc, f"recorded {username}'s '{role}' signature",
                      detail="the uniqueness constraint refused it, which means "
                             "another request for the same attestation won the race")
            raise LifecycleError(
                "already_signed_personally",
                f"{username} has already signed this attestation under another role",
                "a quorum is a number of people, not a number of hats") from exc
        return self._settle(attestation_id)

    def _settle(self, attestation_id: str) -> Dict[str, Any]:
        """Decide whether the attestation is now complete, declined, or waiting."""
        att = self.require(attestation_id)
        signatures = self.signatures.many(attestation_id=attestation_id)
        if any(s["decision"] == "decline" for s in signatures):
            return self._close(att, "declined")
        signed = {s["role"] for s in signatures if s["decision"] == "attest"}
        if signed >= set(att["required_roles"]):
            return self._close(att, "attested")
        return self.progress(attestation_id)

    def _close(self, att: Dict[str, Any], status: str) -> Dict[str, Any]:
        self.attestations.set({"status": status, "completed_at": time.time()},
                              id=att["id"])
        self.evidence.append(f"attestation_{status}", "model", att["model_id"],
                             {"attestation_id": att["id"], "kind": att["kind"]},
                             actor="system")
        logger.info("attestation %s for model %s is now %s",
                    att["id"], att["model_id"], status)
        return self.progress(att["id"])

    # ----------------------------------------------------------------- query
    def get(self, attestation_id: str) -> Optional[Dict[str, Any]]:
        return self.attestations.one(id=attestation_id)

    def require(self, attestation_id: str) -> Dict[str, Any]:
        row = self.get(attestation_id)
        if row is None:
            raise LifecycleError("no_attestation", f"no attestation {attestation_id}", "")
        return row

    def current(self, model_id: str) -> Optional[Dict[str, Any]]:
        return self.attestations.one(model_id=model_id, status="open")

    def history(self, model_id: str) -> List[Dict[str, Any]]:
        return self.attestations.many(model_id=model_id)

    def progress(self, attestation_id: str) -> Dict[str, Any]:
        """The attestation, its signatures, and who is still outstanding."""
        att = self.require(attestation_id)
        signatures = self.signatures.many(attestation_id=attestation_id)
        signed = {s["role"] for s in signatures if s["decision"] == "attest"}
        return {**att, "signatures": signatures,
                "signed_roles": sorted(signed),
                "outstanding_roles": sorted(set(att["required_roles"]) - signed),
                "complete": att["status"] == "attested"}

    def latest_attested(self, model_id: str) -> Optional[Dict[str, Any]]:
        rows = [a for a in self.history(model_id) if a["status"] == "attested"]
        return rows[-1] if rows else None

    def is_expired(self, model_id: str, now: Optional[float] = None) -> bool:
        """Whether the standing attestation has lapsed and is due for renewal."""
        latest = self.latest_attested(model_id)
        if latest is None or not latest.get("expires_at"):
            return False
        return (now if now is not None else time.time()) > latest["expires_at"]
