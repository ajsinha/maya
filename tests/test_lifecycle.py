"""
MAYA — the model record lifecycle.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

The promise this milestone makes is one sentence: an attested record is
immutable, and the only way out is a declared amendment that must itself be
attested. TestImmutability is where that promise is actually tested; everything
else supports it.
"""
import pytest

from core.lifecycle import (AMENDING, APPROVED, ATTESTED, DRAFT, RETIRED, SUBMITTED,
                            LifecycleError, allowed_from, is_mutable)
from core.registry import RegistryError
from tests.conftest import URN


# ============================================================ the state machine
class TestStateMachine:
    def test_only_draft_and_amending_are_mutable(self):
        assert is_mutable(DRAFT) and is_mutable(AMENDING)
        for frozen in (SUBMITTED, APPROVED, ATTESTED, RETIRED):
            assert not is_mutable(frozen)

    def test_every_state_offers_its_legal_moves(self):
        assert {t.name for t in allowed_from(DRAFT)} == {"submit", "retire"}
        assert {t.name for t in allowed_from(SUBMITTED)} == {"return", "approve"}
        assert {t.name for t in allowed_from(APPROVED)} == {"attest", "retire"}
        assert {t.name for t in allowed_from(ATTESTED)} == {"amend", "retire"}

    def test_a_retired_record_has_nowhere_left_to_go(self):
        assert allowed_from(RETIRED) == []

    def test_the_machine_is_inspectable(self, lifecycle):
        described = lifecycle.machine()
        assert {t["name"] for t in described} == {
            "submit", "return", "approve", "attest", "amend", "retire"}
        assert all(t["permission"] and t["note"] for t in described)


# ================================================================= the happy path
class TestApprovalPath:
    def test_a_new_model_starts_in_draft(self, a_model):
        assert a_model["status"] == DRAFT

    def test_submission_requires_at_least_one_version(self, lifecycle, a_model):
        with pytest.raises(LifecycleError) as exc:
            lifecycle.submit(a_model, "j.okafor")
        assert exc.value.code == "nothing_to_approve"

    def test_submission_requires_a_tier(self, registry, lifecycle, a_model, kernel_spec):
        registry.create_version(URN, "1.0.0", kernel_spec)
        registry.catalogue.models.set({"tier": None}, id=a_model["id"])
        with pytest.raises(LifecycleError, match="no risk tier"):
            lifecycle.submit(registry.get(URN), "j.okafor")

    def test_submit_then_approve_then_attest(self, registry, lifecycle, ready_model,
                                             owner, mrm):
        assert lifecycle.submit(ready_model, "j.okafor")["status"] == SUBMITTED
        assert lifecycle.approve(registry.get(URN), "s.iqbal")["status"] == APPROVED
        # Approved is not in force: the attestation is still outstanding.
        state = lifecycle.state(URN)
        assert state["open_attestation"]["outstanding_roles"] == [
            "model_owner", "model_risk_manager"]

        lifecycle.sign(registry.get(URN), owner, "model_owner")
        assert registry.get(URN)["status"] == APPROVED, "one signature is not a quorum"

        lifecycle.sign(registry.get(URN), mrm, "model_risk_manager")
        assert registry.get(URN)["status"] == ATTESTED

    def test_a_reviewer_can_send_it_back_with_a_reason(self, registry, lifecycle,
                                                       ready_model):
        lifecycle.submit(ready_model, "j.okafor")
        returned = lifecycle.send_back(registry.get(URN), "s.iqbal", "tier looks wrong")
        assert returned["status"] == DRAFT

    def test_sending_back_without_a_reason_is_refused(self, registry, lifecycle,
                                                      ready_model):
        lifecycle.submit(ready_model, "j.okafor")
        with pytest.raises(LifecycleError, match="requires a reason"):
            lifecycle.send_back(registry.get(URN), "s.iqbal", "   ")

    def test_an_illegal_move_names_what_is_legal_instead(self, lifecycle, ready_model):
        with pytest.raises(LifecycleError) as exc:
            lifecycle.approve(ready_model, "s.iqbal")
        assert exc.value.code == "illegal_transition"
        assert "from here you may: submit, retire" in exc.value.detail


# =================================================================== attestation
class TestAttestation:
    def test_attestation_needs_every_required_role(self, registry, lifecycle,
                                                   ready_model, owner):
        lifecycle.submit(ready_model, "j.okafor")
        lifecycle.approve(registry.get(URN), "s.iqbal")
        progress = lifecycle.sign(registry.get(URN), owner, "model_owner")
        assert progress["open_attestation"]["signed_roles"] == ["model_owner"]
        assert progress["open_attestation"]["outstanding_roles"] == ["model_risk_manager"]
        assert progress["state"] == APPROVED

    def test_a_principal_cannot_sign_for_a_role_they_do_not_hold(self, registry,
                                                                 lifecycle, ready_model,
                                                                 owner):
        lifecycle.submit(ready_model, "j.okafor")
        lifecycle.approve(registry.get(URN), "s.iqbal")
        with pytest.raises(LifecycleError) as exc:
            lifecycle.sign(registry.get(URN), owner, "model_risk_manager")
        assert exc.value.code == "role_not_held"
        assert "borrowed hat" in exc.value.remediation

    def test_a_role_signs_only_once(self, registry, lifecycle, ready_model, owner):
        lifecycle.submit(ready_model, "j.okafor")
        lifecycle.approve(registry.get(URN), "s.iqbal")
        lifecycle.sign(registry.get(URN), owner, "model_owner")
        with pytest.raises(LifecycleError, match="already recorded"):
            lifecycle.sign(registry.get(URN), owner, "model_owner")

    def test_a_role_outside_the_quorum_cannot_sign(self, registry, lifecycle,
                                                   ready_model):
        lifecycle.submit(ready_model, "j.okafor")
        lifecycle.approve(registry.get(URN), "s.iqbal")
        auditor = {"username": "k.hale", "roles": ["auditor"]}
        with pytest.raises(LifecycleError, match="not one of the roles"):
            lifecycle.sign(registry.get(URN), auditor, "auditor")

    def test_one_decline_ends_the_attestation(self, registry, lifecycle, ready_model,
                                              owner, mrm):
        lifecycle.submit(ready_model, "j.okafor")
        lifecycle.approve(registry.get(URN), "s.iqbal")
        lifecycle.sign(registry.get(URN), owner, "model_owner")
        lifecycle.sign(registry.get(URN), mrm, "model_risk_manager",
                       decision="decline", statement="controls not evidenced")
        assert registry.get(URN)["status"] == DRAFT, "a decline sends it back to work"

    def test_signing_with_no_attestation_open_is_refused(self, lifecycle, ready_model,
                                                         owner):
        with pytest.raises(LifecycleError, match="no attestation is open"):
            lifecycle.sign(ready_model, owner, "model_owner")

    def test_the_attestation_carries_an_expiry(self, lifecycle, attested_model):
        state = lifecycle.state(URN)
        assert state["attested_at"] and state["attestation_expires_at"]
        assert not state["attestation_expired"]


# ================================================================== immutability
class TestImmutability:
    """The promise: attested means immutable, and amendment is the only way out."""

    def test_an_attested_record_refuses_field_changes(self, registry, attested_model):
        with pytest.raises(RegistryError) as exc:
            registry.update(URN, {"description": "quietly different"})
        assert "attested and therefore immutable" in str(exc.value)

    def test_an_attested_record_refuses_new_versions(self, registry, attested_model,
                                                     kernel_spec):
        """A new version IS a change to the model."""
        with pytest.raises(RegistryError) as exc:
            registry.create_version(URN, "2.0.0", kernel_spec)
        assert "cannot add a version" in str(exc.value)

    def test_a_submitted_record_is_frozen_too(self, registry, lifecycle, ready_model,
                                              kernel_spec):
        lifecycle.submit(ready_model, "j.okafor")
        with pytest.raises(RegistryError, match="frozen"):
            registry.create_version(URN, "2.0.0", kernel_spec)

    def test_a_draft_record_accepts_changes(self, registry, ready_model):
        updated = registry.update(URN, {"description": "clarified"})
        assert updated["description"] == "clarified"

    def test_opening_an_amendment_makes_it_changeable_again(self, registry, lifecycle,
                                                            attested_model):
        lifecycle.amend(attested_model, "recalibrate for the 2026 cycle")
        assert registry.get(URN)["status"] == AMENDING
        assert registry.update(URN, {"description": "now editable"})
        assert registry.create_version(URN, "2.0.0", {"parameter_kind": "none"})

    def test_an_amendment_must_say_why(self, lifecycle, attested_model):
        with pytest.raises(LifecycleError, match="what is being changed and why"):
            lifecycle.amend(attested_model, "   ")

    def test_only_one_amendment_at_a_time(self, registry, lifecycle, attested_model):
        lifecycle.amend(attested_model, "first")
        with pytest.raises(LifecycleError, match="already open"):
            lifecycle.amendments.open(attested_model["id"], "second")

    def test_identity_and_status_are_never_editable(self, registry, ready_model):
        for field in ("urn", "status", "tier", "id"):
            with pytest.raises(RegistryError, match="not editable"):
                registry.update(URN, {field: "tampered"})


# ==================================================================== amendment
class TestAmendmentCycle:
    def test_an_amendment_must_itself_be_attested(self, registry, lifecycle,
                                                  attested_model, owner, mrm):
        lifecycle.amend(attested_model, "recalibrate", ["kernel"])
        registry.update(URN, {"description": "recalibrated"})

        lifecycle.submit(registry.get(URN), "j.okafor")
        lifecycle.approve(registry.get(URN), "s.iqbal")
        assert registry.get(URN)["status"] == APPROVED, "not in force until attested"

        lifecycle.sign(registry.get(URN), owner, "model_owner")
        lifecycle.sign(registry.get(URN), mrm, "model_risk_manager")
        assert registry.get(URN)["status"] == ATTESTED

    def test_the_amendment_closes_when_the_attestation_completes(self, registry,
                                                                 lifecycle,
                                                                 attested_model,
                                                                 owner, mrm):
        lifecycle.amend(attested_model, "recalibrate")
        lifecycle.submit(registry.get(URN), "j.okafor")
        lifecycle.approve(registry.get(URN), "s.iqbal")
        lifecycle.sign(registry.get(URN), owner, "model_owner")
        lifecycle.sign(registry.get(URN), mrm, "model_risk_manager")
        assert lifecycle.state(URN)["open_amendment"] is None
        assert lifecycle.amendments.history(attested_model["id"])[0]["status"] == "attested"

    def test_amendments_are_referenced_and_kept(self, registry, lifecycle,
                                                attested_model, owner, mrm):
        lifecycle.amend(attested_model, "first change")
        first = lifecycle.state(URN)["open_amendment"]
        assert first["reference"] == "AMD-001"
        lifecycle.amendments.withdraw(attested_model["id"], "j.okafor")
        assert lifecycle.amendments.history(attested_model["id"])[0]["status"] == "withdrawn"

    def test_a_declined_amendment_returns_to_amending_not_to_draft(self, registry,
                                                                   lifecycle,
                                                                   attested_model,
                                                                   owner, mrm):
        lifecycle.amend(attested_model, "recalibrate")
        lifecycle.submit(registry.get(URN), "j.okafor")
        lifecycle.approve(registry.get(URN), "s.iqbal")
        lifecycle.sign(registry.get(URN), owner, "model_owner")
        lifecycle.sign(registry.get(URN), mrm, "model_risk_manager",
                       decision="decline", statement="not evidenced")
        assert registry.get(URN)["status"] == AMENDING


# ===================================================================== deletion
class TestDeletion:
    def test_nobody_but_an_administrator_may_delete(self, lifecycle, attested_model,
                                                    owner, mrm):
        for who in (owner, mrm, {"username": "k.hale", "roles": ["auditor"]}):
            with pytest.raises(LifecycleError) as exc:
                lifecycle.delete(attested_model, who, "no longer needed")
            assert exc.value.code == "deletion_refused"
            assert "retires it" in exc.value.detail

    def test_the_refusal_points_at_retirement(self, lifecycle, attested_model, owner):
        with pytest.raises(LifecycleError) as exc:
            lifecycle.delete(attested_model, owner, "cleanup")
        assert "/retire" in exc.value.remediation

    def test_an_administrator_may_delete_with_a_reason(self, registry, lifecycle,
                                                       attested_model):
        admin = {"username": "root", "roles": ["admin"]}
        result = lifecycle.delete(attested_model, admin, "registered in error")
        assert result["deleted"] is True
        assert registry.get(URN) is None

    def test_deletion_requires_a_reason(self, lifecycle, attested_model):
        admin = {"username": "root", "roles": ["admin"]}
        with pytest.raises(LifecycleError, match="requires a reason"):
            lifecycle.delete(attested_model, admin, "  ")

    def test_the_evidence_survives_the_deletion(self, registry, lifecycle, evidence,
                                                attested_model):
        admin = {"username": "root", "roles": ["admin"]}
        model_id = attested_model["id"]
        lifecycle.delete(attested_model, admin, "registered in error")
        kinds = [n["kind"] for n in evidence.for_subject(model_id)]
        assert "model_registered" in kinds and "model_deleted" in kinds
        assert evidence.verify_chain()["valid"] is True

    def test_retirement_keeps_the_record(self, registry, lifecycle, attested_model):
        lifecycle.retire(attested_model, "s.iqbal", "superseded by the 2026 model")
        assert registry.get(URN)["status"] == RETIRED
        assert registry.get(URN) is not None


class TestBaselinedIsMutable:
    """C-5: a baselined model must be able to receive the evidence it lacks.

    It arrived without a version, a tier or a validation. Freezing it would mean
    the only route to closing that debt is an amendment to a record that was
    never attested — which is nonsense, and which is how a cold-start capability
    quietly becomes unusable.
    """

    def test_baselined_is_in_the_mutable_set(self):
        from core.lifecycle import BASELINED, MUTABLE
        assert BASELINED in MUTABLE

    def test_a_baselined_model_accepts_a_version(self, registry, lifecycle,
                                                 a_model, kernel_spec):
        from core.lifecycle import BASELINED
        registry.catalogue.models.set({"status": BASELINED}, id=a_model["id"])
        assert registry.create_version(URN, "1.0.0", kernel_spec)

    def test_it_leaves_baseline_through_the_normal_path(self, registry, lifecycle,
                                                        a_model, kernel_spec,
                                                        owner, mrm):
        from core.lifecycle import ATTESTED, BASELINED
        registry.catalogue.models.set({"status": BASELINED}, id=a_model["id"])
        registry.create_version(URN, "1.0.0", kernel_spec, actor="d.raman")

        lifecycle.submit(registry.get(URN), "j.okafor")
        lifecycle.approve(registry.get(URN), "s.iqbal")
        lifecycle.sign(registry.get(URN), owner, "model_owner")
        lifecycle.sign(registry.get(URN), mrm, "model_risk_manager")
        assert registry.get(URN)["status"] == ATTESTED

    def test_its_meaning_says_what_it_is(self):
        from core.lifecycle import BASELINED, MEANING
        assert "governed going forward" in MEANING[BASELINED]
        assert "debt" in MEANING[BASELINED]
