"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — features, featuresets and the rules over them.

Written as tables. Every body comes from the endpoint's own schema, so a case
states the one field it is about and nothing else.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from qa.regression_suite.scenarios.common import (FAIL, PASS, Ctx, Result, case, code_of,
                                       valid_body)

FEATURE = "/api/v1/features"
FEATURESET = "/api/v1/featuresets"


def _feature(ctx: Ctx, **over) -> Dict[str, Any]:
    # Defaults first, then the case's overrides — passing both as keywords
    # gave `valid_body() got multiple values for 'name'` the moment a case
    # overrode one of them.
    body = valid_body(ctx, "POST", FEATURE,
                      name=ctx.unique("f"), description="a QA feature",
                      dtype="float", entity="borrower", owner="owner")
    body.update(over)
    return body


def _define(ctx: Ctx, **over):
    return ctx.api.post(FEATURE, json=_feature(ctx, **over))


#: (id, title, overrides, one of the codes we will accept, why it matters)
REFUSALS: List[Tuple[str, str, Dict[str, Any], Tuple[str, ...], str]] = [
    ("QA-FX-700", "a feature with no name", {"name": "   "},
     ("validation_error", "feature_refused", "validation_refused"),
     "a feature nobody can name is one nobody can cite"),
    ("QA-FX-701", "a feature with no owner", {"owner": "   "},
     ("validation_error", "feature_refused", "validation_refused"),
     "an unowned feature is one nobody maintains"),
    ("QA-FX-702", "a feature of an unknown dtype", {"dtype": "vibes"},
     ("validation_error", "feature_refused", "unknown_dtype",
      "validation_refused"),
     "the dtype decides how every later comparison behaves"),
    ("QA-FX-703", "a feature with no entity", {"entity": "   "},
     ("validation_error", "feature_refused", "validation_refused"),
     "the entity is what a row is keyed on"),
    ("QA-FX-704", "a feature with no description", {"description": "   "},
     ("validation_error", "feature_refused", "validation_refused"),
     "a business definition is what stops two teams meaning different "
     "things by one name"),
    ("QA-FX-705", "a negative ttl", {"ttl_days": -1},
     ("validation_error", "feature_refused", "validation_refused"),
     "a negative lifetime is a row that expired before it arrived"),
    ("QA-FX-706", "a shape that is not a shape", {"shape": "big"},
     ("validation_error", "feature_refused", "validation_refused"),
     "the shape decides how a value is read back"),
]


def _register_refusal(spec):
    case_id, what, over, codes, why = spec

    def run(ctx: Ctx) -> Result:
        got = _define(ctx, **over)
        if got.status_code >= 500:
            return FAIL, f"{got.status_code} — {what} crashed it"
        if got.status_code < 400:
            return FAIL, f"{what} was accepted, and {why}"
        seen = code_of(got)
        if codes and seen not in codes:
            return PASS, (f"refused '{seen}' — a considered refusal, though "
                          f"not one of {codes}")
        return PASS, f"refused '{seen}'"

    case(case_id, f"Define {what}")(run)


for spec in REFUSALS:
    _register_refusal(spec)


@case("QA-FX-622", "A well-formed feature is accepted")
def fx_410(ctx: Ctx) -> Result:
    """The other half of every refusal above. A definition endpoint that
    refuses everything passes all seven cases and is useless."""
    got = _define(ctx)
    if got.status_code >= 400:
        return FAIL, f"a valid feature was refused: {got.text[:170]}"
    return PASS, f"accepted ({got.status_code})"


@case("QA-FX-623", "The same feature name twice")
def fx_411(ctx: Ctx) -> Result:
    body = _feature(ctx)
    ctx.api.post(FEATURE, json=body)
    again = ctx.api.post(FEATURE, json=body)
    if again.status_code < 400:
        return FAIL, ("two features share one name; every later citation is "
                      "a coin toss")
    return PASS, f"refused '{code_of(again)}'"


@case("QA-FX-624", "A feature declared as personal data")
def fx_412(ctx: Ctx) -> Result:
    """Not a refusal — a flag that changes what may be recorded about it."""
    got = _define(ctx, pii=True)
    if got.status_code >= 400:
        return FAIL, f"a feature cannot be declared as personal data: " \
                     f"{got.text[:150]}"
    return PASS, "accepted and flagged"


@case("QA-FX-625", "A feature naming a protected basis")
def fx_413(ctx: Ctx) -> Result:
    got = _define(ctx, protected_basis="ethnicity")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"


@case("QA-FX-626", "A featureset over a feature that does not exist")
def fx_414(ctx: Ctx) -> Result:
    body = valid_body(ctx, "POST", FEATURESET, name=ctx.unique("fs"),
                      entity="borrower", owner="owner",
                      features=["qa-no-such-feature"])
    got = ctx.api.post(FEATURESET, json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a featureset was assembled over a feature that does "
                      "not exist; the slot resolves to nothing at read time")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-415", "A featureset with no features at all")
def fx_415(ctx: Ctx) -> Result:
    body = valid_body(ctx, "POST", FEATURESET, name=ctx.unique("fs"),
                      entity="borrower", owner="owner", features=[])
    got = ctx.api.post(FEATURESET, json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"


@case("QA-FX-627", "Retire a feature that does not exist")
def fx_416(ctx: Ctx) -> Result:
    got = ctx.api.post(f"{FEATURE}/qa-never/retire", json={"reason": "qa"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "retiring something that does not exist reported success"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-417", "Read a feature that does not exist")
def fx_417(ctx: Ctx) -> Result:
    got = ctx.api.get(f"{FEATURE}/qa-never")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an unknown feature name returned a feature"
    return PASS, f"refused ({got.status_code})"


@case("QA-FX-628", "A feature expression that references itself")
def fx_418(ctx: Ctx) -> Result:
    """A derived feature computed from itself has no fixed point, and the
    read either never terminates or silently returns a default."""
    name = ctx.unique("f")
    body = _feature(ctx, name=name, expression=f"{name} + 1")
    got = ctx.api.post(FEATURE, json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} — self-reference crashed it"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"


@case("QA-FX-419", "Trial an expression that divides by zero")
def fx_419(ctx: Ctx) -> Result:
    """An arithmetic error in somebody's draft expression must be a refusal,
    not a 500 — this is the endpoint people iterate on."""
    got = ctx.api.post(f"{FEATURE}/trial",
                       json={"expression": "1 / 0", "rows": [{}]})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} — a draft expression crashed the API"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'accepted'})"


@case("QA-FX-420", "Trial an expression that is not an expression")
def fx_420(ctx: Ctx) -> Result:
    got = ctx.api.post(f"{FEATURE}/trial",
                       json={"expression": "import os; os.system('id')",
                             "rows": [{}]})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an import statement was accepted as a feature "
                      "expression")
    return PASS, f"refused '{code_of(got)}'"
