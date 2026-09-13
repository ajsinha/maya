"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the scheduler, notifications and subscriptions.

The governance batch is where a computed condition becomes somebody's
problem. Its failures are all the same shape: a job that runs twice and raises
twice, or a job that runs and raises nothing because the condition it looks
for is spelled differently from the one that exists.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  expect_refused, valid_body)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
SCHEDULER = "/api/v1/scheduler"
SUBSCRIPTIONS = "/api/v1/subscriptions"


def _model(ctx: Ctx) -> str:
    name = ctx.unique("sc")
    ctx.api.post("/api/v1/models", json={"urn": f"maya://model/{name}",
                                         "name": name, "owner": "owner",
                                         **TIER})
    return f"maya://model/{name}"


# ------------------------------------------------------------- the batch
@case("QA-PLT-800", "The job catalogue publishes what each job is for")
def plt_800(ctx: Ctx) -> Result:
    """A batch nobody can read is a batch nobody will question."""
    # The catalogue is the scheduler resource itself; there is no `/jobs`.
    got = ctx.api.get(SCHEDULER)
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    jobs = got.json().get("jobs", [])
    if not jobs:
        return FAIL, "the catalogue is empty"
    without = [j.get("key") for j in jobs if not (j.get("why") or "").strip()]
    if without:
        return FAIL, (f"these jobs publish no reason for existing: "
                      f"{without[:6]}")
    return PASS, f"{len(jobs)} jobs, each with a stated reason"


@case("QA-PLT-801", "Run a job that does not exist")
def plt_801(ctx: Ctx) -> Result:
    got = ctx.api.post(f"{SCHEDULER}/run", json={"job": "qa-no-such-job"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        body = got.text.lower()
        if "qa-no-such-job" not in body and "unknown" not in body:
            return FAIL, ("an unknown job name was accepted and the pass "
                          "reported success over nothing")
    return PASS, f"answered {got.status_code}"


@case("QA-PLT-802", "Run the whole pass twice and nothing doubles")
def plt_802(ctx: Ctx) -> Result:
    """Every job re-derives its condition, so a second pass in the same
    moment must raise nothing new. A batch that is not idempotent produces
    one finding per run for one problem."""
    _model(ctx)
    first = ctx.api.post(f"{SCHEDULER}/run", json={})
    if first.status_code >= 400:
        return BLOCKED, first.text[:150]
    before = ctx.api.get("/api/v1/findings", params={"limit": 500})
    was = len(before.json().get("findings", before.json().get("rows", [])))
    second = ctx.api.post(f"{SCHEDULER}/run", json={})
    if second.status_code >= 400:
        return FAIL, f"the second pass failed: {second.text[:150]}"
    after = ctx.api.get("/api/v1/findings", params={"limit": 500})
    now = len(after.json().get("findings", after.json().get("rows", [])))
    if now != was:
        return FAIL, (f"a second pass over unchanged state raised "
                      f"{now - was} more finding(s); one problem becomes one "
                      f"per run")
    return PASS, f"{was} findings before and after the second pass"


@case("QA-PLT-803", "A job that raises does not stop the pass")
def plt_803(ctx: Ctx) -> Result:
    """One subsystem failing must not take the other twenty-six with it."""
    got = ctx.api.post(f"{SCHEDULER}/run", json={})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    body = got.json()
    ran = body.get("jobs", body.get("ran", []))
    if isinstance(ran, list) and len(ran) < 5:
        return FAIL, f"only {len(ran)} job(s) ran in a full pass"
    return PASS, f"{len(ran) if isinstance(ran, list) else '?'} jobs ran"


@case("QA-PLT-804", "The run history records what happened")
def plt_804(ctx: Ctx) -> Result:
    ctx.api.post(f"{SCHEDULER}/run", json={})
    got = ctx.api.get(f"{SCHEDULER}/history")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    body = got.json()
    runs = body.get("runs", body.get("history", body.get("rows", [])))
    if not runs:
        return FAIL, ("the scheduler ran and recorded nothing; a batch with "
                      "no history cannot be shown to have run")
    return PASS, f"{len(runs)} run(s) recorded"


@case("QA-PLT-805", "The scheduler reports when it last ran")
def plt_805(ctx: Ctx) -> Result:
    """A batch that has not run for a week looks exactly like an estate with
    nothing wrong."""
    got = ctx.api.get(SCHEDULER)
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    if "ever_run" not in got.text and "last" not in got.text.lower():
        return FAIL, "the scheduler does not report when it last ran"
    return PASS, "it says when it last ran"


# ----------------------------------------------------------- subscriptions
@case("QA-PLT-810", "A subscription to an event that does not exist")
def plt_810(ctx: Ctx) -> Result:
    body = valid_body(ctx, "POST", SUBSCRIPTIONS, kinds=["qa.not.an.event"],
                      endpoint="https://example.invalid/hook")
    got = ctx.api.post(SUBSCRIPTIONS, json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a subscription was accepted for an event the platform "
                      "never emits; it will simply never fire")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-811", "A subscription with no kinds at all")
def plt_811(ctx: Ctx) -> Result:
    body = valid_body(ctx, "POST", SUBSCRIPTIONS, kinds=[],
                      endpoint="https://example.invalid/hook")
    return expect_refused(ctx.api.post(SUBSCRIPTIONS, json=body),
                          "kinds_required", "validation_error",
                          "event_refused")


@case("QA-PLT-812", "A subscription to a plaintext endpoint")
def plt_812(ctx: Ctx) -> Result:
    """The register sends governance events outward. Over http they are
    readable by anything on the path."""
    body = valid_body(ctx, "POST", SUBSCRIPTIONS, kinds=["model_registered"],
                      endpoint="http://example.invalid/hook")
    got = ctx.api.post(SUBSCRIPTIONS, json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a subscription was accepted over plaintext http; "
                      "governance events would be readable in transit")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-813", "A subscription with a wildcard over every event")
def plt_813(ctx: Ctx) -> Result:
    body = valid_body(ctx, "POST", SUBSCRIPTIONS, kinds=["*"],
                      endpoint="https://example.invalid/hook")
    got = ctx.api.post(SUBSCRIPTIONS, json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"
