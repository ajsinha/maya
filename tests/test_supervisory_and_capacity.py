"""A matter a supervisor raised, and the queue behind it.

Two failure modes: a firm telling a supervisor something is done when it is not,
and a backlog nobody can size because half the answer lives in somebody's head.
"""
from __future__ import annotations

import pytest

from core.validation.capacity import (DEFAULT_EFFORT, EFFORT_BY_TIER,
                                      ValidationCapacity)
from core.validation.common import ValidationError
from core.validation.supervisory import (CLOSED, HEADROOM_DAYS, KINDS, OPEN,
                                         SupervisoryMatters)
from tests.conftest import URN

DAY = 86400.0
# A moment far enough into the epoch that a remediation window derived from
# severity lands where it would in a real deployment. Fixed, so the arithmetic
# in these tests is the platform's and not the clock's.
NOW = 1_800_000_000.0


@pytest.fixture
def supervisory(db, registry, findings, evidence):
    from db import SupervisoryMatterRepository
    return SupervisoryMatters(SupervisoryMatterRepository(db), registry,
                              findings, evidence)


@pytest.fixture
def peer(registry):
    return registry.register("urn:maya:model:peer", "Peer", "x.y", "credit",
                             "person/j.okafor", "LE-US-01", "p")


class TestAMatterIsNotAFinding:
    def test_one_matter_reaches_many_models(self, supervisory, a_model, peer,
                                            findings):
        out = supervisory.raise_matter(
            "MRA-2026-14", kind="mra", supervisor="PRA",
            title="Model documentation is incomplete",
            scope=[URN, "urn:maya:model:peer"], owner="person/s.iqbal")
        assert len(out["scope"]) == 2 and out["open_findings"] == 2
        assert len(findings.open_for(a_model["id"])) == 1
        assert len(findings.open_for(peer["id"])) == 1

    def test_the_findings_carry_the_supervisors_reference(self, supervisory,
                                                          a_model, findings):
        supervisory.raise_matter("MRA-1", kind="mra", supervisor="PRA",
                                 title="Documentation", scope=[URN],
                                 owner="person/s.iqbal")
        assert findings.open_for(a_model["id"])[0]["title"].startswith("[MRA-1]")

    def test_an_mria_blocks_and_an_mra_does_not(self, supervisory, a_model,
                                                peer, findings):
        supervisory.raise_matter("MRIA-1", kind="mria", supervisor="PRA",
                                 title="Immediate", scope=[URN],
                                 owner="person/s.iqbal")
        supervisory.raise_matter("MRA-2", kind="mra", supervisor="PRA",
                                 title="Ordinary",
                                 scope=["urn:maya:model:peer"],
                                 owner="person/s.iqbal")
        assert findings.open_for(a_model["id"])[0]["blocking"] is True
        assert findings.open_for(peer["id"])[0]["blocking"] is False

    def test_a_matter_with_no_scope_is_refused(self, supervisory, a_model):
        with pytest.raises(ValidationError) as e:
            supervisory.raise_matter("MRA-3", kind="mra", supervisor="PRA",
                                     title="t", scope=[],
                                     owner="person/s.iqbal")
        assert "nothing to remediate" in str(e.value)

    def test_the_supervisors_own_reference_is_required(self, supervisory,
                                                       a_model):
        with pytest.raises(ValidationError) as e:
            supervisory.raise_matter("  ", kind="mra", supervisor="PRA",
                                     title="t", scope=[URN],
                                     owner="person/s.iqbal")
        assert "reconcile against the letter" in str(e.value)

    def test_one_reference_cannot_be_recorded_twice(self, supervisory, a_model):
        supervisory.raise_matter("MRA-4", kind="mra", supervisor="PRA",
                                 title="t", scope=[URN], owner="person/s.iqbal")
        with pytest.raises(ValidationError) as e:
            supervisory.raise_matter("MRA-4", kind="mra", supervisor="PRA",
                                     title="t", scope=[URN],
                                     owner="person/s.iqbal")
        assert "two remediation programmes for one letter" in str(e.value)

    def test_every_kind_explains_how_hard_it_binds(self):
        assert all(v.strip() for v in KINDS.values())
        assert "mria" in KINDS and "s166" in KINDS


class TestTheTwoDates:
    def test_a_plan_landing_after_the_commitment_is_at_risk(self, supervisory,
                                                            a_model):
        """Arithmetic available months before the letter is due."""
        out = supervisory.raise_matter(
            "MRA-5", kind="mra", supervisor="PRA", title="t", scope=[URN],
            owner="person/s.iqbal", severity="Low",
            committed_at=NOW + 10.0 * DAY, now=NOW)
        assert out["at_risk"] is True
        assert "no room for the firm's own process" in out["detail"]

    def test_a_plan_with_headroom_is_not(self, supervisory, a_model):
        out = supervisory.raise_matter(
            "MRA-6", kind="mria", supervisor="PRA", title="t", scope=[URN],
            owner="person/s.iqbal", severity="Critical",
            committed_at=NOW + 400.0 * DAY, now=NOW)
        assert out["at_risk"] is False

    def test_no_committed_date_is_not_the_same_as_having_time(self,
                                                              supervisory,
                                                              a_model):
        out = supervisory.raise_matter("MRA-7", kind="mra", supervisor="PRA",
                                       title="t", scope=[URN],
                                       owner="person/s.iqbal")
        assert out["at_risk"] is False
        assert "not the same as having time" in out["detail"]

    def test_the_gap_between_the_two_is_computed(self, supervisory, a_model):
        out = supervisory.raise_matter(
            "MRA-8", kind="mra", supervisor="PRA", title="t", scope=[URN],
            owner="person/s.iqbal", committed_at=NOW + 400.0 * DAY, now=NOW)
        assert out["days_between_plan_and_commitment"] is not None

    def test_headroom_is_a_published_number(self):
        assert HEADROOM_DAYS > 0
        assert SupervisoryMatters.kinds()["headroom_days"] == HEADROOM_DAYS


class TestAMatterCannotBeClosedOverOpenWork:
    def test_closing_with_an_open_finding_is_refused(self, supervisory,
                                                     a_model):
        supervisory.raise_matter("MRA-9", kind="mra", supervisor="PRA",
                                 title="t", scope=[URN], owner="person/s.iqbal")
        with pytest.raises(ValidationError) as e:
            supervisory.close("MRA-9", "all done")
        assert "failure of bookkeeping rather than of intent" in str(e.value)

    def test_closing_after_the_findings_close_works(self, supervisory, findings,
                                                    a_model):
        supervisory.raise_matter("MRA-10", kind="mra", supervisor="PRA",
                                 title="t", scope=[URN],
                                 owner="person/s.iqbal")
        for finding in findings.open_for(a_model["id"]):
            findings.close(finding["id"], "person/a.mehta",
                           {"note": "remediated"})
        out = supervisory.close("MRA-10", "documentation rewritten and filed")
        assert out["status"] == CLOSED

    def test_closing_needs_the_sentence_that_goes_to_the_supervisor(
            self, supervisory, findings, a_model):
        supervisory.raise_matter("MRA-11", kind="mra", supervisor="PRA",
                                 title="t", scope=[URN],
                                 owner="person/s.iqbal")
        for finding in findings.open_for(a_model["id"]):
            findings.close(finding["id"], "person/a.mehta", {"note": "done"})
        with pytest.raises(ValidationError) as e:
            supervisory.close("MRA-11", "  ")
        assert "goes back to the supervisor" in str(e.value)

    def test_closing_every_finding_does_not_close_the_matter(self, supervisory,
                                                             findings, a_model):
        """Closing the matter is a separate act, which is the point."""
        supervisory.raise_matter("MRA-12", kind="mra", supervisor="PRA",
                                 title="t", scope=[URN],
                                 owner="person/s.iqbal")
        for finding in findings.open_for(a_model["id"]):
            findings.close(finding["id"], "person/a.mehta", {"note": "done"})
        out = supervisory.status("MRA-12")
        assert out["status"] == OPEN and out["open_findings"] == 0
        assert "closing it is a separate act" in out["detail"]

    def test_whether_the_commitment_was_met_reaches_the_chain(
            self, supervisory, findings, evidence, a_model):
        supervisory.raise_matter("MRA-13", kind="mra", supervisor="PRA",
                                 title="t", scope=[URN],
                                 owner="person/s.iqbal", committed_at=1.0)
        for finding in findings.open_for(a_model["id"]):
            findings.close(finding["id"], "person/a.mehta", {"note": "done"})
        supervisory.close("MRA-13", "done")
        node = next(n for n in evidence.for_subject(
            supervisory.require("MRA-13")["id"])
            if n["kind"] == "supervisory_matter_closed")
        assert node["payload"]["met_commitment"] is False


class TestTheEstateView:
    def test_at_risk_matters_sort_first(self, supervisory, a_model, peer):
        supervisory.raise_matter("MRA-14", kind="mra", supervisor="PRA",
                                 title="fine", scope=[URN],
                                 owner="person/s.iqbal",
                                 committed_at=NOW + 400.0 * DAY, now=NOW)
        supervisory.raise_matter("MRA-15", kind="mra", supervisor="PRA",
                                 title="late",
                                 scope=["urn:maya:model:peer"],
                                 owner="person/s.iqbal", severity="Low",
                                 committed_at=NOW + 5.0 * DAY, now=NOW)
        out = supervisory.across_the_estate(now=NOW)
        assert out["matters"][0]["reference"] == "MRA-15"

    def test_an_absent_commitment_is_named(self, supervisory, a_model):
        supervisory.raise_matter("MRA-16", kind="mra", supervisor="PRA",
                                 title="t", scope=[URN],
                                 owner="person/s.iqbal")
        out = supervisory.across_the_estate()
        assert out["no_committed_date"] == ["MRA-16"]
        assert "exactly like a distant one" in out["detail"]

    def test_an_empty_register_says_what_that_means(self, supervisory):
        assert "about what has been entered" in \
            supervisory.across_the_estate()["detail"]


# ------------------------------------------------------------------ capacity
@pytest.fixture
def capacity(db, registry, validation, validation_plans, evidence):
    from db import ValidatorCapacityRepository
    return ValidationCapacity(ValidatorCapacityRepository(db), registry,
                              validation, plans=validation_plans,
                              evidence=evidence)


@pytest.fixture
def validation_plans(registry, validation, monitoring):
    from core.fibres import FibreRegistry
    from core.validation.plans import ValidationPlans
    return ValidationPlans(registry, FibreRegistry(), validation=validation,
                           monitoring=monitoring)


class TestCapacityIsDeclaredAndWorkloadIsDerived:
    def test_a_capacity_is_recorded(self, capacity):
        out = capacity.declare("person/a.mehta", 6.0, actor="person/s.iqbal")
        assert out["episodes_per_quarter"] == 6.0

    def test_a_zero_capacity_is_refused(self, capacity):
        with pytest.raises(ValidationError) as e:
            capacity.declare("person/a.mehta", 0.0)
        assert "divides into an infinite forecast" in str(e.value)

    def test_redeclaring_replaces_rather_than_duplicates(self, capacity):
        capacity.declare("person/a.mehta", 6.0)
        capacity.declare("person/a.mehta", 8.0)
        assert len(capacity.declared()) == 1
        assert capacity.declared()[0]["episodes_per_quarter"] == 8.0

    def test_a_validator_with_no_declared_capacity_is_named(self, capacity,
                                                            registry, a_model,
                                                            validation,
                                                            approved_version):
        validation.open(URN, "3.2.1", validators=["person/a.mehta"])
        out = capacity.by_validator()
        assert "person/a.mehta" in out["capacity_not_declared"]
        assert "exactly like a generous one" in out["detail"]

    def test_an_overloaded_validator_is_an_independence_problem(
            self, capacity, registry, a_model, validation, approved_version):
        capacity.declare("person/a.mehta", 1.0)
        validation.open(URN, "3.2.1", validators=["person/a.mehta"])
        out = capacity.by_validator()
        assert out["overloaded"] == ["person/a.mehta"]
        assert "independence failures that begin here" in out["detail"]

    def test_effort_is_weighted_by_tier_from_a_published_table(self):
        assert EFFORT_BY_TIER[1] > EFFORT_BY_TIER[4]
        assert DEFAULT_EFFORT > 0


class TestTheForecastStatesItsAssumption:
    def test_the_assumption_travels_with_the_number(self, capacity, a_model):
        out = capacity.forecast()
        assert "it is false in the ordinary case" in out["assumes"]

    def test_no_declared_capacity_is_not_a_forecast_of_zero_work(self, capacity,
                                                                 a_model):
        out = capacity.forecast()
        assert out["capacity_per_quarter"] == 0.0
        assert "the absence of the half of the answer MAYA cannot derive" in \
            out["detail"]

    def test_a_shortfall_is_computed(self, capacity, registry, a_model):
        capacity.declare("person/a.mehta", 0.1)
        out = capacity.forecast()
        assert out["shortfall"] >= 0.0

    def test_the_queue_is_sorted_by_risk_not_by_date(self, capacity, registry,
                                                     a_model):
        registry.register("urn:maya:model:low", "Low", "x.y", "credit",
                          "person/j.okafor", "LE-US-01", "p")
        registry.set_tier(registry.get("urn:maya:model:low")["id"], 4)
        out = capacity.due_within()
        tiers = [r["tier"] for r in out["models"]]
        assert tiers == sorted(tiers)

    def test_an_inverted_queue_is_named(self, capacity, registry, a_model):
        registry.register("urn:maya:model:low", "Low", "x.y", "credit",
                          "person/j.okafor", "LE-US-01", "p")
        registry.set_tier(registry.get("urn:maya:model:low")["id"], 4)
        out = capacity.due_within()
        assert "inverted" in out
        if out["inverted"]["inverted"]:
            assert "invisible in a list sorted by due date" in out["detail"]

    def test_an_empty_queue_says_what_that_means(self, capacity):
        assert "never appears here" in capacity.due_within()["detail"]
