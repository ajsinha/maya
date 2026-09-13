"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The lifecycle service: the state machine, amendments and attestation, wired.

This is where the platform's central promise is kept. An **attested** model record
is immutable — no field changes, and no new versions — and the only way through
that is to open an amendment, which says what is changing and why, and which
must itself be attested before the model is back in force.

It also implements the mutation gate the registry consults. That is deliberately
a port rather than an import: the registry must be able to refuse a change to a
frozen record without knowing that amendments and attestations exist.

Deletion is the one act with no workflow. Nothing else in MAYA removes anything,
and this does not remove the evidence either: a deleted model leaves its whole
chain behind, including the entry recording that it was deleted and by whom.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.evidence import EvidenceEngine
from core.lifecycle.amendments import AmendmentService
from core.lifecycle.attestation import AttestationService
from core.lifecycle.common import LifecycleError
from core.lifecycle.states import (AMENDING, ATTESTED, DRAFT, allowed_from, describe, is_mutable,
                                   MEANING, transition)
from core.log import get_logger
from core.registry import ModelRegistry

logger = get_logger(__name__)


class LifecycleService:
    """Moves model records through their states, and refuses changes to frozen ones."""

    def __init__(self, registry: ModelRegistry, amendments: AmendmentService,
                 attestations: AttestationService, evidence: EvidenceEngine,
                 holds=None, tombstones=None, cascade=None):
        self.registry, self.amendments = registry, amendments
        self.attestations, self.evidence = attestations, evidence
        # What the deletion leaves behind, and what goes with it. Both are
        # optional so a partial wiring still starts — but `delete` refuses
        # without a tombstone rather than proceeding, because a deletion that
        # frees the URN is the failure this pair exists to prevent.
        self.tombstones, self.cascade = tombstones, cascade
        # Legal holds. `LegalHolds.held` has always documented itself as "the
        # question a deleter asks", and no deleter asked it: holds were
        # consulted by the inference log and the retention schedule and not by
        # the one act they exist to stop. A hold that does not reach the
        # irreversible act is a hold in a screenshot.
        self.holds = holds

    # ------------------------------------------------------------ the gate
    def may_mutate(self, model_id: str) -> Tuple[bool, str]:
        """The LifecycleGate port. Whether this record accepts changes right now."""
        model = self.registry.catalogue.models.one(id=model_id)
        if model is None:
            return True, ""                       # not ours to refuse
        state = model["status"]
        if is_mutable(state):
            return True, ""
        if state == ATTESTED:
            return False, ("this model is attested and therefore immutable; open an "
                           "amendment to change it")
        return False, f"this model is '{state}' ({MEANING.get(state, '')}) and is frozen"

    def require_mutable(self, model_id: str) -> None:
        allowed, why = self.may_mutate(model_id)
        if not allowed:
            raise LifecycleError("record_frozen", why,
                                 "POST /api/v1/models/{name}/amend with a reason")

    # -------------------------------------------------------------- movement
    def _move(self, model: Dict[str, Any], name: str, actor: str,
              payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Apply a named transition, or refuse naming what is legal instead."""
        rule = transition(name)
        state = model["status"]
        if rule is None or state not in rule.sources:
            legal = ", ".join(t.name for t in allowed_from(state)) or "nothing"
            raise LifecycleError(
                "illegal_transition",
                f"cannot '{name}' a model that is '{state}'; from here you may: {legal}",
                f"the record is {MEANING.get(state, 'in an unexpected state')}")
        with self.evidence.recording():
            self.registry.catalogue.models.set({"status": rule.target}, id=model["id"])
            self.evidence.append(f"model_{name}", "model", model["id"],
                                 {"from": state, "to": rule.target, **(payload or {})},
                                 actor=actor)
        logger.info("model %s moved %s -> %s by %s", model["urn"], state, rule.target, actor)
        return self.registry.get(model["urn"])

    def submit(self, model: Dict[str, Any], actor: str, note: str = "") -> Dict[str, Any]:
        """Put the record forward. Refuses an empty one — there is nothing to approve."""
        if not self.registry.versions(model["urn"]):
            raise LifecycleError(
                "nothing_to_approve",
                "this model has no versions; there is nothing to approve",
                "create at least one version before submitting the record")
        if model["tier"] is None:
            raise LifecycleError(
                "not_tiered",
                "this model has no risk tier; approval depth depends on it",
                "POST /api/v1/models/{name}/assess before submitting")
        return self._move(model, "submit", actor, {"note": note})

    def send_back(self, model: Dict[str, Any], actor: str, reason: str) -> Dict[str, Any]:
        if not reason.strip():
            raise LifecycleError("reason_required",
                                 "returning a record requires a reason",
                                 "say what needs to change")
        return self._move(model, "return", actor, {"reason": reason})

    def approve(self, model: Dict[str, Any], actor: str, note: str = "",
                required_roles: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        """Approve, and open the attestation the record now needs.

        Approval and attestation are separate on purpose: approval is one
        authorised person saying the work is sound, attestation is the set of
        people who will answer for this model each putting their name to it.
        """
        amendment = self.amendments.current(model["id"])
        moved = self._move(model, "approve", actor, {"note": note})
        self.attestations.open(
            model["id"], kind="amendment" if amendment else "initial",
            amendment_id=amendment["id"] if amendment else None,
            statement=note, required_roles=required_roles, actor=actor)
        return moved

    def sign(self, model: Dict[str, Any], principal: Dict[str, Any], role: str,
             decision: str = "attest", statement: str = "") -> Dict[str, Any]:
        """Record one attestation signature, and act on the outcome."""
        current = self.attestations.current(model["id"])
        if current is None:
            raise LifecycleError(
                "no_attestation_open",
                f"no attestation is open for {model['urn']}",
                "the record must be approved before it can be attested")
        progress = self.attestations.sign(current["id"], principal, role,
                                          decision, statement)
        actor = principal.get("username", "system")

        if progress["status"] == "attested":
            self._move(self.registry.get(model["urn"]), "attest", actor,
                       {"attestation_id": current["id"],
                        "signatories": progress["signed_roles"]})
            if current.get("amendment_id"):
                self.amendments.mark(current["amendment_id"], "attested", actor)
        elif progress["status"] == "declined":
            # A decline returns the record to work, not to limbo.
            back = "amend" if current.get("amendment_id") else "return"
            with self.evidence.recording():
                self.registry.catalogue.models.set(
                    {"status": AMENDING if back == "amend" else DRAFT}, id=model["id"])
                self.evidence.append("model_attestation_declined", "model", model["id"],
                                     {"attestation_id": current["id"],
                                      "to": AMENDING if back == "amend" else DRAFT},
                                     actor=actor)
        return self.state(model["urn"])

    def amend(self, model: Dict[str, Any], reason: str,
              scope: Optional[Sequence[str]] = None, actor: str = "system") -> Dict[str, Any]:
        """Open an amendment: the only route out of immutability."""
        self.amendments.open(model["id"], reason, scope, actor)
        return self._move(model, "amend", actor, {"reason": reason})

    def retire(self, model: Dict[str, Any], actor: str, reason: str) -> Dict[str, Any]:
        if not reason.strip():
            raise LifecycleError("reason_required", "retiring a model requires a reason", "")
        return self._move(model, "retire", actor, {"reason": reason})

    # -------------------------------------------------------------- deletion
    def delete(self, model: Dict[str, Any], principal: Dict[str, Any],
               reason: str) -> Dict[str, Any]:
        """Remove a model. Administrators only, and the evidence survives it.

        Checked against the role rather than only the permission, because this
        is the one act with no workflow, no reversal and no second signature.
        A permission can be granted to a role by mistake; requiring 'admin'
        explicitly means a mistake has to be made twice.
        """
        actor = principal.get("username", "system")
        if "admin" not in (principal.get("roles") or []):
            raise LifecycleError(
                "deletion_refused",
                "only an administrator may delete a model; everyone else retires it",
                "POST /api/v1/models/{name}/retire, which withdraws the model "
                "from use and keeps the record")
        if not reason.strip():
            raise LifecycleError("reason_required", "deleting a model requires a reason", "")
        # Asked BEFORE the evidence node, so a refused deletion leaves no
        # `model_deleted` in the chain saying somebody destroyed a record they
        # did not destroy.
        self._refuse_under_legal_hold(model)

        self._refuse_without_a_marker(model)

        # Appended BEFORE the rows go, so the chain records the intent even if
        # the removal fails halfway.
        self.evidence.append("model_deleted", "model", model["id"],
                             {"urn": model["urn"], "name": model["name"],
                              "status": model["status"], "reason": reason},
                             actor=actor)
        # The cascade runs BEFORE the model row goes, because it reads
        # `model_id` off rows that are only findable while the subject is
        # there to be reasoned about, and because its counts are the only
        # record of scale the tombstone will ever carry.
        destroyed = self.cascade.destroy(model["id"]) if self.cascade else {}
        stone = self.tombstones.mark(model, reason=reason, actor=actor,
                                     destroyed=destroyed)
        removed = self.registry.catalogue.models.remove(id=model["id"])
        logger.warning("model %s deleted by %s: %s", model["urn"], actor, reason)
        return {"deleted": bool(removed), "urn": model["urn"], "reason": reason,
                "evidence_retained": True,
                "tombstone": stone["id"], "destroyed": destroyed,
                "urn_reusable": False,
                "storage_reclaimed": False,
                "detail": ("the record is gone and the identifier is not "
                           "available again; storage is reclaimed separately "
                           "by compaction")}

    def _refuse_without_a_marker(self, model: Dict[str, Any]) -> None:
        """Refuse to delete if nothing will record that the model existed.

        Not a wiring assertion — a control.

        A deletion with no tombstone frees the URN, and the URN is derived from
        the name, so the next model registered under that name inherits every
        evidence node, closed finding and amendment naming it. The chain still
        verifies; it is describing a different model. That is a worse outcome
        than a failed deletion, and it is silent, so the deletion is refused
        instead of degrading.
        """
        if self.tombstones is not None:
            return
        raise LifecycleError(
            "no_tombstone_register",
            "this deployment cannot delete models: nothing would record that "
            f"{model['urn']} had existed, so the identifier would fall free "
            "and the next model registered under this name would silently "
            "inherit its history",
            "wire core/retention/tombstones.py into the lifecycle service, or "
            "retire the model instead — retiring withdraws it from use and "
            "keeps every reference readable")

    def _refuse_under_legal_hold(self, model: Dict[str, Any]) -> None:
        """Refuse to destroy a record somebody has placed a hold over.

        A legal hold is the instruction not to destroy evidence while a matter
        is live, and the act it exists to stop is exactly this one — the only
        act in this platform with no workflow, no reversal and no second
        signature. Deleting through a hold is spoliation, and it is not
        something a register should be able to do by accident.

        Held open rather than overridable: there is no `force`. A matter that
        has ended is lifted with a reason, by somebody, on the record — which
        is a different act from a deletion quietly ignoring it.
        """
        if self.holds is None:
            return
        covering = self.holds.applies(artifact_class="model_record",
                                      model_id=model["id"],
                                      legal_entity=model.get("legal_entity"))
        if not covering:
            return
        matters = ", ".join(sorted(h.get("reference", "?") for h in covering))
        raise LifecycleError(
            "under_legal_hold",
            f"{model['urn']} is covered by {len(covering)} active legal "
            f"hold(s): {matters}",
            "lift the hold first, with a reason and on the record. Destroying "
            "a record while a matter is live is spoliation, and there is "
            "deliberately no override here — a hold that a deletion could "
            "step over would not be a hold")

    # ----------------------------------------------------------------- query
    def state(self, urn: str) -> Dict[str, Any]:
        """Everything the interface and an examiner need about where this is."""
        model = self.registry.require(urn)
        attestation = self.attestations.current(model["id"])
        latest = self.attestations.latest_attested(model["id"])
        return {
            "urn": urn, "state": model["status"],
            "meaning": MEANING.get(model["status"], ""),
            "mutable": is_mutable(model["status"]),
            "available_transitions": [
                {"name": t.name, "to": t.target, "permission": t.permission,
                 "note": t.note} for t in allowed_from(model["status"])],
            "open_amendment": self.amendments.current(model["id"]),
            "open_attestation": self.attestations.progress(attestation["id"])
            if attestation else None,
            "attested_at": latest["completed_at"] if latest else None,
            "attestation_expires_at": latest["expires_at"] if latest else None,
            "attestation_expired": self.attestations.is_expired(model["id"]),
            "amendment_history": self.amendments.history(model["id"]),
        }

    @staticmethod
    def machine() -> List[Dict[str, object]]:
        return describe()
