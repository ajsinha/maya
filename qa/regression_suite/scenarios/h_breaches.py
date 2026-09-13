"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — breaches, escalation and recovery.

One breach is a data point; a run of them is a condition. The cases here walk
the run: what the third consecutive breach is worth, what the sixth is, what a
single passing evaluation does to the count, and — the one that matters most —
what recovery does NOT undo.
"""
from __future__ import annotations

import time

from core.monitoring.common import ADMISSIBLE_TESTS, INPUT_DRIFT
from core.monitoring.breaches import BreachRegister
from core.validation import SEVERITIES
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case,
                                                  refused_by_the_control)

MON = "/api/v1/monitors"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
DAY = 86400.0
#: A reference and a current sample nothing like it, so PSI is large.
REFERENCE = [float(n) for n in range(200)]
DRIFTED = [float(n) + 10_000.0 for n in range(200)]


def _monitor(ctx: Ctx, **over):
    name = ctx.unique("br")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **TIER})
    body = {"urn": urn, "name": f"{name}-monitor", "kind": INPUT_DRIFT,
            "test_key": ADMISSIBLE_TESTS[INPUT_DRIFT][0], "owner": "owner",
            "threshold": {"max": 0.1}, "breach_severity": "Medium",
            "escalate_after": 3,
            "reference": {"sample": REFERENCE, "bins": 10}}
    body.update(over)
    made = ctx.api.post(MON, json=body, auth=ctx.people["risk"])
    return (made.json().get("id") if made.status_code < 400 else ""), urn


def _rows(values):
    now = time.time()
    return [{"scored_at": now - 60, "score": v} for v in values]


def _evaluate(ctx: Ctx, mid: str, values):
    return ctx.api.post(f"{MON}/{mid}/evaluate",
                        json={"rows": _rows(values)}, auth=ctx.people["owner"])


def _breach_register(ctx: Ctx):
    """The breach register, which hangs off the monitoring service rather
    than sitting in the context under its own key, and has no HTTP route."""
    monitoring = ctx.ui.app.state.ctx.get("monitoring")
    return getattr(monitoring, "breaches", None)


def _findings(ctx: Ctx, urn: str) -> list:
    got = ctx.api.get(f"/api/v1/findings?urn={urn}", auth=ctx.people["risk"])
    return (got.json().get("open") or []) if got.status_code < 400 else []


@case("QA-AM-213", "Evaluate a paused monitor")
def am_213(ctx: Ctx) -> Result:
    mid, _ = _monitor(ctx)
    if not mid:
        return BLOCKED, "the monitor could not be defined"
    # `status` is a query parameter on POST /status, not a field on create
    # and not a body — a monitor cannot be born paused.
    paused = ctx.api.post(f"{MON}/{mid}/status?status=paused",
                          auth=ctx.people["risk"])
    if paused.status_code >= 400:
        return BLOCKED, f"could not pause: {paused.text[:140]}"
    return refused_by_the_control(
        _evaluate(ctx, mid, DRIFTED),
        "a paused monitor was evaluated, so a monitor somebody deliberately "
        "stopped went on producing observations")


@case("QA-AM-212", "Evaluate a drift monitor with no reference anywhere")
def am_212(ctx: Ctx) -> Result:
    """Measuring each night against that night's own data makes the series
    mean nothing."""
    mid, _ = _monitor(ctx, reference={})
    if not mid:
        return PASS, "a drift monitor with no reference cannot be defined"
    return refused_by_the_control(
        _evaluate(ctx, mid, DRIFTED),
        "a drift monitor with no reference produced a number, which can only "
        "be a comparison against the data being measured")


@case("QA-AM-1800", "The first breach carries the monitor's own severity")
def am_1800(ctx: Ctx) -> Result:
    mid, urn = _monitor(ctx)
    if not mid:
        return BLOCKED, "the monitor could not be defined"
    got = _evaluate(ctx, mid, DRIFTED)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    raised = [f for f in _findings(ctx, urn) if f.get("source") == "monitoring"]
    if not raised:
        return FAIL, "a breach raised no finding"
    if raised[0].get("severity") != "Medium":
        return FAIL, (f"the first breach was raised {raised[0].get('severity')}"
                      f", not the monitor's declared Medium")
    return PASS, "first breach at the monitor's own severity"


@case("QA-AM-215", "The third consecutive breach with escalate_after 3")
def am_215(ctx: Ctx) -> Result:
    """Severity rises by one level each time the run reaches a multiple of
    the threshold."""
    mid, urn = _monitor(ctx)
    if not mid:
        return BLOCKED, "the monitor could not be defined"
    for n in range(3):
        got = _evaluate(ctx, mid, DRIFTED)
        if got.status_code >= 400:
            return BLOCKED, f"evaluation {n}: {got.text[:140]}"
    raised = [f for f in _findings(ctx, urn) if f.get("source") == "monitoring"]
    worst = min((SEVERITIES.index(f["severity"]) for f in raised), default=None)
    if worst is None:
        return FAIL, "three breaches raised no finding"
    if SEVERITIES[worst] != "High":
        return FAIL, (f"the third consecutive breach was raised "
                      f"{SEVERITIES[worst]}, not High; a run of three is a "
                      f"condition rather than three data points")
    return PASS, "third consecutive breach escalated Medium -> High"


@case("QA-AM-216", "The sixth consecutive breach")
def am_216(ctx: Ctx) -> Result:
    """Two multiples of the threshold, two steps, and it stops at Critical."""
    mid, urn = _monitor(ctx)
    if not mid:
        return BLOCKED, "the monitor could not be defined"
    for n in range(6):
        if _evaluate(ctx, mid, DRIFTED).status_code >= 400:
            return BLOCKED, f"evaluation {n} failed"
    raised = [f for f in _findings(ctx, urn) if f.get("source") == "monitoring"]
    worst = min((SEVERITIES.index(f["severity"]) for f in raised), default=None)
    if worst is None:
        return FAIL, "six breaches raised no finding"
    if SEVERITIES[worst] != "Critical":
        return FAIL, (f"the sixth consecutive breach reached "
                      f"{SEVERITIES[worst]}, not Critical")
    return PASS, "sixth consecutive breach at Critical"


@case("QA-AM-1801", "Escalation stops at Critical")
def am_1801(ctx: Ctx) -> Result:
    """`severity_rank(base) - steps` is clamped at zero, so a very long run
    cannot walk off the end of the vocabulary."""
    reached = BreachRegister.escalate("Medium", 300, 3)
    if reached != SEVERITIES[0]:
        return FAIL, (f"a run of 300 reached '{reached}', not "
                      f"'{SEVERITIES[0]}'")
    return PASS, f"a run of 300 stops at {reached}"


@case("QA-AM-1802", "escalate_after of zero does not escalate")
def am_1802(ctx: Ctx) -> Result:
    """Zero would be a division by zero and, read the other way, escalation
    on every single breach. Neither is what "do not escalate" should mean."""
    reached = BreachRegister.escalate("Medium", 50, 0)
    if reached != "Medium":
        return FAIL, f"escalate_after 0 escalated to '{reached}'"
    return PASS, "escalate_after 0 holds the base severity"


@case("QA-AM-218", "A passing evaluation restarts the consecutive count")
def am_218(ctx: Ctx) -> Result:
    """The run is what escalates, so a recovery in the middle must break it
    — otherwise a monitor that failed five times last year escalates on its
    first bad day this year."""
    mid, urn = _monitor(ctx)
    if not mid:
        return BLOCKED, "the monitor could not be defined"
    for _ in range(5):
        if _evaluate(ctx, mid, DRIFTED).status_code >= 400:
            return BLOCKED, "a breaching evaluation failed"
    recovered = _evaluate(ctx, mid, REFERENCE)
    if recovered.status_code >= 400:
        return BLOCKED, recovered.text[:170]
    if not (recovered.json() or {}).get("passed", True):
        return BLOCKED, "the recovering evaluation did not pass"
    if _evaluate(ctx, mid, DRIFTED).status_code >= 400:
        return BLOCKED, "the sixth evaluation failed"
    raised = [f for f in _findings(ctx, urn) if f.get("source") == "monitoring"]
    latest = max(raised, key=lambda f: f.get("raised_at") or 0, default=None)
    if latest is None:
        return FAIL, "no finding from the last breach"
    if latest["severity"] == "Critical":
        return FAIL, ("the breach after a recovery was raised Critical, so "
                      "the consecutive count carried across a passing "
                      "evaluation and the run never restarts")
    return PASS, f"the run restarted; the next breach is {latest['severity']}"


@case("QA-AM-219", "Recovery resolves the breach and leaves the finding open")
def am_219(ctx: Ctx) -> Result:
    """A metric coming back inside its threshold is not evidence that
    whatever moved it was understood. Closing the finding automatically would
    erase the obligation to find out."""
    mid, urn = _monitor(ctx)
    if not mid:
        return BLOCKED, "the monitor could not be defined"
    if _evaluate(ctx, mid, DRIFTED).status_code >= 400:
        return BLOCKED, "the breaching evaluation failed"
    before = [f for f in _findings(ctx, urn) if f.get("source") == "monitoring"]
    if not before:
        return BLOCKED, "the breach raised no finding"
    recovered = _evaluate(ctx, mid, REFERENCE)
    if recovered.status_code >= 400:
        return BLOCKED, recovered.text[:170]
    after = [f for f in _findings(ctx, urn) if f.get("source") == "monitoring"]
    if len(after) < len(before):
        return FAIL, ("recovering closed the finding, which erases the "
                      "obligation to find out what moved the metric")
    # There is no per-monitor breach route; the register is reached through
    # the application context.
    register = _breach_register(ctx)
    if register is not None:
        still_open = register.breaches.many(monitor_id=mid, status="open")
        if still_open:
            return FAIL, (f"{len(still_open)} breach(es) still open after the "
                          f"monitor recovered")
    return PASS, "the breach resolves; the finding stands"


@case("QA-AM-221", "Resolve breaches for a monitor with none open")
def am_221(ctx: Ctx) -> Result:
    """A passing evaluation on a monitor that never breached must not report
    a recovery that did not happen."""
    mid, urn = _monitor(ctx)
    if not mid:
        return BLOCKED, "the monitor could not be defined"
    got = _evaluate(ctx, mid, REFERENCE)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    resolved = body.get("resolved_breaches")
    if isinstance(resolved, list):
        resolved = len(resolved)
    if resolved:
        return FAIL, (f"a monitor with no open breach reported {resolved} "
                      f"resolved")
    if _findings(ctx, urn):
        return FAIL, "a passing evaluation raised a finding"
    return PASS, "nothing resolved, nothing raised"


@case("QA-AM-1803", "A breach names the observation it came from")
def am_1803(ctx: Ctx) -> Result:
    """A finding that says a monitor breached, without saying which
    evaluation, is one nobody can go back to."""
    mid, _ = _monitor(ctx)
    if not mid:
        return BLOCKED, "the monitor could not be defined"
    got = _evaluate(ctx, mid, DRIFTED)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    register = _breach_register(ctx)
    if register is None:
        return BLOCKED, "no breach register reachable from this run"
    rows = list(register.breaches.many(monitor_id=mid))
    if not rows:
        return FAIL, "the evaluation breached and recorded no breach"
    missing = [r for r in rows if not r.get("observation_id")
               or not r.get("finding_id")]
    if missing:
        return FAIL, (f"{len(missing)} breach(es) name no observation or no "
                      f"finding, so the trail from finding to number is broken")
    return PASS, f"{len(rows)} breach(es), each naming observation and finding"
