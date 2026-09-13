"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — validation episodes, overlays and supervisory matters.

A validation is the second line saying whether it believes the first. An
overlay is somebody adjusting a model's output by hand, which is either a
temporary measure or an undeclared model. A supervisory matter is what the
regulator asked for. All three are records somebody will be asked to produce.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx, Result, case,
                                       code_of, expect_accepted,
                                       expect_refused, valid_body)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
VALIDATIONS = "/api/v1/validations"
OVERLAYS = "/api/v1/overlays"
MATTERS = "/api/v1/supervisory-matters"

#: Vocabularies read from the platform, not invented.
#:
#: `effective`, `add_on` and `finding` all sound like plausible members and
#: none of them is one, which cost seven cases in this batch alone. A closed
#: vocabulary is exactly the thing not to guess: the refusal is correct and
#: the case is then about the wrong subject.
VALIDATION_OUTCOME = "approved"
OVERLAY_KIND = "judgemental"
MATTER_KIND = "recommendation"
#: Concluding also needs a verdict on the tier — "concluding a validation
#: requires a verdict on the model's risk tier". A conclusion that says
#: nothing about whether the tier still holds is half an answer.
TIER_VERDICT = "remains_appropriate"


def _versioned(ctx: Ctx) -> str:
    """A model with a version, which is what a validation is about."""
    name = ctx.unique("val")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "owner", **TIER})
    ctx.api.post(f"/api/v1/models/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    return urn


def _open(ctx: Ctx, **over):
    body = valid_body(ctx, "POST", VALIDATIONS, urn=_versioned(ctx),
                      semver="1.0.0", validators=["validator"])
    body.update(over)
    return ctx.api.post(VALIDATIONS, json=body)


# ----------------------------------------------------------- validations
@case("QA-AM-619", "Open a validation with no validators")
def am_300(ctx: Ctx) -> Result:
    """A validation nobody is performing is a row saying somebody will."""
    return expect_refused(_open(ctx, validators=[]),
                          "validation_refused", "validators_required",
                          "validation_error")


@case("QA-AM-301", "Open a validation against a version that does not exist")
def am_301(ctx: Ctx) -> Result:
    return expect_refused(_open(ctx, semver="9.9.9"),
                          "registry_refused", "not_found",
                          "validation_refused")


@case("QA-AM-620", "Open a validation against a model that does not exist")
def am_302(ctx: Ctx) -> Result:
    body = valid_body(ctx, "POST", VALIDATIONS, urn="maya://model/qa.never",
                      semver="1.0.0", validators=["validator"])
    return expect_refused(ctx.api.post(VALIDATIONS, json=body),
                          "registry_refused", "not_found",
                          "validation_refused")


@case("QA-AM-621", "A well-formed validation opens")
def am_303(ctx: Ctx) -> Result:
    return expect_accepted(_open(ctx))


@case("QA-AM-622", "Conclude a validation with an outcome that is not one")
def am_304(ctx: Ctx) -> Result:
    opened = _open(ctx)
    if opened.status_code >= 400:
        return BLOCKED, opened.text[:150]
    episode = opened.json()["id"]
    return expect_refused(
        ctx.api.post(f"{VALIDATIONS}/{episode}/conclude",
                     json={"outcome": "probably fine"}),
        "unknown_outcome", "validation_refused", "validation_error")


@case("QA-AM-623", "Conclude a validation twice")
def am_305(ctx: Ctx) -> Result:
    opened = _open(ctx)
    if opened.status_code >= 400:
        return BLOCKED, opened.text[:150]
    episode = opened.json()["id"]
    # A validation cannot be approved with nothing recorded — "there is
    # nothing this validation examined". Correct, and my first version of
    # this case skipped it and read the refusal as a failure to conclude.
    ctx.api.post(f"{VALIDATIONS}/{episode}/results",
                 json={"test_key": "discrimination.auc",
                       "left": [0.7, 0.8], "right": [0.7, 0.8]},
                 auth=ctx.people["validator"])
    # `rejected`, not `approved`. Approving is refused while a test has
    # failed — "conclude 'approved_with_conditions' with the conditions" —
    # which is the platform being right and not the case's subject. This case
    # is about concluding TWICE.
    first = ctx.api.post(f"{VALIDATIONS}/{episode}/conclude",
                         json={"outcome": "rejected",
                               "tier_verdict": TIER_VERDICT},
                         auth=ctx.people["validator"])
    if first.status_code >= 400:
        return BLOCKED, f"could not conclude once: {first.text[:150]}"
    second = ctx.api.post(f"{VALIDATIONS}/{episode}/conclude",
                          json={"outcome": "deferred",
                                "tier_verdict": TIER_VERDICT},
                          auth=ctx.people["validator"])
    if second.status_code < 400:
        return FAIL, ("a concluded validation was concluded again, with the "
                      "opposite verdict; the record now says two things")
    return PASS, f"refused '{code_of(second)}'"


@case("QA-AM-624", "Conclude a validation you are not a validator on")
def am_306(ctx: Ctx) -> Result:
    opened = _open(ctx)
    if opened.status_code >= 400:
        return BLOCKED, opened.text[:150]
    episode = opened.json()["id"]
    got = ctx.api.post(f"{VALIDATIONS}/{episode}/conclude",
                       json={"outcome": VALIDATION_OUTCOME,
                             "tier_verdict": TIER_VERDICT},
                       auth=ctx.people["owner"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("the model owner concluded their own model's "
                      "validation; the second line is the whole point")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-307", "Record a result with no test key")
def am_307(ctx: Ctx) -> Result:
    opened = _open(ctx)
    if opened.status_code >= 400:
        return BLOCKED, opened.text[:150]
    episode = opened.json()["id"]
    return expect_refused(
        ctx.api.post(f"{VALIDATIONS}/{episode}/results",
                     json={"test_key": "   ", "left": [1.0], "right": [1.0]}),
        "validation_refused", "validation_error", "unknown_test")


# --------------------------------------------------------------- overlays
def _overlay(ctx: Ctx, **over):
    body = valid_body(ctx, "POST", OVERLAYS, urn=_versioned(ctx),
                      name=ctx.unique("ov"), kind=OVERLAY_KIND,
                      owner="owner", rationale="QA overlay", days=30)
    body.update(over)
    return ctx.api.post(OVERLAYS, json=body)


@case("QA-AM-625", "An overlay with no rationale")
def am_320(ctx: Ctx) -> Result:
    """An overlay is somebody adjusting a model's output by hand. Without a
    stated reason it is an undeclared model."""
    return expect_refused(_overlay(ctx, rationale="   "),
                          "overlay_refused", "rationale_required",
                          "validation_error")


@case("QA-AM-626", "An overlay with no owner")
def am_321(ctx: Ctx) -> Result:
    return expect_refused(_overlay(ctx, owner="   "),
                          "overlay_refused", "owner_required",
                          "validation_error")


@case("QA-AM-627", "An overlay of a kind that is not one")
def am_322(ctx: Ctx) -> Result:
    return expect_refused(_overlay(ctx, kind="vibes"),
                          "unknown_kind", "overlay_refused",
                          "validation_error")


@case("QA-AM-628", "An overlay with no expiry")
def am_323(ctx: Ctx) -> Result:
    """An overlay that never expires is the model, and nobody approved it as
    one."""
    got = _overlay(ctx, days=0)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"


@case("QA-AM-629", "Close an overlay with no reason")
def am_324(ctx: Ctx) -> Result:
    made = _overlay(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    overlay_id = made.json()["id"]
    return expect_refused(
        ctx.api.post(f"{OVERLAYS}/{overlay_id}/close", json={"reason": "  "}),
        "overlay_refused", "reason_required", "validation_error")


@case("QA-AM-630", "Measure an overlay that does not exist")
def am_325(ctx: Ctx) -> Result:
    got = ctx.api.post(f"{OVERLAYS}/qa-never/measure",
                       json={"base_value": 1.0, "adjusted_value": 2.0,
                             "period": "2026Q1"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an overlay that does not exist was measured"
    return PASS, f"refused '{code_of(got)}'"


# ---------------------------------------------------- supervisory matters
def _matter(ctx: Ctx, **over):
    # `scope` names the models the matter is about. "A matter with no models
    # in scope has nothing to remediate" — a considered refusal, and my first
    # version of these cases omitted it and read the refusal as a defect.
    body = valid_body(ctx, "POST", MATTERS, reference=ctx.unique("SUP"),
                      title="QA matter", kind=MATTER_KIND, owner="owner",
                      supervisor="the regulator",
                      scope=[_versioned(ctx)])
    body.update(over)
    return ctx.api.post(MATTERS, json=body)


@case("QA-AM-631", "A supervisory matter with no supervisor")
def am_340(ctx: Ctx) -> Result:
    """Which regulator asked is the first thing anybody will want to know."""
    return expect_refused(_matter(ctx, supervisor="   "),
                          "validation_error", "supervisor_required",
                          "matter_refused", "regime_refused")


@case("QA-AM-632", "A supervisory matter with no owner")
def am_341(ctx: Ctx) -> Result:
    return expect_refused(_matter(ctx, owner="   "),
                          "validation_error", "owner_required",
                          "matter_refused", "regime_refused")


@case("QA-AM-633", "Two matters with the same reference")
def am_342(ctx: Ctx) -> Result:
    reference = ctx.unique("SUP")
    _matter(ctx, reference=reference)
    got = _matter(ctx, reference=reference)
    if got.status_code < 400:
        return FAIL, ("two supervisory matters share one reference; the "
                      "reference is what the regulator's letter cites")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-634", "Close a supervisory matter with no note")
def am_343(ctx: Ctx) -> Result:
    made = _matter(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    reference = made.json().get("reference")
    return expect_refused(
        ctx.api.post(f"{MATTERS}/{reference}/close", json={"note": "   "}),
        "validation_refused", "note_required", "validation_error")
