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

    def test_unknown_purpose_defaults_to_the_lowest_rank(self, tiering):
        assert tiering.materiality(0, "not_a_purpose") == "negligible"


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

    def test_persist_writes_an_assessment_row(self, tiering, store):
        from core.store import risk_assessment
        a = tiering.assess({"exposure": 1e9, "purpose_class": "financial_reporting",
                            "trainability_class": "T3"})
        tiering.persist(store, "model-1", a)
        rows = store.many(risk_assessment)
        assert len(rows) == 1 and rows[0]["tier"] == a.tier
        assert rows[0]["next_review_due"] > 0

    def test_higher_tier_gets_a_sooner_review(self, tiering, store):
        from core.store import risk_assessment
        tiering.persist(store, "m1", tiering.assess({"exposure": 1e10}))
        tiering.persist(store, "m2", tiering.assess({"exposure": 0}))
        rows = sorted(store.many(risk_assessment), key=lambda r: r["tier"])
        assert rows[0]["next_review_due"] < rows[-1]["next_review_due"]
