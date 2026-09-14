"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the batch, and the things that only become records when it runs.

Lapses, overdue findings, stalled monitors and expiring debt are all DERIVED.
They are true whether or not anybody looks — and they only become *recorded*
when the governance batch runs. So a scheduler nobody notices has stopped makes
an estate look clean rather than stale, which is why it reports on itself with
a threshold rather than a number: "thirty days" and "0.2 hours" render
identically as a figure on a tile.

One job must not stop four, and a job that raised a finding yesterday must not
raise it again today — a register filling with duplicates of one problem is a
register whose counts nobody trusts.

And delivery is not the batch. A message that repeats yesterday's is a message
somebody filters, so an unchanged worklist is suppressed until a quiet period
has passed.
"""
from __future__ import annotations

import time

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _scheduler(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("scheduler")


def _model(ctx: Ctx) -> str:
    name = ctx.unique("op")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **SHAPE}, auth=ctx.people["owner"])
    return name


@case("QA-PLT-245", "The scheduler stopped for three hours", isolated=True)
def plt_245(ctx: Ctx) -> Result:
    """Reported stale with a threshold, and readiness stays 200 — a stopped
    batch is a governance problem, not a reason to take the node out of
    service, and conflating the two is how somebody disables the report."""
    from core.scheduler.runner import STALE_AFTER_INTERVALS
    scheduler = _scheduler(ctx)
    if scheduler is None:
        return BLOCKED, "no scheduler is wired"
    scheduler.run(keys=["evidence.verify"], actor="qa")
    now = time.time()
    fresh = scheduler.health(now=now)
    if fresh["stale"]:
        return BLOCKED, f"a batch that just ran reads stale: {fresh['detail']}"
    window = scheduler.interval_seconds * STALE_AFTER_INTERVALS
    later = scheduler.health(now=now + window + 60)
    if not later["stale"]:
        return FAIL, (f"a batch {(window + 60) / 3600:.1f} hours old is not "
                      f"stale against a {window / 3600:.0f}-hour threshold")
    if "considered stopped" not in later["detail"]:
        return FAIL, f"the detail does not say what stale means: {later['detail'][:150]}"
    if "out of date" not in later["detail"]:
        return FAIL, ("the detail does not say the derived conditions are "
                      "stale, which is the consequence")
    if later.get("stale_after_hours") is None:
        return FAIL, "the answer does not publish the threshold it used"
    ready = ctx.api.get("/health/ready")
    if ready.status_code != 200:
        return FAIL, (f"readiness answered {ready.status_code} because the "
                      f"batch is stale; a stopped scheduler is not a reason to "
                      f"take the node out of service")
    body = ready.json() or {}
    reported = ((body.get("scheduler") or {}).get("stale")
                if isinstance(body.get("scheduler"), dict) else None)
    if reported is None:
        return FAIL, (f"readiness says nothing about the scheduler: "
                      f"{sorted(body)}")
    return PASS, (f"stale past {later['stale_after_hours']:.0f} hours with the "
                  f"consequence named, and readiness still 200")


@case("QA-PLT-240", "The database locked while a job records its result",
      isolated=True)
def plt_240(ctx: Ctx) -> Result:
    """One job must not stop four. The `try` around a job's own body is the
    half that was written; recording the result is the half that runs
    afterwards, and a failure there takes the batch with it."""
    scheduler = _scheduler(ctx)
    if scheduler is None:
        return BLOCKED, "no scheduler is wired"
    keys = sorted(scheduler.jobs)
    if len(keys) < 3:
        return BLOCKED, f"only {len(keys)} job(s) are registered"
    real = type(scheduler.runs).add
    state = {"n": 0}

    def locking(self, row):
        state["n"] += 1
        if state["n"] == 2:
            raise RuntimeError("database is locked")
        return real(self, row)

    type(scheduler.runs).add = locking
    try:
        out = scheduler.run(keys=keys[:4], actor="qa")
    except Exception as exc:
        type(scheduler.runs).add = real
        return FAIL, (
            f"a lock while RECORDING the second job's result aborted the whole "
            f"batch with {type(exc).__name__}: {str(exc)[:70]}. "
            f"`Scheduler._one` wraps `job.run(context)` in a try — one job must "
            f"not stop four — and then writes the run row and the evidence node "
            f"outside it. Every job after the second never ran, and the caller "
            f"gets an exception rather than three results and one failure; the "
            f"jobs that did run are recorded, so the batch is half-done and "
            f"the answer says nothing about which half")
    finally:
        type(scheduler.runs).add = real
    failed = [r for r in out["results"] if not r["ok"]]
    if out["ran"] != len(keys[:4]):
        return FAIL, (f"{out['ran']} of {len(keys[:4])} job(s) ran after one "
                      f"recording failure")
    if not failed:
        return FAIL, "the recording failure is not reported as a failed job"
    return PASS, (f"{out['ran']} job(s) ran, {len(failed)} reported failed, "
                  f"the batch completed")


@case("QA-PLT-246", "A finding retitled, then the job that raised it run again",
      isolated=True)
def plt_246(ctx: Ctx) -> Result:
    """Deduplication is by TITLE. A title is prose, and prose gets edited —
    so the guard that stops a nightly job filling the register with copies
    of one problem is keyed on the one field a person is most likely to
    change."""
    import inspect

    from core.scheduler import jobs as module
    source = inspect.getsource(module._already_raised)
    if 'f["title"] == title' not in source:
        return PASS, "deduplication no longer keys on the title"
    scheduler = _scheduler(ctx)
    findings = ctx.ui.app.state.ctx.get("findings")
    registry = ctx.ui.app.state.ctx.get("registry")
    if not (scheduler and findings and registry):
        return BLOCKED, "no scheduler or findings register is wired"
    name = _model(ctx)
    urn = f"maya://model/{name}"
    model = registry.require(urn)
    raised = findings.raise_finding(
        model["id"], "High", "A job-raised title", "person/owner",
        description="qa", actor="qa")
    before = len(findings.open_for(model["id"]))
    findings.findings.set({"title": "somebody rewrote this title"},
                          id=raised["id"])
    again = module._already_raised(findings, model["id"], "A job-raised title")
    if again:
        return PASS, "the retitled finding is still recognised"
    after = len(findings.open_for(model["id"]))
    return FAIL, (
        f"`_already_raised` matches `f['title'] == title`, so a finding whose "
        f"title a person edited is no longer recognised as the one the job "
        f"raised: the check answers False and the next run raises a second "
        f"copy of the same condition. The model holds {after} open finding(s) "
        f"now (was {before}) and would hold {after + 1} after one more batch. "
        f"Six job sites call this, all of them nightly, and the register's "
        f"counts are what the ageing profile and the board pack are computed "
        f"from")


@case("QA-PLT-238", "A manual run inside the in-process loop", isolated=True)
def plt_238(ctx: Ctx) -> Result:
    """Somebody pressing Run while the loop is mid-pass. Jobs are written to
    be safe to call as often as you like, so the outcome must be two
    recorded runs and no doubled effect."""
    from concurrent.futures import ThreadPoolExecutor
    scheduler = _scheduler(ctx)
    if scheduler is None:
        return BLOCKED, "no scheduler is wired"
    key = "evidence.verify"
    if key not in scheduler.jobs:
        key = sorted(scheduler.jobs)[0]
    before = len(scheduler.history(limit=500))
    outcomes = []

    def press(_n):
        try:
            outcomes.append(scheduler.run(keys=[key], actor=f"qa-{_n}"))
        except Exception as exc:
            outcomes.append({"raised": f"{type(exc).__name__}: {exc}"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(press, range(2)))
    raised = [o for o in outcomes if "raised" in o]
    if raised:
        return FAIL, (f"two overlapping runs of one job raised: "
                      f"{raised[0]['raised'][:120]}")
    after = len(scheduler.history(limit=500))
    if after - before != 2:
        return FAIL, (f"two runs recorded {after - before} history row(s); a "
                      f"run that leaves no record is one nobody can audit")
    failed = [r for o in outcomes for r in o.get("results", []) if not r["ok"]]
    if failed:
        return FAIL, (f"an overlapping run failed: "
                      f"{failed[0].get('error', '')[:120]}")
    return PASS, (f"two overlapping runs of '{key}', both recorded, neither "
                  f"failed")


@case("QA-PLT-251", "Two concurrent ingests into the discovery register",
      isolated=True)
def plt_251(ctx: Ctx) -> Result:
    """`DISC-nnnn` is minted from a count of what is already there. Two
    sweeps landing together read the same count, and a reference that is not
    unique is a triage queue where two rows answer to one name."""
    from concurrent.futures import ThreadPoolExecutor
    discovery = ctx.ui.app.state.ctx.get("discovery")
    if discovery is None:
        return BLOCKED, "no discovery register is wired"
    found = []

    def sweep(n):
        candidates = [{"location": f"//share/book-{n}-{i}.xlsx",
                       "source": "fileshare",
                       "fingerprint": f"fp-{n}-{i}",
                       "proposed_as": "model"} for i in range(4)]
        try:
            found.append(discovery.ingest("qa-scanner", candidates, actor="qa"))
        except Exception as exc:
            found.append({"raised": f"{type(exc).__name__}: {exc}"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(sweep, range(2)))
    raised = [f for f in found if "raised" in f]
    if raised:
        return FAIL, f"a concurrent ingest raised: {raised[0]['raised'][:130]}"
    rows = discovery.repo.many()
    references = [r["reference"] for r in rows]
    duplicates = sorted({r for r in references if references.count(r) > 1})
    if duplicates:
        return FAIL, (
            f"{len(duplicates)} reference(s) are held by more than one row "
            f"after two concurrent sweeps: {duplicates[:4]}. `ingest` mints "
            f"`DISC-{{n:04d}}` from a count of the rows already there, so two "
            f"sweeps that read the same count produce the same reference — and "
            f"a triage queue where two candidates answer to one name is one "
            f"where dismissing a spreadsheet dismisses somebody else's")
    return PASS, (f"{len(references)} candidate(s) across two concurrent "
                  f"sweeps, every reference distinct")


@case("QA-PLT-254", "A channel failing for a week, then recovering",
      isolated=True)
def plt_254(ctx: Ctx) -> Result:
    """The quiet window is keyed on the last SENT delivery, so a week of
    failures leaves nothing recent to be quiet about. Whether that is right
    is the question: the work IS outstanding and nobody has been told, and
    the failures have to be visible either way."""
    from core.notify.common import FAILED, SENT
    service = ctx.ui.app.state.ctx.get("notifications")
    if service is None:
        return BLOCKED, "no notification service is wired"
    name = _model(ctx)
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/findings",
                 json={"urn": urn, "severity": "High", "title": "outstanding",
                       "owner": "person/owner", "description": "qa",
                       "category": "general", "source": "validation",
                       "blocking": True},
                 auth=ctx.people["risk"])
    channel = service.default_channel
    transport = service.channels.get(channel)
    if transport is None:
        return BLOCKED, f"no transport for the default channel '{channel}'"
    first = service.run(actor="qa")
    if not first["sent"]:
        return BLOCKED, f"nothing was sent to begin with: {first['detail'][:130]}"
    real = type(transport).send

    def failing(self, *a, **k):
        # The CONTRACT: a channel reports a failure rather than raising, so one
        # unreachable endpoint does not stop everybody else being told.
        return False, "the channel is down"

    type(transport).send = failing
    try:
        for day in range(7):
            service.run(now=time.time() + day * 86400, actor="qa")
    finally:
        type(transport).send = real
    rows = service.notifications.many()
    failures = [r for r in rows if r["state"] == FAILED]
    if not failures:
        return BLOCKED, "the channel did not record any failure"
    recovered = service.run(now=time.time() + 8 * 86400, actor="qa")
    sent_after = [r for r in service.notifications.many()
                  if r["state"] == SENT]
    if not recovered["sent"]:
        return FAIL, (f"after a week of failures and a recovery, nothing was "
                      f"sent: {recovered['detail'][:130]}")
    health = service.status() if hasattr(service, "status") else {}
    summarised = bool(health.get("failed")
                      or "failure" in str(health.get("detail", "")))
    if not summarised:
        return FAIL, (f"{len(failures)} delivery failure(s) are recorded and "
                      f"nothing summarises them, so a channel down for a week "
                      f"is only findable by reading the table")
    # And the other half: the contract is that a channel REPORTS a failure.
    # `_deliver` calls `transport.send` outside any try, so a channel that
    # raises takes the whole pass with it.
    import inspect

    from core.notify.channels import WebhookChannel
    deliver = inspect.getsource(type(service)._deliver)
    guarded = "try:" in deliver and "transport.send" in deliver
    webhook = inspect.getsource(WebhookChannel.send)
    permit_line = next((i for i, ln in enumerate(webhook.splitlines())
                        if "permit(" in ln), None)
    try_line = next((i for i, ln in enumerate(webhook.splitlines())
                     if ln.strip() == "try:"), None)
    if not guarded and permit_line is not None and try_line is not None \
            and permit_line < try_line:
        return FAIL, (
            f"{len(failures)} failure(s) recorded and summarised, and recovery "
            f"sends — all correct. What is not: `_deliver` calls "
            f"`transport.send` outside any try, and the contract that makes "
            f"that safe is that a channel reports rather than raises. "
            f"`WebhookChannel.send` calls `permit(self.url)` BEFORE its own "
            f"try, so an operator who pastes a `file:` URL — the case the "
            f"comment beside it names — raises out of `send`, out of "
            f"`_deliver` and out of `run`. One misconfigured URL stops "
            f"everybody else being notified and records nothing, which is the "
            f"outcome both of those guards exist to prevent")
    return PASS, (f"{len(failures)} failure(s) recorded and summarised; on "
                  f"recovery the outstanding work is sent again "
                  f"({len(sent_after)} sent in total) rather than suppressed "
                  f"against a week-old delivery")
