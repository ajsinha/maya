"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Monitoring an estate that will not fit in this process.

## The problem, stated accurately

`MonitorService.evaluate_from_telemetry` reads a cohort into memory and computes
over it. That is fine at hundreds of models and a few million rows a night. It
is not fine at an estate-wide sweep over billions, and the failure is not
subtle: the read either exhausts the process or takes until lunchtime.

The obvious answer is *put Spark in MAYA*. It is the wrong one twice over. It
makes the governance platform own a cluster, which [04 §7] says it will not; and
it puts MAYA on the compute path for every model in the bank, which is the
availability coupling the whole architecture avoids. A register that is down
should stop issuing warrants, not stop the nightly batch of a hundred teams.

## What is built instead, and why it is stronger than the obvious thing

`core/monitoring/external.py` already takes a number somebody else computed and
refuses their verdict. That solves the compute problem and gives something real
up: an external observation **cannot be replayed**, because MAYA does not hold
the population and cannot re-derive the value. For an estate-wide PSI sweep that
would mean the whole sweep is unreproducible, which is a large price for a
scaling problem.

There is a better trade, and it rests on an ordinary fact about these metrics:
**PSI, KS, AUC and Gini are functions of sufficient statistics, not of rows.**

- PSI needs the count of rows falling in each of the reference's bins. Nothing
  else. The bin edges come from the reference and the register already holds it.
- AUC — by the Mann-Whitney identity — needs the rank sum of the positives and
  the two class counts.
- KS needs the two cumulative curves, which a bounded set of quantile buckets
  carries to whatever precision the buckets give.

All three are **additive over partitions**: a distributed job computes them per
partition and they combine by summing. So the scan can run where the data is, on
a cluster MAYA does not own, and what comes back is a few hundred numbers —
while **MAYA computes the metric and MAYA compares it to the threshold.**

That is the distinction this module exists to hold. `external.py` gives up the
derivation and keeps the judgement. This gives up only the *scan* and keeps
both: the arithmetic from statistics to metric happens here, against the
reference this register holds, using the same comparison every other monitor
uses. A submission that carried `psi: 0.31` would be an external observation
wearing a better name; one that carries bin counts is a measurement this
platform can and does redo.

## What the register still cannot check

**That the job read the population it says it did.** A `WHERE` clause that
quietly excluded a segment produces bin counts that are arithmetically perfect
and describe the wrong population. Nothing here can see that, so a submission
carries the partition predicate and the row count it claims, both are recorded,
and the answer says in words that the *population* is attested rather than
observed. That is a real limit and it is named rather than left for an auditor
to find.

**That the reference is the one MAYA holds.** So the plan carries a digest of
the reference sample and the edges derived from it, and a submission quoting a
different digest is refused. Recomputing PSI against edges somebody else chose
is not the same measurement, and the two are indistinguishable once they are
both a number on a slide.
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Sequence

from core.log import get_logger
from core.monitoring.common import MonitorError
from db.database import digest as canonical_digest

logger = get_logger(__name__)

#: Metrics whose value is a function of statistics rather than of rows, with
#: what a partition has to return for each. Anything not here is not
#: distributable by this route and is refused by name — approximating a metric
#: that does not decompose would produce a number that agrees with the real one
#: most of the time, which is the worst possible property for a control.
DISTRIBUTABLE: Dict[str, Dict[str, Any]] = {
    "stability.psi": {
        "needs": ("bin_counts",),
        "why": "PSI is a sum over bins of (a-e)·ln(a/e). The reference shares "
               "come from the sample the register holds; the actual shares are "
               "counts, and counts add across partitions",
    },
    "discrimination.auc": {
        "needs": ("rank_sum_positive", "n_positive", "n_negative"),
        "why": "AUC by the Mann-Whitney identity is (R⁺ − n⁺(n⁺+1)/2) / (n⁺n⁻). "
               "The rank sum is over the GLOBAL ordering, so a partition cannot "
               "compute it alone — see `global_ranking_required`",
    },
    "discrimination.gini": {
        "needs": ("rank_sum_positive", "n_positive", "n_negative"),
        "why": "Gini is 2·AUC − 1, so it needs exactly what AUC needs",
    },
    "discrimination.ks": {
        "needs": ("positive_quantiles", "negative_quantiles"),
        "why": "KS is the widest gap between two cumulative curves. Bounded "
               "quantile buckets carry both curves to the precision the "
               "buckets give, and the answer says what that precision is",
    },
}

#: Metrics that genuinely do not decompose, with the reason. Naming them is the
#: point: the alternative is a caller discovering that their nightly sweep
#: silently skipped a third of the estate.
NOT_DISTRIBUTABLE: Dict[str, str] = {
    "calibration.hosmer_lemeshow": (
        "the statistic needs deciles of PREDICTED probability, and the decile "
        "boundaries depend on the global distribution. A per-partition decile "
        "is a different partitioning of a different population, and the sum "
        "of the per-partition statistics is not the statistic"),
    "calibration.brier": (
        "it decomposes arithmetically — it is a mean of squared errors — but "
        "its useful form is the reliability/resolution/uncertainty split, and "
        "that does not. Submitting the scalar alone would hide which of the "
        "three moved, which is the only thing anybody asks it"),
}

#: The bucket count for a KS submission. Bounded on purpose: an unbounded
#: quantile vector is the row set with extra steps, which would move the memory
#: problem here rather than solving it.
KS_BUCKETS = 200

#: Below this, distributing is a cost with no benefit. The threshold is on the
#: plan rather than enforced, because how big is too big is a fact about
#: somebody's cluster and not about this register.
WORTH_DISTRIBUTING = 5_000_000


class DistributedEvaluation:
    """Plans a distributed monitor evaluation, and judges what comes back.

    MAYA runs nothing. It states what a job must compute, and then does the
    arithmetic from those statistics to the metric itself — which is the
    difference between this and taking somebody's number.
    """

    def __init__(self, monitors, registry=None, evidence=None):
        self.monitors, self.registry, self.evidence = monitors, registry, evidence

    # ---------------------------------------------------------------- posture
    @staticmethod
    def posture() -> Dict[str, Any]:
        """What this moves off the platform, and what it deliberately does not."""
        return {
            "maya_runs_a_cluster": False,
            "maya_computes_the_metric": True,
            "maya_compares_to_the_threshold": True,
            "distributable": [{"test": k, **v} for k, v in
                              DISTRIBUTABLE.items()],
            "not_distributable": [{"test": k, "why": v} for k, v in
                                  NOT_DISTRIBUTABLE.items()],
            "moves_off_the_platform": "the SCAN, and only the scan",
            "still_here": (
                "the arithmetic from statistics to metric, the reference "
                "distribution, the threshold and the comparison. A submission "
                "carrying a computed `psi` would be an external observation "
                "wearing a better name; one carrying bin counts is a "
                "measurement this platform redoes"),
            "cannot_check": [
                "that the job read the population it says it did. A WHERE "
                "clause that quietly excluded a segment produces statistics "
                "that are arithmetically perfect and describe the wrong "
                "population. The predicate and the claimed row count are "
                "recorded, and the population is ATTESTED rather than observed",
                "that the cluster ran the code the plan describes. This is a "
                "contract, not a sandbox",
            ],
            "replayable": (
                "yes, unlike an external observation — the metric is "
                "recomputed here from the submitted statistics whenever "
                "anybody asks, and the statistics are what was recorded"),
        }

    # ------------------------------------------------------------------ plan
    def plan(self, monitor_id: str, *, since: Optional[float] = None,
             until: Optional[float] = None,
             partitions: int = 64) -> Dict[str, Any]:
        """What a distributed job has to compute, for one monitor.

        The plan is the contract. It names the test, the statistics that test
        needs, the window, the partitioning, and — for a drift monitor — the
        **reference bin edges with a digest of the sample they came from**, so
        that a submission cannot quietly have measured against different edges.
        """
        monitor = self.monitors.registry.require(monitor_id) \
            if hasattr(self.monitors, "registry") else \
            self.monitors.require(monitor_id)
        test_key = monitor["test_key"]
        if test_key in NOT_DISTRIBUTABLE:
            raise MonitorError(
                "test_does_not_decompose",
                f"'{test_key}' cannot be computed from per-partition "
                f"statistics",
                NOT_DISTRIBUTABLE[test_key] + ". Evaluate it in-process over a "
                "sample, or record it as an external observation and accept "
                "that it cannot be replayed")
        if test_key not in DISTRIBUTABLE:
            raise MonitorError(
                "test_not_distributable",
                f"'{test_key}' has no distributed form in this register",
                f"the tests with one are {', '.join(sorted(DISTRIBUTABLE))}. "
                f"A metric approximated by a decomposition it does not have "
                f"would agree with the real one most of the time, which is the "
                f"worst property a control can have")
        spec = DISTRIBUTABLE[test_key]
        reference = self._reference(monitor, test_key)
        plan = {
            "monitor_id": monitor_id,
            "monitor": monitor["name"],
            "test_key": test_key,
            "window": {"since": since, "until": until},
            "partitions": max(1, int(partitions)),
            "returns": list(spec["needs"]),
            "why_these": spec["why"],
            "reference": reference,
            "global_ranking_required": test_key in (
                "discrimination.auc", "discrimination.gini"),
            "ks_buckets": KS_BUCKETS if test_key == "discrimination.ks" else None,
            "maya_runs_it": False,
        }
        plan["plan_digest"] = canonical_digest(plan)
        plan["detail"] = self._plan_detail(plan)
        return plan

    @staticmethod
    def _plan_detail(plan: Dict[str, Any]) -> str:
        out = (f"compute {', '.join(plan['returns'])} per partition and submit "
               f"them. MAYA computes {plan['test_key']} from those statistics "
               f"and compares it to the threshold this firm's second line set "
               f"— the scan moves, the judgement does not")
        if plan["global_ranking_required"]:
            out += (". **This test needs a GLOBAL ranking**: a rank sum over "
                    "one partition's rows is a rank sum in the wrong "
                    "ordering, and summing those produces a number that looks "
                    "like an AUC and is not. Rank across the whole window "
                    "first — a distributed sort — then sum the positives' "
                    "ranks per partition")
        if plan["reference"]:
            out += (f". The reference edges are fixed by the register and "
                    f"carry digest {plan['reference']['digest'][:16]}…; a "
                    f"submission quoting a different one is refused, because "
                    f"PSI against edges somebody else chose is a different "
                    f"measurement that prints the same")
        return out

    def _reference(self, monitor: Dict[str, Any],
                   test_key: str) -> Optional[Dict[str, Any]]:
        """Bin edges from the reference sample the register already holds."""
        if test_key != "stability.psi":
            return None
        sample = list((monitor.get("reference") or {}).get("sample") or [])
        bins = int((monitor.get("reference") or {}).get("bins") or 10)
        if len(sample) < bins:
            raise MonitorError(
                "reference_too_small",
                f"the monitor's reference sample holds {len(sample)} values "
                f"and {bins} bins need at least {bins}",
                "record a development distribution on the monitor. A "
                "distributed PSI has to measure against edges the register "
                "fixed, or every night's number is measured against that "
                "night's own data and the series means nothing")
        ordered = sorted(sample)
        edges = [ordered[round(q * (len(ordered) - 1) / bins)]
                 for q in range(1, bins)]
        shares = _shares(ordered, edges, bins)
        return {"bins": bins, "edges": edges, "expected_shares": shares,
                "digest": canonical_digest({"edges": edges, "bins": bins}),
                "from": "the monitor's declared reference sample"}

    # ------------------------------------------------------------- submission
    def submit(self, monitor_id: str, submission: Dict[str, Any], *,
               now: Optional[float] = None,
               actor: str = "system") -> Dict[str, Any]:
        """Take the statistics, compute the metric here, and judge it here.

        Everything wrong with a submission is reported at once and the whole
        submission is refused, for the reason a discovery sweep is: a partial
        acceptance produces a metric over the partitions that happened to be
        well-formed, which is a measurement of something nobody asked about.
        """
        plan = self.plan(monitor_id,
                         since=(submission.get("window") or {}).get("since"),
                         until=(submission.get("window") or {}).get("until"),
                         partitions=len(submission.get("partitions") or []) or 1)
        problems = self._check(plan, submission)
        if problems:
            raise MonitorError(
                "submission_does_not_meet_the_plan",
                f"{len(problems)} problem(s): "
                + "; ".join(p["what"] for p in problems),
                "fix them and resubmit. The submission is refused whole rather "
                "than in part, because a metric computed over the partitions "
                "that happened to be well-formed is a measurement of a "
                "population nobody chose")
        value = self._compute(plan, submission)
        rows = sum(int(p.get("rows") or 0)
                   for p in submission.get("partitions") or [])
        outcome = {
            "monitor_id": monitor_id, "test_key": plan["test_key"],
            "value": value,
            "rows_attested": rows,
            "partitions": len(submission.get("partitions") or []),
            "computed_by": "maya, from submitted statistics",
            "scanned_by": str(submission.get("engine") or "an external job"),
            "predicate": str(submission.get("predicate") or ""),
            "plan_digest": plan["plan_digest"],
            "replayable": True,
            "population_attested_not_observed": True,
            "at": now if now is not None else time.time(),
            "actor": actor,
        }
        outcome["detail"] = self._outcome_detail(outcome, plan)
        logger.info("distributed %s for monitor %s = %s over %d row(s)",
                    plan["test_key"], monitor_id, value, rows)
        return outcome

    @staticmethod
    def _outcome_detail(outcome: Dict[str, Any], plan: Dict[str, Any]) -> str:
        return (
            f"{plan['test_key']} = {outcome['value']:.4f}, computed HERE from "
            f"statistics over {outcome['partitions']} partition(s) and "
            f"{outcome['rows_attested']:,} attested row(s). The comparison "
            f"against the threshold is the register's, as it is for every "
            f"other monitor. What MAYA cannot see is whether the job read the "
            f"population it says it did: the predicate "
            f"{outcome['predicate'] or '(none given)'} and the row count are "
            f"recorded, and the population is attested rather than observed")

    # ---------------------------------------------------------------- checks
    def _check(self, plan: Dict[str, Any],
               submission: Dict[str, Any]) -> List[Dict[str, str]]:
        problems: List[Dict[str, str]] = []
        partitions = submission.get("partitions")
        if not isinstance(partitions, list) or not partitions:
            problems.append({"what": "submission.partitions is empty",
                             "why": "there is nothing to combine"})
            return problems
        if not submission.get("predicate"):
            problems.append({
                "what": "submission.predicate is missing",
                "why": "the one thing MAYA cannot check is whether the job "
                       "read the population it says it did, so what it read "
                       "has to be written down. An unstated predicate makes "
                       "the attestation unfalsifiable"})
        reference = plan.get("reference")
        if reference:
            quoted = str(submission.get("reference_digest") or "")
            if quoted != reference["digest"]:
                problems.append({
                    "what": "submission.reference_digest does not match the plan",
                    "why": "PSI against edges somebody else chose is a "
                           "different measurement, and the two print the same"})
        for index, part in enumerate(partitions):
            if not isinstance(part, dict):
                problems.append({"what": f"partitions[{index}] is not an object",
                                 "why": "each partition returns statistics"})
                continue
            for field in plan["returns"]:
                if part.get(field) is None:
                    problems.append({
                        "what": f"partitions[{index}].{field} is missing",
                        "why": DISTRIBUTABLE[plan["test_key"]]["why"]})
            if part.get("rows") is None:
                problems.append({
                    "what": f"partitions[{index}].rows is missing",
                    "why": "the row count is half of what makes the "
                           "population claim checkable against the telemetry "
                           "the register already holds"})
        if plan["global_ranking_required"] and not submission.get(
                "ranked_globally"):
            problems.append({
                "what": "submission.ranked_globally is not set",
                "why": "a rank sum over one partition's rows is a rank sum in "
                       "the wrong ordering. Summing those produces a number "
                       "that looks like an AUC and is not, and nothing in the "
                       "result would show it — so the job has to assert that "
                       "it ranked across the whole window"})
        return problems

    # --------------------------------------------------------- the arithmetic
    def _compute(self, plan: Dict[str, Any],
                 submission: Dict[str, Any]) -> float:
        """The metric, from the statistics. This is the part that stays here."""
        parts = submission["partitions"]
        test_key = plan["test_key"]
        if test_key == "stability.psi":
            return _psi_from_counts(plan["reference"], parts)
        if test_key in ("discrimination.auc", "discrimination.gini"):
            value = _auc_from_ranks(parts)
            return value if test_key == "discrimination.auc" else 2.0 * value - 1.0
        return _ks_from_quantiles(parts)


# ------------------------------------------------------------------ helpers
def _shares(sample: Sequence[float], edges: Sequence[float],
            bins: int) -> List[float]:
    floor = 1.0 / (bins * 10.0)
    counts = [0] * bins
    for value in sample:
        slot = 0
        while slot < len(edges) and value > edges[slot]:
            slot += 1
        counts[slot] += 1
    return [max(c / len(sample), floor) for c in counts]


def _psi_from_counts(reference: Dict[str, Any],
                     parts: Sequence[Dict[str, Any]]) -> float:
    """PSI from summed bin counts.

    The same arithmetic `core/validation/statistics.psi` does, over counts
    rather than over values — deliberately the same formula and the same
    empty-bin floor, because two implementations of one metric eventually
    disagree and the disagreement lands in a committee paper.
    """
    bins = reference["bins"]
    totals = [0.0] * bins
    for part in parts:
        counts = part["bin_counts"]
        if len(counts) != bins:
            raise MonitorError(
                "bin_count_mismatch",
                f"a partition returned {len(counts)} bins and the plan fixed "
                f"{bins}",
                "compute against the edges in the plan. Different bins is a "
                "different measurement")
        for index, count in enumerate(counts):
            totals[index] += float(count)
    rows = sum(totals)
    if rows <= 0:
        raise MonitorError(
            "no_rows_in_submission",
            "every partition returned zero rows",
            "check the window and the predicate. A PSI over nothing is not a "
            "PSI of zero")
    floor = 1.0 / (bins * 10.0)
    actual = [max(t / rows, floor) for t in totals]
    expected = reference["expected_shares"]
    return sum((a - e) * math.log(a / e) for e, a in zip(expected, actual))


def _auc_from_ranks(parts: Sequence[Dict[str, Any]]) -> float:
    """AUC by the Mann-Whitney identity, over a global ranking."""
    rank_sum = sum(float(p["rank_sum_positive"]) for p in parts)
    n_pos = sum(float(p["n_positive"]) for p in parts)
    n_neg = sum(float(p["n_negative"]) for p in parts)
    if n_pos <= 0 or n_neg <= 0:
        raise MonitorError(
            "one_class_absent",
            "the window holds only one class, so there is nothing to "
            "discriminate between",
            "widen the window. An AUC over one class is undefined rather than "
            "0.5, and reporting 0.5 would look like a model with no signal")
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def _ks_from_quantiles(parts: Sequence[Dict[str, Any]]) -> float:
    """KS from summed quantile buckets, with its precision stated.

    The buckets are bounded, so this is the KS **to bucket resolution** rather
    than the exact statistic. At `KS_BUCKETS` buckets the error is at most one
    bucket's width in each curve; over billions of rows that is far below any
    threshold anybody sets, and it is the honest description rather than a
    claim of exactness.
    """
    buckets = max(len(p["positive_quantiles"]) for p in parts)
    pos = [0.0] * buckets
    neg = [0.0] * buckets
    for part in parts:
        for index, value in enumerate(part["positive_quantiles"]):
            pos[index] += float(value)
        for index, value in enumerate(part["negative_quantiles"]):
            neg[index] += float(value)
    total_pos, total_neg = sum(pos), sum(neg)
    if total_pos <= 0 or total_neg <= 0:
        raise MonitorError(
            "one_class_absent",
            "the window holds only one class, so there is no gap to measure",
            "widen the window")
    best, cum_pos, cum_neg = 0.0, 0.0, 0.0
    for index in range(buckets):
        cum_pos += pos[index] / total_pos
        cum_neg += neg[index] / total_neg
        best = max(best, abs(cum_pos - cum_neg))
    return best
