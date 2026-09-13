"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — submitting a distributed evaluation.

The scan moves off the platform; the arithmetic from statistics to metric, the
reference, the threshold and the comparison all stay here. That split is what
makes this different from ingesting a number somebody else computed — and it
is why **a metric that does not decompose is refused by name**, because
approximating one would produce a number that agrees with the real one most of
the time, which is the worst property a control can have.

The submission is refused **whole**, never in part: a metric computed over the
partitions that happened to be well-formed is a measurement of a population
nobody chose. And every problem is reported at once, so a job is fixed in one
pass rather than discovering its faults one submission at a time.

The one thing MAYA cannot check is whether the job read the population it says
it did. So the predicate and the row count are written down, and the result
says the population was **attested rather than observed**.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)
from qa.regression_suite.scenarios.h_distributed import (MONITORS, _id,
                                                         _monitor, _plan,
                                                         _submit)


def _psi(ctx: Ctx):
    """A PSI monitor and its plan — the decomposable case everything else
    here is measured against."""
    made = _monitor(ctx)
    if made.status_code >= 400:
        return "", {}
    monitor_id = _id(made)
    got = _plan(ctx, monitor_id)
    return (monitor_id, got.json() or {}) if got.status_code < 400 \
        else (monitor_id, {})


def _counts(plan: dict, rows: int = 1000) -> list:
    bins = len(plan["reference"]["expected_shares"])
    each = rows // bins
    return [each] * bins


def _body(plan: dict, **over) -> dict:
    body = {"predicate": "WHERE scored_at >= :since AND scored_at < :until",
            "engine": "spark-3.5",
            "reference_digest": plan["reference"]["digest"],
            "partitions": [{"rows": 1000, "bin_counts": _counts(plan)}]}
    body.update(over)
    return body


@case("QA-AM-264", "Submit with no `predicate`")
def am_264(ctx: Ctx) -> Result:
    """The one thing MAYA cannot check is whether the job read the population
    it says it did, so what it read has to be written down. An unstated
    predicate makes the attestation unfalsifiable."""
    monitor_id, plan = _psi(ctx)
    if not plan:
        return BLOCKED, "the plan could not be issued"
    got = _submit(ctx, monitor_id, **_body(plan, predicate=""))
    if got.status_code < 400:
        return FAIL, ("a submission with no predicate was accepted, so the "
                      "population claim cannot be falsified by anybody")
    if code_of(got) != "submission_does_not_meet_the_plan":
        return FAIL, f"refused '{code_of(got)}'"
    if "predicate" not in got.text:
        return FAIL, "the refusal does not name the predicate"
    return PASS, "refused, naming the missing predicate"


@case("QA-AM-261", "Submit with a `reference_digest` from a different monitor")
def am_261(ctx: Ctx) -> Result:
    """PSI against edges somebody else chose is a different measurement, and
    the two print the same. The digest is the only thing that tells them
    apart."""
    monitor_id, plan = _psi(ctx)
    # A DIFFERENT reference sample, or the two monitors digest identically and
    # the case cannot tell them apart.
    made = _monitor(ctx, reference={"sample": [float(n) * 3.0 + 7.0
                                               for n in range(100)],
                                    "bins": 10})
    if made.status_code >= 400:
        return BLOCKED, f"the second monitor failed: {made.text[:140]}"
    got_other = _plan(ctx, _id(made))
    other = got_other.json() or {} if got_other.status_code < 400 else {}
    if not (plan and other):
        return BLOCKED, "the two plans could not be issued"
    if plan["reference"]["digest"] == other["reference"]["digest"]:
        return BLOCKED, ("the two monitors share a reference digest, so this "
                         "run cannot tell them apart")
    got = _submit(ctx, monitor_id,
                  **_body(plan, reference_digest=other["reference"]["digest"]))
    if got.status_code < 400:
        return FAIL, ("a PSI was computed against another monitor's bin "
                      "edges: a different measurement, printing the same")
    if code_of(got) != "submission_does_not_meet_the_plan":
        return FAIL, f"refused '{code_of(got)}'"
    if "reference_digest" not in got.text:
        return FAIL, "the refusal does not name the digest"
    return PASS, "refused, naming the reference digest"


@case("QA-AM-265", "Submit with three partitions, one of them missing `rows`")
def am_265(ctx: Ctx) -> Result:
    """Every problem reported at once, and the partition INDEX named — a job
    told only that something is missing has to bisect its own output."""
    monitor_id, plan = _psi(ctx)
    if not plan:
        return BLOCKED, "the plan could not be issued"
    parts = [{"rows": 1000, "bin_counts": _counts(plan)},
             {"bin_counts": _counts(plan)},
             {"rows": 1000, "bin_counts": _counts(plan)}]
    got = _submit(ctx, monitor_id, **_body(plan, partitions=parts))
    if got.status_code < 400:
        return FAIL, ("a submission with a partition missing its row count "
                      "was accepted, so the population claim covers fewer "
                      "rows than it says")
    if code_of(got) != "submission_does_not_meet_the_plan":
        return FAIL, f"refused '{code_of(got)}'"
    if "partitions[1]" not in got.text:
        return FAIL, (f"the refusal does not name which partition is wrong: "
                      f"{got.text[:150]}")
    return PASS, "refused, naming partitions[1].rows"


@case("QA-AM-266", "Submit with a partition returning the wrong number of bins")
def am_266(ctx: Ctx) -> Result:
    """Different bins is a different measurement. The plan fixes the count
    and the refusal has to say both numbers, or the job cannot tell whether
    it computed too many or too few."""
    monitor_id, plan = _psi(ctx)
    if not plan:
        return BLOCKED, "the plan could not be issued"
    short = _counts(plan)[:-1]
    got = _submit(ctx, monitor_id,
                  **_body(plan, partitions=[{"rows": 900,
                                             "bin_counts": short}]))
    if got.status_code < 400:
        return FAIL, ("a partition returning the wrong number of bins was "
                      "accepted, so the PSI is over edges nobody agreed")
    if code_of(got) != "bin_count_mismatch":
        return FAIL, f"refused '{code_of(got)}'"
    bins = len(plan["reference"]["expected_shares"])
    if str(bins) not in got.text or str(len(short)) not in got.text:
        return FAIL, (f"the refusal does not give both counts "
                      f"({len(short)} submitted against {bins} planned)")
    return PASS, f"refused 'bin_count_mismatch', {len(short)} against {bins}"


@case("QA-AM-267", "Submit where every partition returns zero rows")
def am_267(ctx: Ctx) -> Result:
    """A PSI over nothing is not a PSI of zero. Returning zero would read as
    a model whose distribution has not moved at all, which is the most
    reassuring answer available and the least true."""
    monitor_id, plan = _psi(ctx)
    if not plan:
        return BLOCKED, "the plan could not be issued"
    bins = len(plan["reference"]["expected_shares"])
    got = _submit(ctx, monitor_id,
                  **_body(plan, partitions=[{"rows": 0,
                                             "bin_counts": [0] * bins},
                                            {"rows": 0,
                                             "bin_counts": [0] * bins}]))
    if got.status_code < 400:
        value = (got.json() or {}).get("value")
        return FAIL, (f"a PSI of {value} was computed over zero rows, which "
                      f"reads as a distribution that has not moved")
    if code_of(got) != "no_rows_in_submission":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'no_rows_in_submission'"


@case("QA-AM-262", "Submit for AUC without `ranked_globally`")
def am_262(ctx: Ctx) -> Result:
    """A rank sum over one partition's rows is a rank sum in the wrong
    ordering. Summing those produces a number that LOOKS like an AUC and is
    not, and nothing in the result would show it — so the job has to assert
    that it ranked across the whole window."""
    made = _monitor(ctx, test_key="discrimination.auc")
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    monitor_id = _id(made)
    got_plan = _plan(ctx, monitor_id)
    if got_plan.status_code >= 400:
        return BLOCKED, f"no plan for AUC: {got_plan.text[:140]}"
    plan = got_plan.json() or {}
    if not plan.get("global_ranking_required"):
        return FAIL, ("an AUC plan does not require a global ranking, so "
                      "per-partition rank sums add to a number that is not "
                      "an AUC and nothing says so")
    got = _submit(ctx, monitor_id,
                  predicate="WHERE scored_at >= :since",
                  engine="spark-3.5",
                  partitions=[{"rows": 1000, "rank_sum_positive": 260_000.0,
                               "n_positive": 400, "n_negative": 600}])
    if got.status_code < 400:
        return FAIL, ("an AUC was computed from rank sums with no assertion "
                      "that the ranking was global")
    if code_of(got) != "submission_does_not_meet_the_plan":
        return FAIL, f"refused '{code_of(got)}'"
    if "ranked_globally" not in got.text:
        return FAIL, "the refusal does not name what is missing"
    return PASS, "refused, naming ranked_globally"


@case("QA-AM-263",
      "Submit with `ranked_globally: true` but per-partition ranks")
def am_263(ctx: Ctx) -> Result:
    """Accepted, because MAYA cannot check the claim — and the value of the
    case is that the platform does not pretend to. What it must do is record
    the assertion, so the number is traceable to the job that made it."""
    made = _monitor(ctx, test_key="discrimination.auc")
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    monitor_id = _id(made)
    got_plan = _plan(ctx, monitor_id)
    if got_plan.status_code >= 400:
        return BLOCKED, f"no plan for AUC: {got_plan.text[:140]}"
    got = _submit(ctx, monitor_id,
                  predicate="WHERE scored_at >= :since",
                  engine="spark-3.5", ranked_globally=True,
                  partitions=[{"rows": 500, "rank_sum_positive": 60_000.0,
                               "n_positive": 200, "n_negative": 300},
                              {"rows": 500, "rank_sum_positive": 60_000.0,
                               "n_positive": 200, "n_negative": 300}])
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — MAYA cannot tell a global "
                      f"ranking from a per-partition one, so refusing here "
                      f"would be refusing on a fact it does not have")
    body = got.json() or {}
    if not body.get("population_attested_not_observed"):
        return FAIL, ("the result does not say the population was attested "
                      "rather than observed, so a number resting on a claim "
                      "reads like one resting on a measurement")
    if "spark-3.5" not in f"{body}":
        return FAIL, "the engine that made the claim is not recorded"
    return PASS, (f"accepted at {body.get('value')}, attested not observed, "
                  f"scanned by {body.get('scanned_by')}")


@case("QA-AM-268", "Submit an AUC where every row is one class")
def am_268(ctx: Ctx) -> Result:
    """An AUC over one class is undefined rather than 0.5, and reporting 0.5
    would look like a model with no signal — which is a real and different
    finding somebody would act on."""
    made = _monitor(ctx, test_key="discrimination.auc")
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    monitor_id = _id(made)
    if _plan(ctx, monitor_id).status_code >= 400:
        return BLOCKED, "no plan for AUC"
    got = _submit(ctx, monitor_id,
                  predicate="WHERE scored_at >= :since",
                  engine="spark-3.5", ranked_globally=True,
                  partitions=[{"rows": 1000, "rank_sum_positive": 500_500.0,
                               "n_positive": 1000, "n_negative": 0}])
    if got.status_code < 400:
        value = (got.json() or {}).get("value")
        return FAIL, (f"an AUC of {value} was computed over a window holding "
                      f"one class; 0.5 reads as a model with no signal")
    if code_of(got) != "one_class_absent":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'one_class_absent'"


@case("QA-AM-269",
      "Submit a KS where `negative_quantiles` is longer than "
      "`positive_quantiles`")
def am_269(ctx: Ctx) -> Result:
    """The recorded defect: `max(len(positive))` meant a partition whose
    negative quantiles were longer walked off the end and raised an
    IndexError — an unhandled 500 on a submission endpoint an external job
    calls nightly."""
    made = _monitor(ctx, test_key="discrimination.ks")
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    monitor_id = _id(made)
    got_plan = _plan(ctx, monitor_id)
    if got_plan.status_code >= 400:
        return BLOCKED, f"no plan for KS: {got_plan.text[:140]}"
    got = _submit(ctx, monitor_id,
                  predicate="WHERE scored_at >= :since",
                  engine="spark-3.5",
                  partitions=[{"rows": 100,
                               "positive_quantiles": [10, 20, 30],
                               "negative_quantiles": [10, 20, 30, 40, 50]}])
    if got.status_code >= 500:
        return FAIL, (f"a ragged quantile submission answered "
                      f"{got.status_code} with no code: an external job "
                      f"calling this nightly gets an unhandled error")
    if got.status_code < 400:
        return FAIL, ("a KS was computed from quantile lists of different "
                      "lengths, so the two distributions were compared at "
                      "points that do not correspond")
    if code_of(got) != "quantiles_ragged":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'quantiles_ragged', not a 500"


@case("QA-AM-270",
      "Compare the `plan_digest` in a submission against the plan that was "
      "issued")
def am_270(ctx: Ctx) -> Result:
    """EXPLORATORY. The digest is recomputed at submit time from the monitor
    and the window rather than checked against the plan the job was given —
    so a monitor whose threshold or reference changed between plan and submit
    produces a submission judged against a plan nobody issued, and the digest
    on the outcome records the NEW one."""
    monitor_id, plan = _psi(ctx)
    if not plan:
        return BLOCKED, "the plan could not be issued"
    issued = plan.get("plan_digest")
    if not issued:
        return FAIL, "the plan carries no digest"
    planned = int(plan.get("partitions") or 1)
    parts = [{"rows": 1000, "bin_counts": _counts(plan)} for _ in range(planned)]
    matched = _submit(ctx, monitor_id, **_body(plan, partitions=parts))
    if matched.status_code >= 400:
        return BLOCKED, (f"a submission at the planned partition count was "
                         f"refused: {matched.text[:140]}")
    if (matched.json() or {}).get("plan_digest") != issued:
        return FAIL, (f"a submission matching the issued plan in every "
                      f"respect records a different plan digest: "
                      f"{(matched.json() or {}).get('plan_digest')} against "
                      f"{issued}")
    # It agrees only when the job partitions exactly as the plan defaulted.
    fewer = _submit(ctx, monitor_id, **_body(plan))
    if fewer.status_code >= 400:
        return BLOCKED, f"the single-partition submission failed: {fewer.text[:140]}"
    other = (fewer.json() or {}).get("plan_digest")
    if other == issued:
        return PASS, ("the plan digest identifies the plan regardless of how "
                      "the job partitioned its scan")
    return FAIL, (f"the plan digest is recomputed at submit time and the "
                  f"SUBMISSION's partition count is inside the digested plan, "
                  f"so a job that splits its scan differently from the "
                  f"{planned} the plan defaulted to records digest {other} "
                  f"against the issued {issued}. The digest exists to tie a "
                  f"submission to the plan it was computed against, and how "
                  f"many partitions the job chose is not part of what the "
                  f"plan asked for")


@case("QA-AM-272", "Submit the same statistics twice")
def am_272(ctx: Ctx) -> Result:
    """Two submissions of one window. Whatever the platform does with them,
    it must not record two observations for one measurement — and since
    QA-AM-1313 established that `submit` records nothing at all, this case
    also pins that the outcome is at least deterministic."""
    monitor_id, plan = _psi(ctx)
    if not plan:
        return BLOCKED, "the plan could not be issued"
    first = _submit(ctx, monitor_id, **_body(plan))
    if first.status_code >= 400:
        return BLOCKED, f"the first submission failed: {first.text[:140]}"
    second = _submit(ctx, monitor_id, **_body(plan))
    if second.status_code >= 400:
        return PASS, (f"the second submission of one window is refused "
                      f"'{code_of(second)}'")
    one, two = first.json() or {}, second.json() or {}
    if one.get("value") != two.get("value"):
        return FAIL, (f"the same statistics produced {one.get('value')} then "
                      f"{two.get('value')}")
    if one.get("plan_digest") != two.get("plan_digest"):
        return FAIL, "the same window produced two different plan digests"
    history = ctx.api.get(f"{MONITORS}/{monitor_id}/observations",
                          auth=ctx.people["risk"])
    rows = (history.json() or {}).get("observations") or [] \
        if history.status_code < 400 else []
    if len(rows) > 1:
        return FAIL, (f"two submissions of one window left {len(rows)} "
                      f"observations, so a retried job doubles the record")
    return PASS, (f"identical value and digest; {len(rows)} observation(s) "
                  f"recorded — see QA-AM-1313 for why that is zero")
