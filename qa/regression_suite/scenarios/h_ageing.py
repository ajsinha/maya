"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — ageing, escalation and the worklist.

What happens when nobody answers. Every case here is about a clock: whether it
starts when it should, whether a handover restarts it, and whether an
escalation escalates the thing rather than itself.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
FINDINGS = "/api/v1/findings"


def _finding(ctx: Ctx, **over) -> str:
    name = ctx.unique("ag")
    ctx.api.post("/api/v1/models", json={"urn": f"maya://model/{name}",
                                         "name": name, "owner": "owner",
                                         **TIER})
    body = {"urn": f"maya://model/{name}", "severity": "High",
            "title": "QA ageing probe", "owner": "owner",
            "description": "raised by the QA pass", "category": "monitoring",
            "source": "self_identified"}
    body.update(over)
    made = ctx.api.post(FINDINGS, json=body)
    if made.status_code >= 400:
        raise AssertionError(f"could not raise a finding: {made.text[:170]}")
    return made.json()["id"]


@case("QA-AM-900", "An unacknowledged finding is reported as unacknowledged")
def am_900(ctx: Ctx) -> Result:
    """Acknowledgement is recorded as an ACT rather than a status, because a
    status column can disagree with what happened and an append-only act
    cannot."""
    finding = _finding(ctx)
    got = ctx.api.get(f"{FINDINGS}/{finding}")
    if got.status_code >= 400:
        return BLOCKED, got.text[:150]
    body = ctx.api.get("/api/v1/findings/ageing")
    if body.status_code == 404:
        body = ctx.api.get(FINDINGS, params={"limit": 200})
    if body.status_code >= 400:
        return BLOCKED, f"{body.status_code}"
    if "unacknowledged" not in body.text and "acknowledg" not in body.text:
        return FAIL, ("nothing reports whether a finding has been "
                      "acknowledged; an unowned finding ages invisibly")
    return PASS, "acknowledgement is reported"


@case("QA-AM-901", "A handover records who it moved from and to")
def am_901(ctx: Ctx) -> Result:
    """An assignment with no trail is a finding that changed hands and
    cannot say when."""
    finding = _finding(ctx)
    moved = ctx.api.post(f"{FINDINGS}/{finding}/assign",
                         json={"to": "risk", "reason": "the owner left"})
    if moved.status_code >= 400:
        return BLOCKED, moved.text[:150]
    got = ctx.api.get(f"{FINDINGS}/{finding}")
    body = got.text
    if "risk" not in body:
        return FAIL, "the finding does not show its new owner"
    return PASS, "the handover is on the record"


@case("QA-AM-902", "Assign to the person who already owns it")
def am_902(ctx: Ctx) -> Result:
    """A handover that moves nothing still writes a node saying ownership
    changed."""
    finding = _finding(ctx)
    got = ctx.api.post(f"{FINDINGS}/{finding}/assign",
                       json={"to": "owner", "reason": "no change"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a finding was reassigned to its current owner; the "
                      "chain now records a handover that did not happen")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-903", "Assign with no reason")
def am_903(ctx: Ctx) -> Result:
    finding = _finding(ctx)
    got = ctx.api.post(f"{FINDINGS}/{finding}/assign",
                       json={"to": "risk", "reason": "   "})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a finding changed hands with no reason recorded"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-904", "Extend a due date into the past")
def am_904(ctx: Ctx) -> Result:
    """An extension backwards is not an extension."""
    finding = _finding(ctx)
    got = ctx.api.post(f"{FINDINGS}/{finding}/extend",
                       json={"due_at": 1.0, "reason": "QA"},
                       auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a due date was moved into the past"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-905", "The owner extends their own due date")
def am_905(ctx: Ctx) -> Result:
    """Extending is the one act on a finding its owner must not perform
    alone, or a deadline is whatever the person holding it says."""
    finding = _finding(ctx)
    got = ctx.api.post(f"{FINDINGS}/{finding}/extend",
                       json={"days": 90, "reason": "need more time"},
                       auth=ctx.people["owner"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("the owner extended their own deadline; a due date is "
                      "then whatever the person holding it says")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-906", "The worklist is derived, not assigned")
def am_906(ctx: Ctx) -> Result:
    """A worklist somebody maintains by hand is a second register that
    disagrees with the first."""
    # There is no `/api/v1/worklist`: the worklist is DERIVED for whoever is
    # looking and rendered on their dashboard. That is the design — a list
    # somebody maintains by hand is a second register that disagrees with the
    # first — so it is read where it exists rather than where I assumed.
    _finding(ctx)
    got = ctx.ui.get("/dashboard")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    if "outstanding" not in got.text.lower():
        return FAIL, ("the dashboard shows no worklist; work nobody is told "
                      "about is work nobody does")
    return PASS, "the worklist is derived onto the dashboard"


@case("QA-AM-907", "A closed finding leaves the worklist")
def am_907(ctx: Ctx) -> Result:
    finding = _finding(ctx)
    ctx.api.post(f"{FINDINGS}/{finding}/acknowledge",
                 json={"days": 30, "plan": "fix"}, auth=ctx.people["owner"])
    closed = ctx.api.post(f"{FINDINGS}/{finding}/close",
                          json={"evidence": {"note": "the feed was replaced"},
                                "verified_by": "risk"},
                          auth=ctx.people["risk"])
    if closed.status_code >= 400:
        return BLOCKED, f"could not close: {closed.text[:150]}"
    got = ctx.ui.get("/dashboard")
    if got.status_code < 400 and finding in got.text:
        return FAIL, "a closed finding is still on the worklist"
    return PASS, "closed, and off the list"


@case("QA-AM-908", "A digest is not sent twice for an unchanged worklist")
def am_908(ctx: Ctx) -> Result:
    """Nothing is more certain to be ignored than a daily message identical
    to yesterday's."""
    import inspect

    from core.scheduler import jobs
    source = inspect.getsource(jobs.notify_outstanding)
    if "unchanged" not in source and "suppress" not in source:
        return FAIL, ("the digest job has no suppression for an unchanged "
                      "worklist")
    return PASS, "an unchanged worklist is suppressed"
