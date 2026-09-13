"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — numbers computed somewhere else.

**The verdict is still ours.** Whoever produced the value does not get to say
whether it breached: the threshold is this firm's and the comparison happens
here. `IngestIn` has no `passed` field and deliberately no parameter for one —
an external system that could mark its own homework is the failure mode every
*push your metrics to us* API has, and the absence of that field is the
control.

The honest half is the provenance. MAYA does not hold the population an
external number was computed over, so it cannot be replayed — the value is
the register's record of what was ASSERTED, and the assurance behind it is
the asserting system's. An estate where most numbers cannot be replayed is a
finding about the programme, and one that is invisible if the two kinds of
number print the same.
"""
from __future__ import annotations

import time

from qa.regression_suite.harness import ADMIN
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

MON = "/api/v1/monitors"
M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}
FITTED = {"parameter_kind": "estimated_coefficients",
          "fit_procedure": "estimate", "runtime": "estimator",
          "input_schema": [{"name": "x", "dtype": "float"}],
          "output_schema": [{"name": "score", "dtype": "float"}]}
DAY = 86400.0


def _service(ctx: Ctx):
    """`monitor:observe` is a SERVICE permission and no human role holds it —
    the party a monitor judges must not also supply the number it is judged
    on. So an ingesting caller is minted as a service principal."""
    who = ctx.unique("svc")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": ["service"], "kind": "service",
                              "password": f"{who}-password",
                              "legal_entities": [], "domains": []},
                        auth=ADMIN)
    return (who, f"{who}-password") if made.status_code < 400 else None


def _monitor(ctx: Ctx, **over) -> tuple:
    name = ctx.unique("ex")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE})
    ctx.api.post(f"{M}/{name}/versions",
                 json={"semver": "1.0.0", "kernel": dict(FITTED)},
                 auth=ctx.people["developer"])
    body = {"urn": urn, "name": ctx.unique("mon"), "kind": "performance",
            "test_key": "discrimination.auc", "threshold": {"min": 0.6},
            "owner": "person/owner", "reference": {}, "slice": {},
            "cadence_days": 1.0, "label_delay_days": 30.0,
            "breach_severity": "Medium", "escalate_after": 3}
    body.update(over)
    made = ctx.api.post(MON, json=body, auth=ctx.people["owner"])
    return ((made.json() or {}).get("id", "") if made.status_code < 400
            else ""), urn


def _ingest(ctx: Ctx, monitor_id: str, who, **over):
    now = time.time()
    body = {"value": 0.72, "computed_by": "risk-analytics-cluster",
            "method": "spark 3.5, nightly job", "sample_size": 12_000,
            "window_start": now - 30 * DAY, "window_end": now}
    body.update(over)
    return ctx.api.post(f"{MON}/{monitor_id}/ingest", json=body, auth=who)


@case("QA-AM-245", "Ingest a result carrying a `passed` field")
def am_245(ctx: Ctx) -> Result:
    """The control is the absence of the field. A caller who sends one anyway
    must not have it read — an external system marking its own homework is
    the failure mode this whole endpoint is shaped against."""
    who = _service(ctx)
    if who is None:
        return BLOCKED, "the service principal could not be created"
    monitor_id, _urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    # 0.42 against a floor of 0.6 fails. The caller claims it passed.
    got = _ingest(ctx, monitor_id, who, value=0.42, passed=True)
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' — an unknown field is not "
                      f"quietly dropped")
    body = got.json() or {}
    observation = body.get("observation") or body
    if observation.get("passed"):
        return FAIL, ("a caller sent `passed: true` with a value below the "
                      "firm's floor and the observation records it as passed: "
                      "the external system marked its own homework")
    return PASS, "the claimed `passed` is ignored and the verdict computed here"


@case("QA-AM-246", "Ingest with no `computed_by`")
def am_246(ctx: Ctx) -> Result:
    """A number of unknown origin in the system of record is worse than no
    number, because it looks like one MAYA stands behind."""
    who = _service(ctx)
    if who is None:
        return BLOCKED, "the service principal could not be created"
    monitor_id, _urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    got = _ingest(ctx, monitor_id, who, computed_by="   ")
    outcome = refused_by_the_control(
        got, "a number was ingested naming nothing that computed it")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "computed_by_required":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'computed_by_required' on whitespace"


@case("QA-AM-247", "Ingest with no window")
def am_247(ctx: Ctx) -> Result:
    """Without a window the observation cannot be paired against anything,
    compared over time, or read as-at a date."""
    who = _service(ctx)
    if who is None:
        return BLOCKED, "the service principal could not be created"
    monitor_id, _urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    got = _ingest(ctx, monitor_id, who, window_start=None, window_end=None)
    outcome = refused_by_the_control(got, "an observation covering no window")
    if outcome[0] is not PASS:
        return outcome
    # `IngestIn.window_start` is a required float, so the body schema refuses
    # before the service does. Both layers are worth having and both are
    # checked: the service's own `window_required` is what an in-process
    # caller meets, and it must not have become unreachable code.
    engine = ctx.ui.app.state.ctx.get("external_monitoring")
    if engine is None:
        return BLOCKED, "no external monitoring engine is wired"
    try:
        engine.ingest(monitor_id, 0.72, "risk-analytics-cluster",
                      window_start=None, window_end=None)
    except Exception as exc:
        if "window_required" not in f"{getattr(exc, 'code', '')}{exc}":
            return FAIL, (f"the service refuses a windowless observation for "
                          f"some other reason: {exc}")
        return PASS, (f"the body schema refuses first ('{code_of(got)}') and "
                      f"the service's own 'window_required' still stands "
                      f"behind it")
    return FAIL, ("the body schema refuses a windowless observation and the "
                  "service accepts one, so an in-process caller stores an "
                  "observation that cannot be paired, compared or read as-at")


@case("QA-AM-248", "Ingest with `window_end` before `window_start`")
def am_248(ctx: Ctx) -> Result:
    """An inverted window is the ordinary shape of a timezone mistake, and it
    would sort into the history in the wrong place for ever."""
    who = _service(ctx)
    if who is None:
        return BLOCKED, "the service principal could not be created"
    monitor_id, _urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    now = time.time()
    got = _ingest(ctx, monitor_id, who, window_start=now,
                  window_end=now - 30 * DAY)
    outcome = refused_by_the_control(got, "an observation over an inverted window")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "window_inverted":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'window_inverted'"


@case("QA-AM-250", "Ingest a null value")
def am_250(ctx: Ctx) -> Result:
    """*Not computable on this sample* is a real answer and must be
    recordable — but it is not a pass. A null that passed would let an
    external job report nothing and read as healthy."""
    who = _service(ctx)
    if who is None:
        return BLOCKED, "the service principal could not be created"
    monitor_id, _urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    got = _ingest(ctx, monitor_id, who, value=None)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — an external job that could "
                      f"not compute the metric has no way to say so")
    body = got.json() or {}
    observation = body.get("observation") or body
    if observation.get("passed"):
        return FAIL, ("a null value is recorded as passed, so an external job "
                      "reporting nothing reads as a healthy model")
    detail = (observation.get("detail") or "").lower()
    if "not computable" not in detail:
        return FAIL, f"recorded as failed without saying why: {detail[:120]}"
    return PASS, "recorded, not passed, and said to be not computable"


@case("QA-AM-251", "Ingest with `sample_size: 0`")
def am_251(ctx: Ctx) -> Result:
    """EXPLORATORY. A metric over no rows is not a metric, and the sample
    size is part of the digest — so a zero either means *the external job did
    not say* or *it computed an AUC over nothing*, and those are different
    facts the register cannot tell apart."""
    who = _service(ctx)
    if who is None:
        return BLOCKED, "the service principal could not be created"
    monitor_id, _urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    got = _ingest(ctx, monitor_id, who, sample_size=0)
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' — a number over no rows is "
                      f"not a number")
    body = got.json() or {}
    observation = body.get("observation") or body
    detail = (observation.get("detail") or "")
    if "sample" in detail.lower() or "0" in str(observation.get("sample_size")):
        if observation.get("sample_size") == 0 and "sample" not in detail.lower():
            return FAIL, ("an AUC over a stated sample of 0 was accepted and "
                          "the observation says nothing about it: `sample_size` "
                          "defaults to 0, so *the job did not say* and *it "
                          "computed this over nothing* are the same row")
    return PASS, f"accepted, sample_size {observation.get('sample_size')}"


@case("QA-AM-252", "Ingest to a paused monitor")
def am_252(ctx: Ctx) -> Result:
    """A result for a paused monitor is a number against a question this firm
    has stopped asking — and it would move `last_evaluated_at`, so the
    monitor would read as running while paused."""
    who = _service(ctx)
    if who is None:
        return BLOCKED, "the service principal could not be created"
    monitor_id, _urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    # `status` is a QUERY parameter on this route, not a body field.
    paused = ctx.api.post(f"{MON}/{monitor_id}/status?status=paused",
                          auth=ctx.people["owner"])
    if paused.status_code >= 400:
        return BLOCKED, f"the monitor could not be paused: {paused.text[:140]}"
    got = _ingest(ctx, monitor_id, who)
    outcome = refused_by_the_control(got, "a result was ingested to a paused monitor")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "monitor_inactive":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'monitor_inactive'"


@case("QA-AM-255",
      "Provenance for a monitor that has never been evaluated by anybody")
def am_255(ctx: Ctx) -> Result:
    """Never evaluated is not the same as evaluated and clean, and the
    provenance reading is where the two have to be told apart."""
    monitor_id, _urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    got = ctx.api.get(f"/api/v1/monitoring-provenance?monitor_id={monitor_id}",
                      auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the provenance read answered {got.status_code}"
    body = got.json() or {}
    if body.get("observations") != 0:
        return FAIL, f"a fresh monitor reports {body.get('observations')}"
    if "never been evaluated" not in (body.get("detail") or ""):
        return FAIL, (f"an unevaluated monitor's provenance reads "
                      f"'{body.get('detail')}', which does not distinguish it "
                      f"from one evaluated and clean")
    return PASS, "'this monitor has never been evaluated by anybody'"


@case("QA-AM-256",
      "Estate provenance where 80% of observations are external")
def am_256(ctx: Ctx) -> Result:
    """The number that is a finding about the programme. It has to state the
    SHARE and say that those numbers cannot be reproduced — a count of
    observations with no split reads as coverage."""
    who = _service(ctx)
    if who is None:
        return BLOCKED, "the service principal could not be created"
    monitor_id, _urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    for _ in range(4):
        if _ingest(ctx, monitor_id, who).status_code >= 400:
            return BLOCKED, "an ingest failed"
    got = ctx.api.get("/api/v1/monitoring-provenance", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the estate provenance answered {got.status_code}"
    body = got.json() or {}
    if not body.get("external"):
        return FAIL, "the estate view counts no external observations"
    detail = body.get("detail") or ""
    if "%" not in detail:
        return FAIL, (f"the estate view gives no share, only counts, so an "
                      f"estate that cannot reproduce its own monitoring reads "
                      f"the same as one that can: {detail[:130]}")
    if "cannot be reproduced" not in detail and "cannot be replayed" not in detail:
        return FAIL, f"the share is stated without what it costs: {detail[:130]}"
    if "risk-analytics-cluster" not in f"{body.get('systems')}":
        return FAIL, "the systems that computed the numbers are not named"
    return PASS, f"{body['external']} external, and the share is stated"


@case("QA-AM-4710",
      "An ingested breach opens a breach and a finding, like any other")
def am_4710(ctx: Ctx) -> Result:
    """Taking the number and not acting on it would be filing it rather than
    monitoring with it. An external number that breaches has to do everything
    an internal one does, or *push your metrics to us* becomes a way of
    switching the consequences off."""
    who = _service(ctx)
    if who is None:
        return BLOCKED, "the service principal could not be created"
    monitor_id, urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    got = _ingest(ctx, monitor_id, who, value=0.31)
    if got.status_code >= 400:
        return BLOCKED, f"the ingest failed: {got.text[:140]}"
    body = got.json() or {}
    observation = body.get("observation") or body
    if observation.get("passed"):
        return FAIL, "0.31 against a floor of 0.6 was judged as passing"
    breaches = ctx.api.get(f"/api/v1/breaches?urn={urn}",
                           auth=ctx.people["risk"])
    opened = (breaches.json() or {}).get("breaches") or [] \
        if breaches.status_code < 400 else []
    if not opened:
        opened = [b for b in ((body.get("breach") and [body["breach"]]) or [])]
    if not opened:
        return FAIL, ("an external number below the firm's floor was recorded "
                      "and opened no breach, so ingesting a metric is a way "
                      "of reporting a failure with none of its consequences")
    found = ctx.api.get(f"/api/v1/findings?urn={urn}", auth=ctx.people["risk"])
    rows = (found.json() or {}).get("open") or [] \
        if found.status_code < 400 else []
    if not rows:
        return FAIL, "a breach opened and no finding was raised against it"
    return PASS, f"{len(opened)} breach(es) and {len(rows)} finding(s)"
