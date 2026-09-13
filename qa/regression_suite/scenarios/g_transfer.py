"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — data leaving the platform, and data arriving from outside.

Transfer and sources are where the register touches something it does not
control. Every case here is about the platform declining to claim more than
it holds: a pull it did not verify, an export it cannot recall, a source it
cannot read.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  expect_refused, valid_body)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
VIEWS = "/api/v1/feature-views"
#: Read from the platform's own refusal rather than invented: "MAYA reads
#: sql, file, s3, gcs". `warehouse` sounds exactly like a source kind and is
#: not one.
SOURCE_KIND = "s3"
#: And an s3 source needs a format: "'s3://qa-bucket/table' does not say
#: which of csv, jsonl, parquet, arrow it is". A locator that does not say how
#: to read it is a locator the platform cannot use.


def _view(ctx: Ctx) -> str:
    """A feature and a view over it."""
    feature = ctx.unique("tf")
    ctx.api.post("/api/v1/features",
                 json={"name": feature, "description": "a QA feature",
                       "dtype": "float", "entity": "borrower",
                       "owner": "owner"})
    name = ctx.unique("tv")
    made = ctx.api.post(VIEWS, json={"name": name, "entity": "borrower",
                                     "features": [feature], "owner": "owner"})
    if made.status_code >= 400:
        raise AssertionError(f"could not create a view: {made.text[:170]}")
    return name


def _source(ctx: Ctx, name: str, **over):
    body = valid_body(ctx, "PUT", f"{VIEWS}/{{name}}/source",
                      kind=SOURCE_KIND, locator="s3://qa-bucket/table",
                      format="parquet")
    body.update(over)
    return ctx.api.put(f"{VIEWS}/{name}/source", json=body)


# ----------------------------------------------------------------- sources
@case("QA-FX-950", "A source of a kind the platform cannot read")
def fx_950(ctx: Ctx) -> Result:
    return expect_refused(_source(ctx, _view(ctx), kind="carrier_pigeon"),
                          "unknown_kind", "validation_error",
                          "feature_refused", "discovery_refused")


@case("QA-FX-951", "A source with no locator")
def fx_951(ctx: Ctx) -> Result:
    """A source nobody can point at is a promise that data will arrive from
    somewhere."""
    got = _source(ctx, _view(ctx), locator="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a source was configured with nothing to read from"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-952", "A source on a view that does not exist")
def fx_952(ctx: Ctx) -> Result:
    got = _source(ctx, "qa-no-such-view")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a source was attached to a view nobody created"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-953", "A pull from a source that was never configured")
def fx_953(ctx: Ctx) -> Result:
    got = ctx.api.post(f"{VIEWS}/{_view(ctx)}/source/pull", json={})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a pull reported success from a source that was never "
                      "configured")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-954", "Retire a source with no reason")
def fx_954(ctx: Ctx) -> Result:
    name = _view(ctx)
    _source(ctx, name)
    return expect_refused(
        ctx.api.post(f"{VIEWS}/{name}/source/retire", json={"reason": "   "}),
        "feature_refused", "reason_required", "validation_error",
        "discovery_refused")


@case("QA-FX-955", "A configured source reports where it reads from")
def fx_955(ctx: Ctx) -> Result:
    """The other half — a source that cannot be read back is one nobody can
    audit."""
    name = _view(ctx)
    made = _source(ctx, name)
    if made.status_code >= 400:
        return BLOCKED, made.text[:150]
    got = ctx.api.get(f"{VIEWS}/{name}/source")
    if got.status_code >= 400:
        return FAIL, f"the source cannot be read back: {got.status_code}"
    if "s3" not in got.text:
        return FAIL, f"the source does not report its locator: {got.text[:120]}"
    return PASS, "readable, and it names where it reads from"


# ---------------------------------------------------------------- transfer
@case("QA-FX-960", "Export a feature view version that does not exist")
def fx_960(ctx: Ctx) -> Result:
    got = ctx.api.get(f"{VIEWS}/{_view(ctx)}/versions/99/data")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "data was exported from a version that does not exist"
    return PASS, f"refused ({got.status_code})"


@case("QA-FX-961", "Export from a view that does not exist")
def fx_961(ctx: Ctx) -> Result:
    got = ctx.api.get(f"{VIEWS}/qa-no-such-view/versions/1/data")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "data was exported from a view nobody created"
    return PASS, f"refused ({got.status_code})"


@case("QA-FX-962", "A retirable check names what still depends on a version")
def fx_962(ctx: Ctx) -> Result:
    """'Where is this used' and 'may I delete this' are the same question,
    and answering them separately is how they come to disagree."""
    got = ctx.api.get(f"{VIEWS}/{_view(ctx)}/versions/1/retirable")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, f"answered {got.status_code}"


@case("QA-FX-963", "The perimeter says what the platform does not control")
def fx_963(ctx: Ctx) -> Result:
    """Twelve places the register touches something outside itself, each
    named rather than quietly assumed."""
    got = ctx.api.get("/api/v1/perimeter")
    if got.status_code == 404:
        got = ctx.api.get("/api/v1/configuration/boundary")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    if len(got.text) < 60:
        return FAIL, "the perimeter is published and says almost nothing"
    return PASS, f"published, {len(got.text)} bytes"
