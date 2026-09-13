"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — telemetry, parallel runs, regulatory approvals and board packs.

Telemetry is the only thing an outside engine sends back, so everything about
it is about what MAYA may conclude from an unverified report. A parallel run
is a challenger tried against a champion, and its whole value is that the
comparison was fixed before the result was known.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  expect_accepted,
                                                  expect_refused, valid_body)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
TELEMETRY = "/api/v1/telemetry"
PARALLEL = "/api/v1/parallel-runs"
APPROVALS = "/api/v1/regulatory-approvals"
PACKS = "/api/v1/board-packs"

#: One telemetry row, shaped as the platform describes it: "a 'scores' row
#: carries entity_id, scored_at, score". Read from the refusal rather than
#: guessed — my first version omitted `score` and two cases failed on the
#: shape instead of on their subject.
SCORE = {"entity_id": "e1", "scored_at": 1.0, "score": 0.5}


def _versioned(ctx: Ctx) -> str:
    name = ctx.unique("tl")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "owner", **TIER})
    ctx.api.post(f"/api/v1/models/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    return urn


def _send(ctx: Ctx, **over):
    body = valid_body(ctx, "POST", TELEMETRY, urn=_versioned(ctx),
                      semver="1.0.0",
                      rows=[SCORE])
    body.update(over)
    return ctx.api.post(TELEMETRY, json=body)


# --------------------------------------------------------------- telemetry
@case("QA-AM-400", "Telemetry for a version that does not exist")
def am_400(ctx: Ctx) -> Result:
    return expect_refused(_send(ctx, semver="9.9.9"),
                          "registry_refused", "not_found",
                          "telemetry_refused")


@case("QA-AM-635", "Telemetry for a model that does not exist")
def am_401(ctx: Ctx) -> Result:
    body = valid_body(ctx, "POST", TELEMETRY, urn="maya://model/qa.never",
                      semver="1.0.0", rows=[SCORE])
    return expect_refused(ctx.api.post(TELEMETRY, json=body),
                          "registry_refused", "not_found",
                          "telemetry_refused")


@case("QA-AM-402", "Telemetry with no rows")
def am_402(ctx: Ctx) -> Result:
    got = _send(ctx, rows=[])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"


@case("QA-AM-636", "A well-formed batch is accepted")
def am_403(ctx: Ctx) -> Result:
    return expect_accepted(_send(ctx))


@case("QA-AM-404", "A sample rate above one")
def am_404(ctx: Ctx) -> Result:
    """A sample rate is what fraction of scores this batch represents. Above
    one it scales every count up, and the estate reports more decisions than
    were made."""
    got = _send(ctx, sample_rate=5.0)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a sample rate above 1.0 was accepted; every count "
                      "derived from this batch is now inflated")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-637", "A negative sample rate")
def am_405(ctx: Ctx) -> Result:
    got = _send(ctx, sample_rate=-1.0)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a negative sample rate was accepted"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-638", "The same batch sent twice is not counted twice")
def am_406(ctx: Ctx) -> Result:
    urn = _versioned(ctx)
    body = valid_body(ctx, "POST", TELEMETRY, urn=urn, semver="1.0.0",
                      rows=[SCORE])
    first = ctx.api.post(TELEMETRY, json=body)
    if first.status_code >= 400:
        return BLOCKED, first.text[:150]
    ctx.api.post(TELEMETRY, json=body)
    # `semver` is required too — a telemetry stream belongs to a version,
    # not to a model, which is the whole reason a restatement of one version
    # cannot be read as evidence about another.
    seen = ctx.api.get("/api/v1/telemetry",
                       params={"urn": urn, "semver": "1.0.0"})
    if seen.status_code >= 400:
        return BLOCKED, f"cannot read it back: {seen.status_code}"
    return PASS, f"read back: {seen.text[:110]}"


# ---------------------------------------------------------- parallel runs
def _two_versions(ctx: Ctx) -> str:
    """A model with a champion and a challenger to compare."""
    urn = _versioned(ctx)
    name = urn.rsplit("/", 1)[-1]
    ctx.api.post(f"/api/v1/models/{name}/versions", json={"semver": "1.1.0"},
                 auth=ctx.people["developer"])
    return urn


def _run(ctx: Ctx, **over):
    # TWO versions. With one, `same_version` fires first and every case in
    # this group passes on a refusal about the wrong thing — which is the
    # failure this whole pass is about, committed in the setup rather than in
    # the assertion.
    body = valid_body(ctx, "POST", PARALLEL, urn=_two_versions(ctx),
                      champion="1.0.0", challenger="1.1.0",
                      purpose="QA comparison")
    body.update(over)
    return ctx.api.post(PARALLEL, json=body)


@case("QA-AM-639", "A parallel run with no stated purpose")
def am_420(ctx: Ctx) -> Result:
    """The purpose is what the comparison was fixed against. Without it the
    result can be read as whatever it turned out to be."""
    return expect_refused(_run(ctx, purpose="   "),
                          "validation_error", "purpose_required",
                          "parallel_refused", "monitor_refused")


@case("QA-AM-640", "A challenger that is the same version as the champion")
def am_421(ctx: Ctx) -> Result:
    got = _run(ctx, challenger="1.0.0")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a model was run in parallel against itself; the "
                      "comparison can only ever say they agree")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-641", "Conclude a parallel run with no note")
def am_422(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post(f"{PARALLEL}/qa-never/conclude",
                     json={"conclusion": "adopt", "note": "   "}),
        "no_run", "not_found", "note_required")


# ------------------------------------------------------------- approvals
def _approval(ctx: Ctx, **over):
    body = valid_body(ctx, "POST", APPROVALS, urn=_versioned(ctx),
                      regulator="the regulator", kind="model_approval",
                      scope="the whole model", granted_at=1.0)
    body.update(over)
    return ctx.api.post(APPROVALS, json=body)


@case("QA-AM-642", "A regulatory approval with no regulator")
def am_440(ctx: Ctx) -> Result:
    """Which supervisor granted it is the entire content of the record."""
    got = _approval(ctx, regulator="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an approval was recorded with no regulator named; the "
                      "record says a supervisor approved this and cannot say "
                      "which")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-643", "A regulatory approval with no scope")
def am_441(ctx: Ctx) -> Result:
    got = _approval(ctx, scope="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an approval with no scope reads as approval of "
                      "everything")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-644", "Withdraw a regulatory approval with no reason")
def am_442(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post(f"{APPROVALS}/qa-never/withdraw", json={"reason": "  "}),
        "no_approval", "not_found", "reason_required")


# ------------------------------------------------------------ board packs
@case("QA-AM-645", "A board pack preview does not create a pack")
def am_460(ctx: Ctx) -> Result:
    """Somebody preparing for a meeting should be able to look first."""
    before = ctx.api.get(PACKS)
    if before.status_code >= 400:
        return BLOCKED, before.text[:150]
    was = len(before.json().get("packs", before.json().get("rows", [])))
    ctx.api.post(f"{PACKS}/preview", json={"period": "2026Q1"})
    after = ctx.api.get(PACKS)
    now = len(after.json().get("packs", after.json().get("rows", [])))
    if now != was:
        return FAIL, f"a preview created a pack ({was} -> {now})"
    return PASS, "preview creates nothing"


@case("QA-AM-646", "A board pack with no period")
def am_461(ctx: Ctx) -> Result:
    """The period is what the numbers are about. A pack with none is a set of
    figures with no statement of when."""
    got = ctx.api.post(PACKS, json={"period": "   "})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a board pack was cut with no period; the figures in it "
                      "describe no stated span of time")
    return PASS, f"refused '{code_of(got)}'"
