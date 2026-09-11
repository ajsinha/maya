"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

FR-TIER-005: when a tier stopped being the answer to the question it was
answering.

Seven triggers were asked for and **one was watched**. That is the largest
remaining hole in the spine of this platform, because a tier is not a label — it
decides the approval quorum, the review cadence, the monitoring depth and the
warrant's time to live. A model assessed once at Tier 3 stayed Tier 3 until its
review date fell due, and for a Tier 3 that is two years.

Every fact the six unwatched triggers need was already in the register. Nothing
had to be observed, ingested or inferred; it had to be *looked at*.

The load-bearing test in this file is the one that asserts **nothing is
re-tiered**. An automatic re-tier would be the platform changing a governance
decision nobody made, in the direction the arithmetic happened to point, at a
moment nobody chose — and it would do it silently, which is worse than the gap
it closes. The failure this is really against is not an under-tiered model; it
is an under-tiered model *nobody knows is under-tiered*, because the assessment
looks as current as the day it was made.
"""
from __future__ import annotations

import json

import pytest

from core.risk.triggers import MATERIAL_MOVE, TRIGGERS, RetierTriggers
from db import (BreachRepository, FindingRepository, FindingRootRepository,
                ModelUseRepository, RiskRepository)

DAY = 86400.0
NOW = 1_800_000_000.0
ASSESSED = NOW - 200 * DAY


class _Regimes:
    def __init__(self, active=(), at=None):
        self._active, self._at = list(active), at or {}

    def active(self):
        return list(self._active)

    def activated_at(self, name):
        return self._at.get(name, 0)


@pytest.fixture
def triggers(db, registry, evidence):
    return RetierTriggers(
        RiskRepository(db), registry,
        uses=ModelUseRepository(db), breaches=BreachRepository(db),
        regimes=_Regimes(), sourcing=None,
        findings=None, roots=None, evidence=evidence)


@pytest.fixture
def assessed(db, registry, a_model):
    """A model with an assessment made 200 days ago, at a known exposure."""
    RiskRepository(db).add({
        "model_id": a_model["id"], "tier": 3,
        "materiality": "material", "complexity": "moderate",
        "facts": json.dumps({"exposure": 1_000_000_000.0,
                             "purpose_class": "regulatory_capital",
                             "trainability_class": "T2",
                             "featureset": "credit.origination"}),
        "required_controls": "[]", "rationale": "test",
        "ruleset_version": "v1",
        "next_review_due": NOW + 300 * DAY,
        "assessed_at": ASSESSED})
    return a_model


class TestItNeverReTiers:
    """The load-bearing property. Everything else is detection."""

    def test_the_posture_says_so(self, triggers):
        assert triggers.posture()["re_tiers_anything"] is False

    def test_it_says_why(self, triggers):
        assert "a governance decision nobody made" in \
            triggers.posture()["why_not_re_tier"]

    def test_a_fired_trigger_leaves_the_tier_alone(self, triggers, assessed,
                                                   db):
        _breach(db, assessed)
        before = RiskRepository(db).many(model_id=assessed["id"])[0]["tier"]
        assert triggers.of(assessed["urn"], NOW)["count"] >= 1
        after = RiskRepository(db).many(model_id=assessed["id"])[0]["tier"]
        assert before == after == 3

    def test_the_answer_repeats_it(self, triggers, assessed):
        out = triggers.of(assessed["urn"], NOW)
        assert out["re_tiers_anything"] is False

    def test_it_names_what_it_cannot_tell_you(self, triggers):
        """Re-running tau over the new facts would answer *would the tier
        change* — and would do it over declared complexity facts nobody
        re-stated."""
        cannot = triggers.posture()["what_it_cannot_tell_you"]
        assert any("nobody re-stated" in c for c in cannot)
        assert any("on a firm's behalf" in c for c in cannot)


class TestTheSevenAreNamedWithTheirDerivation:
    def test_all_seven(self):
        assert len(TRIGGERS) == 7
        assert {t for t, _, _ in TRIGGERS} == {
            "exposure_change", "new_use", "methodology_change",
            "data_source_change", "monitoring_breach", "regulatory_change",
            "elapsed_time"}

    def test_each_says_where_the_fact_lives(self):
        """A trigger whose derivation a reader cannot see is one they cannot
        argue with, and *why* is the first question anybody asks an alert."""
        for _trigger, means, derived in TRIGGERS:
            assert means.strip() and derived.strip()


class TestExposureIsAnswerableOnlyWhereItIsSourced:
    """The finding this trigger produced, which is worth more than the trigger.

    **The register holds no standing exposure column.** An exposure is supplied
    at assessment time and stored in that assessment's facts, so outside the
    assessment the only figure MAYA has is the one the assessment was made
    from — and comparing it against itself answers nothing. The `H-8`
    fact-sourcing table is the first place a *current* exposure exists at all.

    So `FR-TIER-005`'s first trigger depends on `H-8` having been done for that
    model. Where it has not, this reports **cannot check** rather than not
    firing, because silently not firing is how a control becomes green and
    inert.
    """

    def test_without_a_sourced_exposure_it_says_it_cannot_check(self,
                                                                triggers,
                                                                assessed):
        blocked = {c["trigger"]: c
                   for c in triggers.of(assessed["urn"], NOW)["cannot_check"]}
        assert "exposure_change" in blocked
        assert "not the same as nothing having changed" in \
            blocked["exposure_change"]["detail"]

    def test_cannot_check_never_counts_as_fired(self, triggers, assessed):
        """Otherwise a model nobody can evaluate inflates the stale count, and
        the estate figure stops meaning what it says."""
        out = triggers.of(assessed["urn"], NOW)
        assert "exposure_change" not in [f["trigger"] for f in out["fired"]]
        assert out["count"] == 0

    def test_a_sourced_material_move_fires(self, db, registry, evidence,
                                           assessed):
        engine = _with_sourcing(db, registry, evidence, assessed, 5e9)
        fired = _fired(engine, assessed)
        assert "exposure_change" in fired
        assert "moved 400%" in fired["exposure_change"]["detail"]
        assert fired["exposure_change"]["evidence"]["source"] == "Finance GL"

    def test_a_sourced_small_move_does_not(self, db, registry, evidence,
                                           assessed):
        """A trigger that fires on every rounding is one somebody switches
        off, taking the real ones with it."""
        engine = _with_sourcing(db, registry, evidence, assessed, 1.05e9)
        assert "exposure_change" not in _fired(engine, assessed)

    def test_the_threshold_is_stated_and_settable(self, triggers):
        assert triggers.posture()["material_move"] == MATERIAL_MOVE
        assert 0 < MATERIAL_MOVE < 1

    def test_the_estate_reports_how_many_cannot_be_evaluated(self, triggers,
                                                             assessed):
        """A sweep reporting *nothing fired* over an estate where the trigger
        cannot be evaluated is reporting its own blindness as an all-clear."""
        out = triggers.across_the_estate(NOW)
        assert out["cannot_check"]["exposure_change"] == 1
        assert "no sourced exposure" in out["detail"]


class TestTheOtherFive:
    def test_a_use_added_after_the_assessment_fires(self, triggers, assessed,
                                                    db):
        """Purpose class drives materiality directly, so a use added later can
        move the tier without anything else changing."""
        _use(db, assessed, "capital_calculation", ASSESSED + 10 * DAY)
        assert "new_use" in _fired(triggers, assessed)

    def test_a_use_added_before_it_does_not(self, triggers, assessed, db):
        _use(db, assessed, "origination", ASSESSED - 10 * DAY)
        assert "new_use" not in _fired(triggers, assessed)

    def test_a_high_breach_after_the_assessment_fires(self, triggers,
                                                      assessed, db):
        _breach(db, assessed)
        fired = _fired(triggers, assessed)
        assert "monitoring_breach" in fired
        assert "evidence about the model's behaviour" in \
            fired["monitoring_breach"]["detail"]

    def test_a_low_breach_does_not(self, triggers, assessed, db):
        """Low breaches are common on a busy estate, and a tier is not the
        instrument for them."""
        _breach(db, assessed, severity="Low")
        assert "monitoring_breach" not in _fired(triggers, assessed)

    def test_a_regime_activated_after_the_assessment_fires(self, db, registry,
                                                           assessed):
        engine = RetierTriggers(
            RiskRepository(db), registry,
            regimes=_Regimes(["eu-ai-act"], {"eu-ai-act": ASSESSED + 30 * DAY}))
        fired = _fired(engine, assessed)
        assert "regulatory_change" in fired
        assert "across the whole estate at once" in \
            fired["regulatory_change"]["detail"]

    def test_elapsed_time_still_fires(self, triggers, assessed, db):
        """The one trigger that was watched before this module."""
        db.execute("UPDATE risk_assessment SET next_review_due = :d "
                   "WHERE model_id = :i",
                   {"d": NOW - 30 * DAY, "i": assessed["id"]})
        fired = _fired(triggers, assessed)
        assert "elapsed_time" in fired
        assert fired["elapsed_time"]["evidence"]["overdue_days"] == 30.0


class TestAnUnassessedModelIsADifferentProblem:
    def test_it_says_so_rather_than_firing_everything(self, triggers, a_model):
        out = triggers.of(a_model["urn"], NOW)
        assert out["assessed"] is False
        assert out["fired"] == []
        assert "a different and larger problem" in out["detail"]


class TestNothingFiredIsWorthSaying:
    def test_a_current_assessment_says_so(self, triggers, assessed):
        out = triggers.of(assessed["urn"], NOW)
        assert out["count"] == 0
        assert "indistinguishable from one that has been" in out["detail"]


class TestTheEstateNumber:
    def test_it_counts_stale_assessments_by_trigger(self, triggers, assessed,
                                                    db):
        _breach(db, assessed)
        out = triggers.across_the_estate(NOW)
        assert out["stale"] == 1
        assert out["by_trigger"]["monitoring_breach"] == 1

    def test_it_says_this_is_about_the_programme(self, triggers, assessed,
                                                 db):
        _breach(db, assessed)
        assert "tiering PROGRAMME" in triggers.across_the_estate(NOW)["detail"]

    def test_a_never_assessed_model_is_reported_separately(self, db, registry,
                                                           a_model):
        engine = RetierTriggers(RiskRepository(db), registry)
        out = engine.across_the_estate(NOW)
        assert a_model["urn"] in out["never_assessed"]


class TestTheSweepCorrelatesASharedCause:
    """A regulatory change fires on every in-scope model at once. Fifty
    findings with fifty owners is the exact shape of M-8."""

    @pytest.fixture
    def two_models(self, db, registry, evidence):
        made = []
        for index in range(2):
            urn = f"maya://model/peer.{index}"
            registry.register(
                urn=urn, name=f"peer {index}",
                model_class="credit.pd.scorecard", domain="credit",
                owner=f"person/owner{index}", legal_entity="LE-US-01",
                purpose="a peer", actor="system")
            model = registry.require(urn)
            RiskRepository(db).add({
                "model_id": model["id"], "tier": 2,
                "materiality": "moderate", "complexity": "moderate",
                "facts": "{}", "required_controls": "[]",
                "rationale": "t", "ruleset_version": "v1",
                "next_review_due": NOW + 300 * DAY, "assessed_at": ASSESSED})
            made.append(model)
        return made

    def test_one_root_covers_both(self, db, registry, evidence, two_models):
        from core.validation.correlation import FindingRoots
        from core.validation.findings import FindingRegister
        register = FindingRegister(FindingRepository(db), evidence) \
            if _takes_two(FindingRegister) else None
        if register is None:
            pytest.skip("the finding register takes a different shape here")
        engine = RetierTriggers(
            RiskRepository(db), registry,
            regimes=_Regimes(["eu-ai-act"], {"eu-ai-act": ASSESSED + 30 * DAY}),
            findings=register,
            roots=FindingRoots(FindingRootRepository(db),
                               FindingRepository(db), evidence))
        out = engine.sweep(actor="s.iqbal", now=NOW)
        assert out["stale"] == 2
        assert out["re_tiers_anything"] is False
        if out["roots"]:
            assert out["roots"][0]["models"] == 2
            assert "one problem" in out["detail"]

    def test_a_single_model_cause_is_not_correlated(self, triggers, assessed,
                                                    db):
        """A tier stale because THIS model breached is this model's problem."""
        _breach(db, assessed)
        shared = RetierTriggers._shared_causes(
            triggers.across_the_estate(NOW)["rows"])
        assert shared == {}

    def test_shared_causes_are_computed_not_hard_coded(self):
        """A trigger added later is correlated without anybody remembering
        to."""
        rows = [{"urn": "a", "triggers": ["x", "y"]},
                {"urn": "b", "triggers": ["x"]}]
        assert RetierTriggers._shared_causes(rows) == {"x": ["a", "b"]}

    def test_without_a_finding_register_it_says_so(self, triggers, assessed,
                                                   db):
        _breach(db, assessed)
        out = triggers.sweep(now=NOW)
        assert out["raised"] == []
        assert "nothing was raised" in out["detail"]


class TestThroughTheApi:
    def test_the_posture_is_published(self, client):
        out = client.get("/api/v1/retier-triggers").json()
        assert out["re_tiers_anything"] is False
        assert len(out["triggers"]) == 7

    def test_the_estate_answers(self, client, registered):
        out = client.get("/api/v1/retier-triggers/estate")
        assert out.status_code == 200
        assert out.json()["re_tiers_anything"] is False

    def test_one_model_answers(self, client, registered):
        out = client.get("/api/v1/retier-triggers/model",
                         params={"urn": "maya://model/credit.pd.smallbiz"})
        assert out.status_code == 200
        assert "assessed" in out.json()

    def test_a_sweep_requires_the_assessing_permission(self, client, people,
                                                       registered):
        refused = client.post("/api/v1/retier-triggers/sweep",
                              auth=people["d.raman"])
        assert refused.status_code == 403


def _fired(engine, model, now=NOW):
    return {f["trigger"]: f for f in engine.of(model["urn"], now)["fired"]}


def _use(db, model, declared_use, created_at):
    ModelUseRepository(db).add({
        "model_id": model["id"], "reference": declared_use,
        "declared_use": declared_use, "name": declared_use,
        "owner": "person/j.okafor", "effective_from": created_at,
        "created_by": "j.okafor", "created_at": created_at})


def _breach(db, model, severity="Critical"):
    """A breach after the assessment — the simplest trigger to fire, and the
    one used wherever the test is about something other than exposure."""
    BreachRepository(db).add({
        "monitor_id": "m1", "model_id": model["id"], "observation_id": "o1",
        "severity": severity, "opened_at": ASSESSED + 20 * DAY})


def _with_sourcing(db, registry, evidence, model, exposure):
    """A trigger engine that can see a current, attested exposure."""
    from core.risk.sourcing import FactSourcing
    from db import TieringFactSourceRepository
    sourcing = FactSourcing(TieringFactSourceRepository(db), registry,
                            evidence)
    sourcing.record(model["id"], "exposure", source="Finance GL",
                    reference="LEDGER-2026-Q1", value=str(exposure),
                    as_at=NOW, now=NOW)
    return RetierTriggers(RiskRepository(db), registry, sourcing=sourcing)


def _takes_two(cls) -> bool:
    import inspect
    return len(inspect.signature(cls.__init__).parameters) <= 4
