"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — the acts a finding goes through: assign, acknowledge, plan, extend.

Every one of them is a place a remediation date can move without anybody
deciding it should. The acknowledgement is the interesting one: an owner who
could acknowledge to any date they liked would have an extension mechanism
needing nobody's agreement and leaving no count.
"""
from __future__ import annotations

import time

from core.validation.common import REMEDIATION_DAYS
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

F = "/api/v1/findings"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
DAY = 86400.0
SEVERITY = "High"


def _person(ctx: Ctx, role: str = "validator"):
    who = ctx.unique("fp")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": [role], "password": f"{who}-password",
                              "legal_entities": [], "domains": []})
    return (who, f"{who}-password") if made.status_code < 400 else None


def _finding(ctx: Ctx, owner: str = "person/owner"):
    name = ctx.unique("fa")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    made = ctx.api.post(F, json={"urn": f"maya://model/{name}",
                                 "severity": SEVERITY, "title": "A QA finding",
                                 "owner": owner, "description": "qa",
                                 "category": "general", "source": "validation"},
                        auth=ctx.people["risk"])
    return made.json()["id"] if made.status_code < 400 else ""


def _read(ctx: Ctx, fid: str) -> dict:
    got = ctx.api.get(f"{F}/{fid}", auth=ctx.people["risk"])
    return got.json() if got.status_code < 400 else {}


def _due(ctx: Ctx, fid: str) -> float:
    row = _read(ctx, fid)
    return (row.get("finding") or row).get("due_at") or 0.0


@case("QA-AM-081", "Assign a finding to the person who already owns it")
def am_081(ctx: Ctx) -> Result:
    """A handover to the incumbent is a handover that did not happen, and it
    resets the acknowledgement clock for nothing."""
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    return refused_by_the_control(
        ctx.api.post(f"{F}/{fid}/assign",
                     json={"to": "person/owner", "reason": "qa"},
                     auth=ctx.people["risk"]),
        "a finding was handed to the person who already owns it")


@case("QA-AM-082", "Assign to the current owner without the person/ prefix")
def am_082(ctx: Ctx) -> Result:
    """The same human, seven characters shorter."""
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    return refused_by_the_control(
        ctx.api.post(f"{F}/{fid}/assign", json={"to": "owner", "reason": "qa"},
                     auth=ctx.people["risk"]),
        "a finding was handed to its own owner under a shorter spelling")


@case("QA-AM-084", "Assign with an empty reason")
def am_084(ctx: Ctx) -> Result:
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    return refused_by_the_control(
        ctx.api.post(f"{F}/{fid}/assign",
                     json={"to": "person/validator", "reason": "   "},
                     auth=ctx.people["risk"]),
        "ownership moved with no reason recorded")


@case("QA-AM-085", "Assign to nobody")
def am_085(ctx: Ctx) -> Result:
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    return refused_by_the_control(
        ctx.api.post(f"{F}/{fid}/assign", json={"to": "   ", "reason": "qa"},
                     auth=ctx.people["risk"]),
        "a finding was assigned to nobody, so it is open and unowned")


@case("QA-AM-086", "Acknowledge as somebody other than the owner")
def am_086(ctx: Ctx) -> Result:
    """An acknowledgement somebody else recorded for you is the paperwork of
    a commitment without the commitment."""
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    return refused_by_the_control(
        ctx.api.post(f"{F}/{fid}/acknowledge",
                     json={"plan": "fix it by Friday"},
                     auth=ctx.people["validator"]),
        "somebody who does not own the finding accepted it on the owner's "
        "behalf")


@case("QA-AM-088", "Acknowledge to a date after the finding's due date")
def am_088(ctx: Ctx) -> Result:
    """This is the hole the check closes: an owner acknowledging to any date
    they liked would have an extension mechanism that needs nobody's
    agreement and leaves no count."""
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    return refused_by_the_control(
        ctx.api.post(f"{F}/{fid}/acknowledge",
                     json={"plan": "fix it eventually",
                           "committed_at": _due(ctx, fid) + 30 * DAY},
                     auth=ctx.people["owner"]),
        "an owner committed to a date past the finding's own remediation "
        "date, which is an uncounted extension")


@case("QA-AM-089", "Immediately re-attempt QA-AM-088 with no plan at all")
def am_089(ctx: Ctx) -> Result:
    """`acknowledge` records the plan BEFORE it checks the committed date. So
    an acknowledgement refused `beyond_the_due_date` has already written the
    plan, and the same call repeated with no plan at all now satisfies the
    plan requirement.
    """
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    refused = ctx.api.post(f"{F}/{fid}/acknowledge",
                           json={"plan": "a plan that should not survive",
                                 "committed_at": _due(ctx, fid) + 30 * DAY},
                           auth=ctx.people["owner"])
    if refused.status_code < 400:
        return BLOCKED, "the setup acknowledgement was not refused"
    again = ctx.api.post(f"{F}/{fid}/acknowledge", json={},
                         auth=ctx.people["owner"])
    if again.status_code >= 400:
        if code_of(again) == "plan_required":
            return PASS, "the refused call left no plan behind"
        return BLOCKED, f"refused '{code_of(again)}': {again.text[:130]}"
    return FAIL, (
        "an acknowledgement refused `beyond_the_due_date` still recorded its "
        "plan — `plan_for` runs before the date check — so acknowledging "
        "again with NO plan is accepted. A refused act left a durable write "
        "behind, and the plan requirement is satisfied by a call that failed")


@case("QA-AM-091", "Acknowledge to exactly the due date")
def am_091(ctx: Ctx) -> Result:
    """The boundary is inclusive: committing to the date the finding is due
    is committing within the window."""
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    got = ctx.api.post(f"{F}/{fid}/acknowledge",
                       json={"plan": "fix it", "committed_at": _due(ctx, fid)},
                       auth=ctx.people["owner"])
    if got.status_code >= 400:
        return FAIL, (f"committing to the due date itself was refused "
                      f"'{code_of(got)}', so the window excludes its own last "
                      f"day")
    return PASS, "the due date itself is inside the window"


@case("QA-AM-092", "Acknowledge to a date that has already passed")
def am_092(ctx: Ctx) -> Result:
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    return refused_by_the_control(
        ctx.api.post(f"{F}/{fid}/acknowledge",
                     json={"plan": "fix it", "committed_at": time.time() - 10},
                     auth=ctx.people["owner"]),
        "an owner committed to a date in the past")


@case("QA-AM-093", "Acknowledge, then hand the finding over")
def am_093(ctx: Ctx) -> Result:
    """An acknowledgement is one person's commitment. It cannot survive being
    handed to somebody who never made it."""
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    done = ctx.api.post(f"{F}/{fid}/acknowledge", json={"plan": "fix it"},
                        auth=ctx.people["owner"])
    if done.status_code >= 400:
        return BLOCKED, done.text[:170]
    moved = ctx.api.post(f"{F}/{fid}/assign",
                         json={"to": "person/validator",
                               "reason": "handing over"},
                         auth=ctx.people["risk"])
    if moved.status_code >= 400:
        return BLOCKED, moved.text[:170]
    state = _read(ctx, fid)
    ack = (state.get("acknowledgement") or {})
    if ack.get("acknowledged"):
        return FAIL, ("the acknowledgement survived a handover, so the new "
                      "owner is recorded as having committed to a date they "
                      "never saw")
    return PASS, "the acknowledgement did not follow the finding"


@case("QA-AM-096", "Record a plan that is empty")
def am_096(ctx: Ctx) -> Result:
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    return refused_by_the_control(
        ctx.api.post(f"{F}/{fid}/plan", json={"plan": "  "},
                     auth=ctx.people["owner"]),
        "a finding was planned with nothing written down")


@case("QA-AM-098", "Extend before anybody has acknowledged")
def am_098(ctx: Ctx) -> Result:
    """Extending a date nobody agreed to moves a number, not a commitment."""
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    return refused_by_the_control(
        ctx.api.post(f"{F}/{fid}/extend",
                     json={"reason": "more time", "days": 10},
                     auth=ctx.people["risk"]),
        "a date nobody had agreed to was extended")


@case("QA-AM-099", "Extend as the owner")
def am_099(ctx: Ctx) -> Result:
    """An extension is the point at which somebody independent asks whether
    the date was ever realistic.

    Two layers again, and the outer one hides the inner. `finding:extend` is
    not a permission the owner holds, so over HTTP the owner is stopped at
    the gate and `self_extension` is never consulted. The register's own
    check has to be called directly, or it is a control nobody has run — and
    it is the one that would matter the day a role gains the permission.
    """
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    if ctx.api.post(f"{F}/{fid}/acknowledge", json={"plan": "fix it"},
                    auth=ctx.people["owner"]).status_code >= 400:
        return BLOCKED, "could not acknowledge"
    over_http = ctx.api.post(f"{F}/{fid}/extend",
                             json={"reason": "more time", "days": 10},
                             auth=ctx.people["owner"])
    if over_http.status_code < 400:
        return FAIL, "the owner extended their own deadline over HTTP"
    workflow = ctx.ui.app.state.ctx.get("finding_workflow")
    if workflow is None:
        return PASS, (f"refused '{code_of(over_http)}' at the permission gate")
    from core.validation.workflow import FindingWorkflowError
    try:
        workflow.extend(fid, "person/owner", "more time", days=10)
    except FindingWorkflowError as exc:
        if exc.code != "self_extension":
            return FAIL, f"the register refused '{exc.code}' instead"
        return PASS, (f"refused '{code_of(over_http)}' at the gate and "
                      f"'self_extension' in the register")
    return FAIL, ("the register let the owner extend their own deadline; only "
                  "the permission gate stands between one person and a "
                  "deadline they set for themselves")


@case("QA-AM-100", "Extend as the owner spelled without the person/ prefix")
def am_100(ctx: Ctx) -> Result:
    """The same human, seven characters shorter. `same_person`, not `==`."""
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    if ctx.api.post(f"{F}/{fid}/acknowledge", json={"plan": "fix it"},
                    auth=ctx.people["owner"]).status_code >= 400:
        return BLOCKED, "could not acknowledge"
    workflow = ctx.ui.app.state.ctx.get("finding_workflow")
    if workflow is None:
        return BLOCKED, "no finding workflow reachable from this run"
    from core.validation.workflow import FindingWorkflowError
    try:
        workflow.extend(fid, "owner", "more time", days=10)
    except FindingWorkflowError as exc:
        if exc.code != "self_extension":
            return FAIL, f"refused '{exc.code}', not self_extension"
        return PASS, "refused 'self_extension' on the bare spelling too"
    return FAIL, ("the owner extended their own deadline by dropping seven "
                  "characters from their name")


@case("QA-AM-101", "Extend with no reason")
def am_101(ctx: Ctx) -> Result:
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    ctx.api.post(f"{F}/{fid}/acknowledge", json={"plan": "fix it"},
                 auth=ctx.people["owner"])
    return refused_by_the_control(
        ctx.api.post(f"{F}/{fid}/extend", json={"reason": " ", "days": 10},
                     auth=ctx.people["risk"]),
        "a remediation date moved with no reason, so it changed by itself")


@case("QA-AM-103", "Extend to exactly the current due date")
def am_103(ctx: Ctx) -> Result:
    """An extension moves a date outwards. Zero is not outwards, and allowing
    it would put an `EXTENDED` act on the record for a date that did not
    move."""
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    ctx.api.post(f"{F}/{fid}/acknowledge", json={"plan": "fix it"},
                 auth=ctx.people["owner"])
    return refused_by_the_control(
        ctx.api.post(f"{F}/{fid}/extend",
                     json={"reason": "no change", "due_at": _due(ctx, fid)},
                     auth=ctx.people["risk"]),
        "an extension was recorded that moved the date nowhere")


@case("QA-AM-104", "Extend a High finding by exactly its own window")
def am_104(ctx: Ctx) -> Result:
    """The limit is the original remediation window, and the boundary is
    inclusive."""
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    ctx.api.post(f"{F}/{fid}/acknowledge", json={"plan": "fix it"},
                 auth=ctx.people["owner"])
    window = REMEDIATION_DAYS[SEVERITY]
    got = ctx.api.post(f"{F}/{fid}/extend",
                       json={"reason": "slipped", "days": window},
                       auth=ctx.people["risk"])
    if got.status_code >= 400:
        return FAIL, (f"an extension of exactly the {window}-day window was "
                      f"refused '{code_of(got)}'")
    return PASS, f"{window} days granted, the boundary is inclusive"


@case("QA-AM-105", "Extend a High finding by one day more than its window")
def am_105(ctx: Ctx) -> Result:
    """An extension longer than the original window is a new remediation date
    nobody has justified."""
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    ctx.api.post(f"{F}/{fid}/acknowledge", json={"plan": "fix it"},
                 auth=ctx.people["owner"])
    return refused_by_the_control(
        ctx.api.post(f"{F}/{fid}/extend",
                     json={"reason": "slipped a lot",
                           "days": REMEDIATION_DAYS[SEVERITY] + 1},
                     auth=ctx.people["risk"]),
        "an extension longer than the whole original window was granted")


@case("QA-AM-111", "Act against a closed finding")
def am_111(ctx: Ctx) -> Result:
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    closer = _person(ctx)
    if closer is None:
        return BLOCKED, "could not mint a closer"
    closed = ctx.api.post(f"{F}/{fid}/close",
                          json={"evidence": {"note": "done"}}, auth=closer)
    if closed.status_code >= 400:
        return BLOCKED, closed.text[:170]
    still = []
    for act, body in (("assign", {"to": "person/validator", "reason": "qa"}),
                      ("acknowledge", {"plan": "qa"}),
                      ("plan", {"plan": "qa"}),
                      ("extend", {"reason": "qa", "days": 5})):
        got = ctx.api.post(f"{F}/{fid}/{act}", json=body,
                           auth=ctx.people["risk"])
        if got.status_code < 400:
            still.append(act)
    if still:
        return FAIL, f"a closed finding still accepts: {', '.join(still)}"
    return PASS, "assign, acknowledge, plan and extend all refused once closed"


@case("QA-AM-112", "Act against a finding id that does not exist")
def am_112(ctx: Ctx) -> Result:
    wrong = []
    for act, body in (("assign", {"to": "person/validator", "reason": "qa"}),
                      ("acknowledge", {"plan": "qa"}),
                      ("plan", {"plan": "qa"}),
                      ("extend", {"reason": "qa", "days": 5})):
        got = ctx.api.post(f"{F}/qa-no-such-finding/{act}", json=body,
                           auth=ctx.people["risk"])
        if got.status_code < 400 or got.status_code >= 500:
            wrong.append(f"{act}={got.status_code}")
    if wrong:
        return FAIL, f"unknown finding answered: {', '.join(wrong)}"
    return PASS, "all four acts refused against an unknown id"
