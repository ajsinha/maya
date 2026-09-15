"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — campaigns: a round of asking, over a frozen population.

There is no field for a list of models, and that is the design: a typed
population is one somebody assembled by hand, and nothing can re-derive it
later to say what has changed. Every case here is about the population
staying honest — at launch, during the round, and at the close.
"""
from __future__ import annotations

from core.lifecycle.campaigns import (ANSWERED, DECLINED, ITEM_STATES, KINDS,
                                      NOT_APPLICABLE, OUTSTANDING)
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

C = "/api/v1/campaigns"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx, **over) -> str:
    name = ctx.unique("cp")
    body = {"urn": f"maya://model/{name}", "name": name, "owner": "owner",
            **TIER}
    body.update(over)
    ctx.api.post(M, json=body)
    return body["urn"]


def _open(ctx: Ctx, **over):
    body = {"reference": ctx.unique("CERT"), "kind": sorted(KINDS)[0],
            "title": "A QA round", "where": [], "instruction": "confirm"}
    body.update(over)
    return ctx.api.post(C, json=body, auth=ctx.people["risk"])


def _respond(ctx: Ctx, reference: str, urn: str, **over):
    body = {"urn": urn, "state": ANSWERED, "response": "confirmed"}
    body.update(over)
    return ctx.api.post(f"{C}/{reference}/respond", json=body,
                        auth=ctx.people["owner"])


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-AM-378", "Open a campaign whose derivation selects nothing")
def am_378(ctx: Ctx) -> Result:
    """A campaign over nothing reports 100% complete on the day it opens,
    which is the most misleading number this module could produce."""
    got = _open(ctx, where=[{"field": "domain", "op": "eq",
                             "value": "qa-no-such-domain"}])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, ("a campaign was opened over no models, so it reports "
                      "complete on the day it opened")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-379", "Open a second campaign under one reference")
def am_379(ctx: Ctx) -> Result:
    """Two rounds under one name produce one completion figure covering two
    populations."""
    _model(ctx)
    ref = ctx.unique("CERT")
    if _open(ctx, reference=ref).status_code >= 400:
        return BLOCKED, "the first campaign could not be opened"
    got = _open(ctx, reference=ref)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "two campaigns share one reference"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-2900", "A campaign kind that is not one")
def am_2900(ctx: Ctx) -> Result:
    """The list is closed so that two rounds run three years apart can be
    compared."""
    _model(ctx)
    got = _open(ctx, kind="a quick check")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a campaign of an unknown kind was opened"
    if not any(k in got.text for k in KINDS):
        return FAIL, "the refusal does not name the kinds"
    return PASS, f"refused '{code_of(got)}', naming the {len(KINDS)} kinds"


@case("QA-AM-382", "Respond for a model not in the frozen population")
def am_382(ctx: Ctx) -> Result:
    """The population is frozen at launch. Answering for a model outside it
    would make the completion figure describe a set nobody chose."""
    _model(ctx)
    ref = ctx.unique("CERT")
    if _open(ctx, reference=ref).status_code >= 400:
        return BLOCKED, "the campaign could not be opened"
    outsider = _model(ctx)      # registered AFTER the population froze
    got = _respond(ctx, ref, outsider)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a model outside the frozen population was answered "
                      "for, so the completion figure covers a different set")
    if code_of(got) in DENIAL:
        return BLOCKED, "the caller never reached the check"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-384", "Respond declined with no reason")
def am_384(ctx: Ctx) -> Result:
    """A refusal to confirm is the most interesting answer a round gets, and
    an unexplained one is the least useful record of it."""
    urn = _model(ctx)
    ref = ctx.unique("CERT")
    if _open(ctx, reference=ref).status_code >= 400:
        return BLOCKED, "the campaign could not be opened"
    wrong = []
    for state in (DECLINED, NOT_APPLICABLE):
        got = _respond(ctx, ref, urn, state=state, response="   ")
        if got.status_code >= 500:
            return FAIL, f"{state}: {got.status_code}"
        if got.status_code < 400:
            wrong.append(state)
        elif not _reached(got):
            return BLOCKED, f"'{code_of(got)}' — not reached"
    if wrong:
        return FAIL, f"answered with no reason: {', '.join(wrong)}"
    return PASS, f"'{DECLINED}' and '{NOT_APPLICABLE}' both need a reason"


@case("QA-AM-385", "Respond outstanding")
def am_385(ctx: Ctx) -> Result:
    """`outstanding` is the state an item starts in. Sending it as an answer
    would be answering by not answering."""
    urn = _model(ctx)
    ref = ctx.unique("CERT")
    if _open(ctx, reference=ref).status_code >= 400:
        return BLOCKED, "the campaign could not be opened"
    got = _respond(ctx, ref, urn, state=OUTSTANDING)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an item was 'answered' as outstanding, so not "
                      "answering counts as a response")
    if code_of(got) in DENIAL:
        return BLOCKED, "the caller never reached the check"
    answerable = [s for s in ITEM_STATES if s != OUTSTANDING]
    if not any(s in got.text for s in answerable):
        return FAIL, "the refusal does not name the answerable states"
    return PASS, f"refused '{code_of(got)}', naming {len(answerable)} states"


@case("QA-AM-386", "Respond after the campaign closed")
def am_386(ctx: Ctx) -> Result:
    """A round's figures are about a moment. An answer arriving afterwards
    would change a number somebody already reported."""
    urn = _model(ctx)
    ref = ctx.unique("CERT")
    if _open(ctx, reference=ref).status_code >= 400:
        return BLOCKED, "the campaign could not be opened"
    closed = ctx.api.post(f"{C}/{ref}/close", json={"note": "done"},
                          auth=ctx.people["risk"])
    if closed.status_code >= 400:
        return BLOCKED, f"could not close: {closed.text[:140]}"
    got = _respond(ctx, ref, urn)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an answer landed after the round closed, changing a "
                      "figure somebody already reported")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-2901", "Close a campaign twice")
def am_2901(ctx: Ctx) -> Result:
    _model(ctx)
    ref = ctx.unique("CERT")
    if _open(ctx, reference=ref).status_code >= 400:
        return BLOCKED, "the campaign could not be opened"
    if ctx.api.post(f"{C}/{ref}/close", json={"note": "done"},
                    auth=ctx.people["risk"]).status_code >= 400:
        return BLOCKED, "the campaign could not be closed"
    got = ctx.api.post(f"{C}/{ref}/close", json={"note": "again"},
                       auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a closed campaign was closed a second time"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-387", "Close a round with items outstanding")
def am_387(ctx: Ctx) -> Result:
    """Closing is allowed — a round ends whether or not everybody replied —
    and what matters is that the unanswered items are visible afterwards
    rather than absorbed into the completion figure."""
    _model(ctx)
    ref = ctx.unique("CERT")
    made = _open(ctx, reference=ref)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = ctx.api.post(f"{C}/{ref}/close", json={"note": "time is up"},
                       auth=ctx.people["risk"])
    if got.status_code >= 400:
        return FAIL, (f"a round with outstanding items could not be closed "
                      f"('{code_of(got)}'); a round that cannot end until "
                      f"everybody replies never ends")
    body = got.json() or {}
    text = str(body)
    if "never_answered" not in text and "outstanding" not in text:
        return FAIL, ("the closed round does not report what was never "
                      "answered, so silence is absorbed into the figure")
    return PASS, "closed, and the unanswered items are named"


@case("QA-AM-2902", "The derivation is kept, not the list")
def am_2902(ctx: Ctx) -> Result:
    """A typed population is one somebody assembled by hand and nothing can
    re-derive later. Keeping the WHERE is what lets a round say which models
    joined or left the population since it opened."""
    _model(ctx)
    ref = ctx.unique("CERT")
    where = [{"field": "domain", "operator": "eq", "value": "credit"}]
    made = _open(ctx, reference=ref, where=where)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = ctx.api.get(f"{C}?reference={ref}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    rows = body.get("campaigns") or [body]
    row = next((r for r in rows if r.get("reference") == ref), None)
    if row is None:
        return BLOCKED, "the campaign could not be read back"
    derivation = row.get("derivation") or {}
    if not derivation.get("where"):
        return FAIL, ("the campaign kept no derivation, so nothing can say "
                      "which models have joined or left its population")
    return PASS, f"derivation kept: {str(derivation)[:80]}"
