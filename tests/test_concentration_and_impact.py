"""What several models depend on at once, and who is downstream of a feature.

Two failure modes: an aggregate score that cannot see a shared dependency, and
an impact list that stops at the model.
"""
from __future__ import annotations

import pytest

from core.estate.concentration import (BROAD, DATASET, KINDS, METHODOLOGY,
                                       MINIMUM, UPSTREAM, VENDOR, VIEW,
                                       Concentration)
from core.features.impact import HISTORICAL, LIVE, FeatureImpact
from tests.conftest import URN


@pytest.fixture
def composition(db, registry, evidence):
    from core.registry.composition import ModelComposition
    from db import ModelEdgeRepository
    return ModelComposition(ModelEdgeRepository(db), registry.catalogue,
                            evidence)


@pytest.fixture
def concentration(registry, composition, features, parameters, a_model):
    return Concentration(registry, composition, features=features,
                         parameters=parameters)


@pytest.fixture
def siblings(registry, a_model):
    """Two more models of the SAME class — a methodological concentration."""
    for urn, tier in (("maya://model/credit.pd.midmarket", 2),
                      ("maya://model/credit.pd.corporate", 4)):
        registry.register(urn, urn.rsplit(".", 1)[-1], "credit.pd.scorecard",
                          "credit", "person/j.okafor", "LE-US-01", "12m PD")
        registry.set_tier(registry.get(urn)["id"], tier)
    return registry


class TestSharedThingsAreFoundAndNotScored:
    def test_a_shared_methodology_is_found(self, concentration, siblings):
        out = concentration.across_the_estate()
        methods = [r for r in out["shared"] if r["kind"] == METHODOLOGY]
        assert methods and methods[0]["what"] == "credit.pd.scorecard"
        assert len(methods[0]["relied_on_by"]) == 3

    def test_there_is_no_aggregate_score_and_it_says_why(self, concentration,
                                                         siblings):
        out = concentration.across_the_estate()
        assert out["aggregate_score"] is None
        assert "identical component ratings" in out["detail"]

    def test_the_worst_tier_is_the_read_not_the_count(self, concentration,
                                                      siblings):
        """Twelve tier 4 models on one view is a different sentence from one
        tier 1 model on it."""
        out = concentration.across_the_estate()
        methods = next(r for r in out["shared"]
                       if r["kind"] == METHODOLOGY)
        assert methods["worst_tier"] == 1
        assert "a concentration is not a count" in out["detail"]

    def test_one_dependent_is_not_shared(self, concentration, registry,
                                         a_model):
        """A dependency with one dependent is not shared — it is a dependency."""
        out = concentration.across_the_estate()
        assert all(len(r["relied_on_by"]) >= MINIMUM for r in out["shared"])

    def test_an_upstream_edge_is_a_concentration(self, concentration,
                                                 composition, registry,
                                                 siblings):
        registry.register("maya://model/market.curve.gbp", "Curve",
                          "market.curve", "markets", "person/j.okafor",
                          "LE-US-01", "discount curve")
        for downstream in ("maya://model/credit.pd.midmarket",
                           "maya://model/credit.pd.corporate"):
            composition.relate("maya://model/market.curve.gbp", downstream,
                               "input_to", actor="person/j.okafor")
        out = concentration.across_the_estate()
        assert any(r["kind"] == UPSTREAM for r in out["shared"])

    def test_every_kind_explains_what_is_shared(self):
        assert set(KINDS) == {UPSTREAM, VIEW, DATASET, VENDOR, METHODOLOGY}
        assert all(v.strip() for v in KINDS.values())

    def test_a_broad_share_is_named(self, concentration, siblings):
        out = concentration.across_the_estate()
        assert out["broad"] and BROAD > 0

    def test_an_empty_estate_says_what_that_means(self, registry, composition,
                                                  a_model):
        out = Concentration(registry, composition).across_the_estate()
        assert "a dependency nobody entered" in out["detail"]


class TestASinglePointIsNamedNotAsserted:
    def test_resilience_is_explicitly_not_known(self, concentration, siblings):
        out = concentration.single_points_of_failure()
        assert out["resilience_is_known"] is False

    def test_it_says_which_half_of_the_judgement_it_holds(self, concentration,
                                                          siblings):
        out = concentration.single_points_of_failure()
        assert "resilience" in out["detail"]

    def test_a_tier_one_dependency_is_a_candidate(self, concentration,
                                                  composition, registry,
                                                  siblings):
        registry.register("maya://model/market.curve.gbp", "Curve",
                          "market.curve", "markets", "person/j.okafor",
                          "LE-US-01", "discount curve")
        composition.relate("maya://model/market.curve.gbp", URN, "input_to",
                           actor="person/j.okafor")
        composition.relate("maya://model/market.curve.gbp",
                           "maya://model/credit.pd.midmarket", "input_to",
                           actor="person/j.okafor")
        out = concentration.single_points_of_failure()
        assert out["count"] >= 1


class TestOneModelsShare:
    def test_it_reads_inward(self, concentration, siblings):
        out = concentration.of_model(URN)
        assert out["count"] >= 1
        assert "in the other" in out["detail"]

    def test_a_model_sharing_nothing_says_so(self, registry, composition,
                                             a_model):
        out = Concentration(registry, composition).of_model(URN)
        assert out["count"] == 0
        assert "Read it against what is entered" in out["detail"]


# --------------------------------------------------------------- impact
@pytest.fixture
def impact(features, registry, parameters, warrants, a_model):
    return FeatureImpact(features, registry, parameters=parameters,
                         warrants=warrants)


class TestTheWalkReachesTheUse:
    def test_a_feature_nobody_bound_says_what_that_means(self, impact,
                                                         features, sb_view):
        out = impact.of_feature("dscr")
        assert out["model_count"] == 0
        assert "the binding is what makes the chain traceable" in out["detail"]

    def test_it_never_claims_to_reach_decisions(self, impact, sb_view):
        out = impact.of_feature("dscr")
        assert out["reaches_decisions"] is False

    def test_the_estate_view_says_what_an_empty_answer_means(self, impact,
                                                             sb_view):
        out = impact.across_the_estate()
        assert "an unbound feature is one this walk cannot follow" in \
            out["detail"]

    def test_live_and_historical_grants_are_apart(self):
        """A version referring to a feature is a migration; a live grant is an
        outage."""
        assert LIVE != HISTORICAL


class TestRestatementIsTheSameWalkFromTheOtherEnd:
    def test_a_view_that_has_not_moved_still_answers(self, impact, features,
                                                     sb_view):
        out = impact.of_restatement("sb_financials", 1)
        assert out["restated"] is False
        assert "before the correction rather than after" in out["detail"]

    def test_it_carries_the_movement_detection(self, impact, sb_view):
        out = impact.of_restatement("sb_financials", 1)
        assert "movement" in out and "pinned_version" in out
