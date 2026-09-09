"""
MAYA — risk tiering tests, including laws L-4 (monotonicity) and L-5 (adjunction).
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
import itertools

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.risk import COMPLEXITY, MATERIALITY, TieringEngine


class TestExposureBands:
    @pytest.mark.parametrize("exposure,band", [
        (0, "negligible"), (999_999, "negligible"), (1_000_000, "low"),
        (49_999_999, "low"), (50_000_000, "moderate"), (500_000_000, "material"),
        (5_000_000_000, "critical"), (1e12, "critical")])
    def test_bands(self, tiering, exposure, band):
        assert tiering.exposure_band(exposure) == band


class TestMateriality:
    def test_purpose_can_raise_materiality_above_exposure(self, tiering):
        """A small regulatory-capital model is material despite tiny exposure."""
        assert tiering.materiality(0, "regulatory_capital") == "material"

    def test_exposure_can_raise_materiality_above_purpose(self, tiering):
        assert tiering.materiality(1e10, "commercial") == "critical"

    def test_join_takes_the_more_severe_reading(self, tiering):
        assert tiering.materiality(6e7, "commercial") == "moderate"

    def test_an_unknown_purpose_is_refused_not_read_as_the_lowest_rank(self, tiering):
        """This test used to assert the opposite, and the opposite was wrong.

        Defaulting an unrecognised class to rank 1 does not merely fail to
        constrain: it actively lowers the tier, and does it while printing the
        unrecognised string into the rationale as though it had been read.
        """
        from core.risk.tiering import RiskError
        with pytest.raises(RiskError) as caught:
            tiering.materiality(0, "not_a_purpose")
        assert caught.value.code == "unknown_purpose_class"


class TestComplexity:
    def test_analytic_model_is_simple(self, tiering):
        assert tiering.complexity("T0") == "simple"

    def test_learned_model_is_at_least_moderate(self, tiering):
        assert tiering.complexity("T3") == "moderate"

    def test_generative_scores_higher_than_learned(self, tiering):
        assert (COMPLEXITY.index(tiering.complexity("T5"))
                > COMPLEXITY.index(tiering.complexity("T2")))

    def test_alternative_data_raises_complexity(self, tiering):
        assert (COMPLEXITY.index(tiering.complexity("T3", uses_alternative_data=True))
                > COMPLEXITY.index(tiering.complexity("T3")))

    def test_lack_of_interpretability_raises_complexity(self, tiering):
        assert (COMPLEXITY.index(tiering.complexity("T3", interpretable=False))
                > COMPLEXITY.index(tiering.complexity("T3")))

    def test_many_features_raise_complexity(self, tiering):
        assert (COMPLEXITY.index(tiering.complexity("T2", feature_count=200))
                > COMPLEXITY.index(tiering.complexity("T2", feature_count=5)))

    def test_complexity_is_capped(self, tiering):
        assert tiering.complexity("T5", 500, True, False) == COMPLEXITY[-1]


class TestTauMonotonicity:
    """Law L-4. The guarantee an examiner actually asks for."""

    def test_critical_materiality_is_always_tier_one(self, tiering):
        for c in COMPLEXITY:
            assert tiering.tau("critical", c) == 1

    def test_lowest_of_both_is_tier_four(self, tiering):
        assert tiering.tau("negligible", "simple") == 4

    @pytest.mark.parametrize("m1,m2", list(itertools.combinations(MATERIALITY, 2)))
    def test_rising_materiality_never_lightens_the_tier(self, tiering, m1, m2):
        for c in COMPLEXITY:
            assert tiering.tau(m2, c) <= tiering.tau(m1, c), \
                "a more material model must never fall into a lighter regime"

    @pytest.mark.parametrize("c1,c2", list(itertools.combinations(COMPLEXITY, 2)))
    def test_rising_complexity_never_lightens_the_tier(self, tiering, c1, c2):
        for m in MATERIALITY:
            assert tiering.tau(m, c2) <= tiering.tau(m, c1)

    @settings(max_examples=300, deadline=None)
    @given(mi=st.integers(0, 4), ci=st.integers(0, 3),
           dm=st.integers(0, 4), dc=st.integers(0, 3))
    def test_monotone_under_generated_input(self, mi, ci, dm, dc):
        # tau is a pure static method; no fixture, so hypothesis is happy.
        lo = TieringEngine.tau(MATERIALITY[mi], COMPLEXITY[ci])
        hi = TieringEngine.tau(MATERIALITY[min(mi + dm, 4)], COMPLEXITY[min(ci + dc, 3)])
        assert hi <= lo

    def test_tier_is_always_in_range(self, tiering):
        for m, c in itertools.product(MATERIALITY, COMPLEXITY):
            assert tiering.tau(m, c) in (1, 2, 3, 4)


class TestControlAdjunction:
    """Law L-5: req(t) <= c  iff  t <= sup(c). One definition, both questions."""

    @pytest.mark.parametrize("tier", [1, 2, 3, 4])
    def test_required_controls_support_their_own_tier(self, tiering, tier):
        assert tiering.supports_tier(list(tiering.required_controls(tier))) <= tier

    def test_stricter_tiers_require_more(self, tiering):
        assert len(tiering.required_controls(1)) > len(tiering.required_controls(4))

    def test_insufficient_controls_cannot_defend_tier_one(self, tiering):
        assert tiering.supports_tier(["identification"]) == 4

    def test_empty_control_set_defends_nothing(self, tiering):
        assert tiering.supports_tier([]) == 4

    def test_adjunction_holds_across_all_tiers(self, tiering):
        for t in (1, 2, 3, 4):
            controls = list(tiering.required_controls(t))
            assert tiering.supports_tier(controls) <= t


class TestAssessment:
    def test_derivation_is_recorded_with_the_result(self, tiering):
        """Design rule DR-4: a derived value never travels without its derivation."""
        a = tiering.assess({"exposure": 2e9, "purpose_class": "regulatory_capital",
                            "trainability_class": "T2"})
        assert "materiality=" in a.rationale and "complexity=" in a.rationale
        assert a.ruleset_version and a.facts["exposure"] == 2e9

    def test_material_but_simple_is_tier_two_not_tier_one(self, tiering):
        """Proportionality: a large, interpretable, few-feature model warrants
        less scrutiny than a large opaque one. Controls follow risk, not size."""
        a = tiering.assess({"exposure": 2e9, "purpose_class": "regulatory_capital",
                            "trainability_class": "T2"})
        assert (a.materiality, a.complexity, a.tier) == ("material", "simple", 2)

    def test_material_and_complex_reaches_tier_one(self, tiering):
        a = tiering.assess({"exposure": 2e9, "purpose_class": "regulatory_capital",
                            "trainability_class": "T5", "interpretable": False})
        assert a.tier == 1

    def test_critical_exposure_is_tier_one_however_simple(self, tiering):
        a = tiering.assess({"exposure": 1e10, "purpose_class": "commercial",
                            "trainability_class": "T0"})
        assert (a.materiality, a.tier) == ("critical", 1)

    def test_missing_facts_default_safely(self, tiering):
        a = tiering.assess({})
        assert a.tier == 4 and a.materiality == "negligible"

    def test_none_exposure_is_treated_as_zero(self, tiering):
        assert tiering.assess({"exposure": None}).materiality == "negligible"

    def test_persist_writes_an_assessment_row(self, tiering, repos):
        a = tiering.assess({"exposure": 1e9, "purpose_class": "financial_reporting",
                            "trainability_class": "T3"})
        tiering.persist(repos["risk"], "model-1", a)
        rows = repos["risk"].many(model_id="model-1")
        assert len(rows) == 1 and rows[0]["tier"] == a.tier
        assert rows[0]["next_review_due"] > 0

    def test_higher_tier_gets_a_sooner_review(self, tiering, repos):
        tiering.persist(repos["risk"], "m1", tiering.assess({"exposure": 1e10}))
        tiering.persist(repos["risk"], "m2", tiering.assess({"exposure": 0}))
        high = repos["risk"].first("assessed_at", desc=True, model_id="m1")
        low = repos["risk"].first("assessed_at", desc=True, model_id="m2")
        assert high["tier"] < low["tier"]
        assert high["next_review_due"] < low["next_review_due"]


class TestAnUndeclaredFactThatWouldChangeTheTier:
    """`AssessIn` defaults the three complexity facts to their low-risk reading.

    The SDK sent only exposure and purpose, so every model assessed through it
    silently declared "under fifty features, no alternative data, interpretable"
    — and the stored rationale read those back as if somebody had said them.
    """

    def test_a_load_bearing_omission_is_named(self, tiering):
        facts = {"exposure": 2e9, "purpose_class": "regulatory_capital",
                 "trainability_class": "T0", "feature_count": 0,
                 "uses_alternative_data": False, "interpretable": True}
        missing = tiering.load_bearing(
            facts, declared=["exposure", "purpose_class", "trainability_class"])
        assert set(missing) == {"feature_count", "uses_alternative_data",
                                "interpretable"}
        # And it is load-bearing because the tier really does move.
        worst = {**facts, **tiering.CONSERVATIVE}
        assert tiering.assess(worst).tier != tiering.assess(facts).tier

    def test_an_omission_that_cannot_matter_is_allowed(self, tiering):
        """Materiality dominates: above the critical band the tier is 1 whatever
        the complexity facts say, so refusing there would be noise."""
        facts = {"exposure": 1e10, "purpose_class": "regulatory_capital",
                 "trainability_class": "T0", "feature_count": 0,
                 "uses_alternative_data": False, "interpretable": True}
        assert tiering.load_bearing(facts, declared=["exposure",
                                                     "purpose_class"]) == []

    def test_declaring_them_settles_it(self, tiering):
        facts = {"exposure": 2e9, "purpose_class": "regulatory_capital",
                 "trainability_class": "T0", "feature_count": 12,
                 "uses_alternative_data": False, "interpretable": True}
        assert tiering.load_bearing(
            facts, declared=list(facts)) == [], "nothing was left to assume"


class TestTheAssessRouteRefuses:
    def test_the_api_refuses_an_assessment_that_assumes_its_own_tier(
            self, client, people):
        from tests.conftest import URN
        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "12-month PD"})
        from tests.conftest import NAME
        r = client.post(f"/api/v1/models/{NAME}/assess", auth=people["j.okafor"],
                        json={"exposure": 2e9,
                              "purpose_class": "regulatory_capital"})
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "fact_not_supplied", r.text
        for fact in ("feature_count", "uses_alternative_data", "interpretable"):
            assert fact in r.json()["detail"], "name the fact"

        # Supplying the three sendable facts is no longer enough on its own:
        # the class is still unknown, because the model has no version, and it
        # still moves the tier.
        facts = {"exposure": 2e9, "purpose_class": "regulatory_capital",
                 "feature_count": 12, "uses_alternative_data": False,
                 "interpretable": True}
        still = client.post(f"/api/v1/models/{NAME}/assess",
                            auth=people["j.okafor"], json=facts)
        assert still.status_code == 422, still.text
        assert "trainability_class" in still.json()["detail"], still.text
        # And the remediation names a remedy that EXISTS. `trainability_class`
        # is not a field anybody can send, so "send trainability_class" would
        # have been a refusal pointing at nothing.
        assert "register a version" in still.json()["remediation"], still.text

        # Registering a version supplies it, and the assessment goes through.
        from tests.conftest import CONTRACT, KERNEL
        v = client.post(f"/api/v1/models/{NAME}/versions", auth=people["d.raman"],
                        json={"semver": "3.2.1", "kernel": KERNEL,
                              "contract": CONTRACT,
                              "artifact_digest": "sha256:" + "a" * 64})
        assert v.status_code in (200, 201), v.text
        ok = client.post(f"/api/v1/models/{NAME}/assess",
                         auth=people["j.okafor"], json=facts)
        assert ok.status_code == 200, ok.text

    def test_exposure_and_purpose_have_no_default_at_all(self, client, people):
        """A default of 'nothing, commercial' tiers a model at the bottom of the
        lattice on nobody's word, so those two are simply required."""
        from tests.conftest import NAME, URN
        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "12-month PD"})
        r = client.post(f"/api/v1/models/{NAME}/assess", auth=people["j.okafor"],
                        json={"feature_count": 12})
        assert r.status_code == 422, r.text


def _model_with_a_version(client, people):
    """A registered model that has a version, so its class is known.

    Tiering reads the trainability class off the latest version. Without one
    there is no class, the assessment is refused as under-specified, and these
    tests would be asserting the wrong refusal.
    """
    from tests.conftest import CONTRACT, KERNEL, NAME, URN
    client.post("/api/v1/models", auth=people["j.okafor"], json={
        "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
        "domain": "credit", "owner": "person/j.okafor",
        "legal_entity": "LE-US-01", "purpose": "12-month PD"})
    client.post(f"/api/v1/models/{NAME}/versions", auth=people["d.raman"],
                json={"semver": "3.2.1", "kernel": KERNEL, "contract": CONTRACT,
                      "artifact_digest": "sha256:" + "a" * 64})
    return NAME


class TestPurposeClassVocabulary:
    """An unrecognised purpose class used to rank as `commercial`.

    `self._purpose.get(purpose, 1)` gave any unconfigured string the lowest
    rank there is, and the recorded rationale then printed it back as though it
    had been understood. Five classes across the case studies --- including
    `credit_decision` and `clinical_decision` --- were being read that way, so
    a clinical model and a commercial one with no exposure tiered identically.
    """

    def test_an_unknown_purpose_class_is_refused_rather_than_defaulted(
            self, client, people):
        NAME = _model_with_a_version(client, people)
        r = client.post(f"/api/v1/models/{NAME}/assess", auth=people["j.okafor"],
                        json={"exposure": 0, "purpose_class": "vibes",
                              "feature_count": 12, "uses_alternative_data": False,
                              "interpretable": True})
        assert r.status_code >= 400, r.text
        body = r.json()
        assert body.get("error") == "unknown_purpose_class", body
        # The refusal has to name the vocabulary, or the caller's next guess is
        # as blind as the first.
        assert "regulatory_capital" in body.get("remediation", ""), body

    def test_a_configured_class_beyond_the_original_four_reaches_the_engine(
            self, client, people):
        """The loader named four classes in code while the configuration held
        nine, so a class added to `application.yaml` was refused as unknown ---
        the configuration and the code disagreeing, configuration losing."""
        NAME = _model_with_a_version(client, people)
        r = client.post(f"/api/v1/models/{NAME}/assess", auth=people["j.okafor"],
                        json={"exposure": 0, "purpose_class": "clinical_decision",
                              "feature_count": 12, "uses_alternative_data": False,
                              "interpretable": True})
        assert r.status_code == 200, r.text

    def test_purpose_class_moves_the_tier_at_zero_exposure(self, client, people):
        """The point of the rank: with no exposure at all, what the model is
        FOR is the only thing materiality can read."""
        NAME = _model_with_a_version(client, people)
        tiers = {}
        for purpose in ("commercial", "clinical_decision"):
            r = client.post(f"/api/v1/models/{NAME}/assess", auth=people["j.okafor"],
                            json={"exposure": 0, "purpose_class": purpose,
                                  "feature_count": 12,
                                  "uses_alternative_data": False,
                                  "interpretable": True})
            assert r.status_code == 200, r.text
            tiers[purpose] = r.json()["tier"]
        assert tiers["clinical_decision"] < tiers["commercial"], tiers
