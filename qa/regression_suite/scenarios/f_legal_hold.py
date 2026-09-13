"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — legal holds.

A hold has **no end date, and that is correct**: it inverts the rule every
other bounded thing in this platform follows. A hold ends when the matter
ends, and when that is cannot be known when it is placed — putting a date on
it would be guessing at a litigation timetable and calling the guess a
control. What replaces the deadline is a named owner and a stated matter.

**Lifting is the act that needs the ceremony, not placing.** Placing keeps more
than necessary, which is recoverable. Lifting lets deletion resume on material
somebody may be about to ask for, which is not. So the cases weight lifting
heavily, and the hold is never deleted — what was held and when is the answer
both to *why is this still here* and to *why is this not*.
"""
from __future__ import annotations

from core.retention.holds import SCOPES
from qa.regression_suite.harness import ADMIN
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

H = "/api/v1/legal-holds"
M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> tuple:
    name = ctx.unique("lh")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE})
    return name, urn


def _place(ctx: Ctx, **over):
    body = {"matter": "SEC subpoena 2026-114", "owner": "person/legal-counsel",
            "scope_kind": "estate", "scope_id": None, "classes": []}
    body.update(over)
    return ctx.api.post(H, json=body, auth=ctx.people["risk"])


def _reference(got) -> str:
    if got.status_code >= 400:
        return ""
    body = got.json() or {}
    return (body.get("hold") or body).get("reference", "")


def _lift(ctx: Ctx, reference: str, reason: str = "the matter closed"):
    return ctx.api.post(f"{H}/{reference}/lift", json={"reason": reason},
                        auth=ctx.people["risk"])


@case("QA-GOV-306", "Place a hold with an empty matter")
def gov_306(ctx: Ctx) -> Result:
    """A hold has no end date, so the matter is the only thing that will ever
    end it. One placed without a matter is a hold nobody can tell has ended."""
    got = _place(ctx, matter="   ")
    outcome = refused_by_the_control(got, "a hold with no matter recorded")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "matter_required":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'matter_required' on whitespace"


@case("QA-GOV-307", "Place a hold with no owner")
def gov_307(ctx: Ctx) -> Result:
    """A hold nobody owns is a hold nobody will lift — and because it has no
    expiry, nothing else will lift it either."""
    got = _place(ctx, owner="")
    outcome = refused_by_the_control(got, "a hold nobody owns")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "owner_required":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'owner_required'"


@case("QA-GOV-308", "Place a model-scoped hold with no `scope_id`")
def gov_308(ctx: Ctx) -> Result:
    """A model hold that says no model matches nothing, and reads on the
    screen as protection."""
    got = _place(ctx, scope_kind="model", scope_id=None)
    outcome = refused_by_the_control(got, "a model hold naming no model")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "scope_required":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'scope_required'"


@case("QA-GOV-309", "Place a hold with an unrecognised scope kind")
def gov_309(ctx: Ctx) -> Result:
    """Three scopes and no fourth, and the refusal has to name them — the
    caller reaching for `portfolio` needs to be told that `estate` is the
    blunt instrument that covers it."""
    got = _place(ctx, scope_kind="portfolio", scope_id="pf-1")
    outcome = refused_by_the_control(got, "a hold over a scope that is not one")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "unknown_scope":
        return FAIL, f"refused '{code_of(got)}'"
    missing = [k for k in SCOPES if k not in got.text]
    if missing:
        return FAIL, f"the refusal does not name the scopes {missing}"
    return PASS, f"refused 'unknown_scope', naming all {len(SCOPES)}"


@case("QA-GOV-4630",
      "Place a model-scoped hold naming a model that does not exist")
def gov_4630(ctx: Ctx) -> Result:
    """The recorded defect, and it is the sharpest in this module. `applies`
    compares `scope_id` against the model's internal ROW ID, and `place` used
    to validate only that the field was non-empty — so a hold placed with the
    URN a person would actually type matched no model and deletion proceeded.
    Both spellings must now work, and an identifier that resolves to nothing
    must be refused rather than stored."""
    _name, urn = _model(ctx)
    good = _place(ctx, scope_kind="model", scope_id=urn)
    if good.status_code >= 400:
        return FAIL, (f"a hold placed with the URN a person would type was "
                      f"refused '{code_of(good)}'")
    bad = _place(ctx, scope_kind="model",
                 scope_id="maya://model/never-registered")
    if bad.status_code < 400:
        return FAIL, ("a hold was placed over a model that does not exist: "
                      "somebody believes it is protecting something and it "
                      "matches nothing")
    if code_of(bad) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the resolution"
    return PASS, (f"the URN resolves, and an identifier that resolves to "
                  f"nothing is refused '{code_of(bad)}'")


@case("QA-GOV-310", "Place two overlapping holds, lift one, then delete")
def gov_310(ctx: Ctx) -> Result:
    """Holds are not a counter that reaches zero when one is lifted. The
    second matter has not ended because the first one has."""
    name, urn = _model(ctx)
    first = _reference(_place(ctx, scope_kind="model", scope_id=urn,
                              matter="SEC subpoena 2026-114"))
    second = _reference(_place(ctx, scope_kind="model", scope_id=urn,
                               matter="FCA request 2026-88"))
    if not (first and second):
        return BLOCKED, "both holds could not be placed"
    if first == second:
        return FAIL, f"two holds share the reference '{first}'"
    if _lift(ctx, first).status_code >= 400:
        return BLOCKED, "the first hold could not be lifted"
    got = ctx.api.delete(f"{M}/{name}?reason=qa", auth=ADMIN)
    if got.status_code < 400:
        return FAIL, (f"the model was deleted with '{second}' still in force: "
                      f"lifting one hold resumed deletion while another "
                      f"matter is open")
    if code_of(got) != "under_legal_hold":
        return FAIL, f"refused '{code_of(got)}' rather than naming the hold"
    return PASS, f"refused 'under_legal_hold' with {second} still in force"


@case("QA-GOV-311", "Lift the last hold, then delete")
def gov_311(ctx: Ctx) -> Result:
    """The legitimate route out. A hold that could never be lifted would make
    the first subpoena permanent."""
    name, urn = _model(ctx)
    ref = _reference(_place(ctx, scope_kind="model", scope_id=urn))
    if not ref:
        return BLOCKED, "the hold could not be placed"
    blocked = ctx.api.delete(f"{M}/{name}?reason=qa", auth=ADMIN)
    if blocked.status_code < 400:
        return FAIL, "the model deleted while a hold was in force"
    if _lift(ctx, ref).status_code >= 400:
        return BLOCKED, "the hold could not be lifted"
    got = ctx.api.delete(f"{M}/{name}?reason=qa", auth=ADMIN)
    if got.status_code >= 400 and code_of(got) == "under_legal_hold":
        return FAIL, ("the model is still under hold after the last one was "
                      "lifted, so a lifted hold goes on holding")
    if got.status_code >= 400:
        return PASS, (f"the hold cleared; the deletion is refused "
                      f"'{code_of(got)}' for a different reason")
    return PASS, "the last hold lifted and the deletion proceeded"


@case("QA-GOV-312", "Lift a hold twice")
def gov_312(ctx: Ctx) -> Result:
    """The second lift would rewrite who resumed deletion and why — which is
    the pair of facts this record exists to hold still."""
    ref = _reference(_place(ctx))
    if not ref:
        return BLOCKED, "the hold could not be placed"
    if _lift(ctx, ref).status_code >= 400:
        return BLOCKED, "the first lift failed"
    got = _lift(ctx, ref, reason="a different reason entirely")
    outcome = refused_by_the_control(got, "a hold was lifted twice")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "not_active":
        return FAIL, f"refused '{code_of(got)}'"
    held = ctx.api.get(H, auth=ctx.people["risk"])
    rows = [r for r in ((held.json() or {}).get("holds") or [])
            if r.get("reference") == ref]
    if rows and "different reason" in (rows[0].get("lift_reason") or ""):
        return FAIL, "the refused second lift overwrote the first reason"
    return PASS, "refused 'not_active', first reason intact"


@case("QA-GOV-313", "Lift with no reason")
def gov_313(ctx: Ctx) -> Result:
    """Lifting with no reason resumes deletion on material somebody may be
    about to ask for, and records nothing about why that was safe.

    Model-scoped rather than estate-wide: this hold is never lifted — that is
    the point of the case — and an estate hold left standing covers every
    model a later case creates.
    """
    _name, urn = _model(ctx)
    ref = _reference(_place(ctx, scope_kind="model", scope_id=urn))
    if not ref:
        return BLOCKED, "the hold could not be placed"
    got = _lift(ctx, ref, reason="  ")
    outcome = refused_by_the_control(got, "a hold lifted with no reason")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "reason_required":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'reason_required' on whitespace"


@case("QA-GOV-314", "Lift a hold that does not exist")
def gov_314(ctx: Ctx) -> Result:
    """A reference nobody placed. Answering anything but a refusal here would
    mean the lift is not reading the register at all."""
    got = _lift(ctx, "HOLD-9999")
    outcome = refused_by_the_control(got, "a hold nobody placed was lifted")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "no_hold":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'no_hold'"


@case("QA-GOV-315", "A hold is placed while a deletion is in flight",
      isolated=True)
def gov_315(ctx: Ctx) -> Result:
    """The ordering that matters: a hold arriving during a deletion must
    either stop it or be recorded as having arrived too late. What it must
    not do is be accepted and leave the reader believing the material is
    held."""
    name, urn = _model(ctx)
    gone = ctx.api.delete(f"{M}/{name}?reason=qa", auth=ADMIN)
    if gone.status_code >= 400:
        return BLOCKED, f"the model could not be deleted: {gone.text[:140]}"
    got = _place(ctx, scope_kind="model", scope_id=urn)
    if got.status_code >= 400:
        return PASS, (f"a hold over a model that has been deleted is refused "
                      f"'{code_of(got)}', so nobody is told material is held "
                      f"that is gone")
    return FAIL, (f"a hold was placed over '{urn}' after the model was "
                  f"deleted: the scope resolves against the register and the "
                  f"model is no longer in it, so this hold protects nothing "
                  f"while reading as protection")


@case("QA-GOV-316", "Place the first hold on an estate with no models",
      isolated=True)
def gov_316(ctx: Ctx) -> Result:
    """An estate hold does not depend on there being anything to hold — the
    document request arrives before somebody has worked out what it covers,
    and refusing it would mean the first act of a matter is refused."""
    got = _place(ctx, scope_kind="estate", scope_id=None)
    if got.status_code >= 400:
        return FAIL, (f"an estate hold was refused '{code_of(got)}'")
    body = got.json() or {}
    row = body.get("hold") or body
    if row.get("state") != "active":
        return FAIL, f"the hold reads '{row.get('state')}'"
    if row.get("scope_kind") != "estate":
        return FAIL, f"the scope reads '{row.get('scope_kind')}'"
    return PASS, f"{row.get('reference')} placed over the estate"
