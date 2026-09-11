"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

FR-INV-018: taking a model out of service, and the four things that go missing.

`retire` was always a governed transition that deletes nothing, requires a
reason and appends evidence. That is the hard half and it was built first, which
was right. What the requirement asks for on top is four facts, and every one is
something a firm discovers it needed **months later**: why, what does this job
now, who was relying on it, and how long do we keep it.

None of them is hard to store. **They go missing because retiring a model is the
moment everybody involved has stopped caring about it**, and a form field nobody
is required to fill in is a form field left empty. So the tests here are almost
all about the refusals, and about one number: how many already-retired models
have none of this.
"""
from __future__ import annotations

import pytest

from core.lifecycle.common import LifecycleError
from core.lifecycle.decommission import NOTHING, REQUIRED, Decommissioning
from core.retention import CLASSES
from db import DecommissionRepository

GOOD = {"rationale": "superseded by the 2026 scorecard after the annual review",
        "replacement": NOTHING, "retention_class": "model_record"}


@pytest.fixture
def decommissioning(db, registry, evidence):
    return Decommissioning(DecommissionRepository(db), registry,
                           composition=None, lifecycle=None, evidence=evidence)


class TestItNotifiesNobodyAndArchivesNothing:
    def test_the_posture_says_all_three(self):
        out = Decommissioning.posture()
        assert out["notifies_anybody"] is False
        assert out["archives_anything"] is False
        assert out["deletes_anything"] is False

    def test_it_says_why_it_does_not_notify(self):
        """A platform claiming to have notified them would be claiming a
        delivery it never made."""
        assert "a delivery it never made" in \
            Decommissioning.posture()["why_not_notify"]

    def test_it_says_why_it_does_not_archive(self):
        assert "does not move a byte" in \
            Decommissioning.posture()["why_not_archive"]

    def test_it_names_why_these_fields_go_missing(self):
        assert "stopped caring about it" in Decommissioning.posture()["detail"]


class TestTheThreeRefusals:
    def test_a_thin_rationale_is_refused(self, decommissioning, a_model):
        """Ten characters is a low bar and it is there to stop `n/a`."""
        with pytest.raises(LifecycleError) as e:
            decommissioning.decommission(a_model["urn"], **{**GOOD,
                                                            "rationale": "n/a"})
        assert e.value.code == "rationale_required"
        assert "stop `n/a`" in e.value.remediation

    def test_a_blank_replacement_is_refused(self, decommissioning, a_model):
        """Blank is indistinguishable from nobody having filled it in."""
        with pytest.raises(LifecycleError) as e:
            decommissioning.decommission(a_model["urn"], **{**GOOD,
                                                            "replacement": " "})
        assert e.value.code == "replacement_required"
        assert "indistinguishable from nobody having filled it in" in \
            e.value.remediation

    def test_an_unregistered_replacement_is_refused(self, decommissioning,
                                                    a_model):
        """*Replaced by the new scorecard* is a sentence, not a link — and the
        question it answers is asked in two years by somebody who cannot ask
        you."""
        with pytest.raises(LifecycleError) as e:
            decommissioning.decommission(
                a_model["urn"], **{**GOOD,
                                   "replacement": "the new scorecard"})
        assert e.value.code == "replacement_not_registered"
        assert "somebody who cannot ask you" in e.value.remediation

    def test_an_unknown_retention_class_is_refused_by_name(self,
                                                           decommissioning,
                                                           a_model):
        with pytest.raises(LifecycleError) as e:
            decommissioning.decommission(a_model["urn"],
                                         **{**GOOD,
                                            "retention_class": "forever"})
        assert e.value.code == "unknown_retention_class"
        assert "the obligations do" in e.value.remediation

    def test_the_classes_come_from_the_retention_schedule(self):
        assert set(Decommissioning.posture()["retention_classes"]) \
            == set(CLASSES)

    def test_nothing_is_written_when_it_refuses(self, decommissioning, db,
                                                a_model):
        """Everything is validated BEFORE the transition, so a refusal leaves
        the model in service rather than half-retired with no record of why."""
        with pytest.raises(LifecycleError):
            decommissioning.decommission(a_model["urn"],
                                         **{**GOOD, "rationale": "x"})
        assert DecommissionRepository(db).one(model_id=a_model["id"]) is None


class TestNothingTakingItsPlaceIsRecordedDeliberately:
    def test_none_is_accepted_and_said_out_loud(self, decommissioning,
                                                a_model):
        out = decommissioning.decommission(a_model["urn"], **GOOD)
        assert out["replacement"] == NOTHING
        assert "nothing taking its place" in out["detail"]

    def test_a_registered_replacement_is_linked(self, decommissioning,
                                                registry, a_model):
        registry.register("maya://model/credit.pd.v2", "SB PD v2",
                          "credit.pd.scorecard", "credit", "person/j.okafor",
                          "LE-US-01", "the successor")
        out = decommissioning.decommission(
            a_model["urn"], **{**GOOD,
                               "replacement": "maya://model/credit.pd.v2"})
        assert out["replacement"] == "maya://model/credit.pd.v2"

    def test_every_required_field_says_why_it_is_asked_for(self):
        assert len(REQUIRED) == 3
        for _field, why in REQUIRED:
            assert why.strip()


class TestConsumersAreTheRegistersOwnAnswer:
    def test_an_unwired_graph_says_unknown_rather_than_none(self,
                                                            decommissioning,
                                                            a_model):
        """Not the same as nobody depending on it."""
        out = decommissioning.consumers(a_model["urn"])
        assert out["known"] is False
        assert "not the same as nobody depending on it" in out["detail"]

    def test_an_unnotified_live_consumer_refuses_the_retirement(self, db,
                                                                registry,
                                                                evidence,
                                                                a_model):
        engine = _with_consumers(db, registry, evidence,
                                 ["maya://model/downstream.one"])
        with pytest.raises(LifecycleError) as e:
            engine.decommission(a_model["urn"], **GOOD)
        assert e.value.code == "consumers_not_notified"
        assert "reading nulls" in engine.consumers(a_model["urn"])["detail"]

    def test_notifying_them_lets_it_through(self, db, registry, evidence,
                                            a_model):
        engine = _with_consumers(db, registry, evidence,
                                 ["maya://model/downstream.one"])
        out = engine.decommission(a_model["urn"], **GOOD,
                                  notified=["maya://model/downstream.one"])
        assert out["unnotified"] == []
        assert "1 consumer(s) were told" in out["detail"]

    def test_acknowledging_is_a_different_fact_from_nobody_looking(
            self, db, registry, evidence, a_model):
        """The refusal is escapable deliberately: somebody looked at the list
        and decided, which is not the same as nobody having looked."""
        engine = _with_consumers(db, registry, evidence,
                                 ["maya://model/downstream.one"])
        out = engine.decommission(a_model["urn"], **GOOD, acknowledged=True)
        assert out["acknowledged"] is True
        assert out["unnotified"] == ["maya://model/downstream.one"]
        assert "somebody acknowledged that" in out["detail"]


class TestTheRecord:
    def test_it_goes_on_the_evidence_chain(self, decommissioning, evidence,
                                           a_model):
        decommissioning.decommission(a_model["urn"], **GOOD, actor="s.iqbal")
        blob = str(evidence.for_subject(a_model["id"]))
        assert "model_decommissioned" in blob
        assert "s.iqbal" in blob

    def test_the_retention_note_says_a_period_is_a_floor(self,
                                                         decommissioning,
                                                         a_model):
        """Confusing *may now be deleted* with *must now be deleted* is how a
        register loses the record that was about to be asked for."""
        out = decommissioning.decommission(a_model["urn"], **GOOD)
        assert "FLOOR, never a ceiling" in out["retention"]["note"]

    def test_reading_back_an_undecommissioned_model_says_so(self,
                                                            decommissioning,
                                                            a_model):
        out = decommissioning.of(a_model["urn"])
        assert out["decommissioned"] is False
        assert "in service" in out["detail"]

    def test_the_answer_says_nothing_was_archived(self, decommissioning,
                                                  a_model):
        out = decommissioning.decommission(a_model["urn"], **GOOD)
        assert "does not move bytes" in out["detail"]


class TestWhatTheAdversarialPassFound:
    """Both holes were in the promise this module makes in its own docstring:
    that validation happens before the transition, so a refusal leaves the
    model in service."""

    def test_a_second_decommissioning_is_refused_rather_than_a_five_hundred(
            self, db, registry, evidence, a_model, lifecycle):
        engine = Decommissioning(DecommissionRepository(db), registry,
                                 composition=None, lifecycle=lifecycle,
                                 evidence=evidence)
        engine.decommission(a_model["urn"], **GOOD)
        with pytest.raises(LifecycleError) as e:
            engine.decommission(a_model["urn"], **GOOD)
        assert e.value.code == "already_decommissioned"
        assert "two answers" in e.value.remediation

    def test_a_transition_that_cannot_happen_writes_nothing(
            self, db, registry, evidence, a_model, lifecycle, kernel_spec,
            contract_spec):
        """`retire` is not reachable from `submitted`. The four facts were
        validated, the record was written, and THEN the transition raised —
        leaving a decommissioning record for a model still in service, which is
        exactly what this module says cannot happen."""
        registry.create_version(a_model["urn"], "1.0.0", kernel_spec,
                                contract_spec,
                                artifact_digest="sha256:" + "f" * 64)
        registry.approve_version(a_model["urn"], "1.0.0")
        lifecycle.submit(registry.get(a_model["urn"]), "j.okafor")
        engine = Decommissioning(DecommissionRepository(db), registry,
                                 composition=None, lifecycle=lifecycle,
                                 evidence=evidence)
        with pytest.raises(LifecycleError) as e:
            engine.decommission(a_model["urn"], **GOOD)
        assert e.value.code == "illegal_transition"
        assert DecommissionRepository(db).one(model_id=a_model["id"]) is None

    def test_the_legal_states_come_from_the_machine_not_a_second_list(self):
        from core.lifecycle.states import transition
        assert set(transition("retire").sources) == {
            "attested", "approved", "draft", "baselined"}


class TestRetiredAndDecommissionedAreTwoPopulations:
    """A retirement recorded before this existed carries a reason and nothing
    else, so the gap between the two is a backlog somebody can work."""

    def test_a_model_retired_the_old_way_has_no_record(self, decommissioning,
                                                       registry, a_model, db):
        db.execute("UPDATE model SET status = 'retired' WHERE id = :i",
                   {"i": a_model["id"]})
        out = decommissioning.across_the_estate()
        assert out["retired"] == 1 and out["decommissioned"] == 0
        assert a_model["urn"] in out["without_a_record"]
        assert "a backlog somebody can work" in out["detail"]

    def test_reading_one_back_explains_the_difference(self, decommissioning,
                                                      a_model, db):
        db.execute("UPDATE model SET status = 'retired' WHERE id = :i",
                   {"i": a_model["id"]})
        out = decommissioning.of(a_model["urn"])
        assert "none of the other three facts" in out["detail"]


class TestThroughTheApi:
    def test_the_posture_is_published(self, client):
        out = client.get("/api/v1/decommission").json()
        assert out["notifies_anybody"] is False
        assert len(out["required"]) == 3

    def test_a_model_is_decommissioned_over_the_wire(self, client, registered,
                                                     people):
        urn = "maya://model/credit.pd.smallbiz"
        out = client.post("/api/v1/decommission", params={"urn": urn},
                          auth=people["s.iqbal"],
                          json={**GOOD, "notified": [], "acknowledged": False})
        assert out.status_code == 201, out.text
        assert out.json()["retention_class"] == "model_record"

    def test_a_bad_retention_class_is_refused_over_the_wire(self, client,
                                                            registered,
                                                            people):
        out = client.post("/api/v1/decommission",
                          params={"urn": "maya://model/credit.pd.smallbiz"},
                          auth=people["s.iqbal"],
                          json={**GOOD, "retention_class": "forever"})
        assert out.status_code == 422
        assert "unknown_retention_class" in out.text

    def test_the_estate_answers(self, client, registered):
        out = client.get("/api/v1/decommission/estate")
        assert out.status_code == 200
        assert "without_a_record" in out.json()


def _with_consumers(db, registry, evidence, urns):
    """A decommissioning engine whose model graph reports these downstream."""
    class _Composition:
        @staticmethod
        def blast_radius(_urn):
            return {"reached": [{"urn": u, "status": "approved"}
                                for u in urns]}

    return Decommissioning(DecommissionRepository(db), registry,
                           composition=_Composition(), lifecycle=None,
                           evidence=evidence)
