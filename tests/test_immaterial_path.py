"""The path for a model that does not matter much, and the condition that would
mean it does.

Every framework has a proportionality clause and almost every framework then
fails to use it: four hundred immaterial models go through the same validation
the tier 1 models get, none of it is done properly because there is not enough
of anybody to do it, and the tier 1 models end up governed to the average
standard of the whole estate. Proportionality is not a discount — it is what
makes the expensive controls affordable where they are needed.
"""
from __future__ import annotations

import time


from core.risk.immaterial import (DEPENDENCY_THRESHOLD, IMMATERIAL_TIER,
                                  ImmaterialPath, STALE_DAYS, USAGE_THRESHOLD)
from core.risk.tiering import TieringEngine

DAY = 86400.0


class _Registry:
    def __init__(self, tier=IMMATERIAL_TIER, designations=None):
        self.model = {"id": "m-1", "urn": "maya://model/small", "name": "Small",
                      "owner": "person/o", "tier": tier,
                      "designations": designations or []}

    def require(self, urn):
        return self.model

    def list(self, tier=None, domain=None):
        return [self.model] if tier in (None, self.model["tier"]) else []


class _Invocations:
    def __init__(self, total):
        self._total = total

    def for_model(self, model_id):
        return {"total": self._total}


class _Composition:
    def __init__(self, count):
        self._count = count

    def blast_radius(self, urn):
        return {"count": self._count, "reaches": []}


class _Risk:
    def __init__(self, age_days):
        self._age = age_days

    def many(self, model_id=None):
        if self._age is None:
            return []
        return [{"assessed_at": time.time() - self._age * DAY}]


def _path(*, tier=IMMATERIAL_TIER, calls=0, dependents=0, age=10,
          findings=None, designations=None):
    return ImmaterialPath(
        _Registry(tier, designations),
        TieringEngine({"negligible": 0, "low": 1e6, "moderate": 5e7,
                       "material": 5e8, "critical": 5e9},
                      {"commercial": 1}, {1: 12, 2: 18, 3: 24, 4: 36}),
        invocations=_Invocations(calls), composition=_Composition(dependents),
        risk_repo=_Risk(age), findings=findings)


class TestWhatAnImmaterialModelOwesAndDoesNot:
    def test_it_owes_identification_and_condition_monitoring(self):
        out = _path().for_model("maya://model/small")
        assert out["on_the_immaterial_path"] is True
        assert set(out["owes"]) == {"identification", "condition_monitoring"}

    def test_what_it_does_not_owe_is_named_out_loud(self):
        """An unwritten exemption is one that erodes the first time somebody
        senior asks why a model has no validation report."""
        out = _path().for_model("maya://model/small")
        assert "independent_validation" in out["does_not_owe"]
        assert "committee_approval" in out["does_not_owe"]
        assert "explicitly not" in out["detail"]

    def test_a_designation_still_adds_to_what_it_owes(self):
        """Proportionality is about the tier. A tier 4 model that feeds a
        regulatory submission still owes the reconciliation."""
        out = _path(designations=["regulatory_reporting"]).for_model(
            "maya://model/small")
        assert "reconciliation_to_submission" in out["owes"]

    def test_a_higher_tier_model_is_not_on_this_path(self):
        out = _path(tier=2).for_model("maya://model/small")
        assert out["on_the_immaterial_path"] is False
        assert "does not apply" in out["detail"]

    def test_an_unassessed_model_is_not_immaterial_by_default(self):
        """An unassessed model is the top of the lattice, not the bottom."""
        out = _path(tier=None).for_model("maya://model/small")
        assert out["on_the_immaterial_path"] is False
        assert "top of the lattice" in out["detail"]


class TestTheConditions:
    """Materiality was assessed from what somebody declared, and a declaration
    goes stale quietly. These three the register can observe without being
    told."""

    def test_heavy_usage_trips_it(self):
        out = _path(calls=USAGE_THRESHOLD).for_model("maya://model/small")
        usage = next(c for c in out["conditions"] if c["condition"] == "usage")
        assert usage["tripped"] is True
        assert "declared once; this is observed continuously" in usage["why"]
        assert out["still_immaterial"] is False

    def test_becoming_a_common_dependency_trips_it(self):
        out = _path(dependents=DEPENDENCY_THRESHOLD).for_model(
            "maya://model/small")
        dep = next(c for c in out["conditions"]
                   if c["condition"] == "dependence")
        assert dep["tripped"] is True
        assert "the sum of what rests on it" in dep["why"]

    def test_a_stale_assessment_trips_it(self):
        out = _path(age=STALE_DAYS + 1).for_model("maya://model/small")
        stale = next(c for c in out["conditions"]
                     if c["condition"] == "staleness")
        assert stale["tripped"] is True

    def test_a_quiet_leaf_model_trips_nothing(self):
        out = _path().for_model("maya://model/small")
        assert out["still_immaterial"] is True
        assert "No escalation condition has tripped" in out["detail"]

    def test_a_model_with_no_assessment_is_not_reported_as_stale(self):
        """The approval gate refuses on that for a better reason than this."""
        out = _path(age=None).for_model("maya://model/small")
        stale = next(c for c in out["conditions"]
                     if c["condition"] == "staleness")
        assert stale["tripped"] is False


class TestTheSweep:
    def test_a_tripped_condition_raises_a_finding_that_does_not_re_tier(
            self, findings):
        """Materiality is a judgement, and the register's job is to make sure
        somebody makes it rather than to make it."""
        path = _path(calls=USAGE_THRESHOLD * 2, findings=findings)
        out = path.sweep()
        assert out["count"] == 1
        raised = [f for f in findings.open_for("m-1")
                  if f["category"] == "tiering"]
        assert raised
        assert "Nothing has been re-tiered" in raised[0]["description"]
        assert "so that somebody makes it" in raised[0]["description"]

    def test_a_quiet_estate_raises_nothing(self, findings):
        out = _path(findings=findings).sweep()
        assert out["count"] == 0
        assert "none has tripped" in out["detail"]

    def test_it_does_not_raise_the_same_finding_twice(self, findings):
        path = _path(calls=USAGE_THRESHOLD * 2, findings=findings)
        assert path.sweep()["count"] == 1
        assert path.sweep()["count"] == 0

    def test_the_finding_carries_the_number_and_the_threshold(self, findings):
        path = _path(dependents=5, findings=findings)
        path.sweep()
        raised = next(f for f in findings.open_for("m-1")
                      if f["category"] == "tiering")
        assert "5 against a threshold of 2" in raised["description"]
