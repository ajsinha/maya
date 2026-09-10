"""A challenger running beside the champion, and what that can honestly tell you.

SS1/23 3.3(c) asks for parallel outcomes analysis when a dynamic model changes.
MAYA runs neither model: it registers that a run is happening, takes delivery of
what both produced, and reports the shape of the disagreement.

The distinction the whole thing turns on is that agreement is knowable now and
correctness is not.
"""
from __future__ import annotations

import pytest

from core.lifecycle.common import LifecycleError
from core.lifecycle.parallel import (CONCLUSIONS, MIN_OUTCOME_COVERAGE,
                                     MIN_PAIRED, ParallelRuns)
from core.validation.recode import RecodeHarness
from tests.conftest import KERNEL, URN

NO_ASSUMPTIONS = {"assumptions": [], "guarantees": [],
                  "on_boundary_violation": "reject"}


@pytest.fixture
def runs(db, registry, evidence):
    from db import ParallelObservationRepository, ParallelRunRepository
    return ParallelRuns(ParallelRunRepository(db),
                        ParallelObservationRepository(db), registry, evidence,
                        recode=RecodeHarness())


@pytest.fixture
def versioned(registry, a_model):
    for semver, digest in (("1.0.0", "a"), ("2.0.0", "b")):
        registry.create_version(URN, semver, KERNEL, NO_ASSUMPTIONS,
                                artifact_digest="sha256:" + digest * 64,
                                actor="d.raman")
    return URN


@pytest.fixture
def run(runs, versioned):
    return runs.open(URN, champion="1.0.0", challenger="2.0.0",
                     purpose="does the new scorecard shift the cut-off",
                     actor="s.iqbal")


def _observe(runs, reference, n, offset=0.0, champion_only=0):
    for i in range(n):
        runs.observe(reference, input_key=f"case-{i}",
                     champion=1.0 + i * 0.001,
                     challenger=None if i < champion_only
                     else 1.0 + i * 0.001 + offset)


class TestOpeningOne:
    def test_a_run_is_registered(self, run):
        assert run["reference"] == "PAR-0001"
        assert run["state"] == "running"

    def test_a_version_cannot_challenge_itself(self, runs, versioned):
        with pytest.raises(LifecycleError) as caught:
            runs.open(URN, champion="1.0.0", challenger="1.0.0", purpose="p")
        assert caught.value.code == "same_version"

    def test_a_run_with_no_purpose_is_refused(self, runs, versioned):
        with pytest.raises(LifecycleError) as caught:
            runs.open(URN, champion="1.0.0", challenger="2.0.0", purpose=" ")
        assert caught.value.code == "purpose_required"
        assert "nobody can conclude" in caught.value.detail

    def test_two_runs_at_once_are_refused(self, runs, run, versioned):
        """An observation belongs to one of them and nothing says which."""
        with pytest.raises(LifecycleError) as caught:
            runs.open(URN, champion="1.0.0", challenger="2.0.0", purpose="p")
        assert caught.value.code == "run_already_open"

    def test_it_lands_on_the_evidence_chain(self, runs, run, registry,
                                            evidence):
        model_id = registry.require(URN)["id"]
        kinds = [n["kind"] for n in evidence.for_subject(model_id)]
        assert "parallel_run_opened" in kinds


class TestPairingOnTheInput:
    def test_the_two_sides_may_arrive_separately(self, runs, run):
        """In a real shadow deployment they do: the champion answers in the
        request path and the challenger answers out of band."""
        runs.observe(run["reference"], input_key="case-1", champion=0.4)
        row = runs.observe(run["reference"], input_key="case-1",
                           challenger=0.41)
        assert row["champion"] == 0.4 and row["challenger"] == 0.41

    def test_an_observation_with_no_key_is_refused(self, runs, run):
        """A parallel run whose two sides were not asked the same question is
        two unrelated series printed side by side."""
        with pytest.raises(LifecycleError) as caught:
            runs.observe(run["reference"], input_key="  ", champion=0.4)
        assert caught.value.code == "input_key_required"

    def test_an_unpaired_observation_is_reported_not_dropped(self, runs, run):
        """A challenger that silently failed on the hard cases would otherwise
        look like the better model."""
        _observe(runs, run["reference"], 10, champion_only=3)
        out = runs.divergence(run["reference"])
        assert out["paired"] == 7 and out["unpaired"] == 3
        assert "would otherwise look like the better model" in out["detail"]

    def test_an_observation_after_the_run_closed_is_refused(self, runs, run):
        _observe(runs, run["reference"], MIN_PAIRED)
        runs.conclude(run["reference"], "inconclusive", "no labels yet",
                      actor="s.iqbal")
        with pytest.raises(LifecycleError) as caught:
            runs.observe(run["reference"], input_key="late", champion=1.0)
        assert caught.value.code == "run_concluded"


class TestDivergenceSaysNothingAboutQuality:
    def test_with_nothing_paired_it_says_so(self, runs, run):
        out = runs.divergence(run["reference"])
        assert out["paired"] == 0
        assert "says nothing about either model" in out["detail"]

    def test_the_shape_is_read_by_the_recode_harness(self, runs, run):
        """Two implementations of one judgement eventually disagree."""
        _observe(runs, run["reference"], 100, offset=0.0)
        out = runs.divergence(run["reference"])
        assert out["comparison"]["shape"]["kind"] == "agreement"

    def test_a_handful_of_wild_outliers_reads_as_a_cliff(self, runs, run):
        _observe(runs, run["reference"], 200)
        for key, value in (("case-7", 900.0), ("case-88", -50.0)):
            runs.observe(run["reference"], input_key=key, challenger=value)
        out = runs.divergence(run["reference"])
        assert out["comparison"]["shape"]["kind"] == "cliff"

    def test_too_few_pairs_is_called_noise(self, runs, run):
        _observe(runs, run["reference"], MIN_PAIRED - 1)
        out = runs.divergence(run["reference"])
        assert out["enough_to_read"] is False
        assert "noise rather than a measurement" in out["detail"]

    def test_it_always_says_it_is_not_a_verdict(self, runs, run):
        _observe(runs, run["reference"], 50, offset=0.5)
        assert "the outcome arrives later" in runs.divergence(
            run["reference"])["detail"]


class TestOutcomesArriveLater:
    def test_with_no_labels_it_says_that_is_ordinary(self, runs, run):
        _observe(runs, run["reference"], 50)
        out = runs.outcomes(run["reference"])
        assert out["with_an_outcome"] == 0 and out["conclusive"] is False
        assert "ordinary state of a parallel run" in out["detail"]

    def test_a_label_arriving_needs_an_observation_to_belong_to(self, runs,
                                                                run):
        with pytest.raises(LifecycleError) as caught:
            runs.record_outcome(run["reference"], "never-seen", 1.0)
        assert caught.value.code == "no_observation"
        assert "nothing for this outcome to be the outcome OF" in (
            caught.value.detail)

    def test_a_thin_outcome_set_is_not_a_result_with_a_caveat(self, runs, run):
        """An outcomes analysis over a fraction of a run is not a result."""
        _observe(runs, run["reference"], 200, offset=0.1)
        for i in range(5):
            runs.record_outcome(run["reference"], f"case-{i}", 1.0 + i * 0.001)
        out = runs.outcomes(run["reference"])
        assert out["coverage"] < MIN_OUTCOME_COVERAGE
        assert out["conclusive"] is False
        assert "not a result with a caveat, it is not a result" in out["detail"]

    def test_enough_labels_name_which_model_was_closer(self, runs, run):
        _observe(runs, run["reference"], 100, offset=0.5)
        # The truth is exactly what the champion said, so it wins.
        for i in range(100):
            runs.record_outcome(run["reference"], f"case-{i}", 1.0 + i * 0.001)
        out = runs.outcomes(run["reference"])
        assert out["closer"] == "champion"
        assert out["conclusive"] is True
        assert out["champion_mean_absolute_error"] < (
            out["challenger_mean_absolute_error"])

    def test_the_challenger_can_win(self, runs, run):
        _observe(runs, run["reference"], 100, offset=0.5)
        for i in range(100):
            runs.record_outcome(run["reference"], f"case-{i}",
                                1.0 + i * 0.001 + 0.5)
        assert runs.outcomes(run["reference"])["closer"] == "challenger"


class TestTheTwoReadingsAreNeverMixed:
    def test_the_report_carries_both_apart(self, runs, run):
        _observe(runs, run["reference"], 50, offset=0.3)
        out = runs.report(run["reference"])
        assert "divergence" in out and "outcomes" in out
        assert "lets a reader conclude the second" in out["detail"]


class TestConcluding:
    def test_promoting_without_outcomes_is_refused(self, runs, run):
        """Divergence alone says the two models differ; it does not say the
        challenger is better, and the pressure at the end of an expensive run
        is to conclude something rather than nothing."""
        _observe(runs, run["reference"], 200, offset=0.5)
        with pytest.raises(LifecycleError) as caught:
            runs.conclude(run["reference"], "promote", "it looks better",
                          actor="s.iqbal")
        assert caught.value.code == "not_conclusive"
        assert "answers a different question" in caught.value.detail

    def test_inconclusive_is_always_available(self, runs, run):
        """An honest end and a common one."""
        _observe(runs, run["reference"], 50)
        out = runs.conclude(run["reference"], "inconclusive",
                            "no labels arrived in the window", actor="s.iqbal")
        assert out["conclusion"] == "inconclusive"

    def test_promoting_with_outcomes_goes_through(self, runs, run):
        _observe(runs, run["reference"], 100, offset=0.1)
        for i in range(100):
            runs.record_outcome(run["reference"], f"case-{i}",
                                1.0 + i * 0.001 + 0.1)
        out = runs.conclude(run["reference"], "promote",
                            "challenger is closer over the whole window",
                            actor="s.iqbal")
        assert out["conclusion"] == "promote"

    def test_a_conclusion_with_no_note_is_refused(self, runs, run):
        with pytest.raises(LifecycleError) as caught:
            runs.conclude(run["reference"], "reject", "  ")
        assert caught.value.code == "note_required"

    def test_the_conclusions_are_closed(self, runs, run):
        with pytest.raises(LifecycleError) as caught:
            runs.conclude(run["reference"], "looked at it", "n")
        assert caught.value.code == "unknown_conclusion"
        assert set(CONCLUSIONS) == {"promote", "reject", "inconclusive"}


class TestTheEstate:
    def test_an_empty_estate_says_so(self, runs):
        assert runs.across_the_estate()["count"] == 0

    def test_open_runs_are_listed_with_their_coverage(self, runs, run):
        _observe(runs, run["reference"], 40)
        out = runs.across_the_estate()
        assert out["count"] == 1 and out["waiting_on_outcomes"] == 1
        assert "never be read as a verdict" in out["detail"]


ADMIN = ("admin", "maya-admin-dev")


class TestOverHttp:
    def _opened(self, client, people):
        from tests.conftest import NAME
        for semver, digest in (("2.0.0", "b"),):
            r = client.post(f"/api/v1/models/{NAME}/versions",
                            auth=people["d.raman"],
                            json={"semver": semver, "kernel": KERNEL,
                                  "contract": NO_ASSUMPTIONS,
                                  "artifact_digest": "sha256:" + digest * 64})
            assert r.status_code == 201, r.text
        made = client.post("/api/v1/parallel-runs", auth=people["s.iqbal"],
                           json={"urn": URN, "champion": "3.2.1",
                                 "challenger": "2.0.0",
                                 "purpose": "does the cut-off shift"})
        assert made.status_code == 201, made.text
        return made.json()["reference"]

    def test_a_run_goes_all_the_way_round(self, registered, people):
        # Observations are posted by a SERVICE, not a person: a shadow
        # deployment answers out of band, which is why the permission is
        # `monitor:observe` rather than one a reviewer holds.
        service = ADMIN
        reference = self._opened(registered, people)
        for i in range(MIN_PAIRED + 5):
            r = registered.post(
                f"/api/v1/parallel-runs/{reference}/observations",
                auth=service,
                json={"input_key": f"case-{i}", "champion": 1.0 + i * 0.01,
                      "challenger": 1.0 + i * 0.01 + 0.02})
            assert r.status_code == 201, r.text
        for i in range(MIN_PAIRED + 5):
            registered.post(f"/api/v1/parallel-runs/{reference}/outcomes",
                            auth=service,
                            json={"input_key": f"case-{i}",
                                  "outcome": 1.0 + i * 0.01 + 0.02})
        report = registered.get("/api/v1/parallel-runs",
                                auth=people["a.mehta"],
                                params={"reference": reference})
        assert report.status_code == 200, report.text
        assert report.json()["outcomes"]["closer"] == "challenger"

    def test_promoting_without_outcomes_is_refused(self, registered, people):
        service = ADMIN
        reference = self._opened(registered, people)
        for i in range(MIN_PAIRED + 5):
            registered.post(
                f"/api/v1/parallel-runs/{reference}/observations",
                auth=service,
                json={"input_key": f"case-{i}", "champion": 1.0,
                      "challenger": 2.0})
        r = registered.post(f"/api/v1/parallel-runs/{reference}/conclude",
                            auth=people["s.iqbal"],
                            json={"conclusion": "promote",
                                  "note": "it looks better"})
        assert r.status_code == 409, r.text
        assert r.json()["error"] == "not_conclusive"

    def test_the_estate_view_is_served(self, registered, people):
        self._opened(registered, people)
        r = registered.get("/api/v1/parallel-runs", auth=people["a.mehta"])
        assert r.status_code == 200, r.text
        assert r.json()["count"] == 1

    def test_the_screen_keeps_the_two_readings_apart(self, registered,
                                                     people):
        registered.post("/login", data={"username": "admin",
                                        "password": "maya-admin-dev",
                                        "next": "/lifecycle-profiles"})
        body = registered.get("/lifecycle-profiles").text
        assert "Agreement is knowable now; correctness is not" in body
        assert "Promoting on divergence alone is refused" in body
