"""What a validation must cover for this model, and when the next one is due.

An episode declared its scope and its plan as free text, so every episode was
scoped by whoever opened it — and the thing a scope most needs to be is the same
for two models of the same kind, or "validated" means something different in
each report and nobody can compare them.
"""
from __future__ import annotations

import time

import pytest

from core.fibres import FibreRegistry
from core.validation.common import ValidationError
from core.validation.plans import AREAS, DAY, DEPTH, ELAPSED_DAYS, ValidationPlans


class _Registry:
    def __init__(self, tier=2, trainability="T2"):
        self.model = {"id": "m-1", "urn": "maya://model/x", "tier": tier,
                      "owner": "person/o"}
        self._version = {"semver": "1.0.0", "trainability_class": trainability}
        self.version_service = self

    def require(self, urn, semver=None):
        return self._version if semver else self.model


class _Monitoring:
    def __init__(self, breaching=0):
        self._breaching = breaching

    def status(self, model_id):
        return {"breaching": self._breaching}


class _Validation:
    def __init__(self, completed_at=None):
        self._at = completed_at

    def for_model(self, urn):
        return [{"completed_at": self._at}] if self._at else []


def _plans(tier=2, trainability="T2", breaching=0, last=None):
    return ValidationPlans(_Registry(tier, trainability), FibreRegistry(),
                           validation=_Validation(last),
                           monitoring=_Monitoring(breaching))


class TestTheScopeIsDerivedNotWritten:
    def test_it_covers_the_three_areas_sr_26_2_asks_for(self):
        out = _plans().propose("maya://model/x", "1.0.0")
        assert {a["area"] for a in out["areas"]} == set(AREAS)

    def test_each_area_carries_what_this_class_actually_owes(self):
        """Asking a T0 pricer for out-of-sample discrimination is not rigour.
        It is a category error that teaches everybody the checklist is noise."""
        t0 = _plans(trainability="T0").propose("maya://model/x", "1.0.0")
        t3 = _plans(trainability="T3").propose("maya://model/x", "1.0.0")
        t0_outcomes = next(a for a in t0["areas"]
                           if a["area"] == "outcomes_analysis")
        t3_outcomes = next(a for a in t3["areas"]
                           if a["area"] == "outcomes_analysis")
        assert t0_outcomes["what_this_class_owes"] != \
            t3_outcomes["what_this_class_owes"]
        assert "benchmark" in t3["areas"][0]["what_this_class_owes"], \
            "T3 owes a benchmark against a simpler incumbent"

    def test_each_area_says_which_class_it_came_from(self):
        out = _plans(trainability="T8").propose("maya://model/x", "1.0.0")
        assert all("T8" in a["because"] for a in out["areas"])


class TestTheTierSaysHowDeeply:
    """Two models of one class at different tiers owe the same QUESTIONS and a
    different amount of independence in answering them."""

    @pytest.mark.parametrize("tier,depth", sorted(DEPTH.items()))
    def test_each_tier_has_its_depth_and_a_meaning(self, tier, depth):
        out = _plans(tier=tier).propose("maya://model/x", "1.0.0")
        assert out["depth"] == depth and out["depth_means"]

    def test_the_lightest_depth_is_honest_about_being_the_lightest(self):
        out = _plans(tier=4).propose("maya://model/x", "1.0.0")
        assert "lightest thing that is still a control" in out["depth_means"]

    def test_an_untiered_model_is_refused_rather_than_defaulted(self):
        with pytest.raises(ValidationError) as exc:
            _plans(tier=None).propose("maya://model/x", "1.0.0")
        assert "how deeply it must be validated is undecided" in str(exc.value)


class TestANarrowedScopeIsVisible:
    """A targeted revalidation is a real thing. This is not a refusal — but the
    omission has to be visible."""

    def test_a_complete_scope_is_complete(self):
        out = _plans().check("maya://model/x", "1.0.0", list(AREAS))
        assert out["complete"] is True and out["not_covered"] == []

    def test_a_narrowed_scope_names_what_it_leaves_out(self):
        out = _plans().check("maya://model/x", "1.0.0",
                             ["conceptual_soundness"])
        assert out["complete"] is False
        assert "outcomes_analysis" in out["not_covered"]
        assert "something different in every report" in out["detail"]


class TestNoFixedCadence:
    """SR 26-2 removed the fixed annual rule, and the usual response is to keep
    it anyway because a date is the only thing anybody knows how to
    administer."""

    def test_a_tier_four_model_has_no_elapsed_trigger_at_all(self):
        out = _plans(tier=4, last=time.time() - 4000 * DAY).due("maya://model/x")
        elapsed = next(t for t in out["triggers"] if t["trigger"] == "elapsed")
        assert elapsed["fired"] is False
        assert "rather than quietly discarded" in elapsed["why"]
        assert out["due"] is False, "four thousand days and still not due"

    def test_the_absence_is_a_decision_and_says_so(self):
        out = _plans(tier=4, last=time.time()).due("maya://model/x")
        assert "a decision rather than an omission" in out["detail"]

    def test_a_tier_one_model_is_due_after_its_window(self):
        window = ELAPSED_DAYS[1]
        out = _plans(tier=1, last=time.time() - (window + 1) * DAY).due(
            "maya://model/x")
        assert out["due"] is True

    def test_a_model_never_validated_is_due(self):
        out = _plans(tier=2, last=None).due("maya://model/x")
        elapsed = next(t for t in out["triggers"] if t["trigger"] == "elapsed")
        assert elapsed["fired"] and "never been validated" in elapsed["why"]


class TestTriggersRatherThanACalendar:
    def test_a_breaching_monitor_is_a_better_reason_than_a_date(self):
        out = _plans(tier=4, breaching=2, last=time.time()).due(
            "maya://model/x")
        breach = next(t for t in out["triggers"] if t["trigger"] == "monitoring")
        assert breach["fired"] is True
        assert out["due"] is True, "even a tier 4 model with no cadence"
        assert "better reason to revalidate than a date" in breach["why"]

    def test_a_quiet_model_inside_its_window_is_not_due(self):
        out = _plans(tier=2, last=time.time()).due("maya://model/x")
        assert out["due"] is False
