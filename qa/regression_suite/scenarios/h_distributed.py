"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — distributed evaluation: the scan moves, the judgement must not.

The design claim is precise and worth testing exactly as written: a submission
carrying `psi: 0.31` is an external observation wearing a better name, while
one carrying bin counts is a measurement this register redoes. So the cases
push on both halves — that statistics are accepted and verdicts are not, and
that what comes back is judged here rather than merely arithmetic'd here.
"""
from __future__ import annotations

from core.monitoring.common import ADMISSIBLE_TESTS, INPUT_DRIFT, PERFORMANCE
from core.monitoring.distributed import DISTRIBUTABLE, NOT_DISTRIBUTABLE
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

MONITORS = "/api/v1/monitors"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
#: A reference wide enough for ten bins, and an actual that sits well away
#: from it so a PSI computed honestly is large.
REFERENCE = [float(n) for n in range(100)]


def _monitor(ctx: Ctx, test_key: str = "stability.psi", **over):
    name = ctx.unique("dm")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "owner", **TIER})
    # The kind is not free text and `drift` is not one of them: a monitor
    # pairing a kind with a test that means nothing for it is a definition
    # error, refused when the monitor is defined. The kind is derived from
    # the test rather than passed in, so a case cannot drift from the
    # catalogue.
    kind = next(k for k, tests in ADMISSIBLE_TESTS.items()
                if test_key in tests)
    body = {"urn": urn, "name": f"{name}-monitor", "kind": kind,
            "test_key": test_key, "owner": "owner",
            # A label-dependent kind has to declare how long outcomes take.
            "label_delay_days": 0.0 if kind == INPUT_DRIFT else 30.0,
            "threshold": {"warn": 0.1, "breach": 0.25},
            "reference": {"sample": REFERENCE, "bins": 10}}
    body.update(over)
    made = ctx.api.post(MONITORS, json=body, auth=ctx.people["risk"])
    return made


def _id(made) -> str:
    body = made.json()
    return body.get("id") or body.get("monitor_id") or ""


def _plan(ctx: Ctx, monitor_id: str):
    return ctx.api.get(f"{MONITORS}/{monitor_id}/distributed-plan",
                       auth=ctx.people["risk"])


def _submit(ctx: Ctx, monitor_id: str, **body):
    # `monitor:evaluate` is the OWNER's permission, not the risk manager's.
    # Submitting as `risk` answers `forbidden` — a refusal, and therefore a
    # pass, for every case here that only checked the status code.
    return ctx.api.post(f"{MONITORS}/{monitor_id}/distributed-submit",
                        json=body, auth=ctx.people["owner"])


def _breaching(plan) -> list:
    """Bin counts piled into the top bin: a PSI far above any threshold."""
    bins = len(plan["reference"]["expected_shares"])
    counts = [0] * bins
    counts[-1] = 1_000_000
    return [{"rows": 1_000_000, "bin_counts": counts}]


@case("QA-AM-1300", "A test that does not decompose is refused by name")
def am_1300(ctx: Ctx) -> Result:
    """Naming it is the point: the alternative is a caller discovering that
    their nightly sweep silently skipped a third of the estate."""
    key = next(k for k in sorted(NOT_DISTRIBUTABLE)
               if any(k in tests for tests in ADMISSIBLE_TESTS.values()))
    made = _monitor(ctx, test_key=key)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = _plan(ctx, _id(made))
    if got.status_code < 400:
        return FAIL, f"a distributed plan was issued for '{key}'"
    if code_of(got) != "test_does_not_decompose":
        return FAIL, f"refused '{code_of(got)}', not by name: {got.text[:150]}"
    if key not in got.text:
        return FAIL, "the refusal does not name the test"
    return PASS, f"refused 'test_does_not_decompose' for {key}"


@case("QA-AM-1301", "A test with no distributed form at all")
def am_1301(ctx: Ctx) -> Result:
    # In the catalogue, admissible for its kind, and with no distributed
    # form — the three things that make this case about the right refusal.
    key = next(k for k in ADMISSIBLE_TESTS[PERFORMANCE]
               if k not in DISTRIBUTABLE and k not in NOT_DISTRIBUTABLE)
    made = _monitor(ctx, test_key=key)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = _plan(ctx, _id(made))
    if got.status_code < 400:
        return FAIL, "a plan was issued for a test with no distributed form"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-1302", "A PSI plan against a reference too small to bin")
def am_1302(ctx: Ctx) -> Result:
    """Measuring each night against that night's own data makes the series
    mean nothing, so a monitor with no fixed reference cannot be distributed.
    """
    made = _monitor(ctx, reference={"sample": [1.0, 2.0], "bins": 10})
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = _plan(ctx, _id(made))
    if got.status_code < 400:
        return FAIL, "a PSI plan was issued with no reference to measure against"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-1303", "The plan fixes the reference edges and digests them")
def am_1303(ctx: Ctx) -> Result:
    made = _monitor(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = _plan(ctx, _id(made))
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    ref = got.json().get("reference") or {}
    if not ref.get("edges") or not ref.get("digest"):
        return FAIL, ("the plan does not fix the bin edges, so a submission "
                      "may have measured against edges it chose itself")
    return PASS, f"{len(ref['edges'])} edges under digest {ref['digest'][:12]}"


@case("QA-AM-1304", "A submission quoting different reference edges")
def am_1304(ctx: Ctx) -> Result:
    """PSI against edges somebody else chose is a different measurement that
    prints the same."""
    made = _monitor(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    mid = _id(made)
    plan = _plan(ctx, mid)
    if plan.status_code >= 400:
        return BLOCKED, plan.text[:170]
    return refused_by_the_control(
        _submit(ctx, mid, partitions=_breaching(plan.json()),
                reference_digest="0" * 64, engine="qa"),
        "a submission measured against edges the register did not fix was "
        "accepted")


@case("QA-AM-1305", "A submission carrying the metric instead of statistics")
def am_1305(ctx: Ctx) -> Result:
    """The whole distinction from an external observation."""
    made = _monitor(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    mid = _id(made)
    plan = _plan(ctx, mid)
    if plan.status_code >= 400:
        return BLOCKED, plan.text[:170]
    return refused_by_the_control(
        _submit(ctx, mid, engine="qa",
                reference_digest=plan.json()["reference"]["digest"],
                partitions=[{"rows": 1000, "psi": 0.31}]),
        "a partition supplied a computed metric and it was accepted; that is "
        "an external observation wearing a better name")


@case("QA-AM-1306", "A submission with no partitions")
def am_1306(ctx: Ctx) -> Result:
    made = _monitor(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    mid = _id(made)
    plan = _plan(ctx, mid)
    if plan.status_code >= 400:
        return BLOCKED, plan.text[:170]
    return refused_by_the_control(
        _submit(ctx, mid, partitions=[], engine="qa",
                reference_digest=plan.json()["reference"]["digest"]),
        "a metric was computed over nothing at all")


@case("QA-AM-1307", "A bad submission is refused whole, not in part")
def am_1307(ctx: Ctx) -> Result:
    """A metric over the partitions that happened to be well-formed is a
    measurement of a population nobody chose — so every problem is reported
    at once and nothing is accepted."""
    made = _monitor(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    mid = _id(made)
    plan = _plan(ctx, mid)
    if plan.status_code >= 400:
        return BLOCKED, plan.text[:170]
    good = _breaching(plan.json())[0]
    got = _submit(ctx, mid, engine="qa",
                  reference_digest=plan.json()["reference"]["digest"],
                  partitions=[good, {"rows": 10}, {"rows": 5,
                                                   "bin_counts": [1, 2]}])
    if got.status_code < 400:
        return FAIL, "a submission with malformed partitions was accepted"
    if code_of(got) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the check"
    if code_of(got) != "submission_does_not_meet_the_plan":
        return FAIL, f"refused '{code_of(got)}': {got.text[:150]}"
    if "2 problem" not in got.text and "problem(s)" not in got.text:
        return FAIL, "the refusal does not report every problem at once"
    return PASS, f"refused whole: {got.json().get('detail', '')[:90]}"


@case("QA-AM-1308", "AUC needs a global ranking and the plan says so")
def am_1308(ctx: Ctx) -> Result:
    """A rank sum over one partition is a rank sum in the wrong ordering, and
    summing those produces a number that looks like an AUC and is not."""
    made = _monitor(ctx, test_key="discrimination.auc")
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = _plan(ctx, _id(made))
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    plan = got.json()
    if not plan.get("global_ranking_required"):
        return FAIL, ("the AUC plan does not demand a global ranking, so a "
                      "per-partition rank sum would be summed into a number "
                      "that looks like an AUC and is not")
    return PASS, "global ranking demanded, and the reason is in the plan"


@case("QA-AM-1309", "An AUC submission that was not ranked globally")
def am_1309(ctx: Ctx) -> Result:
    made = _monitor(ctx, test_key="discrimination.auc")
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    mid = _id(made)
    return refused_by_the_control(
        _submit(ctx, mid, engine="qa", ranked_globally=False,
                partitions=[{"rows": 100, "rank_sum_positive": 3000,
                             "n_positive": 40, "n_negative": 60}]),
        "a rank sum in an unknown ordering was accepted as an AUC")


@case("QA-AM-1310", "The distributable list is published, not documented")
def am_1310(ctx: Ctx) -> Result:
    got = ctx.api.get("/api/v1/distributed-evaluation", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json()
    named = {e.get("test") for e in body.get("distributable") or []}
    refused = {e.get("test") for e in body.get("not_distributable") or []}
    if named != set(DISTRIBUTABLE):
        return FAIL, "the published distributable list is not the enforced one"
    if refused != set(NOT_DISTRIBUTABLE):
        return FAIL, ("the published not-distributable list is not the one "
                      "the plan refuses by")
    return PASS, f"{len(named)} distributable, {len(refused)} refused by name"


@case("QA-AM-1311", "The answer says the population is attested, not observed")
def am_1311(ctx: Ctx) -> Result:
    """A WHERE clause that quietly excluded a segment produces statistics
    that are arithmetically perfect and describe the wrong population."""
    made = _monitor(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    mid = _id(made)
    plan = _plan(ctx, mid)
    if plan.status_code >= 400:
        return BLOCKED, plan.text[:170]
    got = _submit(ctx, mid, engine="qa-spark", predicate="ledger = 'UK'",
                  reference_digest=plan.json()["reference"]["digest"],
                  partitions=_breaching(plan.json()))
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json()
    if not body.get("population_attested_not_observed"):
        return FAIL, "the outcome does not say the population is attested"
    if body.get("predicate") != "ledger = 'UK'":
        return FAIL, "the partition predicate was not recorded"
    return PASS, "attested-not-observed, with the predicate on the record"


@case("QA-AM-1312", "A distributed breach is judged, not just computed")
def am_1312(ctx: Ctx) -> Result:
    """`posture()` publishes `maya_compares_to_the_threshold: true`, and the
    plan tells the caller MAYA "compares it to the threshold this firm's
    second line set". A submission far above the breach threshold should
    therefore come back as a breach, not as a bare number.
    """
    made = _monitor(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    mid = _id(made)
    plan = _plan(ctx, mid)
    if plan.status_code >= 400:
        return BLOCKED, plan.text[:170]
    got = _submit(ctx, mid, engine="qa", predicate="ledger = 'UK'",
                  reference_digest=plan.json()["reference"]["digest"],
                  partitions=_breaching(plan.json()))
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json()
    if body.get("value") is None:
        return FAIL, "no value came back"
    verdict = {k: body[k] for k in ("breached", "status", "outcome", "severity",
                                    "threshold") if k in body}
    if not verdict:
        return FAIL, (
            "the submission computed %s and the outcome carries no comparison "
            "to the threshold at all — no breach, no status, not even the "
            "threshold it was supposedly compared against. `posture()` "
            "publishes `maya_compares_to_the_threshold: true` and the plan "
            "tells the caller the judgement stays here; the arithmetic stays "
            "here and the judgement does not happen"
            % round(float(body["value"]), 4))
    return PASS, f"judged: {verdict}"


@case("QA-AM-1313", "A distributed evaluation reaches the monitor's history")
def am_1313(ctx: Ctx) -> Result:
    """A number returned as JSON and recorded nowhere is not a monitoring
    observation; nothing can escalate it, and next month nobody can show the
    sweep ran."""
    made = _monitor(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    mid = _id(made)
    plan = _plan(ctx, mid)
    if plan.status_code >= 400:
        return BLOCKED, plan.text[:170]
    sent = _submit(ctx, mid, engine="qa", predicate="ledger = 'UK'",
                   reference_digest=plan.json()["reference"]["digest"],
                   partitions=_breaching(plan.json()))
    if sent.status_code >= 400:
        return BLOCKED, sent.text[:170]
    seen = ctx.api.get(f"{MONITORS}/{mid}/observations", auth=ctx.people["risk"])
    if seen.status_code >= 400:
        seen = ctx.api.get(f"{MONITORS}/{mid}", auth=ctx.people["risk"])
        if seen.status_code >= 400:
            return BLOCKED, seen.text[:170]
    if "qa" not in seen.text and str(round(float(sent.json()["value"]), 2))[:4] \
            not in seen.text:
        return FAIL, ("the submitted evaluation left no trace on the monitor; "
                      "the estate-wide sweep computes numbers the register "
                      "does not keep")
    return PASS, "the observation is on the monitor"


@case("QA-AM-1314", "Every test refused by name can actually be defined")
def am_1314(ctx: Ctx) -> Result:
    """`NOT_DISTRIBUTABLE` is published as the list of tests that do not
    decompose. A member of it that no monitor can hold is a refusal that can
    never fire, documenting a control nobody reaches.
    """
    admissible = {t for tests in ADMISSIBLE_TESTS.values() for t in tests}
    unreachable = sorted(set(NOT_DISTRIBUTABLE) - admissible)
    if unreachable:
        return FAIL, (
            "published as not-distributable but absent from the test "
            "catalogue, so no monitor can ever carry it and the refusal can "
            "never fire: " + ", ".join(unreachable))
    return PASS, f"all {len(NOT_DISTRIBUTABLE)} are definable tests"


@case("QA-AM-1315", "Every distributable test can actually be defined")
def am_1315(ctx: Ctx) -> Result:
    admissible = {t for tests in ADMISSIBLE_TESTS.values() for t in tests}
    unreachable = sorted(set(DISTRIBUTABLE) - admissible)
    if unreachable:
        return FAIL, ("published as distributable and not in the catalogue: "
                      + ", ".join(unreachable))
    return PASS, f"all {len(DISTRIBUTABLE)} are definable tests"
