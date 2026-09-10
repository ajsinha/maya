"""Runs declared before they happen, and the standing approval for a re-fit.

Two failure modes: a register of successes, and an automation with nobody's name
on it.
"""
from __future__ import annotations

import pytest

from core.parameters.common import ParameterError
from core.parameters.retraining import (ACTIVE, EXPIRED, MAX_POLICY_DAYS,
                                        NEVER_AUTOMATIC_AT_OR_ABOVE, TRIGGERS,
                                        Retraining)
from core.parameters.runs import (ABANDONED, FAILED, LOST, LOST_AFTER, OPEN,
                                  PROFILE_FIELDS, SUCCEEDED, VERBS, Runs)
from tests.conftest import URN

DAY = 86400.0
NOW = 1_800_000_000.0
PROFILE = {"hardware": "a10g", "replicas": 1, "memory_gb": 64,
           "backend": "internal-k8s"}


@pytest.fixture
def runs(db, registry, evidence, a_model):
    from db import RunRepository
    return Runs(RunRepository(db), registry, evidence)


@pytest.fixture
def retraining(db, registry, parameters, evidence, monitoring, a_model):
    from db import RetrainPolicyRepository
    return Retraining(RetrainPolicyRepository(db), registry, parameters,
                      evidence, monitoring=monitoring)


class TestARunIsDeclaredBeforeItHappens:
    def test_opening_records_it_as_open(self, runs):
        out = runs.open("R-1", verb="fit", urn=URN, resource_profile=PROFILE,
                        actor="person/d.raman")
        assert out["state"] == OPEN
        assert "register of successes" in out["detail"]

    def test_a_run_past_its_expected_duration_is_lost(self, runs):
        """A fit that consumed a warrant, read a snapshot and vanished appears
        in no tracker that writes its row at the end."""
        runs.open("R-2", verb="fit", urn=URN, expected_seconds=600.0, now=NOW)
        out = runs.read("R-2", now=NOW + LOST_AFTER * 600.0 + 1.0)
        assert out["state"] == LOST
        assert "would have no record of it at all" in out["detail"]

    def test_lost_cannot_be_asserted_by_a_caller(self, runs):
        runs.open("R-3", verb="fit", urn=URN)
        with pytest.raises(ParameterError) as e:
            runs.close("R-3", state=LOST)
        assert e.value.code == "unknown_outcome"
        assert "close one it would rather nobody read" in e.value.remediation

    def test_a_failed_run_needs_a_note(self, runs):
        runs.open("R-4", verb="fit", urn=URN)
        with pytest.raises(ParameterError) as e:
            runs.close("R-4", state=FAILED)
        assert e.value.code == "note_required"

    def test_a_run_closes_once(self, runs):
        runs.open("R-5", verb="fit", urn=URN)
        runs.close("R-5", state=ABANDONED)
        with pytest.raises(ParameterError) as e:
            runs.close("R-5", state=SUCCEEDED)
        assert e.value.code == "run_closed"

    def test_the_verb_comes_from_the_warrant_grammar(self, runs):
        with pytest.raises(ParameterError) as e:
            runs.open("R-6", verb="retrain", urn=URN)
        assert e.value.code == "unknown_verb"
        assert set(VERBS) >= {"fit", "score", "validate"}

    def test_two_runs_cannot_share_a_reference(self, runs):
        runs.open("R-7", verb="fit", urn=URN)
        with pytest.raises(ParameterError) as e:
            runs.open("R-7", verb="fit", urn=URN)
        assert e.value.code == "run_already_open"


class TestMayaDoesNotSubmitAndDoesNotFetch:
    def test_it_says_so(self, runs):
        out = Runs.describe()
        assert out["submits_jobs"] is False and out["fetches_logs"] is False

    def test_the_log_uri_is_recorded_and_never_read(self, runs):
        out = runs.open("R-8", verb="fit", urn=URN,
                        log_uri="s3://logs/run-8.jsonl")
        assert out["log_uri"] == "s3://logs/run-8.jsonl"
        assert out["logs_fetched"] is False

    def test_there_is_no_submit_method(self):
        import inspect
        methods = {n for n, _ in inspect.getmembers(Runs, inspect.isfunction)}
        assert not (methods & {"submit", "launch", "run", "execute", "start"})

    def test_an_incomplete_resource_profile_is_named(self, runs):
        out = runs.open("R-9", verb="fit", urn=URN,
                        resource_profile={"hardware": "cpu"})
        assert set(out["missing_from_profile"]) == set(PROFILE_FIELDS) - {
            "hardware"}
        assert "cannot be costed or reproduced" in out["detail"]

    def test_an_empty_register_says_what_that_means(self, runs):
        assert "nothing has declared itself" in \
            runs.across_the_estate()["detail"]


class TestASearchIsAParentAndItsChildren:
    def test_children_attach_to_a_parent(self, runs):
        runs.open("S-1", verb="fit", urn=URN)
        for i in range(3):
            runs.open(f"S-1-{i}", verb="fit", urn=URN, parent="S-1")
        assert runs.read("S-1")["child_count"] == 3

    def test_the_count_is_the_finding(self, runs):
        runs.open("S-2", verb="fit", urn=URN)
        for i in range(5):
            runs.open(f"S-2-{i}", verb="fit", urn=URN, parent="S-2")
            runs.close(f"S-2-{i}", state=SUCCEEDED, cost=1.0)
        out = runs.search("S-2")
        assert out["tried"] == 5
        assert "multiple-comparisons problem" in out["detail"]

    def test_maya_selects_no_winner(self, runs):
        runs.open("S-3", verb="fit", urn=URN)
        runs.open("S-3-a", verb="fit", urn=URN, parent="S-3")
        assert runs.search("S-3")["selects"] is None
        assert "an act with a person's name on it" in runs.search("S-3")["detail"]

    def test_cost_is_summed_from_the_children(self, runs):
        runs.open("S-4", verb="fit", urn=URN)
        for i in range(3):
            runs.open(f"S-4-{i}", verb="fit", urn=URN, parent="S-4")
            runs.close(f"S-4-{i}", state=SUCCEEDED, cost=2.5)
        runs.close("S-4", state=SUCCEEDED, cost=1.0)
        assert runs.read("S-4")["cost_including_children"] == 8.5

    def test_grandchildren_are_refused(self, runs):
        """Nesting would make the child count depend on how somebody grouped."""
        runs.open("S-5", verb="fit", urn=URN)
        runs.open("S-5-a", verb="fit", urn=URN, parent="S-5")
        with pytest.raises(ParameterError) as e:
            runs.open("S-5-a-i", verb="fit", urn=URN, parent="S-5-a")
        assert e.value.code == "nesting_too_deep"

    def test_a_child_cannot_join_a_closed_search(self, runs):
        runs.open("S-6", verb="fit", urn=URN)
        runs.close("S-6", state=SUCCEEDED)
        with pytest.raises(ParameterError) as e:
            runs.open("S-6-a", verb="fit", urn=URN, parent="S-6")
        assert e.value.code == "parent_closed"

    def test_a_run_with_no_children_is_not_a_search(self, runs):
        runs.open("S-7", verb="fit", urn=URN)
        assert "not a search" in runs.search("S-7")["detail"]


# --------------------------------------------------------------- retraining
class TestTheCeilingCannotBeRaised:
    def test_tier_one_may_never_auto_accept(self, retraining, a_model):
        with pytest.raises(ParameterError) as e:
            retraining.declare(URN, triggers=["drift"], tolerance={"rmse": {}},
                               auto_accept=True, rationale="r")
        assert e.value.code == "tier_not_eligible"
        assert NEVER_AUTOMATIC_AT_OR_ABOVE == 1

    def test_an_untiered_model_takes_the_strictest_treatment(self, retraining,
                                                             registry):
        registry.register("urn:maya:model:untiered", "U", "x.y", "credit",
                          "person/j.okafor", "LE-US-01", "p")
        with pytest.raises(ParameterError) as e:
            retraining.declare("urn:maya:model:untiered", triggers=["drift"],
                               tolerance={"rmse": {}}, auto_accept=True,
                               rationale="r")
        assert "not a safe model" in e.value.detail

    def test_a_lower_tier_may(self, retraining, registry, a_model):
        registry.set_tier(a_model["id"], 3)
        out = retraining.declare(URN, triggers=["drift"],
                                 tolerance={"rmse": {"max": 0.1}},
                                 auto_accept=True, rationale="quarterly refit")
        assert out["policy"]["auto_accept"] is True

    def test_automatic_acceptance_needs_a_tolerance(self, retraining, registry,
                                                    a_model):
        registry.set_tier(a_model["id"], 3)
        with pytest.raises(ParameterError) as e:
            retraining.declare(URN, triggers=["drift"], tolerance={},
                               auto_accept=True, rationale="r")
        assert e.value.code == "tolerance_required"
        assert "marking its own homework" in e.value.detail

    def test_every_policy_expires_within_the_ceiling(self, retraining, registry,
                                                     a_model):
        registry.set_tier(a_model["id"], 3)
        out = retraining.declare(URN, triggers=["drift"], tolerance={},
                                 auto_accept=False, rationale="r",
                                 expires_at=NOW + 10_000 * DAY, now=NOW)
        assert out["policy"]["expires_at"] <= NOW + MAX_POLICY_DAYS * DAY

    def test_a_policy_with_no_trigger_is_refused(self, retraining, a_model):
        with pytest.raises(ParameterError) as e:
            retraining.declare(URN, triggers=[], tolerance={},
                               auto_accept=False, rationale="r")
        assert e.value.code == "trigger_required"

    def test_a_trigger_maya_cannot_compute_is_refused(self, retraining,
                                                      a_model):
        with pytest.raises(ParameterError) as e:
            retraining.declare(URN, triggers=["vibes"], tolerance={},
                               auto_accept=False, rationale="r")
        assert e.value.code == "unknown_trigger"
        assert "silently never fires" in e.value.remediation

    def test_every_trigger_explains_when_it_fires(self):
        assert all(v.strip() for v in TRIGGERS.values())


class TestTheApprovalHasAHumanName:
    def test_the_author_may_not_approve(self, retraining, registry, a_model):
        registry.set_tier(a_model["id"], 3)
        retraining.declare(URN, triggers=["drift"], tolerance={},
                           auto_accept=False, rationale="r",
                           actor="person/j.okafor")
        with pytest.raises(ParameterError) as e:
            retraining.approve(URN, actor="person/j.okafor")
        assert e.value.code == "author_may_not_approve"
        assert "larger approval than most" in e.value.detail

    def test_an_unapproved_policy_accepts_nothing(self, retraining, registry,
                                                  a_model):
        registry.set_tier(a_model["id"], 3)
        retraining.declare(URN, triggers=["drift"],
                           tolerance={"rmse": {"max": 1.0}}, auto_accept=True,
                           rationale="r", actor="person/j.okafor")
        out = retraining.may_accept(URN, {"rmse": 0.5})
        assert out["may_accept"] is False and "a draft" in out["reason"]

    def test_an_approved_policy_attributes_to_its_approver(self, retraining,
                                                           registry, a_model):
        registry.set_tier(a_model["id"], 3)
        retraining.declare(URN, triggers=["drift"],
                           tolerance={"rmse": {"max": 1.0}}, auto_accept=True,
                           rationale="r", actor="person/j.okafor")
        retraining.approve(URN, actor="person/s.iqbal")
        out = retraining.may_accept(URN, {"rmse": 0.5})
        assert out["may_accept"] is True
        assert out["attributed_to"] == "person/s.iqbal"
        assert "and never to `system`" in out["reason"]

    def test_outside_tolerance_falls_back_to_a_person(self, retraining,
                                                      registry, a_model):
        registry.set_tier(a_model["id"], 3)
        retraining.declare(URN, triggers=["drift"],
                           tolerance={"rmse": {"max": 0.1}}, auto_accept=True,
                           rationale="r", actor="person/j.okafor")
        retraining.approve(URN, actor="person/s.iqbal")
        out = retraining.may_accept(URN, {"rmse": 0.9})
        assert out["may_accept"] is False and out["outside_tolerance"]

    def test_a_diagnostic_that_was_not_reported_is_outside_tolerance(
            self, retraining, registry, a_model):
        """Treating an absent number as inside would let a fit that stopped
        reporting it pass the check it existed for."""
        registry.set_tier(a_model["id"], 3)
        retraining.declare(URN, triggers=["drift"],
                           tolerance={"rmse": {"max": 0.1}}, auto_accept=True,
                           rationale="r", actor="person/j.okafor")
        retraining.approve(URN, actor="person/s.iqbal")
        out = retraining.may_accept(URN, {})
        assert out["may_accept"] is False
        assert "was not reported" in out["outside_tolerance"][0]

    def test_an_expired_policy_decays_to_a_person(self, retraining, registry,
                                                  a_model):
        registry.set_tier(a_model["id"], 3)
        retraining.declare(URN, triggers=["drift"],
                           tolerance={"rmse": {"max": 1.0}}, auto_accept=True,
                           rationale="r", actor="person/j.okafor", now=NOW)
        retraining.approve(URN, actor="person/s.iqbal", now=NOW)
        later = NOW + (MAX_POLICY_DAYS + 1) * DAY
        assert retraining.policy(URN, now=later)["status"] == EXPIRED
        assert retraining.may_accept(URN, {"rmse": 0.5},
                                     now=later)["may_accept"] is False


class TestMayaRetrainsNothing:
    def test_it_says_so(self, retraining):
        assert Retraining.triggers()["retrains_anything"] is False
        assert retraining.across_the_estate()["retrains_anything"] is False

    def test_a_breach_makes_a_refit_due(self, retraining, monitoring,
                                        drift_monitor, a_model, scored):
        _labels, scores = scored
        monitoring.evaluate(drift_monitor["id"],
                            [{"scored_at": float(i), "score": s}
                             for i, s in enumerate(scores)],
                            reference=[0.0] * len(scores))
        out = retraining.due(URN)
        assert out["due"] is True and "monitor_breach" in out["fired"]
        assert out["starts_anything"] is False

    def test_nothing_firing_is_a_decision(self, retraining, a_model):
        out = retraining.due(URN)
        assert out["due"] is False
        assert "a decision rather than an omission" in out["detail"]

    def test_no_policy_means_every_trigger_is_evaluated(self, retraining,
                                                        a_model):
        out = retraining.due(URN)
        assert {t["trigger"] for t in out["triggers"]} == set(TRIGGERS)
        assert "watched more widely rather than less" in out["detail"]

    def test_a_policy_narrows_which_triggers_are_read(self, retraining,
                                                      registry, a_model):
        registry.set_tier(a_model["id"], 3)
        retraining.declare(URN, triggers=["window_elapsed"], tolerance={},
                           auto_accept=False, rationale="r")
        out = retraining.due(URN)
        assert {t["trigger"] for t in out["triggers"]} == {"window_elapsed"}

    def test_revoking_ends_the_delegation(self, retraining, registry, a_model):
        registry.set_tier(a_model["id"], 3)
        retraining.declare(URN, triggers=["drift"],
                           tolerance={"rmse": {"max": 1.0}}, auto_accept=True,
                           rationale="r", actor="person/j.okafor")
        retraining.approve(URN, actor="person/s.iqbal")
        retraining.revoke(URN, "model retired from the automatic programme")
        assert retraining.policy(URN)["status"] != ACTIVE
        assert retraining.may_accept(URN, {"rmse": 0.1})["may_accept"] is False
