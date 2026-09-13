"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — closing a finding.

A blocking finding is the only thing standing between a failed model and
production, and the person who owns the remediation is the person with the
strongest reason to declare it done. So closure has two separate guards: the
route attributes the closure to WHOEVER IS ASKING rather than to a name in the
body, and the register refuses a verifier who is the owner. Both are needed —
the register's check was correct all along while the route was comparing it
against a value the caller invented.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)
from qa.regression_suite.scenarios.g_execution import governed

F = "/api/v1/findings"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
EVIDENCE = {"note": "the feature was repointed and the drift cleared",
            "ticket": "REM-4471"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("cl")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    return f"maya://model/{name}"


def _raise(ctx: Ctx, urn: str, owner: str = "person/owner", *,
           blocking: bool = False, title: str = "A QA finding",
           by: str = "risk") -> str:
    """Raised by the risk manager, so the raiser is never the closer.

    `by` matters more than it looks: the raiser-may-not-close rule fires
    BEFORE the checks a case may be aiming at, so a fixture that raises as
    the person who will later be refused proves the wrong control.
    """
    made = ctx.api.post(F, json={"urn": urn, "severity": "High", "title": title,
                                 "owner": owner, "description": "qa",
                                 "category": "general", "source": "validation",
                                 "blocking": blocking},
                        auth=ctx.people[by])
    return made.json().get("id", "") if made.status_code < 400 else ""


def _close(ctx: Ctx, fid: str, who: str = "validator", **body):
    payload = {"evidence": EVIDENCE, **body}
    return ctx.api.post(f"{F}/{fid}/close", json=payload, auth=ctx.people[who])


@case("QA-AM-113", "Owner closes their own finding")
def am_113(ctx: Ctx) -> Result:
    """The owner here is the validator, who holds `finding:close` — otherwise
    the refusal would be about the permission and would prove nothing about
    the duties check underneath it."""
    fid = _raise(ctx, _model(ctx), owner="person/validator")
    if not fid:
        return BLOCKED, "the finding could not be raised"
    return refused_by_the_control(
        _close(ctx, fid), "a finding was closed by the person who owns it")


@case("QA-AM-114",
      "Owner closes their own finding naming a colleague as `verified_by`")
def am_114(ctx: Ctx) -> Result:
    """The recorded defect: `verified_by` used to be a request field, so the
    owner of a blocking finding could close their own by naming somebody
    else — and that forged attribution went into the permanent evidence
    chain."""
    fid = _raise(ctx, _model(ctx), owner="person/validator")
    if not fid:
        return BLOCKED, "the finding could not be raised"
    got = _close(ctx, fid, verified_by="person/risk")
    outcome = refused_by_the_control(
        got, "a closure was attributed to somebody who did not perform it")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "verifier_not_self":
        return FAIL, (f"refused '{code_of(got)}' rather than naming the "
                      f"attribution problem; the caller cannot tell that the "
                      f"name in the body was the thing rejected")
    return PASS, "refused 'verifier_not_self'"


@case("QA-AM-115", "Owner closes naming themselves in `verified_by`")
def am_115(ctx: Ctx) -> Result:
    """Naming yourself passes the attribution check and must still fail the
    duties one. Two guards, and this is the case that proves the second is
    not dead code behind the first."""
    fid = _raise(ctx, _model(ctx), owner="person/validator")
    if not fid:
        return BLOCKED, "the finding could not be raised"
    got = _close(ctx, fid, verified_by="validator")
    outcome = refused_by_the_control(
        got, "the owner closed their own finding by naming themselves")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) == "verifier_not_self":
        return FAIL, ("the attribution check caught this, which means the "
                      "duties check behind it was never reached and is "
                      "untested by this path")
    return PASS, f"refused '{code_of(got)}' — the duties check, not the name"


@case("QA-AM-116", "A second person closes with an empty evidence object")
def am_116(ctx: Ctx) -> Result:
    """Closure without evidence is an assertion that the problem is gone."""
    fid = _raise(ctx, _model(ctx))
    if not fid:
        return BLOCKED, "the finding could not be raised"
    return refused_by_the_control(
        _close(ctx, fid, evidence={}),
        "a finding was closed with no evidence of what changed")


@case("QA-AM-117", 'A second person closes with `evidence: {"note": ""}`')
def am_117(ctx: Ctx) -> Result:
    """EXPLORATORY, and it found something. `close()` tests the truthiness of
    the evidence DICT, so one key with an empty value satisfies it — while
    `plan_for` and `extend` both `.strip()` their prose and refuse the blank.
    The same platform therefore refuses an empty reason for moving a date and
    accepts an empty note for declaring the work finished."""
    fid = _raise(ctx, _model(ctx))
    if not fid:
        return BLOCKED, "the finding could not be raised"
    got = _close(ctx, fid, evidence={"note": ""})
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}' — the values are checked too"
    return FAIL, ("a finding closed with `{\"note\": \"\"}`: the check is "
                  "`if not evidence`, which is truthiness on the dict and not "
                  "on anything in it, so a closure with nothing written down "
                  "is recorded as evidenced — while `extend` refuses a reason "
                  "that is only whitespace")


@case("QA-AM-118", "Close an already closed finding")
def am_118(ctx: Ctx) -> Result:
    """The second close would rewrite the verifier and the date, which is the
    one pair of facts a closed finding exists to hold still."""
    # Raised by the OWNER, so that the second closer — the risk manager — is
    # not the raiser. Raised by the risk manager, the second attempt refuses
    # `segregation_of_duties` and never reaches the already-closed check.
    fid = _raise(ctx, _model(ctx), by="owner")
    if not fid:
        return BLOCKED, "the finding could not be raised"
    first = _close(ctx, fid)
    if first.status_code >= 400:
        return BLOCKED, f"the first close failed: {first.text[:150]}"
    got = _close(ctx, fid, who="risk")
    outcome = refused_by_the_control(got, "a closed finding was closed again")
    if outcome[0] is PASS and code_of(got) == "segregation_of_duties":
        return FAIL, ("refused on duties, not on the finding being closed, so "
                      "this path never reaches the already-closed guard")
    return outcome


@case("QA-AM-119",
      "Close a finding straight from `open`, never acknowledged or planned")
def am_119(ctx: Ctx) -> Result:
    """Closure does not require the workflow to have been walked. Somebody
    fixing the thing the day it is raised is the outcome the register wants,
    and refusing it would make the process the point."""
    fid = _raise(ctx, _model(ctx))
    if not fid:
        return BLOCKED, "the finding could not be raised"
    got = _close(ctx, fid)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — a finding fixed before "
                      f"anybody acknowledged it cannot be closed, so the "
                      f"process outranks the outcome")
    body = got.json() or {}
    if body.get("status") != "closed":
        return FAIL, f"accepted but the status reads '{body.get('status')}'"
    if not body.get("closure_verified_by"):
        return FAIL, "closed with no verifier recorded"
    return PASS, f"closed, verified by {body.get('closure_verified_by')}"


@case("QA-AM-120", "Close a blocking finding, then resolve a warrant")
def am_120(ctx: Ctx) -> Result:
    """Resolution is the one point every consumer passes through, so it is
    where the block has to bite — and where it has to stop biting."""
    made = governed(ctx)
    urn = made["urn"]
    fid = _raise(ctx, urn, blocking=True, title="Blocks service")
    if not fid:
        return BLOCKED, "the blocking finding could not be raised"
    ctx.api.post("/api/v1/warrants",
                 json={"urn": urn, "principal": "svc-pricing",
                       "environment": "prod",
                       "declared_use": "credit_decision"})
    ask = {"urn": urn, "principal": "svc-pricing", "environment": "prod",
           "declared_use": "credit_decision"}
    blocked = ctx.api.post("/api/v1/resolve", json=ask)
    if blocked.status_code < 400:
        return FAIL, ("a warrant resolved with a blocking finding open: the "
                      "model failed challenge and is being served anyway")
    if code_of(blocked) != "blocked":
        return FAIL, f"refused '{code_of(blocked)}' rather than 'blocked'"
    closed = _close(ctx, fid)
    if closed.status_code >= 400:
        return BLOCKED, f"the finding could not be closed: {closed.text[:150]}"
    after = ctx.api.post("/api/v1/resolve", json=ask)
    if after.status_code >= 400:
        return FAIL, (f"the block did not clear on closure: "
                      f"'{code_of(after)}' — a closed finding still withholds "
                      f"the model")
    return PASS, "refused 'blocked', then resolved once the finding closed"


@case("QA-AM-121",
      "Close a blocking finding while a *second* blocking finding is open")
def am_121(ctx: Ctx) -> Result:
    """The refusal has to name what is still outstanding. "Blocked" without
    the remaining title sends somebody to close a finding that is already
    closed."""
    made = governed(ctx)
    urn = made["urn"]
    first = _raise(ctx, urn, blocking=True, title="The first blocker")
    second = _raise(ctx, urn, blocking=True, title="The second blocker")
    if not (first and second):
        return BLOCKED, "the blocking findings could not be raised"
    ctx.api.post("/api/v1/warrants",
                 json={"urn": urn, "principal": "svc-pricing",
                       "environment": "prod",
                       "declared_use": "credit_decision"})
    closed = _close(ctx, first)
    if closed.status_code >= 400:
        return BLOCKED, f"the first could not be closed: {closed.text[:150]}"
    got = ctx.api.post("/api/v1/resolve",
                       json={"urn": urn, "principal": "svc-pricing",
                             "environment": "prod",
                             "declared_use": "credit_decision"})
    if got.status_code < 400:
        return FAIL, "one of two blocking findings closed and the model served"
    body = got.text
    if "The second blocker" not in body:
        return FAIL, ("the refusal does not name the finding still open, so "
                      "the reader cannot tell which one to go and close")
    if "The first blocker" in body:
        return FAIL, "the refusal still names the finding that was closed"
    return PASS, "refused, naming the second blocker and not the first"


@case("QA-AM-122",
      "The owner is reassigned to the intended verifier, who then closes")
def am_122(ctx: Ctx) -> Result:
    """The way round the duties check that does not need a forged name: take
    ownership first, then close as owner. The comparison is made at closure
    against the owner AS IT STANDS THEN, which is what closes this."""
    fid = _raise(ctx, _model(ctx))
    if not fid:
        return BLOCKED, "the finding could not be raised"
    moved = ctx.api.post(f"{F}/{fid}/assign",
                         json={"to": "person/validator",
                               "reason": "taking this one on"},
                         auth=ctx.people["risk"])
    if moved.status_code >= 400:
        return BLOCKED, f"the handover failed: {moved.text[:150]}"
    return refused_by_the_control(
        _close(ctx, fid),
        "the verifier took ownership and then verified their own closure")
