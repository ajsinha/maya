"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — supervisory matters, and the gap between two dates.

A matter carries the date the FIRM GAVE THE SUPERVISOR. Each finding under it
carries an internal remediation date derived from its severity. The whole
value of the object is that both are held, so the gap can be computed months
before the letter is due rather than on the day it is.
"""
from __future__ import annotations

import time

from core.validation.common import REMEDIATION_DAYS
from core.validation.supervisory import HEADROOM_DAYS, KINDS
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

SM = "/api/v1/supervisory-matters"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
DAY = 86400.0


def _model(ctx: Ctx) -> str:
    name = ctx.unique("sm")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    return f"maya://model/{name}"


def _raise(ctx: Ctx, **over):
    body = {"reference": ctx.unique("MRA"), "kind": "mra",
            "supervisor": "the PRA", "title": "A QA matter",
            "scope": [_model(ctx)], "owner": "owner",
            "description": "a QA description", "severity": "High"}
    body.update(over)
    return ctx.api.post(SM, json=body, auth=ctx.people["risk"])


def _status(ctx: Ctx, reference: str):
    return ctx.api.get(f"{SM}?reference={reference}", auth=ctx.people["risk"])


@case("QA-AM-148", "Raise a second matter under one supervisor reference")
def am_148(ctx: Ctx) -> Result:
    """A second row under one reference is how a firm ends up reporting two
    remediation programmes for one letter."""
    ref = ctx.unique("MRA")
    if _raise(ctx, reference=ref).status_code >= 400:
        return BLOCKED, "the first matter could not be raised"
    return refused_by_the_control(
        _raise(ctx, reference=ref),
        "two matters were recorded under one supervisor reference")


@case("QA-AM-149", "Raise a matter with an empty scope")
def am_149(ctx: Ctx) -> Result:
    """A matter with no models in scope has nothing to remediate. If the
    supervisor's point is about a process, the models it governs are what
    make it trackable."""
    return refused_by_the_control(
        _raise(ctx, scope=[]),
        "a matter was recorded over no models, so nothing is tracked against "
        "it")


@case("QA-AM-1500", "Raise a matter of a kind that is not one")
def am_1500(ctx: Ctx) -> Result:
    got = _raise(ctx, kind="stern_letter")
    if got.status_code < 400:
        return FAIL, "a matter of an unknown kind was recorded"
    if code_of(got) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the check"
    if not any(k in got.text for k in KINDS):
        return FAIL, "the refusal does not name the five kinds"
    return PASS, f"refused '{code_of(got)}', naming the {len(KINDS)} kinds"


@case("QA-AM-1501", "Raise a matter with no supervisor reference")
def am_1501(ctx: Ctx) -> Result:
    """A matter tracked under an internal id only is one nobody can reconcile
    against the letter."""
    return refused_by_the_control(
        _raise(ctx, reference="   "),
        "a matter was recorded with no supervisor reference, so nothing "
        "reconciles it against the letter")


@case("QA-AM-147", "One matter raises one finding per model in scope")
def am_147(ctx: Ctx) -> Result:
    urns = [_model(ctx) for _ in range(4)]
    ref = ctx.unique("MRA")
    got = _raise(ctx, reference=ref, scope=urns)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json()
    raised = body.get("findings") or []
    if len(raised) != len(urns):
        return FAIL, (f"{len(urns)} models in scope produced {len(raised)} "
                      f"finding(s); a model in scope with no finding is one "
                      f"nobody is remediating")
    return PASS, f"{len(urns)} models, {len(raised)} findings"


@case("QA-AM-150", "An MRIA's findings block")
def am_150(ctx: Ctx) -> Result:
    """An MRIA is a deficiency in a core process and the remediation date is
    not negotiable, so its findings must stop the model rather than sit
    beside it."""
    got = _raise(ctx, kind="mria", reference=ctx.unique("MRIA"))
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    raised = got.json().get("findings") or []
    if not raised:
        return BLOCKED, "no findings came back to inspect"
    unblocking = [f for f in raised if not f.get("blocking")]
    if unblocking:
        return FAIL, (f"{len(unblocking)} of {len(raised)} MRIA finding(s) do "
                      f"not block, so the model runs on through a deficiency "
                      f"the supervisor called immediate")
    return PASS, f"all {len(raised)} MRIA findings block"


@case("QA-AM-1502", "An MRA's findings do not block")
def am_1502(ctx: Ctx) -> Result:
    """The distinction has to cut both ways, or `blocking` says nothing about
    which kind of matter this is."""
    got = _raise(ctx, kind="mra")
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    raised = got.json().get("findings") or []
    if not raised:
        return BLOCKED, "no findings came back"
    blocking = [f for f in raised if f.get("blocking")]
    if blocking:
        return FAIL, (f"{len(blocking)} MRA finding(s) block, so an MRA is "
                      f"treated as an MRIA and the two kinds are the same "
                      f"object with different labels")
    return PASS, "MRA findings do not block; MRIA findings do"


@case("QA-AM-151", "Close a matter with a finding still open")
def am_151(ctx: Ctx) -> Result:
    ref = ctx.unique("MRA")
    if _raise(ctx, reference=ref).status_code >= 400:
        return BLOCKED, "the matter could not be raised"
    return refused_by_the_control(
        ctx.api.post(f"{SM}/{ref}/close", json={"note": "done"},
                     auth=ctx.people["risk"]),
        "a matter was closed while a finding under it was still open, so the "
        "firm reports remediation it has not finished")


@case("QA-AM-153", "Close a matter with an empty note")
def am_153(ctx: Ctx) -> Result:
    return refused_by_the_control(
        ctx.api.post(f"{SM}/{ctx.unique('MRA')}/close", json={"note": "   "},
                     auth=ctx.people["risk"]),
        "a matter was closed with nothing recorded about how")


@case("QA-AM-157", "A matter with open findings and no committed date")
def am_157(ctx: Ctx) -> Result:
    """Not at risk, and the reason must say why: no commitment recorded is
    not the same as having time."""
    ref = ctx.unique("MRA")
    got = _raise(ctx, reference=ref, committed_at=None)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json()
    if body.get("at_risk"):
        return FAIL, "a matter with no committed date reports as at risk"
    why = (body.get("detail") or "").lower()
    if "committed" not in why and "commitment" not in why:
        return FAIL, (f"the reason does not say the commitment is missing: "
                      f"{why[:120]}")
    return PASS, "not at risk, and the missing commitment is the stated reason"


@case("QA-AM-154", "The internal plan lands months after the committed date")
def am_154(ctx: Ctx) -> Result:
    """A plan landing five months after the date the firm gave a supervisor
    is not a near miss, and must not be described as one."""
    ref = ctx.unique("MRA")
    got = _raise(ctx, reference=ref, severity="Low",
                 committed_at=time.time() + 5 * DAY)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json()
    if not body.get("at_risk"):
        return BLOCKED, ("the internal date did not fall after the commitment "
                         f"in this fixture: {(body.get('why') or '')[:120]}")
    why = body.get("detail") or ""
    if "AFTER" not in why:
        return FAIL, (f"a plan that misses the commitment outright is not "
                      f"said in its own words: {why[:150]}")
    if "headroom" in why.lower() and "not a question of headroom" not in why:
        return FAIL, "an outright miss is reported as a headroom problem"
    return PASS, "reported as a miss, not a near miss"


@case("QA-AM-158", "Every finding closed, the matter still open")
def am_158(ctx: Ctx) -> Result:
    """Nothing open comes first: a fully remediated matter with no recorded
    commitment must not report the missing commitment as its headline."""
    ref = ctx.unique("MRA")
    got = _raise(ctx, reference=ref)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    # A different person closes. Raising the matter recorded
    # `finding_raised` against `risk`, and the person who raised a finding may
    # not close it — so `risk` closing its own is refused
    # `segregation_of_duties`, correctly.
    closer = ctx.unique("closer")
    ctx.api.post("/api/v1/principals",
                 json={"username": closer, "display_name": closer,
                       "roles": ["validator"], "password": f"{closer}-password",
                       "legal_entities": [], "domains": []})
    for finding in got.json().get("findings") or []:
        # `evidence` is required and the verifier is the authenticated caller,
        # never a request field — a `note` alone is refused.
        closed = ctx.api.post(f"/api/v1/findings/{finding.get('id')}/close",
                              json={"evidence": {"note": "remediated"}},
                              auth=(closer, f"{closer}-password"))
        if closed.status_code >= 400:
            return BLOCKED, f"could not close a finding: {closed.text[:140]}"
    body = _status(ctx, ref)
    if body.status_code >= 400:
        return BLOCKED, body.text[:170]
    row = body.json()
    row = (row.get("matters") or [row])[0] if isinstance(row, dict) else row
    if row.get("at_risk"):
        return FAIL, "a fully remediated matter reports as at risk"
    why = (row.get("detail") or "").lower()
    if "closed" not in why:
        return BLOCKED, f"the findings did not close in this fixture: {why[:120]}"
    if "commit" in why:
        return FAIL, ("a matter whose work is done reports the missing "
                      f"commitment as its headline: {why[:130]}")
    return PASS, "the headline is that the work is done"


@case("QA-AM-161", "The estate view with no matters recorded")
def am_161(ctx: Ctx) -> Result:
    """An empty supervisory estate has to say it is empty rather than
    answering nothing, or a clean bill of health is indistinguishable from a
    report that failed to run."""
    got = ctx.api.get(SM, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json()
    if not (body.get("detail") or "").strip():
        return FAIL, ("the estate view carries no statement, so no matters "
                      "recorded and the report not running look the same")
    return PASS, f"{body.get('at_risk', 0)} at risk, and the view says so"


@case("QA-AM-1503", "The headroom boundary is stated, not implied")
def am_1503(ctx: Ctx) -> Result:
    """`HEADROOM_DAYS` decides whether a matter is reported at risk. A
    threshold a reader cannot see is one nobody can argue with."""
    ref = ctx.unique("MRA")
    internal = REMEDIATION_DAYS["Low"]
    got = _raise(ctx, reference=ref, severity="Low",
                 committed_at=time.time() + (internal + 100) * DAY)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json()
    if body.get("at_risk"):
        return BLOCKED, f"this fixture is at risk: {(body.get('detail') or '')[:110]}"
    why = body.get("detail") or ""
    if "day(s) ahead" not in why:
        return FAIL, f"the slack is not reported: {why[:130]}"
    tight = _raise(ctx, reference=ctx.unique("MRA"), severity="Low",
                   committed_at=time.time()
                   + (internal + HEADROOM_DAYS - 1) * DAY)
    if tight.status_code >= 400:
        return BLOCKED, tight.text[:170]
    if f"{HEADROOM_DAYS:.0f}" not in (tight.json().get("detail") or ""):
        return FAIL, ("a matter inside the headroom does not name the "
                      f"threshold: {(tight.json().get('detail') or '')[:130]}")
    return PASS, f"slack reported, and {HEADROOM_DAYS:.0f} days named at the edge"
