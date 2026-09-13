"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — access recertification.

Two things make this control real rather than a form. **`unreviewed` is a
first-class number**: an item nobody looked at is not a confirmed one and
never becomes one, the campaign does not time out, and closing decides
nothing about what was left. And **a reviewer may not answer their own row**,
which is the whole failure mode of an access review and is not hypothetical —
a reviewer assigned their own row confirms it, because there is nothing to
think about.

The authority to answer is being NAMED as the reviewer, not holding a
permission. That was a recorded defect in the other direction: the route once
asked for `principal:manage`, which only an administrator holds, while
`answer()` refuses anybody who is not the reviewer — so the two checks
excluded each other and a campaign over a second-line reviewer could never be
answered by anyone.

Every case is `isolated`: a campaign reference is estate-wide and a reviewer's
roles are mutated by a revocation.
"""
from __future__ import annotations

import time

from core.authz.recertification import DORMANT_AFTER_DAYS
from qa.regression_suite.harness import ADMIN
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

C = "/api/v1/recertification"
P = "/api/v1/principals"
DAY = 86400.0


def _person(ctx: Ctx, roles=("model_owner",), **over) -> str:
    who = ctx.unique("rc")
    body = {"username": who, "display_name": who, "roles": list(roles),
            "password": f"{who}-password", "legal_entities": [], "domains": []}
    body.update(over)
    made = ctx.api.post(P, json=body, auth=ADMIN)
    return who if made.status_code < 400 else ""


def _open(ctx: Ctx, reviewer: str, population, **over):
    body = {"reference": ctx.unique("REC"), "reviewer": reviewer,
            "title": "QA access review", "population": list(population)}
    body.update(over)
    return ctx.api.post(C, json=body, auth=ADMIN)


def _answer(ctx: Ctx, reference: str, principal: str, reviewer: str,
            state: str = "confirmed", reason: str = ""):
    return ctx.api.post(f"{C}/{reference}/{principal}",
                        json={"state": state, "reason": reason},
                        auth=(reviewer, f"{reviewer}-password"))


def _status(ctx: Ctx, reference: str) -> dict:
    got = ctx.api.get(f"{C}/{reference}", auth=ADMIN)
    return got.json() if got.status_code < 400 else {}


@case("QA-GOV-253", "Open a campaign on an estate with no active principals",
      isolated=True)
def gov_253(ctx: Ctx) -> Result:
    """An empty review that closes clean is a control reporting an all-clear
    over an estate it never saw.

    An estate with no active principals cannot be built through the API —
    somebody has to be authenticated to build anything — so the population is
    emptied under the engine instead. Opening the campaign over the real QA
    estate would prove only that eight accounts exist.
    """
    engine = ctx.ui.app.state.ctx.get("recertification")
    if engine is None:
        return BLOCKED, "no recertification engine is wired"
    reviewer = _person(ctx, ["auditor"])
    if not reviewer:
        return BLOCKED, "the reviewer could not be created"

    class Nobody:
        """Everybody is suspended, and the reviewer still resolves."""

        def __init__(self, real):
            self.require = real.require

        @staticmethod
        def list():
            return []

    was, engine.principals = engine.principals, Nobody(engine.principals)
    try:
        engine.open(ctx.unique("REC"), reviewer=reviewer, population=None)
    except Exception as exc:
        code = getattr(exc, "error", None) or getattr(exc, "code", None) \
            or f"{exc}"
        if "empty_population" not in f"{code}{exc}":
            return FAIL, f"refused for some other reason: {exc}"
        return PASS, "refused 'empty_population' over an estate with nobody in it"
    finally:
        engine.principals = was
    return FAIL, ("a campaign was opened over nobody: it will close clean and "
                  "report an all-clear over an estate it never saw")


@case("QA-GOV-254", "Open a campaign whose only subject is the reviewer",
      isolated=True)
def gov_254(ctx: Ctx) -> Result:
    """Accepted, and then permanently unanswerable: `self_recertification`
    refuses the only row. The campaign is not wrong to exist — somebody has
    to be told — but it must be visible as unanswerable rather than sitting
    open for ever looking like work in progress."""
    reviewer = _person(ctx, ["auditor"])
    if not reviewer:
        return BLOCKED, "the reviewer could not be created"
    made = _open(ctx, reviewer, population=[reviewer])
    if made.status_code >= 400:
        return PASS, (f"refused at open ('{code_of(made)}') — a campaign that "
                      f"cannot be answered is not opened")
    reference = (made.json() or {}).get("reference")
    got = _answer(ctx, reference, reviewer, reviewer)
    if got.status_code < 400:
        return FAIL, ("the reviewer answered their own row, which is the "
                      "whole failure mode this control exists for")
    if code_of(got) != "self_recertification":
        return FAIL, f"refused '{code_of(got)}'"
    status = _status(ctx, reference)
    if status.get("unreviewed") != 1:
        return FAIL, f"the unanswerable row is not unreviewed: {status}"
    return PASS, ("refused 'self_recertification', and the row stands as "
                  "unreviewed rather than as answered")


@case("QA-GOV-255", "Reviewer answers their own row after a reassignment",
      isolated=True)
def gov_255(ctx: Ctx) -> Result:
    """The legitimate way out of QA-GOV-254. Handing the campaign over
    records who passed it on and why, and the new reviewer may answer the row
    the old one could not."""
    first, second = _person(ctx, ["auditor"]), _person(ctx, ["auditor"])
    if not (first and second):
        return BLOCKED, "the reviewers could not be created"
    made = _open(ctx, first, population=[first])
    if made.status_code >= 400:
        return BLOCKED, f"the campaign could not be opened: {made.text[:140]}"
    reference = (made.json() or {}).get("reference")
    moved = ctx.api.post(f"{C}/{reference}/reassign",
                         json={"to": second,
                               "reason": "the subject cannot review himself"},
                         auth=ADMIN)
    if moved.status_code >= 400:
        return BLOCKED, f"the reassignment failed: {moved.text[:140]}"
    got = _answer(ctx, reference, first, second)
    if got.status_code >= 400:
        return FAIL, (f"the new reviewer was refused '{code_of(got)}', so a "
                      f"campaign over its own reviewer stays unanswerable "
                      f"even after being handed over")
    if _answer(ctx, reference, first, first).status_code < 400:
        return FAIL, "the old reviewer can still answer after handing over"
    return PASS, "the new reviewer answers the row the old one could not"


@case("QA-GOV-258", "Answer the same person twice with different answers",
      isolated=True)
def gov_258(ctx: Ctx) -> Result:
    """EXPECTED TO FAIL. `answer` refuses a closed campaign and the wrong
    reviewer, and nothing refuses an item that has already been answered — so
    a confirmation can be turned into a revocation, or back, while the
    campaign is open, and only the last one is reported."""
    reviewer, subject = _person(ctx, ["auditor"]), _person(ctx)
    if not (reviewer and subject):
        return BLOCKED, "the principals could not be created"
    made = _open(ctx, reviewer, population=[subject])
    if made.status_code >= 400:
        return BLOCKED, f"the campaign could not be opened: {made.text[:140]}"
    reference = (made.json() or {}).get("reference")
    if _answer(ctx, reference, subject, reviewer).status_code >= 400:
        return BLOCKED, "the first answer failed"
    got = _answer(ctx, reference, subject, reviewer, state="revoked",
                  reason="on reflection, no")
    if got.status_code >= 400:
        return PASS, (f"the second answer is refused '{code_of(got)}' — an "
                      f"answer is given once")
    status = _status(ctx, reference)
    return FAIL, (f"a confirmed item was answered again as revoked and only "
                  f"the last answer is reported ({status.get('confirmed')} "
                  f"confirmed, {status.get('revoked')} revoked): nothing "
                  f"refuses re-answering an item, so what a reviewer first "
                  f"said is not on the record they signed")


@case("QA-GOV-262", "Revoke the last administrator's access", isolated=True)
def gov_262(ctx: Ctx) -> Result:
    """The lockout `suspend` has always refused, reachable by a second door.
    Recertification calls `set_roles` to revoke, over a population that
    includes the administrators — and a register with nobody who can grant a
    role has only an UPDATE against the database as a route back."""
    reviewer = _person(ctx, ["auditor"])
    if not reviewer:
        return BLOCKED, "the reviewer could not be created"
    made = _open(ctx, reviewer, population=[ADMIN[0]])
    if made.status_code >= 400:
        return BLOCKED, f"the campaign could not be opened: {made.text[:140]}"
    reference = (made.json() or {}).get("reference")
    got = _answer(ctx, reference, ADMIN[0], reviewer, state="revoked",
                  reason="leaver")
    if got.status_code < 400:
        return FAIL, ("the last administrator's roles were revoked through a "
                      "recertification, leaving nobody who can grant a role")
    if code_of(got) != "last_administrator":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'last_administrator'"


@case("QA-GOV-263", "Revoke somebody, then read the answer's wording",
      isolated=True)
def gov_263(ctx: Ctx) -> Result:
    """Revoking removes roles IN THIS REGISTER and nothing else. It does not
    touch a directory, a database grant, a VPN profile or anybody's job, and
    a platform reporting *access removed* would be reporting a removal it
    cannot see."""
    reviewer, subject = _person(ctx, ["auditor"]), _person(ctx)
    if not (reviewer and subject):
        return BLOCKED, "the principals could not be created"
    made = _open(ctx, reviewer, population=[subject])
    if made.status_code >= 400:
        return BLOCKED, f"the campaign could not be opened: {made.text[:140]}"
    reference = (made.json() or {}).get("reference")
    got = _answer(ctx, reference, subject, reviewer, state="revoked",
                  reason="left the firm in March")
    if got.status_code >= 400:
        return BLOCKED, f"the revocation failed: {got.text[:140]}"
    body = got.json() or {}
    if "roles_removed_in_maya" not in body:
        return FAIL, ("the answer does not say the removal was in this "
                      "register, so a reader takes it for a removal of access")
    if body["roles_removed_in_maya"] != ["model_owner"]:
        return FAIL, (f"the roles removed read "
                      f"{body['roles_removed_in_maya']}")
    detail = (body.get("detail") or "").lower()
    if "directory" not in detail and "somebody else's record" not in detail:
        return FAIL, f"the detail claims more than it did: {detail[:130]}"
    return PASS, "the answer scopes the removal to this register, in words"


@case("QA-GOV-264", "Close a campaign with items still unreviewed",
      isolated=True)
def gov_264(ctx: Ctx) -> Result:
    """Closing decides nothing about what was unreviewed. The number has to
    survive the close and say so, or a campaign closed early reads as a
    campaign completed."""
    reviewer = _person(ctx, ["auditor"])
    a, b = _person(ctx), _person(ctx)
    if not (reviewer and a and b):
        return BLOCKED, "the principals could not be created"
    made = _open(ctx, reviewer, population=[a, b])
    if made.status_code >= 400:
        return BLOCKED, f"the campaign could not be opened: {made.text[:140]}"
    reference = (made.json() or {}).get("reference")
    if _answer(ctx, reference, a, reviewer).status_code >= 400:
        return BLOCKED, "the first answer failed"
    closed = ctx.api.post(f"{C}/{reference}/close", json={}, auth=ADMIN)
    if closed.status_code >= 400:
        return FAIL, (f"a campaign with an unreviewed item cannot be closed "
                      f"('{code_of(closed)}'), so an unanswerable row holds it "
                      f"open for ever")
    body = closed.json() or {}
    if body.get("unreviewed") != 1:
        return FAIL, f"unreviewed reads {body.get('unreviewed')} after close"
    if b not in (body.get("unreviewed_accounts") or []):
        return FAIL, "the unreviewed account is counted and not named"
    if "decided nothing" not in (body.get("detail") or ""):
        return FAIL, (f"the closed campaign does not say the unreviewed items "
                      f"were not decided: {body.get('detail')}")
    return PASS, "closed with 1 unreviewed, named, and said out loud"


@case("QA-GOV-271", "Open a campaign naming a suspended principal explicitly",
      isolated=True)
def gov_271(ctx: Ctx) -> Result:
    """EXPLORATORY. A blank population reviews everybody ACTIVE, so a
    suspended account is never swept in — but naming one explicitly is how a
    leaver's residual access gets looked at, which is the case an auditor
    asks about."""
    reviewer, subject = _person(ctx, ["auditor"]), _person(ctx)
    if not (reviewer and subject):
        return BLOCKED, "the principals could not be created"
    if ctx.api.post(f"{P}/{subject}/suspend",
                    auth=ADMIN).status_code >= 400:
        return BLOCKED, "the subject could not be suspended"
    named = _open(ctx, reviewer, population=[subject])
    if named.status_code >= 400:
        return FAIL, (f"a suspended account cannot be named in a campaign "
                      f"('{code_of(named)}'), so a leaver's residual access "
                      f"cannot be reviewed at all")
    reference = (named.json() or {}).get("reference")
    blank = _open(ctx, reviewer, population=[])
    if blank.status_code >= 400:
        return BLOCKED, "the estate-wide campaign could not be opened"
    swept = _status(ctx, (blank.json() or {}).get("reference"))
    if subject in (swept.get("unreviewed_accounts") or []):
        return FAIL, ("a suspended account was swept into a blank-population "
                      "campaign, which reviews everybody ACTIVE")
    return PASS, (f"{reference} reviews the suspended account by name, and a "
                  f"blank population does not sweep it in")


@case("QA-GOV-272", "An account not seen for exactly 90 days", isolated=True)
def gov_272(ctx: Ctx) -> Result:
    """The dormancy boundary is `>`, so the ninetieth day is not yet dormant.
    Flagging is an observation and not a recommendation — a reviewer handed a
    ranked list reviews the top of it — so the boundary has to be where it is
    documented."""
    engine = ctx.ui.app.state.ctx.get("recertification")
    if engine is None:
        return BLOCKED, "no recertification engine is wired"
    now = time.time()
    at = engine._flagged(
        [{"principal": "p", "state": "unreviewed", "roles": ["model_owner"],
          "last_seen_at": now - DORMANT_AFTER_DAYS * DAY}], now)
    if any("not seen" in w for r in at for w in r["why"]):
        return FAIL, (f"flagged dormant at exactly {DORMANT_AFTER_DAYS} days")
    past = engine._flagged(
        [{"principal": "p", "state": "unreviewed", "roles": ["model_owner"],
          "last_seen_at": now - DORMANT_AFTER_DAYS * DAY - 3600}], now)
    if not any("not seen" in w for r in past for w in r["why"]):
        return FAIL, (f"an hour past {DORMANT_AFTER_DAYS} days is still not "
                      f"flagged, so the boundary is not where it is written")
    return PASS, f"not at {DORMANT_AFTER_DAYS} days, flagged an hour later"


@case("QA-GOV-273", "An account with no `last_seen_at` at all", isolated=True)
def gov_273(ctx: Ctx) -> Result:
    """EXPLORATORY, and the answer is the right one: never signed in is a
    different fact from dormant, and it is said in different words. Treating
    a null as a very old date would report an account created this morning as
    dormant for ever."""
    engine = ctx.ui.app.state.ctx.get("recertification")
    if engine is None:
        return BLOCKED, "no recertification engine is wired"
    flagged = engine._flagged(
        [{"principal": "p", "state": "unreviewed", "roles": ["model_owner"],
          "last_seen_at": None}], time.time())
    why = [w for r in flagged for w in r["why"]]
    if not why:
        return FAIL, ("an account that has never signed in is not flagged at "
                      "all, so a dormant account created before the platform "
                      "recorded sign-ins passes unremarked")
    if any("not seen for more than" in w for w in why):
        return FAIL, (f"a null last_seen_at is reported as dormancy rather "
                      f"than as never having signed in: {why}")
    if not any("never signed in" in w for w in why):
        return FAIL, f"flagged for some other reason: {why}"
    return PASS, "'this account has never signed in', in its own words"


@case("QA-GOV-274", "Open two campaigns covering the same people at once",
      isolated=True)
def gov_274(ctx: Ctx) -> Result:
    """EXPLORATORY. Nothing refuses it, and that is defensible — a targeted
    review of one team runs alongside the annual one. What matters is that
    answering in one does not answer in the other, or the narrower campaign
    would silently complete the broader one."""
    reviewer, subject = _person(ctx, ["auditor"]), _person(ctx)
    if not (reviewer and subject):
        return BLOCKED, "the principals could not be created"
    one = _open(ctx, reviewer, population=[subject])
    two = _open(ctx, reviewer, population=[subject])
    if two.status_code >= 400:
        return PASS, (f"a second campaign over the same person is refused "
                      f"'{code_of(two)}'")
    first = (one.json() or {}).get("reference")
    second = (two.json() or {}).get("reference")
    if _answer(ctx, first, subject, reviewer).status_code >= 400:
        return BLOCKED, "the answer in the first campaign failed"
    still = _status(ctx, second)
    if still.get("unreviewed") != 1:
        return FAIL, (f"answering in {first} answered the row in {second} "
                      f"too, so a narrow review completes a broad one: "
                      f"{still}")
    return PASS, f"answered in {first}, still unreviewed in {second}"
