"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — delegated authority, break-glass, recertification, conditions.

The controls here are about **who may say yes**, and the ways that question
goes wrong are all the same shape: an amount nobody sourced, a delegation with
no ceiling, an emergency access nobody reviewed, a reviewer certifying
themselves.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx, Result, case,
                                       code_of, expect_accepted,
                                       expect_refused, valid_body)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
BANDS = "/api/v1/authority/bands"
DELEGATIONS = "/api/v1/authority/delegations"
GLASS = "/api/v1/break-glass"
RECERT = "/api/v1/recertification"
CONDITIONS = "/api/v1/approval-conditions"
#: Filled in at import from the platform's own vocabulary rather than guessed
#: — `monitoring` is not a condition kind and inventing one produced
#: `unknown_condition` for two cases that were about something else.
CONDITION_KIND = "human_review"
#: A real review outcome, read from the platform rather than invented.
#: `justified` sounds right and is not one of them.
from core.authz.breakglass import OUTCOMES

REVIEW_OUTCOME = next(iter(OUTCOMES))


def _model(ctx: Ctx) -> str:
    name = ctx.unique("au")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "owner", **TIER})
    return urn


def _band(ctx: Ctx, **over):
    body = valid_body(ctx, "POST", BANDS, name=ctx.unique("band"),
                      stages=[["model_risk_manager"]], at_or_above=1_000_000.0)
    body.update(over)
    return ctx.api.post(BANDS, json=body)


def _delegation(ctx: Ctx, **over):
    body = valid_body(ctx, "POST", DELEGATIONS, principal="risk",
                      ceiling=500_000.0, currency="USD",
                      instrument="a signed delegation letter")
    body.update(over)
    return ctx.api.post(DELEGATIONS, json=body)


# ------------------------------------------------------------------ bands
@case("QA-GOV-513", "A band with no stages")
def gov_200(ctx: Ctx) -> Result:
    """A band is a sequence of who signs. With no stages it approves
    everything at that amount by approving nothing."""
    return expect_refused(_band(ctx, stages=[]),
                          "validation_error", "stages_required",
                          "authority_refused", "lifecycle_refused")


@case("QA-GOV-201", "A band with no name")
def gov_201(ctx: Ctx) -> Result:
    return expect_refused(_band(ctx, name="   "), "band_name_required")


@case("QA-GOV-514", "A band naming a role that does not exist")
def gov_202(ctx: Ctx) -> Result:
    return expect_refused(_band(ctx, stages=[["chief_vibes_officer"]]),
                          "unknown_role", "validation_error",
                          "authority_refused", "lifecycle_refused")


@case("QA-GOV-515", "A well-formed band is accepted")
def gov_203(ctx: Ctx) -> Result:
    return expect_accepted(_band(ctx))


@case("QA-GOV-516", "Two bands with the same name")
def gov_204(ctx: Ctx) -> Result:
    name = ctx.unique("band")
    _band(ctx, name=name)
    return expect_refused(_band(ctx, name=name),
                          "band_exists", "authority_refused",
                          "lifecycle_refused")


# ------------------------------------------------------------ delegations
@case("QA-GOV-517", "A delegation with no ceiling")
def gov_210(ctx: Ctx) -> Result:
    """A delegation without a ceiling is not a delegation, it is a transfer
    of the whole authority."""
    got = _delegation(ctx, ceiling=0.0)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"


@case("QA-GOV-518", "A delegation with a negative ceiling")
def gov_211(ctx: Ctx) -> Result:
    got = _delegation(ctx, ceiling=-1.0)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a negative ceiling was accepted; every amount is above "
                      "it, so the delegation authorises nothing and reads as "
                      "though it authorises something")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-519", "A delegation with no instrument")
def gov_212(ctx: Ctx) -> Result:
    """The instrument is the document the authority actually rests on. A
    delegation with none is somebody's recollection."""
    return expect_refused(_delegation(ctx, instrument="   "),
                          "validation_error", "instrument_required",
                          "authority_refused", "lifecycle_refused")


@case("QA-GOV-520", "A delegation with a blank currency")
def gov_213(ctx: Ctx) -> Result:
    """A ceiling with no currency is a number. The platform reports in USD,
    so an unlabelled ceiling is compared against amounts it may not match."""
    got = _delegation(ctx, currency="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a ceiling was accepted with no currency; the "
                      "comparison it governs is then between a number and an "
                      "amount")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-521", "A delegation to a principal that does not exist")
def gov_214(ctx: Ctx) -> Result:
    got = _delegation(ctx, principal="qa-nobody")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"


# ------------------------------------------------------------- break-glass
@case("QA-GOV-522", "Break-glass with no reason")
def gov_220(ctx: Ctx) -> Result:
    """Emergency access with no stated reason is the one record anybody will
    ask for afterwards."""
    return expect_refused(
        ctx.api.post(GLASS, json={"reason": "   ", "principal": "owner"}),
        "validation_error", "reason_required", "break_glass_refused")


@case("QA-GOV-523", "Break-glass is opened, and it is reviewable", isolated=True)
def gov_221(ctx: Ctx) -> Result:
    opened = ctx.api.post(GLASS, json={"reason": "QA emergency",
                                       "principal": "owner"})
    if opened.status_code >= 400:
        return BLOCKED, opened.text[:150]
    reference = opened.json().get("reference")
    if not reference:
        return FAIL, ("break-glass was opened with no reference, so nobody "
                      "can review it afterwards")
    return PASS, f"opened as {reference}"


def _closed_glass(ctx: Ctx) -> str:
    """An opened and closed break-glass, ready to be reviewed.

    Review refuses `still_open` on an access that is running, which is right:
    reviewing an emergency somebody is still inside is reviewing something
    that has not finished happening. The first version of these two cases
    skipped the close and reported that refusal as a defect.
    """
    opened = ctx.api.post(GLASS, json={"reason": "QA emergency",
                                       "principal": "owner"})
    if opened.status_code >= 400:
        raise AssertionError(f"could not open: {opened.text[:150]}")
    reference = opened.json()["reference"]
    ctx.api.post(f"{GLASS}/{reference}/close", json={"reason": "QA done"})
    return reference


@case("QA-GOV-222", "Review a break-glass with no note", isolated=True)
def gov_222(ctx: Ctx) -> Result:
    reference = _closed_glass(ctx)
    return expect_refused(
        ctx.api.post(f"{GLASS}/{reference}/review",
                     json={"outcome": REVIEW_OUTCOME, "note": "   "}),
        "validation_error", "note_required", "break_glass_refused",
        "review_note_required")


@case("QA-GOV-524", "Review a break-glass with an outcome that is not one", isolated=True)
def gov_223(ctx: Ctx) -> Result:
    reference = _closed_glass(ctx)
    return expect_refused(
        ctx.api.post(f"{GLASS}/{reference}/review",
                     json={"outcome": "fine i guess", "note": "QA"}),
        "unknown_outcome", "validation_error", "break_glass_refused")


# ------------------------------------------------------- recertification
@case("QA-GOV-230", "A recertification campaign with no reviewer")
def gov_230(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post(RECERT, json={"reference": ctx.unique("rc"),
                                   "reviewer": "   ", "title": "QA"}),
        "no_such_principal", "reviewer_required", "validation_error")


@case("QA-GOV-525", "A campaign over an empty population")
def gov_231(ctx: Ctx) -> Result:
    """A campaign nobody is in completes the moment it opens, and reports as
    a clean recertification of nothing."""
    got = ctx.api.post(RECERT, json={"reference": ctx.unique("rc"),
                                     "reviewer": "risk", "title": "QA",
                                     "population": []})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a campaign opened over nobody; it completes "
                      "immediately and reads as a clean recertification")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-232", "Two campaigns with the same reference")
def gov_232(ctx: Ctx) -> Result:
    reference = ctx.unique("rc")
    body = {"reference": reference, "reviewer": "risk", "title": "QA",
            "population": ["owner"]}
    ctx.api.post(RECERT, json=body)
    return expect_refused(ctx.api.post(RECERT, json=body),
                          "campaign_exists", "recertification_refused",
                          "validation_error")


# --------------------------------------------------------------- conditions
@case("QA-GOV-526", "An approval condition with no rationale")
def gov_240(ctx: Ctx) -> Result:
    urn = _model(ctx)
    return expect_refused(
        ctx.api.post(CONDITIONS, json={"urn": urn, "kind": CONDITION_KIND,
                                       "days": 30, "rationale": "   "}),
        "rationale_required", "validation_error", "lifecycle_refused")


@case("QA-GOV-527", "A condition with a negative window")
def gov_241(ctx: Ctx) -> Result:
    urn = _model(ctx)
    got = ctx.api.post(CONDITIONS, json={"urn": urn, "kind": CONDITION_KIND,
                                         "days": -30, "rationale": "QA"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a condition was accepted that came due before it was "
                      "imposed")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-528", "Discharge a condition with no reason")
def gov_242(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post(f"{CONDITIONS}/qa-never/discharge", json={"reason": "  "}),
        "no_condition", "reason_required", "validation_error")
