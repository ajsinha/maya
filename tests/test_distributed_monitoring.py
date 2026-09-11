"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Monitoring an estate that will not fit in this process.

The obvious answer to *the nightly sweep does not fit in memory* is to put Spark
in MAYA. It is wrong twice: the governance platform would own a cluster, and it
would sit on the compute path for every model in the bank — the availability
coupling the whole architecture avoids.

The next answer is `external.py`: take the number somebody else computed and
refuse their verdict. That works and gives something real up. An external
observation **cannot be replayed**, because MAYA does not hold the population,
and for an estate-wide sweep that would mean the whole sweep is unreproducible.

This is the better trade, and it rests on an ordinary fact: PSI, AUC, Gini and
KS are functions of **sufficient statistics**, not of rows, and those statistics
are additive over partitions. So the scan runs on somebody else's cluster and a
few hundred numbers come back — and MAYA computes the metric and MAYA compares
it to the threshold.

The load-bearing test in this file is the first one: the distributed value must
equal the in-process value to the last decimal place. Anything less and this is
an approximation being reported as a measurement, which is the failure mode the
whole module is arranged against.
"""
from __future__ import annotations

import random

import pytest

from core.monitoring.common import MonitorError
from core.monitoring.distributed import (DISTRIBUTABLE, NOT_DISTRIBUTABLE,
                                         DistributedEvaluation)
from core.validation.statistics import auc, gini, psi

BINS = 10


@pytest.fixture
def samples():
    random.seed(11)
    return ([random.gauss(0, 1) for _ in range(5000)],
            [random.gauss(0.4, 1.2) for _ in range(4000)])


class _Monitors:
    def __init__(self, test_key, reference=None):
        self.test_key, self.reference = test_key, reference or {}

    def require(self, monitor_id):
        return {"id": monitor_id, "name": "score drift",
                "test_key": self.test_key, "reference": self.reference,
                "threshold": {"max": 0.25}, "status": "active"}


def _counts(rows, edges):
    counts = [0] * BINS
    for value in rows:
        slot = 0
        while slot < len(edges) and value > edges[slot]:
            slot += 1
        counts[slot] += 1
    return counts


def _partitioned(engine, plan, actual, parts=4):
    edges = plan["reference"]["edges"]
    return [{"bin_counts": _counts(actual[i::parts], edges),
             "rows": len(actual[i::parts])} for i in range(parts)]


class TestTheDistributedValueIsTheValue:
    """The load-bearing test. An approximation reported as a measurement is
    exactly what this module is arranged against."""

    def test_psi_matches_the_in_process_computation_exactly(self, samples):
        reference, actual = samples
        engine = DistributedEvaluation(
            _Monitors("stability.psi",
                      {"sample": reference, "bins": BINS}))
        plan = engine.plan("m1", partitions=4)
        out = engine.submit("m1", {
            "partitions": _partitioned(engine, plan, actual),
            "predicate": "scored_at between :a and :b",
            "reference_digest": plan["reference"]["digest"],
            "engine": "spark-3.5"})
        assert out["value"] == psi(reference, actual, BINS)

    def test_the_partitioning_does_not_change_the_answer(self, samples):
        """Counts add. If they did not, the number would depend on how
        somebody's cluster happened to split the data — which is a metric
        nobody could reproduce and everybody would quote."""
        reference, actual = samples
        engine = DistributedEvaluation(
            _Monitors("stability.psi", {"sample": reference, "bins": BINS}))
        plan = engine.plan("m1")
        values = {
            engine.submit("m1", {
                "partitions": _partitioned(engine, plan, actual, parts),
                "predicate": "p", "engine": "spark",
                "reference_digest": plan["reference"]["digest"]})["value"]
            for parts in (1, 3, 8, 64)}
        assert len(values) == 1

    def test_auc_matches_the_mann_whitney_identity(self):
        random.seed(3)
        labels = [1 if random.random() < 0.3 else 0 for _ in range(2000)]
        scores = [random.random() + 0.4 * y for y in labels]
        engine = DistributedEvaluation(_Monitors("discrimination.auc"))
        ranks = _ranks(scores)
        out = engine.submit("m1", {
            "partitions": [{
                "rank_sum_positive": sum(r for r, y in zip(ranks, labels)
                                         if y == 1),
                "n_positive": sum(labels),
                "n_negative": len(labels) - sum(labels),
                "rows": len(labels)}],
            "predicate": "p", "engine": "spark", "ranked_globally": True})
        assert out["value"] == pytest.approx(auc(labels, scores), abs=1e-12)

    def test_gini_is_two_auc_minus_one_here_too(self):
        random.seed(4)
        labels = [1 if random.random() < 0.4 else 0 for _ in range(1500)]
        scores = [random.random() + 0.5 * y for y in labels]
        engine = DistributedEvaluation(_Monitors("discrimination.gini"))
        ranks = _ranks(scores)
        out = engine.submit("m1", {
            "partitions": [{
                "rank_sum_positive": sum(r for r, y in zip(ranks, labels)
                                         if y == 1),
                "n_positive": sum(labels),
                "n_negative": len(labels) - sum(labels),
                "rows": len(labels)}],
            "predicate": "p", "engine": "spark", "ranked_globally": True})
        assert out["value"] == pytest.approx(gini(labels, scores), abs=1e-12)


def _ranks(scores):
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    index = 0
    while index < len(order):
        stop = index
        while stop + 1 < len(order) \
                and scores[order[stop + 1]] == scores[order[index]]:
            stop += 1
        average = (index + stop) / 2.0 + 1
        for position in range(index, stop + 1):
            ranks[order[position]] = average
        index = stop + 1
    return ranks


class TestWhatStaysHere:
    def test_maya_computes_the_metric_and_says_so(self):
        out = DistributedEvaluation.posture()
        assert out["maya_computes_the_metric"] is True
        assert out["maya_compares_to_the_threshold"] is True
        assert out["maya_runs_a_cluster"] is False
        assert out["moves_off_the_platform"] == "the SCAN, and only the scan"

    def test_the_result_is_replayable_unlike_an_external_observation(self,
                                                                    samples):
        reference, actual = samples
        engine = DistributedEvaluation(
            _Monitors("stability.psi", {"sample": reference, "bins": BINS}))
        plan = engine.plan("m1")
        out = engine.submit("m1", {
            "partitions": _partitioned(engine, plan, actual),
            "predicate": "p", "engine": "spark",
            "reference_digest": plan["reference"]["digest"]})
        assert out["replayable"] is True
        assert out["computed_by"] == "maya, from submitted statistics"

    def test_a_submitted_metric_would_be_an_external_observation(self):
        assert "wearing a better name" in \
            DistributedEvaluation.posture()["still_here"]


class TestWhatItCannotCheck:
    def test_the_population_is_attested_not_observed(self, samples):
        reference, actual = samples
        engine = DistributedEvaluation(
            _Monitors("stability.psi", {"sample": reference, "bins": BINS}))
        plan = engine.plan("m1")
        out = engine.submit("m1", {
            "partitions": _partitioned(engine, plan, actual),
            "predicate": "dt >= '2026-01-01'", "engine": "spark",
            "reference_digest": plan["reference"]["digest"]})
        assert out["population_attested_not_observed"] is True
        assert "attested rather than observed" in out["detail"]

    def test_an_unstated_predicate_is_refused(self, samples):
        """A WHERE clause that quietly excluded a segment produces statistics
        that are arithmetically perfect and describe the wrong population.
        Nothing here can see that — so what was read has to be written down,
        or the attestation is unfalsifiable."""
        reference, actual = samples
        engine = DistributedEvaluation(
            _Monitors("stability.psi", {"sample": reference, "bins": BINS}))
        plan = engine.plan("m1")
        with pytest.raises(MonitorError) as e:
            engine.submit("m1", {
                "partitions": _partitioned(engine, plan, actual),
                "reference_digest": plan["reference"]["digest"]})
        assert e.value.code == "submission_does_not_meet_the_plan"
        assert "predicate" in str(e.value)

    def test_it_names_both_limits_rather_than_one(self):
        assert len(DistributedEvaluation.posture()["cannot_check"]) == 2


class TestTheReferenceIsTheRegistersOwn:
    def test_a_different_reference_digest_is_refused(self, samples):
        """PSI against edges somebody else chose is a different measurement,
        and the two print the same."""
        reference, actual = samples
        engine = DistributedEvaluation(
            _Monitors("stability.psi", {"sample": reference, "bins": BINS}))
        plan = engine.plan("m1")
        with pytest.raises(MonitorError) as e:
            engine.submit("m1", {
                "partitions": _partitioned(engine, plan, actual),
                "predicate": "p", "reference_digest": "sha256:somethingelse"})
        assert "reference_digest" in str(e.value)

    def test_the_wrong_number_of_bins_is_refused(self, samples):
        reference, _ = samples
        engine = DistributedEvaluation(
            _Monitors("stability.psi", {"sample": reference, "bins": BINS}))
        plan = engine.plan("m1")
        with pytest.raises(MonitorError) as e:
            engine.submit("m1", {
                "partitions": [{"bin_counts": [1] * 5, "rows": 5}],
                "predicate": "p",
                "reference_digest": plan["reference"]["digest"]})
        assert e.value.code == "bin_count_mismatch"

    def test_a_monitor_with_no_reference_cannot_be_planned(self):
        engine = DistributedEvaluation(
            _Monitors("stability.psi", {"sample": [1.0, 2.0], "bins": BINS}))
        with pytest.raises(MonitorError) as e:
            engine.plan("m1")
        assert e.value.code == "reference_too_small"
        assert "every night's number is measured against that night's own " \
               "data" in e.value.remediation


class TestAGlobalRankingIsNotAPartitionRanking:
    def test_the_plan_says_so(self):
        engine = DistributedEvaluation(_Monitors("discrimination.auc"))
        plan = engine.plan("m1")
        assert plan["global_ranking_required"] is True
        assert "looks like an AUC and is not" in plan["detail"]

    def test_a_submission_that_does_not_assert_it_is_refused(self):
        """Nothing in the result would show it. Summing per-partition rank
        sums produces a plausible number computed in the wrong ordering, so
        the job has to assert that it ranked across the whole window."""
        engine = DistributedEvaluation(_Monitors("discrimination.auc"))
        with pytest.raises(MonitorError) as e:
            engine.submit("m1", {
                "partitions": [{"rank_sum_positive": 10, "n_positive": 2,
                                "n_negative": 3, "rows": 5}],
                "predicate": "p"})
        assert "ranked_globally" in str(e.value)

    def test_psi_does_not_require_it(self, samples):
        engine = DistributedEvaluation(
            _Monitors("stability.psi", {"sample": samples[0], "bins": BINS}))
        assert engine.plan("m1")["global_ranking_required"] is False


class TestWhatDoesNotDecompose:
    def test_hosmer_lemeshow_is_refused_by_name(self):
        engine = DistributedEvaluation(
            _Monitors("calibration.hosmer_lemeshow"))
        with pytest.raises(MonitorError) as e:
            engine.plan("m1")
        assert e.value.code == "test_does_not_decompose"
        assert "a different partitioning of a different population" in \
            e.value.remediation

    def test_brier_is_refused_for_a_subtler_reason(self):
        """It decomposes arithmetically and its useful form does not, which is
        the kind of distinction a scaling exercise loses."""
        assert "which of the three moved" in NOT_DISTRIBUTABLE[
            "calibration.brier"]

    def test_an_unknown_test_names_the_ones_that_work(self):
        engine = DistributedEvaluation(_Monitors("stability.kl_divergence"))
        with pytest.raises(MonitorError) as e:
            engine.plan("m1")
        assert e.value.code == "test_not_distributable"
        assert "agree with the real one most of the time" in e.value.remediation

    def test_every_distributable_test_says_what_it_needs_and_why(self):
        for spec in DISTRIBUTABLE.values():
            assert spec["needs"] and spec["why"].strip()


class TestEveryProblemIsReported:
    def test_not_the_first(self, samples):
        engine = DistributedEvaluation(
            _Monitors("stability.psi", {"sample": samples[0], "bins": BINS}))
        with pytest.raises(MonitorError) as e:
            engine.submit("m1", {"partitions": [{}, {}]})
        assert e.value.code == "submission_does_not_meet_the_plan"
        # predicate, reference digest, and bin_counts + rows for each partition
        assert "6 problem(s)" in str(e.value)

    def test_a_submission_is_refused_whole(self, samples):
        assert "a population nobody chose" in _remediation(samples)

    def test_an_empty_submission_says_there_is_nothing_to_combine(self):
        engine = DistributedEvaluation(_Monitors("discrimination.auc"))
        with pytest.raises(MonitorError) as e:
            engine.submit("m1", {"partitions": []})
        assert "partitions is empty" in str(e.value)


def _remediation(samples):
    engine = DistributedEvaluation(
        _Monitors("stability.psi", {"sample": samples[0], "bins": BINS}))
    try:
        engine.submit("m1", {"partitions": [{}]})
    except MonitorError as exc:
        return exc.remediation
    raise AssertionError("expected a refusal")


class TestZeroIsNotAnAnswer:
    def test_a_psi_over_no_rows_is_refused(self, samples):
        engine = DistributedEvaluation(
            _Monitors("stability.psi", {"sample": samples[0], "bins": BINS}))
        plan = engine.plan("m1")
        with pytest.raises(MonitorError) as e:
            engine.submit("m1", {
                "partitions": [{"bin_counts": [0] * BINS, "rows": 0}],
                "predicate": "p",
                "reference_digest": plan["reference"]["digest"]})
        assert e.value.code == "no_rows_in_submission"
        assert "not a PSI of zero" in e.value.remediation

    def test_an_auc_over_one_class_is_refused_not_reported_as_half(self):
        """0.5 looks like a model with no signal. Undefined is the truth."""
        engine = DistributedEvaluation(_Monitors("discrimination.auc"))
        with pytest.raises(MonitorError) as e:
            engine.submit("m1", {
                "partitions": [{"rank_sum_positive": 0, "n_positive": 0,
                                "n_negative": 100, "rows": 100}],
                "predicate": "p", "ranked_globally": True})
        assert e.value.code == "one_class_absent"
        assert "no signal" in e.value.remediation


class TestThroughTheApi:
    def test_the_posture_is_published(self, client):
        out = client.get("/api/v1/distributed-evaluation").json()
        assert out["maya_runs_a_cluster"] is False
        assert out["not_distributable"]

    def test_a_plan_comes_back_for_a_real_monitor(self, client, registered,
                                                  people):
        made = client.post("/api/v1/monitors", auth=people["j.okafor"], json={
            "urn": "maya://model/credit.pd.smallbiz", "name": "score drift",
            "kind": "score_drift", "test_key": "stability.psi",
            "threshold": {"max": 0.25}, "owner": "person/j.okafor",
            "reference": {"sample": [i / 100 for i in range(200)], "bins": 10}})
        assert made.status_code == 201, made.text
        plan = client.get(
            f"/api/v1/monitors/{made.json()['id']}/distributed-plan")
        assert plan.status_code == 200, plan.text
        body = plan.json()
        assert body["maya_runs_it"] is False
        assert body["returns"] == ["bin_counts"]
        assert body["reference"]["digest"].startswith("sha256:")
