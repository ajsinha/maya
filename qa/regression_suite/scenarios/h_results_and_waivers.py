"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — what a recorded test result has to be, and what a waiver has to
carry.

Two subjects, one shape between them: both produce a row that somebody later
reads as evidence, and both have a way of producing a row that LOOKS like
evidence and is not. A test reported over nothing is a number with no sample
behind it; a waiver with no end date is not an exception but a decision to stop
applying a control, recorded as though it were temporary.
"""
from __future__ import annotations

from core.waivers.register import WAIVABLE
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of,
                                                  refused_by_the_control)

V = "/api/v1/validations"
W = "/api/v1/waivers"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
TIER_ONE = {"exposure": 5_000_000_000.0, "purpose_class": "credit_decision",
            "feature_count": 400, "interpretable": False,
            "uses_alternative_data": True}


def _versioned(ctx: Ctx) -> str:
    name = ctx.unique("rw")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    return urn


def _episode(ctx: Ctx) -> str:
    got = ctx.api.post(V, json={"urn": _versioned(ctx), "semver": "1.0.0",
                                "validators": ["validator"], "kind": "initial"})
    return (got.json() or {}).get("id", "") if got.status_code < 400 else ""


def _record(ctx: Ctx, episode: str, **over):
    body = {"test_key": "discrimination.auc",
            "left": [0, 1, 0, 1, 1, 0, 1, 0],
            "right": [0.1, 0.9, 0.2, 0.8, 0.7, 0.3, 0.95, 0.05],
            "threshold": {"min": 0.6}}
    body.update(over)
    return ctx.api.post(f"{V}/{episode}/results", json=body,
                        auth=ctx.people["validator"])


# --------------------------------------------------------------- results
@case("QA-AM-740", "The test catalogue is published")
def am_740(ctx: Ctx) -> Result:
    """A validation is only meaningful if the tests it ran are named,
    versioned things rather than a validator's notebook — and that claim rests
    on the catalogue being readable by the person reading the result."""
    from core.validation.catalogue import TESTS
    got = ctx.api.get("/api/v1/test-catalogue")
    if got.status_code == 404:
        got = ctx.api.get("/api/v1/tests")
    if got.status_code >= 400:
        return FAIL, (f"the test catalogue is not published over the API "
                      f"({got.status_code}), so a reader handed a result "
                      f"naming `discrimination.auc` has nowhere to find out "
                      f"what that is or which way is better")
    body = got.json() or {}
    rows = body.get("tests") or body.get("catalogue") or []
    named = {r.get("key") for r in rows}
    absent = sorted({t.key for t in TESTS} - named)
    if absent:
        return FAIL, f"these tests can be run and are not published: {absent}"
    silent = [r.get("key") for r in rows if not r.get("direction")]
    if silent:
        return FAIL, (f"{silent} are published without a direction, so a "
                      f"reader cannot tell whether a high number is good")
    return PASS, f"{len(rows)} test(s), each with its direction"


@case("QA-AM-741", "A result naming a test that is not in the catalogue")
def am_741(ctx: Ctx) -> Result:
    """The refusal has to list what exists. A validator who mistyped
    `discrimination.gini` needs the vocabulary, not a no."""
    episode = _episode(ctx)
    if not episode:
        return BLOCKED, "no validation episode could be opened"
    got = _record(ctx, episode, test_key="discrimination.made_up")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, ("a result was recorded against a test the catalogue does "
                      "not hold, so the episode cites a measurement nothing "
                      "can reproduce")
    if "discrimination.auc" not in got.text:
        return FAIL, (f"refused '{code_of(got)}' without naming the tests that "
                      f"do exist")
    return PASS, f"refused '{code_of(got)}', listing the catalogue"


@case("QA-AM-742", "A result whose two series are different lengths")
def am_742(ctx: Ctx) -> Result:
    """A label and a score belong to the same observation, so unequal lengths
    mean the caller has lost the pairing. Truncating to the shorter one is the
    defect this refusal exists for: the drift monitor did exactly that and
    reported a PSI of 3.54 as 0.023, passing, while its own detail line
    claimed all 5,200 observations had been used."""
    episode = _episode(ctx)
    if not episode:
        return BLOCKED, "no validation episode could be opened"
    got = _record(ctx, episode, left=[0, 1, 0, 1], right=[0.1, 0.9])
    answer = refused_by_the_control(
        got, "a paired test was recorded over series of different lengths, so "
             "the pairing was lost and whatever was computed is about "
             "observations that were never together")
    if answer[0] != PASS:
        return answer
    if "align" not in got.text and "same observation" not in got.text:
        return FAIL, (f"refused '{code_of(got)}' without saying that a label "
                      f"and a score belong to the same observation")
    return PASS, f"refused '{code_of(got)}', naming the pairing"


@case("QA-AM-743", "A result with empty series")
def am_743(ctx: Ctx) -> Result:
    """The sharpest of the three, because it is the one that can pass.

    Both series empty are the same length, so the pairing check is satisfied.
    Every statistic in the catalogue returns None on an empty sample rather
    than a number — "not computable on this sample is a real answer and 0.0 is
    a lie" — so what must never happen is a recorded row carrying a VALUE and
    a verdict over no observations at all.
    """
    episode = _episode(ctx)
    if not episode:
        return BLOCKED, "no validation episode could be opened"
    got = _record(ctx, episode, left=[], right=[])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}' before anything was recorded"
    body = got.json() or {}
    row = body.get("result") or body
    value, passed = row.get("value"), row.get("passed")
    if value is not None:
        return FAIL, (f"a test over ZERO observations recorded a value of "
                      f"{value}, so a metric computed from nothing reads on "
                      f"the episode exactly like a metric")
    if passed:
        return FAIL, ("a test over zero observations is recorded as PASSED "
                      "with no value, so an episode can be completed by "
                      "running every test over an empty sample")
    detail = str(row.get("detail") or "")
    if "not computable" not in detail:
        return FAIL, (f"recorded null and not-passed, and the detail does not "
                      f"say why: {detail[:100]!r}")
    return PASS, f"recorded as not computable: {detail[:80]}"


# --------------------------------------------------------------- waivers
def _tier_one(ctx: Ctx) -> str:
    name = ctx.unique("wv")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/assess", json=TIER_ONE)
    return urn


def _propose(ctx: Ctx, **over):
    body = {"urn": _tier_one(ctx), "control": WAIVABLE[0],
            "rationale": "a QA rationale",
            "compensating_control": "daily manual review", "days": 30}
    body.update(over)
    return ctx.api.post(W, json=body, auth=ctx.people["owner"])


@case("QA-AM-720", "A waiver with no rationale")
def am_720(ctx: Ctx) -> Result:
    """The rationale is the waiver. Without it the record says a control was
    switched off and nothing about why, which is indistinguishable from the
    control having been forgotten."""
    return refused_by_the_control(
        _propose(ctx, rationale="   "),
        "a control was waived with no reason recorded, so the record cannot "
        "be told apart from the control having been forgotten")


@case("QA-AM-721", "A waiver with no compensating control")
def am_721(ctx: Ctx) -> Result:
    """Records the gap and not the containment. If the honest answer is that
    nothing compensates, this is an accepted risk and belongs in a finding
    somebody owns rather than in a waiver that reads as managed."""
    return refused_by_the_control(
        _propose(ctx, compensating_control=""),
        "a control was relaxed with nothing recorded in its place, so the "
        "register shows a managed exception over an unmanaged gap")


@case("QA-AM-722", "A waiver that never expires")
def am_722(ctx: Ctx) -> Result:
    """The register's whole position on exceptions. An exception with no end
    date is not an exception; it is a decision to stop applying a control,
    taken by somebody who did not have to say so."""
    answers = []
    for days in (0, -1, 100_000):
        got = _propose(ctx, days=days)
        if got.status_code >= 500:
            return FAIL, f"days={days} answered {got.status_code}"
        if code_of(got) in DENIAL:
            return BLOCKED, f"answered '{code_of(got)}' — not reached"
        if got.status_code < 400:
            return FAIL, (f"a waiver was granted for {days} day(s), which is "
                          f"not a bounded window — an exception with no end "
                          f"date is a decision to stop applying the control")
        answers.append(f"{days}:{code_of(got)}")
    return PASS, f"all three refused ({', '.join(answers)})"


@case("QA-AM-723", "A waiver over a control that does not exist")
def am_723(ctx: Ctx) -> Result:
    """Waiving it would relax nothing while reading on a report as though it
    had, which is worse than not waiving it at all."""
    got = _propose(ctx, control="quarterly_vibes")
    answer = refused_by_the_control(
        got, "a waiver was granted against a control that is not one, so a "
             "report shows a relaxation of nothing")
    if answer[0] != PASS:
        return answer
    if not any(c in got.text for c in WAIVABLE[:3]):
        return FAIL, (f"refused '{code_of(got)}' without naming what may be "
                      f"waived")
    return PASS, f"refused '{code_of(got)}', naming the {len(WAIVABLE)} controls"


@case("QA-AM-724", "A well-formed waiver is granted")
def am_724(ctx: Ctx) -> Result:
    """A register that refuses everything is not a control, it is an outage.
    The accepted case is what makes the four refusals above mean something —
    and the row it produces has to carry its end date, because that is the
    difference between a waiver and a decision."""
    got = _propose(ctx)
    if got.status_code >= 400:
        return FAIL, (f"a complete waiver — rationale, compensating control "
                      f"and a thirty-day window — was refused "
                      f"'{code_of(got)}': {got.text[:150]}")
    row = got.json() or {}
    row = row.get("waiver") or row
    if not row.get("expires_at"):
        return FAIL, (f"the waiver was granted and carries no expiry, so the "
                      f"bound the refusals above enforce is not written down "
                      f"anywhere: {sorted(row)}")
    if row.get("status") in ("active", "approved"):
        return FAIL, (f"a proposed waiver is already '{row.get('status')}' — "
                      f"the proposer would have waived a control by asking")
    return PASS, (f"proposed as '{row.get('status')}', expiring at "
                  f"{row['expires_at']}, awaiting somebody else")
