"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — featuresets, assumptions, limitations and expert elicitation.

A featureset is what a model reads. An assumption is what somebody believed
when they built it. An elicitation is what a panel thought when there was no
data. All three are the register holding a claim that nothing else can check,
so all three turn on whether the claim is attributable.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  expect_accepted,
                                                  expect_refused, valid_body)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
FEATURESETS = "/api/v1/featuresets"
ASSUMPTIONS = "/api/v1/assumptions"
LIMITATIONS = "/api/v1/limitations"
ELICITATIONS = "/api/v1/elicitations"


def _versioned(ctx: Ctx) -> str:
    name = ctx.unique("fs")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "owner", **TIER})
    ctx.api.post(f"/api/v1/models/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    return urn


#: A featureset is a schema, and "a schema with nothing in it is not one" —
#: so a set with no slots is refused. My first version omitted them and three
#: cases failed on the empty schema rather than on their own subject.
SLOTS = {"dscr": {"dtype": "float"}}


def _featureset(ctx: Ctx, **over):
    body = valid_body(ctx, "POST", FEATURESETS, name=ctx.unique("set"),
                      entity="borrower", description="a QA featureset",
                      slots=SLOTS)
    body.update(over)
    return ctx.api.post(FEATURESETS, json=body)


# ------------------------------------------------------------- featuresets
@case("QA-FX-900", "A featureset with no name")
def fx_900(ctx: Ctx) -> Result:
    got = _featureset(ctx, name="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a featureset nobody can name was created"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-901", "A featureset with no entity")
def fx_901(ctx: Ctx) -> Result:
    """The entity is what a row is keyed on. Without it an assembly has no
    join key and returns whatever it finds."""
    got = _featureset(ctx, entity="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a featureset was created with nothing to key rows on"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-902", "A well-formed featureset is accepted")
def fx_902(ctx: Ctx) -> Result:
    return expect_accepted(_featureset(ctx), status=201)


@case("QA-FX-903", "Two featuresets with the same name")
def fx_903(ctx: Ctx) -> Result:
    name = ctx.unique("set")
    _featureset(ctx, name=name)
    got = _featureset(ctx, name=name)
    if got.status_code < 400:
        return FAIL, "two featuresets share one name"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-904", "A negative outcome window")
def fx_904(ctx: Ctx) -> Result:
    """The outcome window is how long you wait for a label. Negative, the
    label is expected before the decision."""
    got = _featureset(ctx, outcome_window_days=-30)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an outcome window was accepted that expects the label "
                      "before the decision it labels")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-905", "Retire a featureset with no reason")
def fx_905(ctx: Ctx) -> Result:
    made = _featureset(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    name = made.json().get("name") or made.json().get("featureset", {}).get("name")
    return expect_refused(
        ctx.api.post(f"{FEATURESETS}/{name}/retire", json={"reason": "   "}),
        "feature_refused", "reason_required", "validation_error")


@case("QA-FX-906", "Publish a version with no bindings")
def fx_906(ctx: Ctx) -> Result:
    """A version binds each slot to a feature view version. With no bindings
    the set resolves to nothing at read time."""
    made = _featureset(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    name = made.json().get("name") or made.json().get("featureset", {}).get("name")
    got = ctx.api.post(f"{FEATURESETS}/{name}/versions", json={"bindings": {}})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a featureset version was published binding nothing"
    return PASS, f"refused '{code_of(got)}'"


# ------------------------------------------------------------- assumptions
def _assumption(ctx: Ctx, **over):
    body = valid_body(ctx, "POST", ASSUMPTIONS, urn=_versioned(ctx),
                      semver="1.0.0", kind="data",
                      statement="the feed arrives daily")
    body.update(over)
    return ctx.api.post(ASSUMPTIONS, json=body)


@case("QA-FX-920", "An assumption with no statement")
def fx_920(ctx: Ctx) -> Result:
    """An assumption is a sentence somebody has to be able to disagree with."""
    got = _assumption(ctx, statement="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an assumption was recorded with nothing stated; "
                      "nobody can review a blank belief")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-921", "An assumption of a kind that is not one")
def fx_921(ctx: Ctx) -> Result:
    return expect_refused(_assumption(ctx, kind="vibes"),
                          "unknown_kind", "validation_error",
                          "registry_refused", "assumption_refused")


@case("QA-FX-922", "An assumption against a version that does not exist")
def fx_922(ctx: Ctx) -> Result:
    return expect_refused(_assumption(ctx, semver="9.9.9"),
                          "no_such_version", "registry_refused", "not_found")


@case("QA-FX-923", "Withdraw an assumption with no reason")
def fx_923(ctx: Ctx) -> Result:
    """Withdrawing makes the register say less than it did about an immutable
    version, so the reason is the whole record of the change."""
    return expect_refused(
        ctx.api.post(f"{ASSUMPTIONS}/qa-never/withdraw",
                     json={"reason": "   "}),
        "registry_refused", "not_found", "reason_required")


@case("QA-FX-924", "A well-formed assumption is accepted")
def fx_924(ctx: Ctx) -> Result:
    return expect_accepted(_assumption(ctx), status=201)


# ------------------------------------------------------------ elicitations
#: Three is the floor: "one expert's judgement is not an elicitation". The
#: panel is the control, so a fixture without one is refused before the case
#: reaches whatever it was asking.
#: And the facilitator is NOT on it — "the facilitator sets the question and
#: does not answer it". Putting `risk` in both places is the conflict the
#: platform exists to refuse, committed in my own fixture.
PANEL = ["owner", "developer", "validator"]


def _elicitation(ctx: Ctx, **over):
    body = valid_body(ctx, "POST", ELICITATIONS, urn=_versioned(ctx),
                      reference=ctx.unique("EL"), facilitator="risk",
                      panel=PANEL,
                      question="What is the loss given default?")
    body.update(over)
    return ctx.api.post(ELICITATIONS, json=body)


@case("QA-FX-940", "An elicitation with no question")
def fx_940(ctx: Ctx) -> Result:
    got = _elicitation(ctx, question="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a panel was convened with nothing asked of it")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-941", "An elicitation with no facilitator")
def fx_941(ctx: Ctx) -> Result:
    got = _elicitation(ctx, facilitator="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an elicitation with no facilitator; the one role that "
                      "makes a panel's answer attributable")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-942", "Respond to an elicitation that does not exist")
def fx_942(ctx: Ctx) -> Result:
    got = ctx.api.post(f"{ELICITATIONS}/qa-never/respond",
                       json={"panellist": "owner", "value": 0.4})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a response was recorded against no elicitation"
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-FX-943", "Conclude an elicitation with no note")
def fx_943(ctx: Ctx) -> Result:
    """The note is how a number arrived at by judgement is defended later."""
    got = ctx.api.post(f"{ELICITATIONS}/qa-never/conclude",
                       json={"value": 0.4, "note": "   "})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an elicitation concluded with no reasoning recorded"
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-FX-944", "A well-formed elicitation opens")
def fx_944(ctx: Ctx) -> Result:
    return expect_accepted(_elicitation(ctx), status=201)
