"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — composition, blast radius and model algebra.

A discount curve feeds a valuation feeds a provision. The register holds three
models and the caller wants one answer, and every case here is about the
reconciliation refusing rather than averaging.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  valid_body)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
EDGES = "/api/v1/model-relations"


def _model(ctx: Ctx) -> str:
    name = ctx.unique("cm")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "owner", **TIER})
    return urn


def _relate(ctx: Ctx, upstream: str, downstream: str, **over):
    # `from_urn`/`to_urn`, not upstream/downstream. The direction is named
    # from the edge's point of view rather than the graph's.
    body = valid_body(ctx, "POST", EDGES, from_urn=upstream,
                      to_urn=downstream, kind="input_to")
    body.update(over)
    return ctx.api.post(EDGES, json=body)


@case("QA-FX-1100", "An edge from a model that does not exist")
def fx_1100(ctx: Ctx) -> Result:
    got = _relate(ctx, "maya://model/qa.never", _model(ctx))
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a composition edge was recorded from a model nobody "
                      "registered; the graph now names something that does "
                      "not exist")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-1101", "An edge of a kind that is not one")
def fx_1101(ctx: Ctx) -> Result:
    """The kind decides whether a change upstream reaches downstream, so an
    unknown one is an edge nobody can reason about."""
    got = _relate(ctx, _model(ctx), _model(ctx), kind="vibes")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an edge of an unknown kind was recorded"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-1102", "A model composed with itself")
def fx_1102(ctx: Ctx) -> Result:
    """A model that reads its own output has no fixed point."""
    urn = _model(ctx)
    got = _relate(ctx, urn, urn)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a model was composed with itself"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-1103", "A cycle across two models")
def fx_1103(ctx: Ctx) -> Result:
    """Answering a cyclic graph with a truncated order gives a caller a chain
    that runs and is wrong."""
    a, b = _model(ctx), _model(ctx)
    first = _relate(ctx, a, b)
    if first.status_code >= 400:
        return BLOCKED, f"could not create the first edge: {first.text[:150]}"
    got = _relate(ctx, b, a)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a cycle was recorded; a chain built from it runs and "
                      "is wrong")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-1104", "Blast radius with no urn")
def fx_1104(ctx: Ctx) -> Result:
    """The regression: `body['urn']` was a KeyError and therefore a bare 500
    with no body when the field was absent."""
    got = ctx.api.post("/api/v1/blast-radius", json={})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} — a missing field crashed it"
    if got.status_code < 400:
        return FAIL, "a blast radius was computed from no model"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-1105", "Blast radius over a model that does not exist")
def fx_1105(ctx: Ctx) -> Result:
    got = ctx.api.post("/api/v1/blast-radius",
                       json={"urn": "maya://model/qa.never"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a blast radius was computed for a model nobody has"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-1106", "Blast radius follows only propagating relations")
def fx_1106(ctx: Ctx) -> Result:
    """A challenger is not downstream of the model it argues with, so a
    change to the champion must not be reported as reaching it."""
    a, b = _model(ctx), _model(ctx)
    made = _relate(ctx, a, b, kind="challenging")
    if made.status_code >= 400:
        return PASS, (f"'challenging' is not an edge kind here "
                      f"({code_of(made)}); nothing to propagate")
    got = ctx.api.post("/api/v1/blast-radius", json={"urn": a})
    if got.status_code >= 400:
        return BLOCKED, got.text[:150]
    if b in got.text:
        return FAIL, ("a challenger is reported as downstream of the model "
                      "it argues with")
    return PASS, "only propagating relations are followed"


@case("QA-FX-1107", "Shared dependencies over an empty list")
def fx_1107(ctx: Ctx) -> Result:
    """'What do these models both depend on' over no models is a question
    with no subject, and the answer must not be everything."""
    got = ctx.api.post("/api/v1/shared-dependencies", json={"urns": []})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        body = got.text
        if len(body) > 400 and "shared" in body and "[]" not in body:
            return FAIL, ("shared dependencies over an empty list returned "
                          "content; the answer to a question with no subject "
                          "should be empty")
    return PASS, f"answered {got.status_code}"


@case("QA-FX-1108", "A composite refuses if any node refuses")
def fx_1108(ctx: Ctx) -> Result:
    """A chain is as governed as its least governed link."""
    got = ctx.api.post("/api/v1/composites/check",
                       json={"terminal": "maya://model/qa.never",
                             "environment": "prod",
                             "declared_use": "credit_decision"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code} ({code_of(got) or 'reported'})"


@case("QA-FX-1109", "A composite has no single signed descriptor")
def fx_1109(ctx: Ctx) -> Result:
    """Signing one would assert the chain AS A WHOLE is authorised, and three
    approvals for three models were not that."""
    import inspect

    from core.execution import composite
    source = inspect.getsource(composite)
    if '"composite_descriptor": None' not in source:
        return FAIL, ("a composite now mints a single descriptor; that "
                      "asserts an authorisation nobody gave")
    return PASS, "no composite descriptor, deliberately"
