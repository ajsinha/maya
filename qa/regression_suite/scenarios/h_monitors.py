"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — monitor definition and evaluation.

A monitor that is not running looks exactly like a monitor that is passing,
so most of these are about the difference between *no breach* and *no
measurement*.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx, Result, case,
                                       code_of, expect_accepted,
                                       expect_refused, valid_body)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("mon")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "owner", **TIER})
    return urn


#: A threshold is a MAPPING — `{"max": 0.25}` — not a number. The comparison
#: direction is part of the threshold, because "0.25" does not say whether
#: more is worse.
DRIFT = {"max": 0.25}


def _define(ctx: Ctx, urn: str, **over):
    body = valid_body(ctx, "POST", "/api/v1/monitors",
                      urn=urn, name=ctx.unique("m"), kind="input_drift",
                      test_key="stability.psi", threshold=DRIFT,
                      owner="owner", cadence_days=30.0)
    body.update(over)
    return ctx.api.post("/api/v1/monitors", json=body)


def _defined(ctx: Ctx, **over) -> str:
    got = _define(ctx, _model(ctx), **over)
    if got.status_code >= 400:
        raise AssertionError(f"could not define a monitor: {got.text[:180]}")
    return got.json()["id"]


@case("QA-AM-200", "Define with cadence_days: 0")
def am_200(ctx: Ctx) -> Result:
    """Either refused, or accepted and honestly due for ever. What must not
    happen is a monitor that silently never comes due."""
    got = _define(ctx, _model(ctx), cadence_days=0)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    return PASS, f"accepted; cadence_days={got.json().get('cadence_days')}"


@case("QA-AM-205", "Set a monitor's status to something that is not a status")
def am_205(ctx: Ctx) -> Result:
    monitor_id = _defined(ctx)
    return expect_refused(
        ctx.api.post(f"/api/v1/monitors/{monitor_id}/status",
                     json={"status": "banana"}),
        "unknown_status", "validation_error", "not_found")


@case("QA-AM-611", "Define with a negative threshold")
def am_210(ctx: Ctx) -> Result:
    got = _define(ctx, _model(ctx), threshold={"max": -1.0})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return PASS, (f"answered {got.status_code} "
                  f"({code_of(got) or 'accepted'})")


@case("QA-AM-5207", "Define a monitor of an unknown kind")
def am_211(ctx: Ctx) -> Result:
    return expect_refused(_define(ctx, _model(ctx), kind="vibes"),
                          "unknown_kind", "validation_error",
                          "validation_refused", "kind_not_answerable")


@case("QA-AM-612", "Define against a model that does not exist")
def am_212(ctx: Ctx) -> Result:
    return expect_refused(_define(ctx, "maya://model/qa.never"),
                          "registry_refused", "not_found")


@case("QA-AM-613", "Define with no owner")
def am_213(ctx: Ctx) -> Result:
    return expect_refused(_define(ctx, _model(ctx), owner="  "),
                          "validation_error", "owner_required",
                          "validation_refused", "monitor_refused")


@case("QA-AM-5208", "A valid monitor is accepted")
def am_214(ctx: Ctx) -> Result:
    return expect_accepted(_define(ctx, _model(ctx)), status=201)


@case("QA-AM-614", "Ingest an observation with no computed_by")
def am_215(ctx: Ctx) -> Result:
    """Who computed a number is the difference between a measurement and an
    assertion."""
    monitor_id = _defined(ctx)
    return expect_refused(
        ctx.api.post(f"/api/v1/monitors/{monitor_id}/ingest",
                     json={"value": 0.01, "window_start": 0.0,
                           "window_end": 1.0, "computed_by": "  "}),
        "validation_error", "computed_by_required", "monitor_refused",
        "validation_refused")


@case("QA-AM-615", "Ingest a window that ends before it starts")
def am_216(ctx: Ctx) -> Result:
    monitor_id = _defined(ctx)
    got = ctx.api.post(f"/api/v1/monitors/{monitor_id}/ingest",
                       json={"value": 0.01, "window_start": 100.0,
                             "window_end": 1.0, "computed_by": "qa", "sample_size": 5000})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a window ending before it starts was accepted; every "
                      "later query over that window returns nothing and reads "
                      "as no breach")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-5209", "Ingest against a monitor that does not exist")
def am_217(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post("/api/v1/monitors/qa-never/ingest",
                     json={"value": 0.01, "window_start": 0.0,
                           "window_end": 1.0, "computed_by": "qa", "sample_size": 5000}),
        "no_monitor", "not_found", "unknown_monitor")


@case("QA-AM-616", "An observation inside the threshold does not breach")
def am_218(ctx: Ctx) -> Result:
    monitor_id = _defined(ctx, threshold=DRIFT)
    got = ctx.api.post(f"/api/v1/monitors/{monitor_id}/ingest",
                       json={"value": 0.01, "window_start": 0.0,
                             "window_end": 1.0, "computed_by": "qa", "sample_size": 5000})
    if got.status_code >= 400:
        return BLOCKED, got.text[:150]
    if got.json().get("breach"):
        return FAIL, "0.01 breached a threshold of 0.05"
    return PASS, "no breach, as expected"


@case("QA-AM-617", "An observation past the threshold breaches")
def am_219(ctx: Ctx) -> Result:
    """The other half. A monitor that never breaches is indistinguishable
    from a model that never misbehaves, and only one of those is common."""
    monitor_id = _defined(ctx, threshold=DRIFT)
    got = ctx.api.post(f"/api/v1/monitors/{monitor_id}/ingest",
                       json={"value": 0.9, "window_start": 0.0,
                             "window_end": 1.0, "computed_by": "qa", "sample_size": 5000})
    if got.status_code >= 400:
        return BLOCKED, got.text[:150]
    if not got.json().get("breach"):
        return FAIL, ("0.9 did not breach a threshold of 0.05 — the monitor "
                      "cannot report anything")
    return PASS, "breached"


@case("QA-AM-618", "Two identical observations are not two breaches")
def am_220(ctx: Ctx) -> Result:
    monitor_id = _defined(ctx, threshold=DRIFT)
    body = {"value": 0.9, "window_start": 0.0, "window_end": 1.0,
            "computed_by": "qa", "sample_size": 5000}
    ctx.api.post(f"/api/v1/monitors/{monitor_id}/ingest", json=body)
    ctx.api.post(f"/api/v1/monitors/{monitor_id}/ingest", json=body)
    # Observations are read from the monitor, not from a `/breaches`
    # collection — there is no such route.
    seen = ctx.api.get(f"/api/v1/monitors/{monitor_id}/observations")
    if seen.status_code >= 400:
        return BLOCKED, f"cannot read observations: {seen.status_code}"
    body = seen.json()
    rows = [o for o in body.get("observations", body.get("rows", []))
            if o.get("breach")]
    if len(rows) > 1:
        return FAIL, (f"the same window ingested twice produced {len(rows)} "
                      f"breaches; one condition counted twice is two owners' "
                      f"worth of work for one problem")
    return PASS, f"{len(rows)} breach for the same window twice"
