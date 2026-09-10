"""A panel's disagreement, and the part of a number that is not the model.

Two failure modes: an elicitation that stores only the answer, and a disclosure
that silently omits an adjustment nobody measured.
"""
from __future__ import annotations

import pytest

from core.overlays.common import OverlayError
from core.overlays.disclosure import (GREW, NEW, STRUCTURAL_AFTER, Disclosure)
from core.parameters.common import ParameterError
from core.parameters.elicitation import (CONCLUDED, METHODS, MINIMUM_PANEL,
                                         WIDE_SPREAD, Elicitations)
from tests.conftest import URN

PANEL = ["person/a.expert", "person/b.expert", "person/c.expert"]


@pytest.fixture
def elicitations(db, registry, evidence, a_model):
    from db import ElicitationRepository, ElicitationResponseRepository
    return Elicitations(ElicitationRepository(db),
                        ElicitationResponseRepository(db), registry, evidence)


@pytest.fixture
def opened(elicitations, a_model):
    return elicitations.open(
        "E-1", URN, question="What is the 2030 transition probability?",
        panel=PANEL, facilitator="person/s.iqbal", units="probability")


class TestAPanelIsAtLeastThree:
    def test_two_is_not_a_panel(self, elicitations, a_model):
        with pytest.raises(ParameterError) as e:
            elicitations.open("E-x", URN, question="q", panel=PANEL[:2],
                              facilitator="person/s.iqbal")
        assert e.value.code == "panel_too_small"
        assert "the assumption register is where an assumption belongs" in \
            e.value.remediation

    def test_the_facilitator_may_not_answer(self, elicitations, a_model):
        with pytest.raises(ParameterError) as e:
            elicitations.open("E-y", URN, question="q",
                              panel=PANEL + ["person/s.iqbal"],
                              facilitator="person/s.iqbal")
        assert e.value.code == "facilitator_is_a_panellist"
        assert "shape the spread they are about to report" in \
            e.value.remediation

    def test_the_question_must_be_written_down(self, elicitations, a_model):
        with pytest.raises(ParameterError) as e:
            elicitations.open("E-z", URN, question="  ", panel=PANEL,
                              facilitator="person/s.iqbal")
        assert e.value.code == "question_required"
        assert "slightly different questions" in e.value.detail

    def test_an_unknown_method_is_refused(self, elicitations, a_model):
        with pytest.raises(ParameterError) as e:
            elicitations.open("E-w", URN, question="q", panel=PANEL,
                              facilitator="person/s.iqbal", method="vote")
        assert e.value.code == "unknown_method"

    def test_every_method_says_what_its_spread_means(self):
        assert all(v.strip() for v in METHODS.values())
        assert MINIMUM_PANEL == 3

    def test_somebody_off_the_panel_cannot_answer(self, elicitations, opened):
        with pytest.raises(ParameterError) as e:
            elicitations.respond("E-1", "person/d.outsider", value=0.3)
        assert e.value.code == "not_on_the_panel"


class TestTheSpreadIsTheAnswer:
    def test_a_round_reports_its_spread(self, elicitations, opened):
        for person, value in zip(PANEL, (0.1, 0.3, 0.9)):
            elicitations.respond("E-1", person, value=value)
        latest = elicitations.rounds("E-1")[-1]
        assert latest["spread"] == pytest.approx(0.8)
        assert latest["median"] == pytest.approx(0.3)

    def test_a_response_is_never_overwritten(self, elicitations, opened):
        """A response revised in place erases the movement between rounds."""
        elicitations.respond("E-1", PANEL[0], value=0.1)
        with pytest.raises(ParameterError) as e:
            elicitations.respond("E-1", PANEL[0], value=0.5)
        assert e.value.code == "already_answered"
        assert "the movement is the only thing convergence" in \
            e.value.remediation

    def test_an_empty_round_cannot_be_advanced(self, elicitations, opened):
        with pytest.raises(ParameterError) as e:
            elicitations.next_round("E-1")
        assert e.value.code == "round_is_empty"
        assert "the convergence series would carry a gap" in \
            e.value.remediation

    def test_a_second_round_keeps_the_first(self, elicitations, opened):
        for person, value in zip(PANEL, (0.1, 0.3, 0.9)):
            elicitations.respond("E-1", person, value=value)
        elicitations.next_round("E-1")
        for person, value in zip(PANEL, (0.25, 0.3, 0.35)):
            elicitations.respond("E-1", person, value=value)
        rounds = elicitations.rounds("E-1")
        assert len(rounds) == 2
        assert rounds[0]["spread"] == pytest.approx(0.8)
        assert rounds[1]["spread"] == pytest.approx(0.1)


class TestConvergenceCannotSayWhy:
    def test_it_reports_the_narrowing(self, elicitations, opened):
        for person, value in zip(PANEL, (0.1, 0.3, 0.9)):
            elicitations.respond("E-1", person, value=value)
        elicitations.next_round("E-1")
        for person, value in zip(PANEL, (0.28, 0.3, 0.32)):
            elicitations.respond("E-1", person, value=value)
        out = elicitations.convergence("E-1")
        assert out["narrowed"] is True

    def test_it_says_it_cannot_say_why(self, elicitations, opened):
        for person, value in zip(PANEL, (0.1, 0.3, 0.9)):
            elicitations.respond("E-1", person, value=value)
        elicitations.next_round("E-1")
        for person, value in zip(PANEL, (0.28, 0.3, 0.32)):
            elicitations.respond("E-1", person, value=value)
        out = elicitations.convergence("E-1")
        assert out["explains_why"] is False
        assert "the most senior person answered first" in out["detail"]

    def test_the_method_is_named_in_the_reading(self, elicitations, a_model):
        elicitations.open("E-2", URN, question="q", panel=PANEL,
                          facilitator="person/s.iqbal", method="workshop")
        for person, value in zip(PANEL, (0.1, 0.3, 0.9)):
            elicitations.respond("E-2", person, value=value)
        elicitations.next_round("E-2")
        for person, value in zip(PANEL, (0.2, 0.3, 0.4)):
            elicitations.respond("E-2", person, value=value)
        assert "**workshop**" in elicitations.convergence("E-2")["detail"]

    def test_one_round_is_a_snapshot_of_priors(self, elicitations, opened):
        for person, value in zip(PANEL, (0.1, 0.3, 0.9)):
            elicitations.respond("E-1", person, value=value)
        assert "snapshot of the panel's priors" in \
            elicitations.convergence("E-1")["detail"]

    def test_a_wide_final_spread_is_a_disagreement(self, elicitations, opened):
        for person, value in zip(PANEL, (0.1, 0.3, 0.9)):
            elicitations.respond("E-1", person, value=value)
        out = elicitations.convergence("E-1")
        assert out["still_wide"] is True and WIDE_SPREAD == 0.5


class TestDissentIsPartOfTheNumber:
    def test_it_travels_to_the_evidence_chain(self, elicitations, opened,
                                              evidence, a_model):
        for person, value in zip(PANEL, (0.1, 0.3, 0.9)):
            elicitations.respond("E-1", person, value=value,
                                 dissented=person == PANEL[2])
        elicitations.conclude("E-1", value=0.3,
                              note="the panel settled on the median",
                              actor="person/s.iqbal")
        node = next(n for n in evidence.for_subject(a_model["id"])
                    if n["kind"] == "elicitation_concluded")
        assert node["payload"]["dissent"] == [PANEL[2]]

    def test_it_is_on_the_reading(self, elicitations, opened):
        for person, value in zip(PANEL, (0.1, 0.3, 0.9)):
            elicitations.respond("E-1", person, value=value,
                                 dissented=person == PANEL[2])
        out = elicitations.read("E-1")
        assert out["dissent"] == [PANEL[2]]
        assert "looks unanimous" in out["detail"]

    def test_a_conclusion_needs_the_reasoning(self, elicitations, opened):
        for person in PANEL:
            elicitations.respond("E-1", person, value=0.3)
        with pytest.raises(ParameterError) as e:
            elicitations.conclude("E-1", value=0.3, note="  ")
        assert e.value.code == "note_required"

    def test_nothing_to_conclude_is_refused(self, elicitations, opened):
        with pytest.raises(ParameterError) as e:
            elicitations.conclude("E-1", value=0.3, note="n")
        assert e.value.code == "nothing_to_conclude"
        assert "one person's number wearing a panel's name" in \
            e.value.remediation

    def test_a_concluded_panel_takes_no_more_answers(self, elicitations,
                                                     opened):
        for person in PANEL:
            elicitations.respond("E-1", person, value=0.3)
        elicitations.conclude("E-1", value=0.3, note="agreed")
        assert elicitations.read("E-1")["state"] == CONCLUDED
        with pytest.raises(ParameterError) as e:
            elicitations.respond("E-1", PANEL[0], value=0.4)
        assert e.value.code == "elicitation_closed"


class TestIndependenceIsRecordedNotRequired:
    def test_a_conflicted_panellist_is_accepted_and_named(self, elicitations,
                                                          opened):
        for person, value in zip(PANEL, (0.1, 0.3, 0.9)):
            elicitations.respond("E-1", person, value=value,
                                 independent=person != PANEL[0])
        out = elicitations.read("E-1")
        assert out["not_independent"] == [PANEL[0]]
        assert out["share_not_independent"] == pytest.approx(1 / 3,
                                                             abs=1e-3)
        assert "would push the elicitation off the platform" in out["detail"]

    def test_the_estate_names_them(self, elicitations, opened):
        elicitations.respond("E-1", PANEL[0], value=0.1, independent=False)
        assert "E-1" in \
            elicitations.across_the_estate()["with_conflicted_panellists"]

    def test_an_empty_register_says_what_that_means(self, elicitations):
        assert "a number somebody chose" in \
            elicitations.across_the_estate()["detail"]


# --------------------------------------------------------------- disclosure
@pytest.fixture
def disclosure(overlays, registry, a_model):
    return Disclosure(overlays, registry)


@pytest.fixture
def an_overlay(overlays, a_model):
    row = overlays.propose(a_model["id"], "Sector add-on", "judgemental",
                           "the model under-provisions for hospitality",
                           basis={"kind": "expert"}, owner="person/j.okafor",
                           actor="person/j.okafor")
    return overlays.approve(row["id"], "person/s.iqbal")


class TestAnUnmeasuredOverlayCannotBeDisclosed:
    def test_it_is_named_and_the_extract_is_incomplete(self, disclosure,
                                                       an_overlay):
        out = disclosure.extract("2026Q1")
        assert out["complete"] is False and out["unmeasured"]
        assert "zero is a measurement" in out["detail"]

    def test_a_measured_overlay_appears(self, disclosure, overlays,
                                        an_overlay):
        overlays.measure(an_overlay["id"], "2026Q1", 1000.0, 1180.0,
                         actor="person/j.okafor")
        out = disclosure.extract("2026Q1")
        assert out["count"] == 1 and out["complete"] is True
        assert out["aggregate_magnitude"] == pytest.approx(180.0)

    def test_a_period_is_required(self, disclosure):
        with pytest.raises(OverlayError) as e:
            disclosure.extract("  ")
        assert e.value.code == "period_required"
        assert "filed as a quarter" in e.value.detail

    def test_it_is_not_a_disclosure_note(self, disclosure, an_overlay):
        out = disclosure.extract("2026Q1")
        assert out["is_a_disclosure_note"] is False
        assert "the words and the materiality judgement are the firm's" in \
            out["detail"]


class TestNewAndGrownAreDifferentDisclosures:
    def test_a_first_measurement_is_new(self, disclosure, overlays,
                                        an_overlay):
        overlays.measure(an_overlay["id"], "2026Q1", 1000.0, 1180.0,
                         actor="person/j.okafor")
        out = disclosure.extract("2026Q1")
        assert out["overlays"][0]["movement"] == NEW

    def test_a_larger_second_measurement_grew(self, disclosure, overlays,
                                              an_overlay):
        overlays.measure(an_overlay["id"], "2026Q1", 1000.0, 1180.0,
                         actor="person/j.okafor")
        overlays.measure(an_overlay["id"], "2026Q2", 1000.0, 1400.0,
                         actor="person/j.okafor")
        out = disclosure.extract("2026Q2", prior="2026Q1")
        assert out["overlays"][0]["movement"] == GREW
        assert out["movement"][GREW]["count"] == 1
        assert "the one an auditor asks about" in out["detail"]

    def test_the_trend_reads_a_rising_series(self, disclosure, overlays,
                                             an_overlay):
        for index, period in enumerate(("2026Q1", "2026Q2", "2026Q3")):
            overlays.measure(an_overlay["id"], period, 1000.0,
                             1100.0 + 100.0 * index, actor="person/j.okafor")
        out = disclosure.trend(["2026Q1", "2026Q2", "2026Q3"])
        assert out["monotonically_rising"] is True
        assert "the series is the finding" in out["detail"]

    def test_an_incomplete_period_is_named_in_the_trend(self, disclosure,
                                                        an_overlay):
        out = disclosure.trend(["2026Q1", "2026Q2"])
        assert out["any_incomplete"] == ["2026Q1", "2026Q2"]
        assert "a moving definition of the total" in out["detail"]

    def test_the_structural_threshold_matches_the_renewal_limit(self):
        assert STRUCTURAL_AFTER >= 3
