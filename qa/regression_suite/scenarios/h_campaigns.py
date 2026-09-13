"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — campaigns, ageing, and the worklist.

A campaign is an obligation put to a population; ageing is what happens when
nobody answers. Both are arithmetic over people's attention, and both fail by
reporting completion over a population nobody chose.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  expect_refused, valid_body)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
CAMPAIGNS = "/api/v1/campaigns"
#: A real kind, and the population is `where` rather than a `derivation`
#: object. `attestation_round` sounds like one of the five and is not.
CAMPAIGN_KIND = "attestation"


def _model(ctx: Ctx) -> str:
    name = ctx.unique("cp")
    ctx.api.post("/api/v1/models", json={"urn": f"maya://model/{name}",
                                         "name": name, "owner": "owner",
                                         **TIER})
    return f"maya://model/{name}"


def _campaign(ctx: Ctx, **over):
    body = valid_body(ctx, "POST", CAMPAIGNS, reference=ctx.unique("CMP"),
                      kind=CAMPAIGN_KIND, title="QA round", where=[])
    body.update(over)
    return ctx.api.post(CAMPAIGNS, json=body)


@case("QA-AM-800", "A campaign of a kind that is not one")
def am_800(ctx: Ctx) -> Result:
    return expect_refused(_campaign(ctx, kind="vibes"),
                          "unknown_campaign_kind")


@case("QA-AM-801", "A campaign with no reference")
def am_801(ctx: Ctx) -> Result:
    """The reference is what the round is cited by afterwards."""
    got = _campaign(ctx, reference="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a campaign was opened with nothing to cite it by"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-802", "Two campaigns with the same reference")
def am_802(ctx: Ctx) -> Result:
    reference = ctx.unique("CMP")
    _model(ctx)
    first = _campaign(ctx, reference=reference)
    if first.status_code >= 400:
        return BLOCKED, first.text[:150]
    got = _campaign(ctx, reference=reference)
    if got.status_code < 400:
        return FAIL, "two campaigns share one reference"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-803", "Respond to a campaign item that is not in the population")
def am_803(ctx: Ctx) -> Result:
    """A response about a model nobody put in the round is an answer to a
    question that was never asked."""
    _model(ctx)
    made = _campaign(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    reference = made.json().get("reference")
    got = ctx.api.post(f"{CAMPAIGNS}/{reference}/respond",
                       json={"urn": "maya://model/qa.never",
                             "state": "answered", "response": "QA"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a response was recorded for a model outside the "
                      "campaign's population")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-804", "Respond with a state that is not one")
def am_804(ctx: Ctx) -> Result:
    urn = _model(ctx)
    made = _campaign(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    reference = made.json().get("reference")
    got = ctx.api.post(f"{CAMPAIGNS}/{reference}/respond",
                       json={"urn": urn, "state": "maybe", "response": "QA"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an item was answered with a state outside the vocabulary"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-805", "Respond `outstanding`, which is not an answer")
def am_805(ctx: Ctx) -> Result:
    """`outstanding` is the state an item starts in. Setting it as a response
    would let somebody 'answer' by saying nothing."""
    urn = _model(ctx)
    made = _campaign(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    reference = made.json().get("reference")
    got = ctx.api.post(f"{CAMPAIGNS}/{reference}/respond",
                       json={"urn": urn, "state": "outstanding"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an item was 'answered' as outstanding; a campaign "
                      "could be completed by answering nothing")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-806", "Reassign a campaign item to nobody")
def am_806(ctx: Ctx) -> Result:
    made = _campaign(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    reference = made.json().get("reference")
    got = ctx.api.post(f"{CAMPAIGNS}/{reference}/reassign",
                       json={"urn": "maya://model/qa.any", "to": "   ",
                             "reason": "QA"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an item was reassigned to nobody"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-807", "A campaign's population is frozen at launch")
def am_807(ctx: Ctx) -> Result:
    """A model registered after the round opened is drift, not a new item —
    otherwise completion could never be reached."""
    _model(ctx)
    made = _campaign(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    reference = made.json().get("reference")
    # `reference` is a QUERY filter on the collection; there is no
    # `GET /campaigns/{reference}`.
    before = ctx.api.get(CAMPAIGNS, params={"reference": reference})
    if before.status_code >= 400:
        return BLOCKED, before.text[:150]
    was = before.json().get("items", before.json().get("population", 0))
    was = len(was) if isinstance(was, list) else was
    _model(ctx)
    after = ctx.api.get(CAMPAIGNS, params={"reference": reference})
    now = after.json().get("items", after.json().get("population", 0))
    now = len(now) if isinstance(now, list) else now
    if now != was:
        return FAIL, (f"the population moved from {was} to {now} after a new "
                      f"model was registered; a round whose population grows "
                      f"can never complete")
    return PASS, f"frozen at {was} item(s)"


@case("QA-AM-808", "The kinds a campaign may be for are published")
def am_808(ctx: Ctx) -> Result:
    got = ctx.api.get(f"{CAMPAIGNS}/kinds")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    kinds = got.json().get("kinds", [])
    if not kinds:
        return FAIL, "no campaign kinds are published"
    return PASS, f"{len(kinds)} kind(s) published"


@case("QA-AM-809", "Read a campaign that does not exist")
def am_809(ctx: Ctx) -> Result:
    got = ctx.api.get(CAMPAIGNS, params={"reference": "QA-NEVER"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        body = got.json()
        rows = body.get("campaigns", body.get("rows", []))
        if rows:
            return FAIL, "a reference nobody used matched a campaign"
        return PASS, "no campaign matches an unused reference"
    return PASS, f"refused ({got.status_code})"
