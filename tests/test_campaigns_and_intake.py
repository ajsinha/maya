"""Rounds of asking, and what arrives before a model.

Two failure modes: a completion figure that improves on its own, and a register
that becomes an inventory of ideas.
"""
from __future__ import annotations

import pytest

from core.lifecycle.campaigns import (ANSWERED, CLOSED, DECLINED,
                                      NOT_APPLICABLE, Campaigns)
from core.lifecycle.intake import (BUY, PROPOSED, QUESTIONS, REGISTERED,
                                   SOURCING, Intake)
from core.lifecycle.intake import DECLINED as INTAKE_DECLINED
from core.lifecycle.common import LifecycleError
from core.reporting.semantics import SemanticLayer
from tests.conftest import URN

DAY = 86400.0


@pytest.fixture
def semantics(db, registry, findings, monitoring):
    return SemanticLayer(db, registry, findings=findings, monitoring=monitoring)


@pytest.fixture
def campaigns(db, registry, semantics, evidence):
    from db import CampaignItemRepository, CampaignRepository
    return Campaigns(CampaignRepository(db), CampaignItemRepository(db),
                     registry, semantics, evidence)


@pytest.fixture
def intake(db, registry, evidence):
    from db import IntakeProposalRepository
    return Intake(IntakeProposalRepository(db), registry, evidence)


@pytest.fixture
def two_models(registry, a_model):
    registry.register("urn:maya:model:peer", "Peer", "x.y", "markets",
                      "person/a.other", "LE-UK-01", "p")
    return registry


class TestThePopulationIsFrozen:
    def test_a_round_covers_what_the_derivation_selected(self, campaigns,
                                                         two_models):
        out = campaigns.open("Q1-2026", kind="attestation",
                             title="Annual attestation")
        assert out["population"] == 2 and out["completion"] == 0.0

    def test_a_model_added_after_launch_is_drift_and_not_folded_in(
            self, campaigns, registry, two_models):
        campaigns.open("Q1", kind="attestation", title="t")
        registry.register("urn:maya:model:new", "New", "x.y", "credit",
                          "person/j.okafor", "LE-US-01", "p")
        out = campaigns.status("Q1")
        assert out["population"] == 2 and out["drift"] == ["urn:maya:model:new"]
        assert "improves on its own" in out["detail"]

    def test_completion_cannot_rise_because_a_model_left(self, campaigns,
                                                         registry, two_models):
        """47 of 50 becoming 47 of 49 is the number this design exists to stop."""
        campaigns.open("Q2", kind="attestation", title="t")
        before = campaigns.status("Q2")["completion"]
        registry.catalogue.set_status(
            registry.get("urn:maya:model:peer")["id"], "retired")
        after = campaigns.status("Q2")
        assert after["completion"] == before
        assert after["population"] == 2

    def test_the_derivation_is_kept(self, campaigns, two_models):
        out = campaigns.open("Q3", kind="attestation", title="t",
                             where=[{"field": "domain", "operator": "eq",
                                     "value": "credit"}])
        assert out["derivation"]["where"][0]["value"] == "credit"
        assert out["population"] == 1

    def test_an_empty_population_is_refused(self, campaigns, two_models):
        with pytest.raises(LifecycleError) as e:
            campaigns.open("Q4", kind="attestation", title="t",
                           where=[{"field": "domain", "operator": "eq",
                                   "value": "nowhere"}])
        assert e.value.code == "empty_population"
        assert "reports 100% complete on the day it opens" in \
            e.value.remediation

    def test_an_unknown_kind_is_refused(self, campaigns, two_models):
        with pytest.raises(LifecycleError) as e:
            campaigns.open("Q5", kind="vibes", title="t")
        assert e.value.code == "unknown_campaign_kind"

    def test_two_rounds_cannot_share_a_reference(self, campaigns, two_models):
        campaigns.open("Q6", kind="attestation", title="t")
        with pytest.raises(LifecycleError) as e:
            campaigns.open("Q6", kind="attestation", title="t")
        assert e.value.code == "campaign_already_open"


class TestAssignmentIsDerived:
    def test_items_go_to_the_models_own_owner(self, campaigns, two_models):
        out = campaigns.open("Q7", kind="owner_confirmation", title="t")
        owners = {i["urn"]: i["assignee"] for i in out["items"]}
        assert owners[URN] == "person/j.okafor"
        assert owners["urn:maya:model:peer"] == "person/a.other"

    def test_reassignment_is_an_act_with_a_reason(self, campaigns, two_models,
                                                  evidence):
        campaigns.open("Q8", kind="attestation", title="t")
        campaigns.reassign("Q8", URN, "person/s.iqbal", "owner on leave",
                           actor="person/j.okafor")
        kinds = {n["kind"] for n in evidence.for_subject(
            campaigns.registry.get(URN)["id"])}
        assert "campaign_item_reassigned" in kinds

    def test_reassignment_without_a_reason_is_refused(self, campaigns,
                                                      two_models):
        campaigns.open("Q9", kind="attestation", title="t")
        with pytest.raises(LifecycleError) as e:
            campaigns.reassign("Q9", URN, "person/s.iqbal", "  ")
        assert e.value.code == "reason_required"


class TestAnswering:
    def test_answering_moves_completion(self, campaigns, two_models):
        campaigns.open("Q10", kind="attestation", title="t")
        out = campaigns.respond("Q10", URN, state=ANSWERED,
                                actor="person/j.okafor")
        assert out["completion"] == 0.5

    def test_declining_needs_a_reason(self, campaigns, two_models):
        campaigns.open("Q11", kind="attestation", title="t")
        with pytest.raises(LifecycleError) as e:
            campaigns.respond("Q11", URN, state=DECLINED)
        assert e.value.code == "reason_required"

    def test_not_applicable_is_an_answer(self, campaigns, two_models):
        campaigns.open("Q12", kind="use_confirmation", title="t")
        out = campaigns.respond("Q12", URN, state=NOT_APPLICABLE,
                                response="retired last quarter")
        assert out["by_state"][NOT_APPLICABLE] == 1

    def test_a_model_outside_the_frozen_population_cannot_answer(
            self, campaigns, registry, two_models):
        campaigns.open("Q13", kind="attestation", title="t",
                       where=[{"field": "domain", "operator": "eq",
                               "value": "credit"}])
        with pytest.raises(LifecycleError) as e:
            campaigns.respond("Q13", "urn:maya:model:peer", state=ANSWERED)
        assert e.value.code == "not_in_this_campaign"
        assert "would move the denominator" in e.value.remediation

    def test_a_closed_round_takes_no_more_answers(self, campaigns, two_models):
        campaigns.open("Q14", kind="attestation", title="t")
        campaigns.close("Q14")
        with pytest.raises(LifecycleError) as e:
            campaigns.respond("Q14", URN, state=ANSWERED)
        assert e.value.code == "campaign_closed"


class TestClosingRecordsWhatWasNeverAnswered:
    def test_a_round_can_close_over_outstanding_items(self, campaigns,
                                                      two_models, evidence):
        campaigns.open("Q15", kind="attestation", title="t")
        campaigns.respond("Q15", URN, state=ANSWERED)
        out = campaigns.close("Q15", actor="person/s.iqbal")
        assert out["status"] == CLOSED
        node = next(n for n in evidence.for_subject(out["id"])
                    if n["kind"] == "campaign_closed")
        assert node["payload"]["never_answered"] == 1
        assert node["payload"]["completion"] == 0.5

    def test_an_all_closed_estate_says_why_that_matters(self, campaigns,
                                                        two_models):
        campaigns.open("Q16", kind="attestation", title="t")
        campaigns.close("Q16")
        assert "reports 84% and stops" in \
            campaigns.across_the_estate()["detail"]

    def test_overdue_is_computed(self, campaigns, two_models):
        campaigns.open("Q17", kind="attestation", title="t", due_at=10.0,
                       now=0.0)
        assert campaigns.status("Q17", now=100.0 * DAY)["overdue"] is True

    def test_the_estate_sorts_least_complete_first(self, campaigns, two_models):
        campaigns.open("A", kind="attestation", title="t")
        campaigns.open("B", kind="limitation_review", title="t")
        campaigns.respond("A", URN, state=ANSWERED)
        assert campaigns.across_the_estate()["campaigns"][0]["reference"] == "B"


# ------------------------------------------------------------------ intake
GENERATIVE = ("A retrieval-augmented LLM assistant that will summarise vendor "
              "documentation and draft responses for analysts.")
SCORECARD = ("A logistic regression scorecard that will estimate the "
             "probability of default and decide whether to approve an "
             "applicant.")
NOT_A_MODEL = ("A dashboard that displays the total number of open findings "
               "recorded in the register, refreshed nightly.")


class TestAProposalIsNotAModel:
    def test_it_is_recorded_apart_from_the_register(self, intake, registry):
        out = intake.propose("P-1", title="Scorecard", description=SCORECARD,
                             proposed_by="person/j.okafor")
        assert out["state"] == PROPOSED
        assert registry.get("P-1") is None
        assert "inventory of ideas" in out["detail"]

    def test_a_description_is_required(self, intake):
        with pytest.raises(LifecycleError) as e:
            intake.propose("P-2", title="Something", description="  ",
                           proposed_by="person/j.okafor")
        assert e.value.code == "description_required"

    def test_registering_before_triage_is_refused(self, intake):
        intake.propose("P-3", title="s", description=SCORECARD,
                       proposed_by="person/j.okafor")
        with pytest.raises(LifecycleError) as e:
            intake.register("P-3", urn="urn:maya:model:x", name="X",
                            model_class="credit.pd", domain="credit",
                            owner="person/j.okafor", legal_entity="LE-US-01",
                            purpose="p")
        assert e.value.code == "not_triaged"
        assert "only three questions asked before a model exists" in \
            e.value.detail


class TestTheReadingIsShownAndTheDecisionIsAPersons:
    def test_a_scorecard_reads_as_in_scope(self, intake):
        intake.propose("P-4", title="Scorecard", description=SCORECARD,
                       proposed_by="person/j.okafor")
        out = intake.assess("P-4")
        assert out["suggests_in_scope"] is True
        assert out["answers"]["reaches_a_decision"]["suggests"] is True

    def test_a_dashboard_does_not(self, intake):
        intake.propose("P-5", title="Findings dashboard",
                       description=NOT_A_MODEL, proposed_by="person/j.okafor")
        out = intake.assess("P-5")
        assert out["suggests_in_scope"] is False
        assert "nobody is ever criticised for registering something" in \
            out["detail"]

    def test_a_generative_proposal_is_read_as_generative(self, intake):
        intake.propose("P-6", title="Assistant", description=GENERATIVE,
                       proposed_by="person/j.okafor")
        assert intake.assess("P-6")["suggests_generative"] is True

    def test_a_vendor_proposal_reads_as_buy(self, intake):
        intake.propose("P-7", title="Bureau score",
                       description="A licensed third-party bureau score that "
                                   "will estimate default probability.",
                       proposed_by="person/j.okafor")
        assert intake.assess("P-7")["suggests_sourcing"] == BUY

    def test_the_words_it_turned_on_are_shown(self, intake):
        intake.propose("P-8", title="s", description=SCORECARD,
                       proposed_by="person/j.okafor")
        answers = intake.assess("P-8")["answers"]
        assert answers["quantitative_method"]["on_words"]

    def test_it_is_never_a_determination(self, intake):
        intake.propose("P-9", title="s", description=SCORECARD,
                       proposed_by="person/j.okafor")
        out = intake.assess("P-9")
        assert out["decided"] is False
        assert "not a determination" in out["detail"]

    def test_every_question_publishes_why_it_matters(self):
        assert all(q["why"].strip() and q["cues"] for q in QUESTIONS.values())


class TestTriageIsRecordedWithItsDisagreements:
    def test_a_person_may_disagree_with_the_reading(self, intake):
        intake.propose("P-10", title="Findings dashboard",
                       description=NOT_A_MODEL, proposed_by="person/j.okafor")
        out = intake.triage("P-10", in_scope=True, sourcing="build",
                            generative=False,
                            rationale="the nightly refresh applies a decay "
                                      "weighting nobody documented",
                            actor="person/s.iqbal")
        assert out["rationale"]["disagreed_with_the_reading"] is True
        assert "disagreed with the platform's reading" in out["detail"]

    def test_an_out_of_scope_determination_is_kept(self, intake):
        intake.propose("P-11", title="Dashboard", description=NOT_A_MODEL,
                       proposed_by="person/j.okafor")
        out = intake.triage("P-11", in_scope=False, sourcing="build",
                            generative=False,
                            rationale="displays stored values only")
        assert out["state"] == INTAKE_DECLINED
        assert "comes back next year as a fresh idea" in out["detail"]

    def test_a_rationale_is_required(self, intake):
        intake.propose("P-12", title="s", description=SCORECARD,
                       proposed_by="person/j.okafor")
        with pytest.raises(LifecycleError) as e:
            intake.triage("P-12", in_scope=True, sourcing="build",
                          generative=False, rationale="  ")
        assert e.value.code == "rationale_required"
        assert "re-litigated every year" in e.value.detail

    def test_an_unknown_sourcing_is_refused(self, intake):
        intake.propose("P-13", title="s", description=SCORECARD,
                       proposed_by="person/j.okafor")
        with pytest.raises(LifecycleError) as e:
            intake.triage("P-13", in_scope=True, sourcing="borrow",
                          generative=False, rationale="r")
        assert e.value.code == "unknown_sourcing"

    def test_undecided_sourcing_is_recorded_rather_than_defaulted(self):
        assert "defaulted to build" in SOURCING["undecided"]

    def test_a_declined_proposal_cannot_be_registered(self, intake):
        intake.propose("P-14", title="d", description=NOT_A_MODEL,
                       proposed_by="person/j.okafor")
        intake.triage("P-14", in_scope=False, sourcing="build",
                      generative=False, rationale="stored values only")
        with pytest.raises(LifecycleError) as e:
            intake.register("P-14", urn="urn:maya:model:x", name="X",
                            model_class="c", domain="credit",
                            owner="person/j.okafor", legal_entity="LE-US-01",
                            purpose="p")
        assert e.value.code == "proposal_declined"


class TestCrossingIntoTheRegister:
    def test_a_triaged_proposal_becomes_a_model(self, intake, registry):
        intake.propose("P-15", title="Scorecard", description=SCORECARD,
                       proposed_by="person/j.okafor")
        intake.triage("P-15", in_scope=True, sourcing="build",
                      generative=False, rationale="quantitative and decisive")
        out = intake.register("P-15", urn="urn:maya:model:new", name="New",
                              model_class="credit.pd", domain="credit",
                              owner="person/j.okafor",
                              legal_entity="LE-US-01", purpose="12m PD")
        assert out["state"] == REGISTERED
        assert registry.get("urn:maya:model:new") is not None

    def test_the_triage_travels_with_the_model(self, intake, registry,
                                               evidence):
        intake.propose("P-16", title="Bureau", description=SCORECARD,
                       proposed_by="person/j.okafor")
        intake.triage("P-16", in_scope=True, sourcing=BUY, generative=False,
                      rationale="a licensed bureau score")
        intake.register("P-16", urn="urn:maya:model:bought", name="B",
                        model_class="credit.pd", domain="credit",
                        owner="person/j.okafor", legal_entity="LE-US-01",
                        purpose="p")
        model = registry.get("urn:maya:model:bought")
        node = next(n for n in evidence.for_subject(model["id"])
                    if n["kind"] == "proposal_registered")
        assert node["payload"]["sourcing"] == BUY
        assert node["payload"]["triage_rationale"]

    def test_the_queue_names_the_oldest_untriaged(self, intake):
        intake.propose("P-17", title="s", description=SCORECARD,
                       proposed_by="person/j.okafor", now=0.0)
        out = intake.across_the_estate(now=30.0 * DAY)
        assert out["untriaged"] == 1
        assert "an intake queue nobody works" in out["detail"]

    def test_an_empty_queue_says_what_that_means(self, intake):
        assert "intake is happening somewhere else" in \
            intake.across_the_estate()["detail"]
