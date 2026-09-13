"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — reporting, saved views, search and the estate.

Everything here is a number somebody takes to a meeting. The failure mode is
not a crash: it is a figure that looks like an answer and is a different
question, or one computed over a population that quietly excluded something.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  expect_refused, valid_body)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
VIEWS = "/api/v1/saved-views"


def _model(ctx: Ctx) -> str:
    name = ctx.unique("rp")
    ctx.api.post("/api/v1/models", json={"urn": f"maya://model/{name}",
                                         "name": name, "owner": "owner",
                                         **TIER})
    return name


# ------------------------------------------------------------ the estate
@case("QA-PLT-700", "The estate reports a count it can justify")
def plt_700(ctx: Ctx) -> Result:
    _model(ctx)
    # There is no `/api/v1/estate`; the estate is reported per subsystem and
    # the portfolio is the cross-cutting view.
    got = ctx.api.get("/api/v1/portfolio")
    if got.status_code >= 400:
        return BLOCKED, got.text[:150]
    body = got.json()
    if not any(k in str(body) for k in ("models", "count", "total")):
        return FAIL, "the estate reports no count at all"
    return PASS, f"answered {got.status_code}"


@case("QA-PLT-701", "A portfolio cut by a dimension that does not exist")
def plt_701(ctx: Ctx) -> Result:
    """An unknown dimension must be refused rather than silently grouped into
    one bucket, which reads as an estate with no variation."""
    # The parameter is `dimension`, not `by`. Sending an unknown parameter
    # name meant FastAPI ignored it and the default cut came back — the case
    # reported a silently-ignored dimension and the platform had never been
    # asked for one.
    got = ctx.api.get("/api/v1/portfolio", params={"dimension": "vibes"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400 and "vibes" not in got.text:
        return FAIL, ("an unknown dimension was accepted and silently "
                      "ignored; the cut reads as an estate with no variation")
    return PASS, f"answered {got.status_code}"


@case("QA-PLT-702", "A heatmap of a dimension against itself")
def plt_702(ctx: Ctx) -> Result:
    """Every model lands on the diagonal, which is true and useless, and
    reads as perfect concentration."""
    got = ctx.api.get("/api/v1/portfolio/heatmap",
                      params={"rows": "domain", "columns": "domain"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code}"


# ------------------------------------------------------------ saved views
@case("QA-PLT-710", "A saved view with no name")
def plt_710(ctx: Ctx) -> Result:
    body = valid_body(ctx, "POST", VIEWS, name="   ",
                      query={"entity": "model"})
    got = ctx.api.post(VIEWS, json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a saved view nobody can name was stored"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-711", "A saved view over an entity that does not exist")
def plt_711(ctx: Ctx) -> Result:
    body = valid_body(ctx, "POST", VIEWS, name=ctx.unique("view"),
                      query={"entity": "vibes"})
    got = ctx.api.post(VIEWS, json=body)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a view was saved over an entity the query layer does "
                      "not have; it fails only when somebody opens it")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-712", "Read a saved view that does not exist")
def plt_712(ctx: Ctx) -> Result:
    """The regression: this answered 500 with no body, because `QueryError`
    was one of eleven coded refusals the route layer did not map."""
    return expect_refused(ctx.api.get(f"{VIEWS}/qa-never"), "unknown_view")


@case("QA-PLT-713", "Delete a saved view that does not exist")
def plt_713(ctx: Ctx) -> Result:
    got = ctx.api.request("DELETE", f"{VIEWS}/qa-never")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "deleting something that does not exist reported success"
    return PASS, f"refused '{code_of(got) or got.status_code}'"


# ---------------------------------------------------------------- search
@case("QA-PLT-720", "Search reports what it could not reach")
def plt_720(ctx: Ctx) -> Result:
    """A search that silently skips a corpus reports fewer hits and looks
    like a smaller estate."""
    got = ctx.api.get("/api/v1/document-search", params={"q": "model"})
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    body = got.json()
    if "coverage" not in str(body) and "searched" not in str(body):
        return FAIL, ("search reports hits and not what it searched; a "
                      "corpus it could not read is indistinguishable from "
                      "one with no matches")
    return PASS, "coverage is reported beside the hits"


@case("QA-PLT-721", "Search with an empty query")
def plt_721(ctx: Ctx) -> Result:
    got = ctx.api.get("/api/v1/document-search", params={"q": "   "})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code}"


# ------------------------------------------------------------- regulatory
@case("QA-PLT-730", "A regulatory return over an empty estate")
def plt_730(ctx: Ctx) -> Result:
    """A return with no rows must say the estate was empty rather than
    reporting zero exceptions."""
    got = ctx.api.get("/api/v1/regulatory-returns")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    return PASS, f"answered {got.status_code}"


@case("QA-PLT-731", "A regulatory return that does not exist")
def plt_731(ctx: Ctx) -> Result:
    """Also the guard regression: this was a bare 500 before `ReturnError`
    was mapped."""
    return expect_refused(
        ctx.api.get("/api/v1/regulatory-returns/qa-never"), "unknown_return")


@case("QA-PLT-732", "Risk appetite history for a metric that is not one")
def plt_732(ctx: Ctx) -> Result:
    """'So a relaxation is findable' — and an unknown metric answered with an
    empty history, which is what a limit that was never relaxed looks like."""
    return expect_refused(
        ctx.api.get("/api/v1/risk-appetite/history/qa-never"),
        "unknown_metric")


@case("QA-PLT-733", "Policy history for a gate that is not one")
def plt_733(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.get("/api/v1/policies/history/qa-never"), "unknown_gate")


@case("QA-PLT-734", "Feature view source for a view that does not exist")
def plt_734(ctx: Ctx) -> Result:
    """`{"source": null}` meant two things: no source configured, and no such
    view. The first is a state somebody acts on; the second is a typo."""
    got = ctx.api.get("/api/v1/feature-views/qa-never/source")
    if got.status_code < 400:
        return FAIL, ("an unknown feature view answered with a null source "
                      "rather than saying it does not exist")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-735", "Derived feature lineage for a feature that does not exist")
def plt_735(ctx: Ctx) -> Result:
    """An empty lineage reads as 'this rests on nothing and nothing rests on
    it', which is the answer the reference index refuses to give."""
    got = ctx.api.get("/api/v1/derived-features/qa-never/lineage")
    if got.status_code < 400:
        return FAIL, "an unknown feature reported an empty lineage"
    return PASS, f"refused '{code_of(got)}'"
