"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

H-8: where a tiering fact came from.

`exposure` is a float on the assessment request and the tier is a monotone
function of it, so the number that decides how many signatures an approval
needs is typed in by the person the controls apply to. The finding calls that
*tier gaming through input manipulation*, and the adversarial reading is the
less common one. The ordinary case is worse: somebody registering a model does
not know the exposure, puts in a plausible figure to get past the form, and the
platform derives a tier with a rationale that reads exactly like one derived
from a measurement.

The audit half already worked. What was missing was the difference between a
claim and a measurement — and a register that cannot make that distinction
presents both with the same confidence.

Two refusals shape what this is. It **fetches nothing**, because a governance
register holding read credentials to the general ledger has to be trusted with
one more thing than it needs. And it **refuses no unsourced fact**, because a
register nobody can register into produces unregistered models, which is
strictly worse than a tiered-from-a-guess one.
"""
from __future__ import annotations

import time

import pytest

from core.risk.sourcing import (ASSERTED, AT_LEAST_A_COHORT, FRESH_FOR_DAYS,
                                SOURCEABLE, SOURCED, STALE, FactSourcing)
from core.risk.tiering import RiskError
from db import TieringFactSourceRepository

DAY = 86400.0


@pytest.fixture
def sourcing(db, registry, evidence):
    return FactSourcing(TieringFactSourceRepository(db), registry, evidence)


class TestItFetchesNothingAndRefusesNothing:
    def test_the_posture_says_both(self):
        out = FactSourcing.posture()
        assert out["fetches_anything"] is False
        assert out["refuses_an_unsourced_fact"] is False

    def test_it_says_why_it_does_not_fetch(self):
        assert "one more thing than it needs" in \
            FactSourcing.posture()["why_not_fetch"]

    def test_it_says_why_it_does_not_refuse(self):
        """A register nobody can register into produces UNREGISTERED models,
        which is strictly worse than a tiered-from-a-guess one."""
        assert "UNREGISTERED" in FactSourcing.posture()["why_not_refuse"]

    def test_the_trainability_class_is_not_sourceable(self):
        """It is derived from how the parameter object is inhabited and cannot
        be asserted at all — which is the shape the others would like to be."""
        assert "trainability_class" not in {f for f, _ in SOURCEABLE}


class TestASourceHasToBeCheckable:
    def test_a_source_with_no_reference_is_refused(self, sourcing, a_model):
        """*Finance said so* cannot be checked by whoever relies on it a year
        later, and the whole value of the record is that somebody can go and
        look."""
        with pytest.raises(RiskError) as e:
            sourcing.record(a_model["id"], "exposure", source="Finance",
                            reference="")
        assert e.value.code == "reference_required"
        assert "go and look" in e.value.remediation

    def test_an_unnamed_source_is_refused(self, sourcing, a_model):
        with pytest.raises(RiskError) as e:
            sourcing.record(a_model["id"], "exposure", source="  ",
                            reference="LEDGER-2026-Q1")
        assert e.value.code == "source_required"
        assert "recorded with more confidence" in e.value.remediation

    def test_a_fact_that_is_not_a_tiering_input_is_refused(self, sourcing,
                                                          a_model):
        with pytest.raises(RiskError) as e:
            sourcing.record(a_model["id"], "favourite_colour",
                            source="x", reference="y")
        assert e.value.code == "not_a_sourceable_fact"

    def test_recording_one_goes_on_the_chain(self, sourcing, a_model,
                                             evidence):
        sourcing.record(a_model["id"], "exposure", source="Finance GL",
                        reference="LEDGER-2026-Q1", value="2000000000",
                        actor="j.okafor")
        assert "tiering_fact_sourced" in str(
            evidence.for_subject(a_model["id"]))


class TestThreeStatesAndStaleIsNotAsserted:
    def test_an_unrecorded_fact_is_asserted(self, sourcing, a_model):
        out = sourcing.of(a_model["id"])
        assert {f["fact"]: f["state"] for f in out["facts"]}["exposure"] \
            == ASSERTED

    def test_a_recorded_fact_is_sourced(self, sourcing, a_model):
        sourcing.record(a_model["id"], "exposure", source="Finance GL",
                        reference="LEDGER-2026-Q1")
        out = sourcing.of(a_model["id"])
        assert {f["fact"]: f["state"] for f in out["facts"]}["exposure"] \
            == SOURCED

    def test_an_old_measurement_is_stale_rather_than_asserted(self, sourcing,
                                                              a_model):
        """A figure that WAS measured and has aged is a different thing from
        one nobody ever measured, and the remedy differs too: refresh the
        extract, rather than go and find out."""
        now = time.time()
        sourcing.record(a_model["id"], "exposure", source="Finance GL",
                        reference="LEDGER-2024-Q1",
                        as_at=now - (FRESH_FOR_DAYS + 30) * DAY, now=now)
        out = sourcing.of(a_model["id"], now=now)
        assert {f["fact"]: f["state"] for f in out["facts"]}["exposure"] \
            == STALE
        assert "refresh the extract" in out["detail"]

    def test_re_sourcing_keeps_the_history_and_reads_the_latest(self, sourcing,
                                                               a_model):
        """A fact re-sourced is a new row, so what was claimed when survives a
        correction."""
        now = time.time()
        sourcing.record(a_model["id"], "exposure", source="Guess",
                        reference="OLD-1", as_at=now - 10 * DAY, now=now)
        sourcing.record(a_model["id"], "exposure", source="Finance GL",
                        reference="LEDGER-2026-Q1", as_at=now, now=now)
        out = sourcing.of(a_model["id"], now=now)
        exposure = next(f for f in out["facts"] if f["fact"] == "exposure")
        assert exposure["source"] == "Finance GL"
        assert len(sourcing.repo.many(model_id=a_model["id"])) == 2

    def test_the_answer_names_exposure_specially(self, sourcing, a_model):
        """It is the one that matters: the tier is a monotone function of it,
        and the tier decides how many signatures an approval needs."""
        assert "**Exposure is one of them**" in sourcing.of(a_model["id"])[
            "detail"]


class TestTheEstateNumber:
    def test_it_counts_what_rests_on_somebody_s_word(self, sourcing, a_model):
        out = sourcing.across_the_estate()
        assert out["models"] >= 1
        assert out["by_state"][ASSERTED] > 0
        assert a_model["urn"] in out["exposure_unsourced"]

    def test_it_says_this_is_about_the_programme(self, sourcing, a_model):
        """An estate where sixty percent of exposures are asserted is a
        finding about the tiering PROGRAMME rather than about any one model."""
        assert "tiering PROGRAMME" in sourcing.across_the_estate()["detail"]

    def test_sourcing_one_moves_the_number(self, sourcing, a_model):
        before = sourcing.across_the_estate()["sourced_share"]
        sourcing.record(a_model["id"], "exposure", source="Finance GL",
                        reference="LEDGER-2026-Q1")
        assert sourcing.across_the_estate()["sourced_share"] > before


class TestTheCohortIsAQuestionNotAnAlarm:
    def test_a_small_cohort_is_refused_a_comparison(self, sourcing, a_model):
        """A cohort of four is not a distribution, and an outlier call over one
        is a number that will be argued with and should be."""
        out = sourcing.outliers(a_model["urn"])
        assert out["worth_asking"] is False
        assert out["cohort"] < AT_LEAST_A_COHORT
        assert "is not a distribution" in out["detail"]

    def test_it_never_raises_a_finding(self, registry, sourcing, a_model):
        """A control that cried wolf at every small book would be switched off,
        taking the real signal with it."""
        for index in range(AT_LEAST_A_COHORT + 1):
            registry.register(
                urn=f"maya://model/peer.{index}", name=f"peer {index}",
                model_class=a_model["model_class"], domain=a_model["domain"],
                owner="person/j.okafor", legal_entity="LE-US-01",
                purpose="a peer", actor="system")
            registry.set_exposure(f"maya://model/peer.{index}", 1e9) \
                if hasattr(registry, "set_exposure") else None
        out = sourcing.outliers(a_model["urn"])
        assert out.get("raises_a_finding", False) is False


class TestThroughTheApi:
    def test_the_posture_is_published(self, client):
        out = client.get("/api/v1/fact-sourcing").json()
        assert out["fetches_anything"] is False
        assert out["sourceable"]

    def test_a_fact_is_sourced_over_the_wire(self, client, registered, people):
        urn = "maya://model/credit.pd.smallbiz"
        made = client.post("/api/v1/fact-sourcing/model",
                           params={"urn": urn}, auth=people["j.okafor"],
                           json={"fact": "exposure", "source": "Finance GL",
                                 "reference": "LEDGER-2026-Q1",
                                 "value": "2000000000"})
        assert made.status_code == 201, made.text
        read = client.get("/api/v1/fact-sourcing/model",
                          params={"urn": urn}).json()
        states = {f["fact"]: f["state"] for f in read["facts"]}
        assert states["exposure"] == SOURCED

    def test_a_reference_less_source_is_refused_over_the_wire(
            self, client, registered, people):
        out = client.post("/api/v1/fact-sourcing/model",
                          params={"urn": "maya://model/credit.pd.smallbiz"},
                          auth=people["j.okafor"],
                          json={"fact": "exposure", "source": "Finance",
                                "reference": ""})
        assert out.status_code == 422
        assert "reference_required" in out.text

    def test_the_estate_view_answers(self, client, registered):
        out = client.get("/api/v1/fact-sourcing/estate")
        assert out.status_code == 200
        assert out.json()["models"] >= 1

    def test_the_cohort_answers_without_raising_anything(self, client,
                                                         registered):
        out = client.get("/api/v1/fact-sourcing/cohort",
                         params={"urn": "maya://model/credit.pd.smallbiz"})
        assert out.status_code == 200
        assert out.json()["worth_asking"] is False
