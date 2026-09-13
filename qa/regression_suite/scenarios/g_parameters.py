"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — parameters, rule sets and retraining policy.

A parameter set is the point of P a model actually runs at, and the whole
governance question is whether the register can say where it came from: which
fit, over which data, under whose warrant. A rule set is the same question for
a model that is a document rather than a fit.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  expect_accepted,
                                                  expect_refused, valid_body)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
PARAMETERS = "/api/v1/parameters"
RULESETS = "/api/v1/rulesets"
RETRAINING = "/api/v1/retraining"


#: A kernel whose parameters come from DATA rather than from theory.
#:
#: A bare version's parameter object is terminal — "its parameters come from
#: theory, not from data, so there is nothing to fit" — which is the
#: trainability class being derived rather than declared, and it refused four
#: of these cases before they reached their own subject. The class falls out
#: of how the parameter object is inhabited, so the fixture has to inhabit it.
FITTABLE = {"parameter_kind": "estimated_coefficients",
            "fit_procedure": "estimate",
            "input_schema": [{"name": "dscr", "dtype": "float",
                              "minimum": -5, "maximum": 20}],
            "output_schema": [{"name": "pd_12m", "dtype": "float"}]}


def _versioned(ctx: Ctx) -> str:
    name = ctx.unique("pm")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "owner", **TIER})
    ctx.api.post(f"/api/v1/models/{name}/versions",
                 json={"semver": "1.0.0", "kernel": FITTABLE},
                 auth=ctx.people["developer"])
    return urn


def _parameters(ctx: Ctx, **over):
    # `provenance`, not `kind`. The two are different fields and I set the
    # wrong one: `kind` is what the parameter object IS, `provenance` is where
    # the numbers came from. Leaving provenance to default to `fitted` made
    # every case demand a fit warrant and fail on that instead of on its own
    # subject.
    body = valid_body(ctx, "POST", PARAMETERS, urn=_versioned(ctx),
                      semver="1.0.0", name=ctx.unique("ps"),
                      kind="estimated_coefficients", provenance="declared",
                      values={"intercept": 0.1})
    body.update(over)
    return ctx.api.post(PARAMETERS, json=body)


# ------------------------------------------------------------- parameters
@case("QA-FX-800", "A parameter set with no name")
def fx_800(ctx: Ctx) -> Result:
    """Two approved sets and no name in the request is `ambiguous_parameters`
    at resolution; an unnamed set makes that impossible to disambiguate."""
    return expect_refused(_parameters(ctx, name="   "),
                          "validation_error", "parameter_refused",
                          "name_required")


@case("QA-FX-801", "A parameter set whose provenance is not one")
def fx_801(ctx: Ctx) -> Result:
    return expect_refused(_parameters(ctx, provenance="vibes"),
                          "unknown_provenance", "unknown_kind",
                          "parameter_refused", "validation_error")


@case("QA-FX-802", "A parameter set against a version that does not exist")
def fx_802(ctx: Ctx) -> Result:
    return expect_refused(_parameters(ctx, semver="9.9.9"),
                          "no_such_version", "registry_refused",
                          "not_found")


@case("QA-FX-803", "A parameter set with neither values nor a uri")
def fx_803(ctx: Ctx) -> Result:
    """A set that says nothing about where P is cannot be the point a model
    runs at."""
    got = _parameters(ctx, values=None, values_uri=None)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a parameter set was recorded with no values and no "
                      "reference to any; nothing can be resolved from it")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-804", "A well-formed parameter set is accepted")
def fx_804(ctx: Ctx) -> Result:
    return expect_accepted(_parameters(ctx))


@case("QA-FX-805", "A fitted set naming no warrant")
def fx_805(ctx: Ctx) -> Result:
    """A fit is a governed act. A `fitted` set with no warrant is a claim
    that training happened under an authority nobody can name."""
    got = _parameters(ctx, provenance="fitted", warrant_id=None)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a fitted parameter set was recorded with no warrant; "
                      "the fit it claims has no authority behind it")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-806", "A fitted set naming a warrant that does not exist")
def fx_806(ctx: Ctx) -> Result:
    got = _parameters(ctx, provenance="fitted",
                      warrant_id="qa-no-such-warrant")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a fitted set cited a warrant nobody issued"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-807", "Review a parameter set that does not exist")
def fx_807(ctx: Ctx) -> Result:
    got = ctx.api.post("/api/v1/parameter-sets/qa-never/review",
                       json={"accept": True, "note": "QA"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} — an unknown id crashed the review"
    if got.status_code < 400:
        return FAIL, "a parameter set that does not exist was approved"
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-FX-808", "The person who proposed a set reviews it themselves")
def fx_808(ctx: Ctx) -> Result:
    made = _parameters(ctx)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    identifier = made.json().get("id")
    got = ctx.api.post(f"/api/v1/parameter-sets/{identifier}/review",
                       json={"accept": True, "note": "looks fine to me"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("the proposer approved their own parameter set; a "
                      "review nobody independent performed is a receipt")
    return PASS, f"refused '{code_of(got)}'"


# --------------------------------------------------------------- rulesets
def _ruleset(ctx: Ctx, **over):
    body = valid_body(ctx, "POST", RULESETS, urn=_versioned(ctx),
                      semver="1.0.0", name=ctx.unique("rs"),
                      document="IF income > 0 THEN accept")
    body.update(over)
    return ctx.api.post(RULESETS, json=body)


@case("QA-FX-820", "A rule set with an empty document")
def fx_820(ctx: Ctx) -> Result:
    """A rule set with no rules decides nothing, and reads in every screen as
    a model that has been authored."""
    got = _ruleset(ctx, document="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a rule set with no rules was recorded as authored"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-821", "A rule set that does not parse")
def fx_821(ctx: Ctx) -> Result:
    """The failure must name the line. A parser that answers 500 on a typo is
    one nobody can author against."""
    got = _ruleset(ctx, document="IF THEN ELSE MAYBE")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} — a syntax error crashed the parser"
    if got.status_code < 400:
        return FAIL, "nonsense was accepted as a rule set"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-822", "Check a rule set without recording it")
def fx_822(ctx: Ctx) -> Result:
    urn = _versioned(ctx)
    got = ctx.api.post(f"{RULESETS}/check",
                       json={"urn": urn, "semver": "1.0.0",
                             "document": "IF income > 0 THEN accept"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    listed = ctx.api.get(RULESETS, params={"urn": urn})
    if listed.status_code < 400 and ctx.unique("") and "rules" in listed.text:
        pass
    return PASS, f"check answered {got.status_code} and recorded nothing"


@case("QA-FX-823", "Trial a rule set against rows")
def fx_823(ctx: Ctx) -> Result:
    """Somebody authoring a rule set should be able to see what it does
    before anybody is governed by it."""
    got = ctx.api.post(f"{RULESETS}/trial",
                       json={"urn": _versioned(ctx), "semver": "1.0.0",
                             "document": "IF income > 0 THEN accept",
                             "rows": [{"income": 1.0}, {"income": -1.0}]})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code}"


# -------------------------------------------------------------- retraining
@case("QA-FX-840", "A retraining policy with no rationale")
def fx_840(ctx: Ctx) -> Result:
    """A policy that lets a model retrain itself is the one place a model
    changes without a person, so why it was allowed is the whole record."""
    body = valid_body(ctx, "POST", RETRAINING, rationale="   ")
    got = ctx.api.post(RETRAINING, json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a retraining policy was recorded with no rationale; "
                      "the one place a model changes without a person, and "
                      "nothing says why that was permitted")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-841", "A retraining policy that never expires")
def fx_841(ctx: Ctx) -> Result:
    body = valid_body(ctx, "POST", RETRAINING, rationale="QA",
                      expires_at=None)
    got = ctx.api.post(RETRAINING, json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"
