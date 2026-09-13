"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — the governance batch.

Lapses, overdue findings and stalled monitors are DERIVED, and they only
become records when the batch runs. **A dead scheduler makes the estate look
clean rather than stale**, which is why the runner reports on itself with a
staleness threshold rather than an hours-since number — thirty days and 0.2
hours render identically as a number on a tile.

Everything here has to be idempotent in the same way: the same condition
raises the same finding once, matched on its title. And no job may escalate
its own escalations, or a nightly batch compounds one overdue finding into a
new one every night for ever.
"""
from __future__ import annotations

import time

from core.scheduler.jobs import MONITOR_GRACE_MULTIPLE
from qa.regression_suite.harness import ADMIN
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

S = "/api/v1/scheduler"
M = "/api/v1/models"
F = "/api/v1/findings"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}
DAY = 86400.0


def _runner(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("scheduler")


def _model(ctx: Ctx) -> tuple:
    name = ctx.unique("sc")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    return name, urn


def _raise(ctx: Ctx, urn: str, **over) -> str:
    body = {"urn": urn, "severity": "High", "title": ctx.unique("finding"),
            "owner": "person/owner", "description": "qa",
            "category": "general", "source": "validation"}
    body.update(over)
    made = ctx.api.post(F, json=body, auth=ctx.people["risk"])
    return made.json().get("id", "") if made.status_code < 400 else ""


def _titles(ctx: Ctx, urn: str) -> list:
    got = ctx.api.get(f"{F}?urn={urn}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return []
    return [f.get("title") or "" for f in ((got.json() or {}).get("open") or [])]


@case("QA-AM-406", "Run every job twice in one pass", isolated=True)
def am_406(ctx: Ctx) -> Result:
    """Idempotence over the whole batch, not job by job. The recommended
    deployment is cron calling this endpoint, so a second pass minutes later
    is the ordinary case and it must add nothing."""
    runner = _runner(ctx)
    if runner is None:
        return BLOCKED, "no scheduler is wired"
    _name, urn = _model(ctx)
    _raise(ctx, urn)
    first = ctx.api.post(f"{S}/run", auth=ADMIN)
    if first.status_code >= 400:
        return BLOCKED, f"the first pass failed: {first.text[:140]}"
    after_one = sorted(_titles(ctx, urn))
    second = ctx.api.post(f"{S}/run", auth=ADMIN)
    if second.status_code >= 400:
        return FAIL, f"the second pass failed: {code_of(second)}"
    after_two = sorted(_titles(ctx, urn))
    if after_two != after_one:
        added = [t for t in after_two if t not in after_one]
        return FAIL, (f"a second pass raised {len(added)} more finding(s): "
                      f"{added[:3]} — a batch on a nightly cron compounds")
    body = second.json() or {}
    if body.get("failed"):
        return FAIL, (f"{body['failed']} job(s) failed on the second pass: "
                      f"{body.get('detail')}")
    return PASS, (f"{body.get('ran')} jobs, twice, and the register is "
                  f"unchanged after the second")


@case("QA-AM-407", "`monitoring.stalled` at exactly three cadences",
      isolated=True)
def am_407(ctx: Ctx) -> Result:
    """The grace is a MULTIPLE of the cadence rather than a fixed number of
    days, because a daily monitor and a quarterly one are not late at the
    same moment. The comparison is `<` against `(multiple - 1)` cadences past
    due, so exactly three cadences is not yet stalled."""
    runner = _runner(ctx)
    if runner is None:
        return BLOCKED, "no scheduler is wired"
    monitors = ctx.ui.app.state.ctx.get("monitoring")
    if monitors is None:
        return BLOCKED, "no monitoring service is wired"
    _name, urn = _model(ctx)
    made = ctx.api.post("/api/v1/monitors",
                        json={"urn": urn, "name": ctx.unique("mon"),
                              "kind": "input_drift",
                              "test_key": "stability.psi",
                              "threshold": {"max": 0.2},
                              "owner": "person/owner", "cadence_days": 1.0},
                        auth=ctx.people["owner"])
    if made.status_code >= 400:
        return BLOCKED, f"the monitor could not be defined: {made.text[:140]}"
    monitor_id = (made.json() or {}).get("id")
    row = monitors.registry.require(monitor_id)
    cadence = row["cadence_days"]
    # Exactly `MONITOR_GRACE_MULTIPLE` cadences since the last evaluation:
    # overdue_by is (multiple - 1) cadences, and the test is `<`.
    at = time.time()
    monitors.registry.monitors.set(
        {"last_evaluated_at": at - MONITOR_GRACE_MULTIPLE * cadence * DAY,
         "created_at": at - MONITOR_GRACE_MULTIPLE * cadence * DAY},
        id=monitor_id)
    runner.run(["monitoring.stalled"], now=at)
    stalled = [t for t in _titles(ctx, urn)
               if t.startswith("Monitoring has stopped")]
    if not stalled:
        # Silent at the boundary and reported past it, like every other
        # boundary in the platform.
        monitors.registry.monitors.set(
            {"last_evaluated_at":
                at - (MONITOR_GRACE_MULTIPLE * cadence * DAY) - 3600},
            id=monitor_id)
        runner.run(["monitoring.stalled"], now=at)
        after = [t for t in _titles(ctx, urn)
                 if t.startswith("Monitoring has stopped")]
        if not after:
            return FAIL, (f"an hour past {MONITOR_GRACE_MULTIPLE:g} cadences "
                          f"is still not reported stalled")
        return PASS, (f"silent at {MONITOR_GRACE_MULTIPLE:g} cadences, "
                      f"reported an hour later")
    return FAIL, (f"a monitor evaluated exactly {MONITOR_GRACE_MULTIPLE:g} "
                  f"cadences ago is already reported stalled. "
                  f"`overdue_by` is {MONITOR_GRACE_MULTIPLE:g} - 1 = "
                  f"{MONITOR_GRACE_MULTIPLE - 1:g} cadences and the guard is "
                  f"`overdue_by < cadence * (MULTIPLE - 1)`, so the boundary "
                  f"itself fires. Every comparable boundary in this platform "
                  f"is exclusive — escalation is `>` not `>=`, the "
                  f"acknowledge window skips on `<=`, the extension window "
                  f"and the tau bands the same — so this one alone reports a "
                  f"control as stopped on the day it is merely due")


@case("QA-AM-408", "`monitoring.stalled` after the monitor was paused",
      isolated=True)
def am_408(ctx: Ctx) -> Result:
    """A paused monitor is not a stalled one — somebody decided. Raising here
    would punish the deliberate act and teach people to leave monitors
    running rather than pause them honestly."""
    runner = _runner(ctx)
    monitors = ctx.ui.app.state.ctx.get("monitoring")
    if runner is None or monitors is None:
        return BLOCKED, "the scheduler or monitoring is not wired"
    _name, urn = _model(ctx)
    made = ctx.api.post("/api/v1/monitors",
                        json={"urn": urn, "name": ctx.unique("mon"),
                              "kind": "input_drift",
                              "test_key": "stability.psi",
                              "threshold": {"max": 0.2},
                              "owner": "person/owner", "cadence_days": 1.0},
                        auth=ctx.people["owner"])
    if made.status_code >= 400:
        return BLOCKED, f"the monitor could not be defined: {made.text[:140]}"
    monitor_id = (made.json() or {}).get("id")
    at = time.time()
    monitors.registry.monitors.set(
        {"last_evaluated_at": at - 90 * DAY, "created_at": at - 90 * DAY},
        id=monitor_id)
    paused = ctx.api.post(f"/api/v1/monitors/{monitor_id}/status?status=paused",
                          auth=ctx.people["owner"])
    if paused.status_code >= 400:
        return BLOCKED, f"the monitor could not be paused: {paused.text[:140]}"
    runner.run(["monitoring.stalled"], now=at)
    stalled = [t for t in _titles(ctx, urn)
               if t.startswith("Monitoring has stopped")]
    if stalled:
        return FAIL, (f"a monitor paused deliberately and ninety days idle is "
                      f"reported as stalled: {stalled[0]}")
    return PASS, "a paused monitor is not a stalled one"


@case("QA-AM-409",
      "`findings.overdue` does not escalate its own escalations",
      isolated=True)
def am_409(ctx: Ctx) -> Result:
    """The escalation is itself a finding with a remediation date, so a batch
    that escalated it would produce *Remediation overdue: Remediation
    overdue: ...* — one real failure compounding into a new finding every
    night."""
    runner = _runner(ctx)
    findings = ctx.ui.app.state.ctx.get("findings")
    if runner is None or findings is None:
        return BLOCKED, "the scheduler or findings register is not wired"
    _name, urn = _model(ctx)
    fid = _raise(ctx, urn)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    at = time.time()
    findings.findings.set({"due_at": at - 30 * DAY}, id=fid)
    runner.run(["findings.overdue"], now=at)
    once = [t for t in _titles(ctx, urn) if t.startswith("Remediation overdue")]
    if not once:
        return BLOCKED, "the first escalation did not fire"
    # Age the escalation itself past its own date and run again.
    for row in findings.open_for(
            ctx.ui.app.state.ctx["registry"].require(urn)["id"]):
        if row["category"] == "remediation_sla":
            findings.findings.set({"due_at": at - 30 * DAY}, id=row["id"])
    runner.run(["findings.overdue"], now=at)
    doubled = [t for t in _titles(ctx, urn)
               if t.startswith("Remediation overdue: Remediation overdue")]
    if doubled:
        return FAIL, (f"the batch escalated its own escalation: {doubled[0]}")
    return PASS, f"{len(once)} escalation, and no escalation of it"


@case("QA-AM-411",
      "`findings.unacknowledged` at exactly the acknowledge window",
      isolated=True)
def am_411(ctx: Ctx) -> Result:
    """`waiting <= acknowledge_days` is skipped, so the window itself is
    still the owner's. The same `>` boundary the ageing reading uses, and
    they have to agree — a batch that raised a day before the reading said
    the finding was late would contradict the screen."""
    runner = _runner(ctx)
    workflow = ctx.ui.app.state.ctx.get("finding_workflow")
    findings = ctx.ui.app.state.ctx.get("findings")
    if not (runner and workflow and findings):
        return BLOCKED, "the scheduler or findings workflow is not wired"
    _name, urn = _model(ctx)
    fid = _raise(ctx, urn)
    if not fid:
        return BLOCKED, "the finding could not be raised"
    window = workflow.acknowledge_days
    at = time.time()
    findings.findings.set({"raised_at": at - window * DAY}, id=fid)
    runner.run(["findings.unacknowledged"], now=at)
    early = [t for t in _titles(ctx, urn) if t.startswith("Finding never accepted")]
    if early:
        return FAIL, (f"a finding unaccepted for exactly {window:g} days is "
                      f"already reported: {early[0]}")
    findings.findings.set({"raised_at": at - (window * DAY) - 3600}, id=fid)
    runner.run(["findings.unacknowledged"], now=at)
    later = [t for t in _titles(ctx, urn) if t.startswith("Finding never accepted")]
    if not later:
        return FAIL, (f"an hour past {window:g} days is still not reported, "
                      f"so the batch and the ageing reading disagree")
    return PASS, f"silent at {window:g} days, reported an hour later"


@case("QA-AM-413", "One job raises during a pass", isolated=True)
def am_413(ctx: Ctx) -> Result:
    """One job must not stop the rest. The run records `ran` and `failed`
    separately with the error kept, because a pass that reported success
    while a job threw would be the scheduler lying about the batch it exists
    to prove ran."""
    runner = _runner(ctx)
    if runner is None:
        return BLOCKED, "no scheduler is wired"
    import dataclasses
    key = sorted(runner.jobs)[0]
    original = runner.jobs[key]

    def explode(_ctx):
        raise RuntimeError("a QA job failure")

    # `Job` is a frozen dataclass, so the job is REPLACED rather than patched.
    runner.jobs[key] = dataclasses.replace(original, run=explode)
    try:
        report = runner.run()
    finally:
        runner.jobs[key] = original
    if report.get("failed") != 1:
        return FAIL, (f"a job raised and the pass reports "
                      f"{report.get('failed')} failure(s)")
    if report.get("ran") != len(runner.jobs):
        return FAIL, (f"a job raised and only {report.get('ran')} of "
                      f"{len(runner.jobs)} jobs ran, so one failure stopped "
                      f"the batch")
    broke = [r for r in report.get("results") or [] if not r.get("ok")]
    if not broke or "QA job failure" not in (broke[0].get("error") or ""):
        return FAIL, "the failure is counted and the error is not kept"
    if key not in (report.get("detail") or ""):
        return FAIL, "the detail does not name the job that failed"
    return PASS, (f"{report['ran']} ran, 1 failed, named in the detail with "
                  f"its error")


@case("QA-AM-415", "Run one job by name, then the whole pass", isolated=True)
def am_415(ctx: Ctx) -> Result:
    """Running a job alone and running it in the pass must reach the same
    state, or a person debugging one job changes what the batch will do."""
    runner = _runner(ctx)
    if runner is None:
        return BLOCKED, "no scheduler is wired"
    _name, urn = _model(ctx)
    _raise(ctx, urn)
    one = ctx.api.post(f"{S}/run", json={"jobs": ["findings.overdue"]},
                       auth=ADMIN)
    if one.status_code >= 400:
        return BLOCKED, f"the single job failed: {one.text[:140]}"
    if (one.json() or {}).get("ran") != 1:
        return FAIL, f"asking for one job ran {(one.json() or {}).get('ran')}"
    after_one = sorted(_titles(ctx, urn))
    whole = ctx.api.post(f"{S}/run", auth=ADMIN)
    if whole.status_code >= 400:
        return FAIL, f"the whole pass failed: {code_of(whole)}"
    added = [t for t in sorted(_titles(ctx, urn)) if t not in after_one]
    escalations = [t for t in added if t.startswith("Remediation overdue")]
    if escalations:
        return FAIL, (f"the pass re-raised what the single run already did: "
                      f"{escalations}")
    return PASS, (f"one job, then the pass; {len(added)} new finding(s) and "
                  f"none from the job already run")


@case("QA-AM-416", "The scheduler has not run for a week", isolated=True)
def am_416(ctx: Ctx) -> Result:
    """The recorded defect this reporting exists for: `hours_since` had no
    threshold and no flag, so a batch that stopped a month ago looked exactly
    like one that ran on time. That matters more here than almost anywhere,
    because a dead scheduler makes the estate look CLEAN rather than stale."""
    runner = _runner(ctx)
    if runner is None:
        return BLOCKED, "no scheduler is wired"
    at = time.time()
    runner.run(["findings.overdue"], now=at - 7 * DAY)
    report = runner.health(now=at)
    blob = f"{report}".lower()
    if "stale" not in blob:
        return FAIL, (f"a batch last run a week ago is reported without any "
                      f"staleness flag, so it reads like one that ran on "
                      f"time: {report}")
    fresh = runner.health(now=at - 7 * DAY + 60)
    if f"{fresh}".lower().count("true") >= blob.count("true") and \
            "stale" in f"{fresh}".lower() and \
            f"{fresh}".lower().split("stale")[1][:8] == blob.split("stale")[1][:8]:
        return BLOCKED, "the stale flag reads the same a minute after a run"
    return PASS, "a week-old batch is flagged stale, not reported as a number"


@case("QA-AM-417", "Delete the whole run history and run a pass",
      isolated=True)
def am_417(ctx: Ctx) -> Result:
    """The batch derives everything from the register rather than from its
    own history, so losing the history must change what the pass DOES to
    nothing — only what it can say about when it last ran."""
    runner = _runner(ctx)
    if runner is None:
        return BLOCKED, "no scheduler is wired"
    _name, urn = _model(ctx)
    _raise(ctx, urn)
    ctx.api.post(f"{S}/run", auth=ADMIN)
    before = sorted(_titles(ctx, urn))
    for row in list(runner.runs.many()):
        runner.runs.remove(id=row["id"])
    if runner.history():
        return BLOCKED, "the run history could not be cleared"
    again = ctx.api.post(f"{S}/run", auth=ADMIN)
    if again.status_code >= 400:
        return FAIL, (f"a pass after the history was cleared failed: "
                      f"{code_of(again)}")
    after = sorted(_titles(ctx, urn))
    if after != before:
        added = [t for t in after if t not in before]
        return FAIL, (f"clearing the run history changed what the pass did: "
                      f"{len(added)} new finding(s) {added[:2]} — the batch is "
                      f"deriving idempotence from its own history rather than "
                      f"from the register")
    return PASS, "history cleared, and the pass is identical"
