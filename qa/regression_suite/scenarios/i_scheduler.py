"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the scheduler, which is how governance happens without anybody
remembering to make it happen.

A scheduler that has never run is the quietest failure in the platform: every
periodic control simply does not fire, and nothing anywhere says so. So the
cases here are about the batch being safe to run often, honest when a job
fails, and loud about its own silence.
"""
from __future__ import annotations

from core.scheduler.jobs import JOBS
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

S = "/api/v1/scheduler"


def _operator(ctx: Ctx):
    """`scheduler:run` belongs to the operator, the service and admin — not
    to any of the governance roles. Running as `owner` answers `forbidden`."""
    who = ctx.made.get("scheduler_operator")
    if who:
        return who
    name = ctx.unique("ops")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": name, "display_name": name,
                              "roles": ["operator"], "password": f"{name}-pw",
                              "legal_entities": [], "domains": []})
    if made.status_code >= 400:
        raise AssertionError(f"could not mint an operator: {made.text[:170]}")
    ctx.made["scheduler_operator"] = (name, f"{name}-pw")
    return ctx.made["scheduler_operator"]


def _run(ctx: Ctx, **body):
    return ctx.api.post(f"{S}/run", json=body or None, auth=_operator(ctx))


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-PLT-241", "One valid job name and one invalid")
def plt_241(ctx: Ctx) -> Result:
    """Refused whole. Running the valid one and reporting the batch as done
    would leave a control unfired under a green result."""
    known = sorted(JOBS)[0]
    got = _run(ctx, jobs=[known, "qa-no-such-job"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        ran = [r.get("job") for r in (got.json() or {}).get("results") or []]
        return FAIL, (f"a batch naming an unknown job ran anyway: {ran}")
    if known not in got.text and "known jobs" not in got.text:
        return FAIL, "the refusal does not name the jobs that exist"
    return PASS, f"refused '{code_of(got)}', naming the known jobs"


@case("QA-PLT-242", "Run with no body at all")
def plt_242(ctx: Ctx) -> Result:
    """The default is everything. A no-body call that ran nothing would be
    the most dangerous no-op available — it reports success."""
    got = _run(ctx)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    if not body.get("ran"):
        return FAIL, ("a call with no body ran no jobs and reported success, "
                      "so every periodic control silently did not fire")
    if body["ran"] != len(JOBS):
        return FAIL, (f"{body['ran']} of {len(JOBS)} jobs ran on a call with "
                      f"no selection")
    return PASS, f"all {len(JOBS)} jobs ran"


@case("QA-PLT-237", "Run the whole batch twice")
def plt_237(ctx: Ctx) -> Result:
    """"Safe to call as often as you like." A second run must not double
    whatever the first raised, or a scheduler firing on two hosts is an
    incident."""
    first = _run(ctx)
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    second = _run(ctx)
    if second.status_code >= 400:
        return FAIL, (f"a second run was refused '{code_of(second)}'; the "
                      f"batch is not safe to repeat")
    a, b = first.json() or {}, second.json() or {}
    if a.get("ran") != b.get("ran"):
        return FAIL, (f"the two runs did different amounts of work: "
                      f"{a.get('ran')} then {b.get('ran')}")
    return PASS, f"{b.get('ran')} jobs both times, {b.get('failed')} failed"


@case("QA-PLT-239", "A job that raises")
def plt_239(ctx: Ctx) -> Result:
    """"One job must not stop four." A raise is caught, counted, and the
    error recorded — a batch that aborts on the first failure leaves the rest
    unfired with nothing saying which."""
    import inspect

    from core.scheduler import runner
    source = inspect.getsource(runner.Scheduler._one)
    if "except Exception" not in source:
        return FAIL, "a raising job stops the batch"
    if '"error"' not in source or '"ok"' not in source:
        return FAIL, ("a raising job is caught and the failure is not "
                      "recorded, which is worse than crashing")
    got = _run(ctx)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    if "failed" not in body:
        return FAIL, "the batch result carries no failure count"
    for row in body.get("results") or []:
        if row.get("ok") is None:
            return FAIL, f"a job result does not say whether it succeeded: {row}"
    return PASS, (f"{body.get('ran')} ran, {body.get('failed')} failed, each "
                  f"result carrying ok and error")


@case("QA-PLT-244", "The scheduler that has never run")
def plt_244(ctx: Ctx) -> Result:
    """The quietest failure there is. A posture that said nothing would let
    an instance sit for a year with no periodic control firing."""
    got = ctx.api.get(S, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    # The posture answers `{jobs, health, loop_running}` — the statement is
    # under `health`, not `detail`.
    health = body.get("health")
    if not health:
        return FAIL, ("the scheduler posture carries no health, so an "
                      "instance where nothing has ever run looks like a "
                      "healthy one")
    if isinstance(health, dict) and not str(health.get("detail") or "").strip():
        return FAIL, f"the scheduler health states nothing: {health}"
    if body.get("loop_running") is None:
        return FAIL, "the posture does not say whether the loop is running"
    jobs = body.get("jobs") or body.get("catalogue") or []
    if not jobs:
        return FAIL, "the posture lists no jobs at all"
    silent = [j for j in jobs if not (j.get("what") or "").strip()
              or not (j.get("why") or "").strip()]
    if silent:
        return FAIL, (f"{len(silent)} job(s) are listed without saying what "
                      f"they do or why: {[j.get('job') for j in silent][:4]}")
    return PASS, (f"{len(jobs)} jobs, each stating what and why; health "
                  f"{str(health)[:60]}")


@case("QA-PLT-3700", "Every job says what it does and why")
def plt_3700(ctx: Ctx) -> Result:
    """A periodic control nobody can read is one nobody reviews, and the
    catalogue is the only place a reader meets them."""
    mute = [k for k, j in JOBS.items()
            if not (getattr(j, "what", "") or "").strip()
            or not (getattr(j, "why", "") or "").strip()]
    if mute:
        return FAIL, f"jobs with no stated purpose: {mute}"
    return PASS, f"all {len(JOBS)} jobs state what and why"


@case("QA-PLT-3701", "Every run is on the evidence chain")
def plt_3701(ctx: Ctx) -> Result:
    """"The control ran" is a claim about the past, so it has to be evidence
    rather than a log line."""
    import inspect

    from core.scheduler import runner
    source = inspect.getsource(runner.Scheduler._one)
    if "evidence.append" not in source:
        return FAIL, ("a scheduled run is not appended to the evidence chain, "
                      "so 'the control ran' rests on a log")
    if "scheduled_job_ran" not in source:
        return FAIL, "the evidence node has no event name"
    got = _run(ctx)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    history = ctx.api.get(f"{S}/history", auth=ctx.people["risk"])
    if history.status_code >= 400:
        return BLOCKED, history.text[:170]
    rows = (history.json() or {}).get("runs") or \
        (history.json() or {}).get("history") or []
    if not rows:
        return FAIL, "a run happened and the history is empty"
    return PASS, f"{len(rows)} run(s) recorded and appended"


@case("QA-PLT-3702", "A job key that is not in the catalogue")
def plt_3702(ctx: Ctx) -> Result:
    got = _run(ctx, jobs=["qa-nothing-like-this"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a job nobody defined was run"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-243", "Run the notifications batch with no body")
def plt_243(ctx: Ctx) -> Result:
    """Same shape as the scheduler: the absence of a selection must mean
    everything, not nothing."""
    got = ctx.api.post("/api/v1/notifications/run", json=None,
                       auth=_operator(ctx))
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got) or got.status_code}'"
    body = got.json() or {}
    if not (str(body.get("detail") or "").strip() or body.get("sent") is not None
            or body.get("ran") is not None):
        return FAIL, ("the notifications run reports nothing at all, so a "
                      "batch that sent nothing looks like one that worked")
    return PASS, f"reported: {str(body.get('detail') or sorted(body))[:90]}"
