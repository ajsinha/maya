"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — replay, waivers, and the test catalogue.

Replay is the claim that a validation can be re-performed and reach the same
answer. A waiver is a control this firm has decided not to meet, for a stated
time, with something else in its place. Both are promises about the future,
and both fail quietly when the thing they promised stops being true.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  expect_accepted,
                                                  expect_refused, valid_body)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
WAIVERS = "/api/v1/waivers"
VALIDATIONS = "/api/v1/validations"


def _versioned(ctx: Ctx) -> str:
    name = ctx.unique("rp")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "owner", **TIER})
    ctx.api.post(f"/api/v1/models/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    return urn


def _episode(ctx: Ctx) -> str:
    body = valid_body(ctx, "POST", VALIDATIONS, urn=_versioned(ctx),
                      semver="1.0.0", validators=["validator"])
    made = ctx.api.post(VALIDATIONS, json=body)
    if made.status_code >= 400:
        raise AssertionError(f"could not open a validation: {made.text[:170]}")
    return made.json()["id"]


# ------------------------------------------------------------------ replay
@case("QA-AM-700", "Replay a validation that has no results")
def am_700(ctx: Ctx) -> Result:
    """Nothing recorded means nothing to re-perform, and a replay reporting
    agreement over an empty set is the worst answer available."""
    got = ctx.api.post(f"{VALIDATIONS}/{_episode(ctx)}/replay",
                       json={"data": {}})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400 and "0" not in got.text and "nothing" not in got.text.lower():
        return FAIL, ("a replay over an episode with no results reported "
                      "without saying it checked nothing")
    return PASS, f"answered {got.status_code}: {got.text[:100]}"


@case("QA-AM-701", "Replay a validation that does not exist")
def am_701(ctx: Ctx) -> Result:
    got = ctx.api.post(f"{VALIDATIONS}/qa-never/replay", json={"data": {}})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a replay ran against no episode"
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-AM-702", "Replay the same episode twice gives the same report")
def am_702(ctx: Ctx) -> Result:
    """Replay is only evidence if it is deterministic."""
    episode = _episode(ctx)
    ctx.api.post(f"{VALIDATIONS}/{episode}/results",
                 json={"test_key": "discrimination.auc",
                       "left": [0.7, 0.8], "right": [0.7, 0.8]},
                 auth=ctx.people["validator"])
    first = ctx.api.post(f"{VALIDATIONS}/{episode}/replay", json={"data": {}})
    second = ctx.api.post(f"{VALIDATIONS}/{episode}/replay", json={"data": {}})
    if first.status_code >= 500 or second.status_code >= 500:
        return FAIL, f"{first.status_code}/{second.status_code}"
    a, b = first.text, second.text
    for volatile in ("replayed_at", "took", "request_id"):
        a = a.split(volatile)[0]
        b = b.split(volatile)[0]
    if a != b:
        return FAIL, "two replays of one episode reported differently"
    return PASS, "identical"


@case("QA-AM-703", "Replay from storage with no snapshot pinned")
def am_703(ctx: Ctx) -> Result:
    """A replay that silently invents its data is worse than one that says it
    cannot run."""
    got = ctx.api.post(f"{VALIDATIONS}/{_episode(ctx)}/replay-from-storage",
                       json={})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        body = got.text.lower()
        if "snapshot" not in body and "no" not in body:
            return FAIL, ("a storage replay ran with nothing pinned and did "
                          "not say where the data came from")
    return PASS, f"answered {got.status_code}"


# ----------------------------------------------------------------- waivers
def _waiver(ctx: Ctx, **over):
    body = valid_body(ctx, "POST", WAIVERS, urn=_versioned(ctx),
                      control="independent_validation",
                      rationale="the validator is on leave",
                      compensating_control="a second review by the risk "
                                           "committee",
                      days=30)
    body.update(over)
    return ctx.api.post(WAIVERS, json=body)


@case("QA-AM-720", "A waiver with no rationale")
def am_720(ctx: Ctx) -> Result:
    """A waiver is the firm deciding not to meet a control. Why is the only
    thing that makes that decision reviewable."""
    got = _waiver(ctx, rationale="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a control was waived with no stated reason")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-721", "A waiver with no compensating control")
def am_721(ctx: Ctx) -> Result:
    """A waiver with nothing in place of the control is not a waiver, it is
    the control being switched off."""
    got = _waiver(ctx, compensating_control="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a control was waived with nothing put in its place")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-722", "A waiver that never expires")
def am_722(ctx: Ctx) -> Result:
    """A permanent waiver is a change to what the tier requires, and that is
    a different act with different signatures."""
    got = _waiver(ctx, days=0)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a waiver was granted with no end; a control waived "
                      "for ever is the framework, not an exception")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-723", "A waiver over a control that does not exist")
def am_723(ctx: Ctx) -> Result:
    return expect_refused(_waiver(ctx, control="model:levitate"),
                          "unknown_control", "validation_error",
                          "waiver_refused")


@case("QA-AM-724", "A well-formed waiver is granted")
def am_724(ctx: Ctx) -> Result:
    return expect_accepted(_waiver(ctx), status=201)


# -------------------------------------------------------- test catalogue
@case("QA-AM-740", "The test catalogue is published")
def am_740(ctx: Ctx) -> Result:
    """A validator choosing a test needs to know which ones the platform can
    actually compute, and what each one means."""
    got = ctx.api.get("/api/v1/tests")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    body = got.json()
    tests = body.get("tests", body.get("rows", []))
    if not tests:
        return FAIL, "the catalogue is empty"
    return PASS, f"{len(tests)} test(s) published"


@case("QA-AM-741", "A result naming a test that is not in the catalogue")
def am_741(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post(f"{VALIDATIONS}/{_episode(ctx)}/results",
                     json={"test_key": "vibes.check", "left": [1.0],
                           "right": [1.0]}, auth=ctx.people["validator"]),
        "unknown_test", "validation_refused", "validation_error")


@case("QA-AM-742", "A result whose two series are different lengths")
def am_742(ctx: Ctx) -> Result:
    """Paired comparisons over unequal series either crash or silently
    truncate, and truncation is the worse of the two."""
    got = ctx.api.post(f"{VALIDATIONS}/{_episode(ctx)}/results",
                       json={"test_key": "discrimination.auc",
                             "left": [0.7, 0.8, 0.9], "right": [0.7]},
                       auth=ctx.people["validator"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} — unequal series crashed the test"
    if got.status_code < 400:
        return FAIL, ("two series of different lengths were compared; the "
                      "pairing is silently truncated")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-743", "A result with empty series")
def am_743(ctx: Ctx) -> Result:
    got = ctx.api.post(f"{VALIDATIONS}/{_episode(ctx)}/results",
                       json={"test_key": "discrimination.auc",
                             "left": [], "right": []},
                       auth=ctx.people["validator"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a test reported over no observations at all; a metric "
                      "computed from nothing reads as a metric")
    return PASS, f"refused '{code_of(got)}'"
