"""
MAYA — tests for version approval as a quorum.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The asymmetry this closes: the model *record* was attested by several people
while the version — the thing that actually runs — was approved by one.
"""
from __future__ import annotations

import pytest

from core.lifecycle import LifecycleError
from tests.conftest import person

URN = "maya://model/credit.pd.smallbiz"
MRM = person("s.iqbal", "model_risk_manager")
VAL = person("a.mehta", "validator")


@pytest.fixture
def unapproved(registry, a_model, kernel_spec, contract_spec):
    registry.create_version(URN, "3.2.1", kernel_spec, contract_spec,
                            artifact_digest="sha256:abc")
    return registry.version(URN, "3.2.1")


class TestParametersMustBeExplained:
    """A version cannot say both that it has parameters and that nothing
    produced them.

    Left permitted, this failed in the direction that costs something.
    `trainability_class` falls back to **T0** for a fit procedure it has no
    entry for, and the only one missing is `none` — so a model with real,
    inspectable parameters and no declared fit procedure was classified as
    having *no parameters at all*, and `requires_fitting_evidence` exempted it
    from fitting evidence on exactly that basis.

    Nothing caught it. The property test over the derivation asserts it is
    *total*, which stays true when the answer is wrong; the parametrised table
    covers the nine well-formed rows and this is not one of them; and the
    resulting T0 is indistinguishable downstream from a model that genuinely has
    no parameters. An artefact whose provenance was never recorded is precisely
    the one that most needs fitting evidence.

    So the state is refused where it would be created, rather than handled
    everywhere it could propagate.
    """

    UNEXPLAINED = ("calibration_set", "estimated_coefficients", "learned_weights",
                   "llm_configuration", "elicited_weights", "rule_set")

    @pytest.mark.parametrize("kind", UNEXPLAINED)
    def test_inhabited_parameters_with_no_fit_procedure_are_refused(
            self, registry, a_model, kind):
        from core.registry.common import RegistryError
        with pytest.raises(RegistryError, match="nothing produced them"):
            registry.create_version(URN, "9.0.0",
                                    {"parameter_kind": kind, "fit_procedure": "none"})

    def test_the_refusal_says_what_to_declare_instead(self, registry, a_model):
        from core.registry.common import RegistryError
        with pytest.raises(RegistryError) as exc:
            registry.create_version(URN, "9.0.1",
                                    {"parameter_kind": "learned_weights",
                                     "fit_procedure": "none"})
        for procedure in ("calibrate", "estimate", "train", "configure",
                          "elicit", "author"):
            assert procedure in str(exc.value)

    def test_no_parameters_and_no_procedure_is_the_ordinary_t0_case(
            self, registry, a_model):
        """The pricer. `P` really is terminal, and nothing is contradictory."""
        registry.create_version(URN, "9.1.0",
                                {"parameter_kind": "none", "fit_procedure": "none"})
        assert registry.version(URN, "9.1.0")["trainability_class"] == "T0"

    def test_an_opaque_vendor_model_needs_no_procedure(self, registry, a_model):
        """`P` is inhabited here too, and inaccessibly — which is T6, a real
        class with its own consequences, decided before this question is asked.
        Demanding a procedure would refuse the vendor black box the taxonomy
        exists to accommodate."""
        registry.create_version(URN, "9.2.0",
                                {"parameter_kind": "opaque", "fit_procedure": "none"})
        assert registry.version(URN, "9.2.0")["trainability_class"] == "T6"


class TestTheDepthOfControlFollowsTheTier:
    def test_a_tier_one_version_needs_two_signatures(self, approvals, unapproved):
        needed = approvals.needed(URN, "3.2.1")
        assert needed["quorum_required"]
        assert needed["required_roles"] == ["model_risk_manager", "validator"]
        assert "needs 2 signatures" in needed["detail"]

    def test_a_tier_four_version_needs_one(self, approvals, registry, unapproved,
                                           a_model):
        registry.set_tier(a_model["id"], 4)
        needed = approvals.needed(URN, "3.2.1")
        assert not needed["quorum_required"]
        assert "approved by one authorised person" in needed["detail"]

    def test_the_table_is_published_rather_than_configured_in_private(self,
                                                                     approvals):
        by_tier = {row["tier"]: row["signatures"] for row in approvals.describes()}
        assert by_tier[1] == 2 and by_tier[4] == 1


class TestApprovingBeforeAssessingIsRefused:
    """The tier decides how many signatures are needed, so approving first would
    be a way of choosing your own control depth."""

    @pytest.fixture
    def untiered(self, registry, kernel_spec, contract_spec):
        registry.register("maya://model/ops.untiered", "Untiered", "ops.x", "ops",
                          "person/j.okafor", "LE-US-01", "no tier yet")
        registry.create_version("maya://model/ops.untiered", "1.0.0",
                                kernel_spec, contract_spec)
        return "maya://model/ops.untiered"

    def test_a_direct_approval_is_refused(self, approvals, untiered, registry):
        with pytest.raises(LifecycleError) as exc:
            registry.approve_version(untiered, "1.0.0")
        assert exc.value.code == "no_tier"
        assert "choosing your own control depth" in exc.value.remediation

    def test_opening_a_quorum_is_refused_too(self, approvals, untiered):
        with pytest.raises(LifecycleError) as exc:
            approvals.open(untiered, "1.0.0")
        assert exc.value.code == "no_tier"


class TestASingleSignatureIsRefusedWhereAQuorumApplies:
    def test_the_registry_refuses_and_names_the_route(self, approvals, registry,
                                                      unapproved):
        with pytest.raises(LifecycleError) as exc:
            registry.approve_version(URN, "3.2.1", actor="person/s.iqbal")
        assert exc.value.code == "quorum_required"
        assert "not by one signature" in exc.value.detail
        # The route it names must be one that exists. It used to name
        # /models/.../versions/{semver}/approval, which was never built, so a
        # blocked caller had no way forward from the product or the docs.
        assert "/api/v1/version-approvals" in exc.value.remediation
        assert "/sign" in exc.value.remediation

    def test_a_tier_that_needs_no_quorum_still_approves_directly(
            self, approvals, registry, unapproved, a_model):
        registry.set_tier(a_model["id"], 4)
        assert registry.approve_version(URN, "3.2.1")["status"] == "approved"

    def test_opening_a_quorum_where_none_is_needed_is_refused(
            self, approvals, registry, unapproved, a_model):
        registry.set_tier(a_model["id"], 3)
        with pytest.raises(LifecycleError) as exc:
            approvals.open(URN, "3.2.1")
        assert exc.value.code == "no_quorum_required"


class TestCollectingTheQuorum:
    @pytest.fixture
    def opened(self, approvals, unapproved):
        return approvals.open(URN, "3.2.1", "ready for second line",
                              actor="person/d.raman")

    def test_one_signature_is_not_enough(self, approvals, opened, registry):
        progress = approvals.sign(opened["id"], MRM, "model_risk_manager")
        assert progress["status"] == "open"
        assert progress["outstanding_roles"] == ["validator"]
        assert "waiting on validator" in progress["detail"]
        assert registry.version(URN, "3.2.1")["status"] != "approved"

    def test_the_second_signature_approves_the_version(self, approvals, opened,
                                                       registry):
        approvals.sign(opened["id"], MRM, "model_risk_manager")
        final = approvals.sign(opened["id"], VAL, "validator")
        assert final["status"] == "approved"
        assert "approved by 2 signatures" in final["detail"]
        assert registry.version(URN, "3.2.1")["status"] == "approved"

    def test_one_decline_closes_it(self, approvals, opened, registry):
        approvals.sign(opened["id"], MRM, "model_risk_manager")
        final = approvals.sign(opened["id"], VAL, "validator", decision="decline",
                               statement="back-testing is thin")
        assert final["status"] == "declined"
        assert "returns the version to its author" in final["detail"]
        assert registry.version(URN, "3.2.1")["status"] != "approved"

    def test_one_person_may_not_wear_two_hats(self, approvals, opened):
        """A quorum is a number of people, not a number of roles."""
        both = person("s.iqbal", "model_risk_manager", "validator")
        approvals.sign(opened["id"], both, "model_risk_manager")
        with pytest.raises(LifecycleError) as exc:
            approvals.sign(opened["id"], both, "validator")
        assert exc.value.code == "already_signed_personally"

    def test_a_role_the_signer_does_not_hold_is_refused(self, approvals, opened):
        with pytest.raises(LifecycleError) as exc:
            approvals.sign(opened["id"], person("x.y", "model_developer"),
                           "validator")
        assert exc.value.code == "role_not_held"

    def test_a_role_the_approval_does_not_need_is_refused(self, approvals, opened):
        with pytest.raises(LifecycleError) as exc:
            approvals.sign(opened["id"], person("j.okafor", "model_owner"),
                           "model_owner")
        assert exc.value.code == "role_not_required"

    def test_the_same_role_cannot_sign_twice(self, approvals, opened):
        approvals.sign(opened["id"], MRM, "model_risk_manager")
        with pytest.raises(LifecycleError) as exc:
            approvals.sign(opened["id"], person("k.other", "model_risk_manager"),
                           "model_risk_manager")
        assert exc.value.code == "already_signed"

    def test_two_open_approvals_are_refused(self, approvals, opened):
        with pytest.raises(LifecycleError) as exc:
            approvals.open(URN, "3.2.1")
        assert exc.value.code == "approval_open"

    def test_withdrawing_leaves_the_version_unapproved(self, approvals, opened,
                                                       registry):
        approvals.sign(opened["id"], MRM, "model_risk_manager")
        final = approvals.withdraw(opened["id"])
        assert final["status"] == "withdrawn"
        assert registry.version(URN, "3.2.1")["status"] != "approved"

    def test_every_signature_is_witnessed(self, approvals, opened, repos):
        approvals.sign(opened["id"], MRM, "model_risk_manager")
        approvals.sign(opened["id"], VAL, "validator")
        kinds = [e["kind"] for e in repos["evidence"].many()]
        assert "version_approval_opened" in kinds
        assert kinds.count("version_approval_signed") == 2
        assert "version_approval_approved" in kinds

    def test_the_history_survives_a_declined_round(self, approvals, opened,
                                                   unapproved):
        approvals.sign(opened["id"], MRM, "model_risk_manager", decision="decline",
                       statement="no")
        again = approvals.open(URN, "3.2.1")
        approvals.sign(again["id"], MRM, "model_risk_manager")
        approvals.sign(again["id"], VAL, "validator")
        history = approvals.history(URN, "3.2.1")
        assert [h["status"] for h in history] == ["declined", "approved"]
