"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section J — retention, legal holds, and the inference log.

How long something is kept, and what stops it going. A retention period is a
floor and never a ceiling, and the commonest way to get this wrong is to read
*may now be deleted* as *must now be deleted*.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  expect_refused, valid_body)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
HOLDS = "/api/v1/legal-holds"


def _model(ctx: Ctx) -> str:
    name = ctx.unique("rt")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "owner", **TIER})
    return urn


def _hold(ctx: Ctx, **over):
    body = valid_body(ctx, "POST", HOLDS,
                      matter=f"QA matter {ctx.unique('m')}", owner="risk",
                      scope_kind="estate")
    body.update(over)
    return ctx.api.post(HOLDS, json=body)


# --------------------------------------------------------------- retention
@case("QA-DEL-300", "The retention schedule is published with its reasons")
def del_300(ctx: Ctx) -> Result:
    """A period nobody can see is a period nobody can challenge."""
    got = ctx.api.get("/api/v1/retention")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    body = got.json()
    classes = body.get("classes", body.get("rows", []))
    if not classes:
        return FAIL, "no retention classes are published"
    return PASS, f"{len(classes)} class(es) published"


@case("QA-DEL-301", "A period is a floor and says so")
def del_301(ctx: Ctx) -> Result:
    """Confusing 'may now be deleted' with 'must now be deleted' is how a
    register loses the record that was about to be asked for."""
    got = ctx.api.get("/api/v1/retention")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    said = got.text.lower()
    if "floor" not in said and "at least" not in said and "minimum" not in said:
        return FAIL, ("the schedule does not say a period is a floor; read "
                      "as a ceiling it becomes an instruction to destroy")
    return PASS, "the schedule states that a period is a floor"


# ------------------------------------------------------------- legal holds
@case("QA-DEL-310", "A hold over a model that does not exist")
def del_310(ctx: Ctx) -> Result:
    """The regression: a hold scoped by an identifier nothing resolves
    protects nothing and looks, from every screen, exactly like one that
    does."""
    got = _hold(ctx, scope_kind="model", scope_id="maya://model/qa.never")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a hold was placed over a model nobody registered; it "
                      "protects nothing and reads as protection")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-DEL-311", "A model-scoped hold with no identifier")
def del_311(ctx: Ctx) -> Result:
    got = _hold(ctx, scope_kind="model", scope_id="")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a model-scoped hold was placed over no model"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-DEL-312", "A hold of a scope kind that is not one")
def del_312(ctx: Ctx) -> Result:
    return expect_refused(_hold(ctx, scope_kind="vibes"),
                          "unknown_scope", "validation_error",
                          "retention_refused")


@case("QA-DEL-313", "Two holds with the same reference")
def del_313(ctx: Ctx) -> Result:
    first = _hold(ctx)
    if first.status_code >= 400:
        return BLOCKED, first.text[:150]
    reference = first.json().get("reference")
    got = _hold(ctx, reference=reference)
    if got.status_code < 400:
        return FAIL, ("two holds share one reference; the reference is what "
                      "the matter is tracked by")
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-DEL-314", "Lift a hold with no reason")
def del_314(ctx: Ctx) -> Result:
    """Placing a hold keeps more than necessary, which is recoverable.
    Lifting one lets deletion resume on material somebody may be about to
    ask for, which is not."""
    made = _hold(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    reference = made.json()["reference"]
    return expect_refused(
        ctx.api.post(f"{HOLDS}/{reference}/lift", json={"reason": "   "}),
        "reason_required", "validation_error", "retention_refused")


@case("QA-DEL-315", "Lift a hold that does not exist")
def del_315(ctx: Ctx) -> Result:
    got = ctx.api.post(f"{HOLDS}/QA-NEVER/lift", json={"reason": "QA"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "lifting a hold that does not exist reported success"
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-DEL-316", "A hold has no end date, deliberately")
def del_316(ctx: Ctx) -> Result:
    """It inverts the rule every other bounded thing here follows, because a
    hold ends when the matter ends and when that is cannot be known when it
    is placed."""
    made = _hold(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    body = made.json()
    for field in ("expires_at", "ends_at", "until"):
        if body.get(field):
            return FAIL, (f"a hold was given an end date ({field}); that is "
                          f"guessing at a litigation timetable and calling "
                          f"the guess a control")
    return PASS, "no end date, as designed"


@case("QA-DEL-317", "A lifted hold no longer applies", isolated=True)
def del_317(ctx: Ctx) -> Result:
    """The other half — a hold that could not be lifted would make the
    platform unusable after any matter closed.

    Isolated, because the other cases in this module leave estate-wide holds
    in place and an estate hold covers every model. Run together, this one
    lifted its own hold and was still refused by three of theirs — a case
    failing on state its neighbours created.
    """
    urn = _model(ctx)
    made = _hold(ctx, scope_kind="model", scope_id=urn)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    reference = made.json()["reference"]
    lifted = ctx.api.post(f"{HOLDS}/{reference}/lift",
                          json={"reason": "the matter closed"})
    if lifted.status_code >= 400:
        return FAIL, f"a hold could not be lifted: {lifted.text[:150]}"
    name = urn.rsplit("/", 1)[-1]
    gone = ctx.api.request("DELETE", f"/api/v1/models/{name}",
                           params={"reason": "QA after the lift"})
    if gone.status_code >= 400:
        return FAIL, (f"the hold was lifted and the deletion is still "
                      f"refused: {gone.text[:150]}")
    return PASS, "lifted, and the deletion proceeds"


# ------------------------------------------------------------- inference
@case("QA-DEL-330", "The inference log says what it holds and for how long")
def del_330(ctx: Ctx) -> Result:
    """It is the one place the platform stores anything about a decision
    somebody was subject to."""
    got = ctx.api.get("/api/v1/inference-posture")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    said = got.text.lower()
    if "retention" not in said and "days" not in said:
        return FAIL, "the inference posture says nothing about retention"
    return PASS, "posture published with retention"


@case("QA-DEL-331", "Inference past its retention is reported, not hidden")
def del_331(ctx: Ctx) -> Result:
    got = ctx.api.get("/api/v1/inference-posture")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    if "past_retention" not in got.text:
        return FAIL, ("nothing reports inference held past its own retention "
                      "period; it would simply accumulate")
    return PASS, "past_retention is reported"
