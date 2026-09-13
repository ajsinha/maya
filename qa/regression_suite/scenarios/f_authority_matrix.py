"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — the delegated authority matrix.

A band says who signs, in what order, for a model of this tier above this
exposure. `stages` is a list of LISTS on purpose: a flat role list cannot say
"the second line signs after the first", and that ordering is the half of the
requirement a quorum does not cover.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

A = "/api/v1/authority"


def _matrix(ctx: Ctx) -> list:
    """The live matrix. There is no `GET /authority/bands` — the collection
    route is POST-only and the item route is DELETE-only — so the matrix is
    read through the service."""
    authority = ctx.ui.app.state.ctx.get("authority")
    return list(authority.matrix()) if authority is not None else []


def _band(ctx: Ctx, **over):
    body = {"name": ctx.unique("band"),
            "stages": [["model_owner"], ["model_risk_manager"]],
            "tier": 3, "at_or_above": 0.0, "note": "QA"}
    body.update(over)
    return ctx.api.post(f"{A}/bands", json=body)


def _delegate(ctx: Ctx, **over):
    body = {"principal": "person/owner", "ceiling": 1_000_000.0,
            "instrument": "board minute 2026-03", "currency": "USD"}
    body.update(over)
    return ctx.api.post(f"{A}/delegations", json=body)


@case("QA-GOV-117", "Publish a band with no stages")
def gov_117(ctx: Ctx) -> Result:
    """A band that names nobody is a row that matches models and demands
    nothing, which reads on a matrix as a control."""
    return refused_by_the_control(
        _band(ctx, stages=[]),
        "a band was published naming nobody to sign")


@case("QA-GOV-118", "Publish a band with a stage that is an empty list")
def gov_118(ctx: Ctx) -> Result:
    """An empty stage is a step in the sequence that anybody satisfies by
    doing nothing, and it would let the stage after it be reached
    immediately."""
    got = _band(ctx, stages=[["model_owner"], []])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a band was published with an empty stage, so one step "
                      "of the sequence is satisfied by nobody")
    if code_of(got) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the check"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-119", "Publish a band naming a tier that does not exist")
def gov_119(ctx: Ctx) -> Result:
    """A band on tier 5 matches nothing for ever, and a matrix row that can
    never fire reads as coverage."""
    bad = []
    for tier in (0, 5, -1, 99):
        got = _band(ctx, tier=tier)
        if got.status_code < 400:
            bad.append(tier)
        elif got.status_code >= 500:
            return FAIL, f"tier {tier} crashed ({got.status_code})"
    if bad:
        return FAIL, f"bands published on tiers that do not exist: {bad}"
    return PASS, "tiers 0, 5, -1 and 99 all refused"


@case("QA-GOV-121", "Publish a band with a negative amount floor")
def gov_121(ctx: Ctx) -> Result:
    """An amount floor below zero matches nothing — or, read the other way,
    matches everything including the absence of an exposure."""
    return refused_by_the_control(
        _band(ctx, at_or_above=-1.0),
        "a band was published with a floor below zero")


@case("QA-GOV-122", "Publish the same band name twice")
def gov_122(ctx: Ctx) -> Result:
    """Two rows under one name is a matrix nobody can reason about, and
    withdrawing one leaves the other."""
    name = ctx.unique("band")
    if _band(ctx, name=name).status_code >= 400:
        return BLOCKED, "the first band could not be published"
    return refused_by_the_control(
        _band(ctx, name=name),
        "two bands were published under one name")


@case("QA-GOV-124", "Withdraw a band nobody published")
def gov_124(ctx: Ctx) -> Result:
    return refused_by_the_control(
        ctx.api.delete(f"{A}/bands/qa-no-such-band"),
        "a band that does not exist was withdrawn")


@case("QA-GOV-125", "Withdraw a band and read the matrix")
def gov_125(ctx: Ctx) -> Result:
    """Withdrawal takes the row out of the live matrix. Approvals already
    open keep the band they were opened under, which is why withdrawal is not
    deletion."""
    name = ctx.unique("band")
    if _band(ctx, name=name).status_code >= 400:
        return BLOCKED, "the band could not be published"
    gone = ctx.api.delete(f"{A}/bands/{name}")
    if gone.status_code >= 400:
        return BLOCKED, gone.text[:170]
    still = [b for b in _matrix(ctx)
             if b.get("name") == name and not b.get("withdrawn_at")]
    if still:
        return FAIL, f"'{name}' is still live after withdrawal"
    return PASS, "withdrawn from the live matrix"


@case("QA-GOV-128", "An amount exactly equal to a band's floor")
def gov_128(ctx: Ctx) -> Result:
    """`at_or_above` is inclusive, and the boundary is where a matrix is
    argued about."""
    name = ctx.unique("band")
    if _band(ctx, name=name, at_or_above=1_000_000.0).status_code >= 400:
        return BLOCKED, "the band could not be published"
    row = next((b for b in _matrix(ctx) if b.get("name") == name), None)
    if row is None:
        return BLOCKED, "the band is not in the matrix"
    if float(row.get("at_or_above")) != 1_000_000.0:
        return FAIL, f"the floor was stored as {row.get('at_or_above')}"
    return PASS, "the floor is stored as given, and named at_or_above"


@case("QA-GOV-137", "Delegate with a ceiling of zero")
def gov_137(ctx: Ctx) -> Result:
    """A ceiling of zero delegates nothing, and recording it would put
    somebody on the matrix who cannot approve anything."""
    return refused_by_the_control(
        _delegate(ctx, ceiling=0),
        "a delegation of zero was recorded, so somebody appears on the "
        "matrix able to approve nothing")


@case("QA-GOV-138", "Delegate with a ceiling that is not a number")
def gov_138(ctx: Ctx) -> Result:
    return refused_by_the_control(
        _delegate(ctx, ceiling="a lot"),
        "a delegation with a ceiling nobody can compare against was recorded")


@case("QA-GOV-139", "Delegate with no instrument")
def gov_139(ctx: Ctx) -> Result:
    """MAYA holds the reference rather than the resolution, and a delegation
    nobody can trace to a decision is the precise thing an authority matrix
    exists to prevent."""
    return refused_by_the_control(
        _delegate(ctx, instrument="   "),
        "a delegation was recorded with no instrument, so nobody can trace it "
        "to the decision that granted it")


@case("QA-GOV-2200", "A delegation names a currency")
def gov_2200(ctx: Ctx) -> Result:
    """A ceiling is an amount of money. A ceiling with no currency is a
    number that means one thing to the person who typed it."""
    got = _delegate(ctx, currency="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    stored = (got.json() or {}).get("currency")
    if not (stored or "").strip():
        return FAIL, ("a ceiling was recorded with no currency, so the number "
                      "means whatever the reader assumes")
    return PASS, f"currency recorded as '{stored}'"


@case("QA-GOV-134", "Sign out of stage order")
def gov_134(ctx: Ctx) -> Result:
    """The ordering is the half of the requirement a quorum does not cover:
    the second line signs after the first, not alongside it."""
    from core.lifecycle.authority import AuthorityMatrix
    from core.lifecycle.common import LifecycleError
    stages = [["model_owner"], ["model_risk_manager"]]
    try:
        AuthorityMatrix.refuse_out_of_sequence(stages, "model_risk_manager",
                                               [])
    except LifecycleError as exc:
        if exc.code != "out_of_sequence":
            return FAIL, f"refused '{exc.code}', not out_of_sequence"
        return PASS, "the second stage cannot sign before the first"
    return FAIL, ("the second stage signed with the first unsigned, so the "
                  "matrix records an order it does not enforce")


@case("QA-GOV-135", "Sign in stage order")
def gov_135(ctx: Ctx) -> Result:
    """The refusal has to admit the legitimate case, or the control is a
    deadlock."""
    from core.lifecycle.authority import AuthorityMatrix
    stages = [["model_owner"], ["model_risk_manager"]]
    try:
        AuthorityMatrix.refuse_out_of_sequence(stages, "model_owner", [])
        AuthorityMatrix.refuse_out_of_sequence(stages, "model_risk_manager",
                                               ["model_owner"])
    except Exception as exc:
        return FAIL, f"signing in order was refused: {exc}"
    return PASS, "first stage, then second"


@case("QA-GOV-136", "A single-stage band with two roles signs either way")
def gov_136(ctx: Ctx) -> Result:
    """Roles inside one stage sign TOGETHER. Imposing an order within a stage
    would be an ordering nobody wrote down."""
    from core.lifecycle.authority import AuthorityMatrix
    stages = [["model_owner", "model_risk_manager"]]
    for first, second in (("model_owner", "model_risk_manager"),
                          ("model_risk_manager", "model_owner")):
        try:
            AuthorityMatrix.refuse_out_of_sequence(stages, first, [])
            AuthorityMatrix.refuse_out_of_sequence(stages, second, [first])
        except Exception as exc:
            return FAIL, f"{first} then {second} was refused: {exc}"
    return PASS, "either order within one stage"
