"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — evaluating a monitor, and what a breach does.

Two ideas carry this module. **A cohort has to have matured**: a performance
monitor compares predictions to outcomes, and measuring before the outcome
window closes measures whichever rows happened to resolve early — which is
never a random sample. And **the window is read at the moment it names**, not
the moment the read happens, so a review of last quarter sees the population
last quarter saw rather than everything that has arrived since.

The permission split matters as much as the arithmetic. `monitor:evaluate`
reaches a verdict; `monitor:observe` delivers the rows. Authorising the
evaluation against the delivery permission would let whoever supplies the
population also rule on it, and no human role holds `monitor:observe` at all.
"""
from __future__ import annotations

import time

from qa.regression_suite.harness import ADMIN
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

MON = "/api/v1/monitors"
M = "/api/v1/models"
T = "/api/v1/telemetry"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}
FITTED = {"parameter_kind": "estimated_coefficients",
          "fit_procedure": "estimate", "runtime": "estimator",
          "input_schema": [{"name": "x", "dtype": "float"}],
          "output_schema": [{"name": "score", "dtype": "float"}]}
DAY = 86400.0
DELAY = 30.0


def _service(ctx: Ctx):
    who = ctx.unique("svc")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": ["service"], "kind": "service",
                              "password": f"{who}-password",
                              "legal_entities": [], "domains": []},
                        auth=ADMIN)
    return (who, f"{who}-password") if made.status_code < 400 else None


def _monitor(ctx: Ctx, *, bind: bool = True, **over) -> tuple:
    name = ctx.unique("ev")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE})
    ctx.api.post(f"{M}/{name}/versions",
                 json={"semver": "1.0.0", "kernel": dict(FITTED)},
                 auth=ctx.people["developer"])
    # `bind` is a parameter this fixture cannot honour: `MonitorIn` carries no
    # version field and the route never passes `model_version_id`, so every
    # monitor created through the API is unbound. QA-AM-4720 is the case.
    del bind
    body = {"urn": urn, "name": ctx.unique("mon"), "kind": "performance",
            "test_key": "discrimination.auc", "threshold": {"min": 0.6},
            "owner": "person/owner", "reference": {}, "slice": {},
            "cadence_days": 1.0, "label_delay_days": DELAY,
            "breach_severity": "Medium", "escalate_after": 3}
    body.update(over)
    got = ctx.api.post(MON, json=body, auth=ctx.people["owner"])
    return ((got.json() or {}).get("id", "") if got.status_code < 400 else ""), urn


def _rows(n: int, *, age_days: float, labelled: bool = True) -> list:
    now = time.time()
    out = []
    for i in range(n):
        row = {"scored_at": now - age_days * DAY, "score": (i % 10) / 10.0}
        if labelled:
            row["label"] = 1 if i % 2 else 0
        out.append(row)
    return out


def _evaluate(ctx: Ctx, monitor_id: str, rows, **over):
    body = {"rows": rows, "reference": None, "now": None}
    body.update(over)
    return ctx.api.post(f"{MON}/{monitor_id}/evaluate", json=body,
                        auth=ctx.people["owner"])


@case("QA-AM-207",
      "Evaluate a `performance` monitor over a cohort where nothing has "
      "matured")
def am_207(ctx: Ctx) -> Result:
    """Measuring before the outcome window closes measures whichever rows
    resolved early, which is never a random sample. The remediation has to
    name WHEN, or the caller retries tomorrow and every day after."""
    monitor_id, _urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    got = _evaluate(ctx, monitor_id, _rows(40, age_days=1.0))
    outcome = refused_by_the_control(
        got, "a performance monitor was evaluated over an immature cohort")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "cohort_immature":
        return FAIL, f"refused '{code_of(got)}'"
    body = got.json() or {}
    remediation = f"{body.get('remediation') or body.get('detail') or ''}"
    if not any(ch.isdigit() for ch in remediation):
        return FAIL, (f"the refusal does not say when the cohort matures, so "
                      f"the caller retries daily: {remediation[:120]}")
    return PASS, "refused 'cohort_immature', naming the maturity date"


@case("QA-AM-208",
      "Evaluate over a cohort where 20 of 70 rows have matured")
def am_208(ctx: Ctx) -> Result:
    """The metric is computed over the matured part and the detail says so.
    A number over 20 rows presented as a number over 70 is the failure this
    split exists to prevent."""
    monitor_id, _urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    rows = _rows(20, age_days=DELAY + 5) + _rows(50, age_days=1.0)
    got = _evaluate(ctx, monitor_id, rows)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' with 20 rows matured, so a "
                      f"partly mature cohort cannot be measured at all")
    body = got.json() or {}
    observation = body.get("observation") or body
    if observation.get("sample") not in (20, None):
        return FAIL, (f"the observation reports a sample of "
                      f"{observation.get('sample')} over a cohort where 20 of "
                      f"70 rows have matured")
    note = f"{observation.get('note') or observation.get('detail') or ''}"
    if "20" not in note and "70" not in note:
        return FAIL, (f"the detail does not say how much of the cohort was "
                      f"measured: {note[:130]}")
    return PASS, "measured over the matured part, and the detail says so"


@case("QA-AM-209",
      "Evaluate over a cohort where exactly one row has matured")
def am_209(ctx: Ctx) -> Result:
    """One matured row is a cohort of one. Whatever the metric does with it,
    the observation must not present it as a measurement of the population —
    an AUC over one row is not computable, and that is the honest answer."""
    monitor_id, _urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    rows = _rows(1, age_days=DELAY + 5) + _rows(60, age_days=1.0)
    got = _evaluate(ctx, monitor_id, rows)
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' — a cohort of one is not a "
                      f"cohort")
    body = got.json() or {}
    observation = body.get("observation") or body
    if observation.get("value") is not None and observation.get("passed"):
        return FAIL, (f"an AUC of {observation.get('value')} over ONE matured "
                      f"row was recorded as passing, so a monitor reads clean "
                      f"on a sample that cannot discriminate anything")
    return PASS, (f"one matured row, value {observation.get('value')!r}, "
                  f"passed={observation.get('passed')}")


@case("QA-AM-210",
      "Evaluate over a partly mature cohort where every mature row carries "
      "the same label")
def am_210(ctx: Ctx) -> Result:
    """AUC is undefined when either class is absent — there is nothing to
    discriminate between. The value is null and `passed` is FALSE, which is
    the important half: absent evidence is not evidence of compliance."""
    monitor_id, _urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    now = time.time()
    mature = [{"scored_at": now - (DELAY + 5) * DAY, "score": i / 20.0,
               "label": 1} for i in range(20)]
    got = _evaluate(ctx, monitor_id, mature + _rows(40, age_days=1.0))
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' — a single-class cohort is "
                      f"refused rather than recorded")
    body = got.json() or {}
    observation = body.get("observation") or body
    if observation.get("value") is not None:
        return FAIL, (f"an AUC of {observation.get('value')} was computed over "
                      f"a cohort with one class present")
    if observation.get("passed"):
        return FAIL, ("a not-computable result was recorded as PASSED: absent "
                      "evidence is being read as evidence of compliance")
    return PASS, "value null, passed false"


@case("QA-AM-222", "Evaluate the same rows twice")
def am_222(ctx: Ctx) -> Result:
    """Two evaluations of one population are two observations, and if both
    breach they are two breaches — which is right, because the monitor was
    run twice, and wrong only if the second one escalates as though the
    problem had persisted through a cadence."""
    monitor_id, _urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    now = time.time()
    rows = [{"scored_at": now - (DELAY + 5) * DAY, "score": 0.5,
             "label": i % 2} for i in range(40)]
    first = _evaluate(ctx, monitor_id, rows)
    if first.status_code >= 400:
        return BLOCKED, f"the first evaluation failed: {first.text[:140]}"
    second = _evaluate(ctx, monitor_id, rows)
    if second.status_code >= 400:
        return PASS, (f"the second evaluation is refused '{code_of(second)}' "
                      f"— one population, one observation")
    got = ctx.api.get(f"{MON}/{monitor_id}/observations",
                      auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the history answered {got.status_code}"
    body = got.json() or {}
    observations = body.get("observations") or []
    breaches = body.get("breaches") or []
    if len(observations) != 2:
        return FAIL, f"two evaluations left {len(observations)} observation(s)"
    severities = {b.get("severity") for b in breaches}
    if len(breaches) > 1 and len(severities) > 1:
        return FAIL, (f"re-running the same rows escalated the breach "
                      f"({sorted(severities)}): the severity rises because "
                      f"the monitor was run twice, not because the problem "
                      f"persisted")
    return PASS, (f"{len(observations)} observations, {len(breaches)} "
                  f"breach(es), severity {sorted(severities) or 'none'}")


@case("QA-AM-223", "Evaluate from telemetry with no rows in the window")
def am_223(ctx: Ctx) -> Result:
    """An empty window is not a clean model. Returning a number over nothing
    would be the worst available answer, and returning nothing silently is
    the second worst."""
    monitor_id, _urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    now = time.time()
    got = ctx.api.post(f"{MON}/{monitor_id}/evaluate-from-telemetry",
                       json={"since": now - DAY, "until": now},
                       auth=ctx.people["owner"])
    outcome = refused_by_the_control(
        got, "a monitor was evaluated over a window holding no telemetry")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) == "monitor_has_no_version":
        return BLOCKED, ("the monitor names no version, so the read never "
                         "reaches the window at all — nothing binds one "
                         "through the API, see QA-AM-4720")
    if code_of(got) not in ("no_telemetry_in_window", "no_telemetry"):
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-AM-227",
      "Evaluate from telemetry on a monitor bound to no version")
def am_227(ctx: Ctx) -> Result:
    """A monitor with no version has no telemetry stream to read. Falling
    back to *the latest version* would silently change what is being watched
    every time somebody ships."""
    monitor_id, _urn = _monitor(ctx, bind=False)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    now = time.time()
    got = ctx.api.post(f"{MON}/{monitor_id}/evaluate-from-telemetry",
                       json={"since": now - 90 * DAY, "until": now},
                       auth=ctx.people["owner"])
    outcome = refused_by_the_control(
        got, "an unbound monitor was evaluated from telemetry")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "monitor_has_no_version":
        return FAIL, (f"refused '{code_of(got)}' — the refusal does not say "
                      f"the monitor names no version, so nobody knows what to "
                      f"fix")
    return PASS, "refused 'monitor_has_no_version'"


@case("QA-AM-229", "`monitor:observe` holder attempts to evaluate")
def am_229(ctx: Ctx) -> Result:
    """Evaluating is not observing. Authorising the verdict against the
    delivery permission would let whoever supplies the rows also rule on
    them — which is the party the monitor exists to judge."""
    who = _service(ctx)
    if who is None:
        return BLOCKED, "the service principal could not be created"
    monitor_id, _urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    got = ctx.api.post(f"{MON}/{monitor_id}/evaluate",
                       json={"rows": _rows(40, age_days=DELAY + 5)},
                       auth=who)
    if got.status_code < 400:
        return FAIL, ("a principal holding only the delivery permission "
                      "reached a verdict, so whoever supplies the population "
                      "can rule on it")
    if code_of(got) not in ("forbidden", "unauthorised"):
        return FAIL, f"refused '{code_of(got)}' rather than on the permission"
    return PASS, f"refused '{code_of(got)}' — observing is not evaluating"


@case("QA-AM-230", "`monitor:evaluate` holder attempts to post telemetry")
def am_230(ctx: Ctx) -> Result:
    """The other direction, and the one that matters more: the owner is the
    party the monitor judges, so an owner who could supply the telemetry
    would be marking their own work."""
    monitor_id, urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    got = ctx.api.post(f"{T}",
                       json={"urn": urn, "semver": "1.0.0",
                             "stream": "scores",
                             "rows": _rows(10, age_days=1.0),
                             "sample_rate": 1.0, "source": "qa"},
                       auth=ctx.people["owner"])
    if got.status_code < 400:
        return FAIL, ("the model owner supplied the population their own "
                      "monitor is judged on, so the party being judged is "
                      "also the party reporting")
    if code_of(got) not in ("forbidden", "unauthorised"):
        return FAIL, f"refused '{code_of(got)}' rather than on the permission"
    return PASS, f"refused '{code_of(got)}' — evaluating is not delivering"


@case("QA-AM-4720",
      "Bind a monitor to a model version through the API")
def am_4720(ctx: Ctx) -> Result:
    """`evaluate_from_telemetry` reads `monitor["model_version_id"]` to work
    out which stream to read, and refuses `monitor_has_no_version` without
    one. Nothing sets it. `MonitorIn` carries no version field, the create
    route never passes `model_version_id`, and `MonitoringDefaults.seed` does
    not pass it either — so every monitor in an estate built through the API
    is unbound and the whole telemetry-driven evaluation path is unreachable.

    The recurring shape once more: a control that is built, wired, routed and
    documented, and cannot run.
    """
    monitor_id, urn = _monitor(ctx)
    if not monitor_id:
        return BLOCKED, "the monitor could not be defined"
    got = ctx.api.get(f"{MON}?urn={urn}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the monitor list answered {got.status_code}"
    # `GET /monitors` answers a STATUS reading: `monitors` is a count and the
    # rows live under `detail`. Reading `monitors` as a list iterates an int.
    rows = [m for m in ((got.json() or {}).get("detail") or [])
            if m.get("id") == monitor_id]
    if not rows:
        return BLOCKED, "the monitor is not in the list"
    if rows[0].get("model_version_id"):
        return PASS, (f"the monitor is bound to version "
                      f"{rows[0]['model_version_id']}")
    # Seeding the defaults is the other creation path; if IT binds, the gap is
    # only in the explicit one.
    seeded = ctx.api.post(f"/api/v1/monitor-defaults?urn={urn}",
                          auth=ctx.people["owner"])
    made = (seeded.json() or {}).get("created") or [] \
        if seeded.status_code < 400 else []
    if any(m.get("model_version_id") for m in made):
        return FAIL, ("seeding the defaults binds a monitor to a version and "
                      "defining one explicitly does not, so which creation "
                      "path was used decides whether the monitor can ever be "
                      "evaluated from telemetry")
    return FAIL, (f"no route binds a monitor to a version: `MonitorIn` has no "
                  f"version field, the create route never passes "
                  f"`model_version_id`, and seeding the defaults created "
                  f"{len(made)} monitor(s) with none either. "
                  f"`evaluate_from_telemetry` reads that column to find the "
                  f"stream, so it refuses `monitor_has_no_version` for every "
                  f"monitor in the estate and the telemetry-driven evaluation "
                  f"path cannot be reached at all")
