"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Running the jobs — from a loop, from cron, or from a person pressing a button.

**MAYA does not insist on owning the clock.** The same reasoning that keeps it
out of model execution applies here: a governance platform that must be running
for a bank's schedule to advance is a platform whose outage is a governance
outage. So a run is an ordinary, authenticated call. An in-process loop is
offered as a convenience and can be switched off in one line; cron calling the
endpoint every hour is an equally supported deployment, and the two produce
identical results.

That equivalence is only true because every job is idempotent and derives its own
work from the register. Nothing here is a queue. Deleting the whole run history
would change nothing about what the next run does.

**A job that fails does not stop the others.** The failure mode of a scheduler is
that one broken job silently prevents four working ones, and the symptom is
nothing happening — which looks exactly like nothing needing to happen.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.evidence import EvidenceEngine
from core.log import get_logger
from core.scheduler.jobs import JOBS, JobContext
from db import ScheduledRunRepository

logger = get_logger(__name__)


class SchedulerError(RuntimeError):
    """A scheduler operation was refused. The message says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


#: The batch's expected cadence, and how many missed cycles count as stopped.
#: Two rather than one, so a single slow or skipped run is not an alarm.
DEFAULT_INTERVAL_SECONDS = 3600.0
STALE_AFTER_INTERVALS = 2


class Scheduler:
    """Runs the idempotent jobs and records what each one did."""

    def __init__(self, runs: ScheduledRunRepository, evidence: EvidenceEngine,
                 context: JobContext, jobs: Optional[Dict[str, Any]] = None,
                 interval_seconds: float = DEFAULT_INTERVAL_SECONDS):
        self.runs, self.evidence = runs, evidence
        self.context, self.jobs = context, jobs or JOBS
        # How often this batch is SUPPOSED to run, so `health` can say whether
        # it has stopped rather than only how long it has been.
        self.interval_seconds = interval_seconds

    # -------------------------------------------------------------------- run
    def run(self, keys: Optional[Sequence[str]] = None, now: Optional[float] = None,
            actor: str = "scheduler") -> Dict[str, Any]:
        """Run some or all jobs. Safe to call as often as you like."""
        selected = list(keys) if keys else list(self.jobs)
        unknown = [k for k in selected if k not in self.jobs]
        if unknown:
            raise SchedulerError(
                "unknown_job", f"no job named {', '.join(unknown)}",
                f"known jobs are {', '.join(sorted(self.jobs))}")

        moment = now if now is not None else time.time()
        results = [self._one(self.jobs[key], moment, actor) for key in selected]
        failed = [r for r in results if not r["ok"]]
        return {
            "ran": len(results), "failed": len(failed), "at": moment,
            "results": results,
            "detail": (f"{len(results)} job(s) ran"
                       + (f", {len(failed)} failed: "
                          + ", ".join(r["job"] for r in failed) if failed else "")),
        }

    def _one(self, job, moment: float, actor: str) -> Dict[str, Any]:
        context = JobContext(**{**vars(self.context), "now": moment, "actor": actor})
        started = time.perf_counter()
        outcome: Dict[str, Any] = {}
        error = None
        try:
            outcome = job.run(context) or {}
        except Exception as exc:                       # one job must not stop four
            error = f"{type(exc).__name__}: {exc}"
            logger.exception("scheduled job %s failed", job.key)

        row = {"job": job.key, "outcome": outcome, "ok": error is None,
               "error": error,
               "duration_ms": round((time.perf_counter() - started) * 1000, 2),
               "ran_by": actor, "ran_at": moment}
        with self.evidence.recording():
            self.runs.add(row)
            self.evidence.append("scheduled_job_ran", "scheduler", job.key,
                                 {"job": job.key, "ok": error is None,
                                  "outcome": outcome, "error": error}, actor=actor)
        return self.runs.one(id=row["id"])

    # ------------------------------------------------------------------ query
    def catalogue(self) -> List[Dict[str, Any]]:
        """The jobs, what each does and why — and when each last ran."""
        return [{"job": j.key, "what": j.what, "why": j.why,
                 "last_run": self.last(j.key)}
                for j in sorted(self.jobs.values(), key=lambda j: j.key)]

    def last(self, key: str) -> Optional[Dict[str, Any]]:
        """The most recent run of one job.

        This called `latest_version(rows)`, which orders by `semver` — a field a
        scheduled run does not have. Every row keyed to `(-1,)` with a
        `created_at` of nothing, `max` returned the FIRST of the equals, and the
        repository orders by `ran_at` ascending: so `last()` returned the OLDEST
        run of every job, permanently.

        Nothing raised. `/admin/scheduler` showed the first time the batch ever
        ran as its last run, `health()` computed "hours since" from that, and a
        job that failed once on the day it was installed was reported as failing
        forever while every run since had succeeded. The screen that exists to
        say whether the governance batch is alive was answering with the day it
        was born.
        """
        rows = self.runs.many(job=key)
        return max(rows, key=lambda r: r.get("ran_at") or 0) if rows else None

    def history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """The most recent runs, newest first — the order somebody reads them in
        when they are asking what just happened."""
        return sorted(self.runs.many(), key=lambda r: r.get("ran_at") or 0,
                      reverse=True)[:limit]

    def health(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Is the scheduler itself running?

        A scheduler nobody notices has stopped is the same problem as a monitor
        nobody notices has stopped, one level up — so it reports on itself.
        """
        moment = now if now is not None else time.time()
        last = [self.last(k) for k in self.jobs]
        ran = [r for r in last if r]
        newest = max((r["ran_at"] for r in ran), default=None)
        failing = [r["job"] for r in ran if not r["ok"]]
        # STALE, with a threshold, because "30 days" and "0.2 hours" rendered
        # identically as a number on a tile. `hours_since` had no threshold and
        # no flag, so a batch that stopped a month ago looked exactly like one
        # that ran on time — and that matters more here than almost anywhere,
        # because lapses, overdue findings and stalled monitors are DERIVED and
        # only become records when the batch runs. A dead scheduler makes the
        # estate look clean rather than stale.
        overdue_after = self.interval_seconds * STALE_AFTER_INTERVALS
        stale = newest is None or (moment - newest) > overdue_after
        return {
            "jobs": len(self.jobs), "ever_run": len(ran),
            "never_run": [k for k in sorted(self.jobs) if not self.last(k)],
            "last_run_at": newest,
            "hours_since": round((moment - newest) / 3600, 1) if newest else None,
            "failing": failing,
            "stale": stale,
            "expected_every_hours": round(self.interval_seconds / 3600, 2),
            "stale_after_hours": round(overdue_after / 3600, 2),
            "detail": (
                "the governance batch has NEVER run, so nothing in this estate "
                "has been checked for lapses, overdue findings or silent "
                "monitors — an estate with nothing outstanding looks exactly "
                "like this one" if not ran else
                f"last ran {(moment - newest) / 3600:.1f} hours ago"
                + (f", which is past the {overdue_after / 3600:.0f}-hour point "
                   f"at which this batch is considered stopped; every derived "
                   f"condition it records is therefore out of date"
                   if stale else "")
                + (f"; {len(failing)} job(s) failing: {', '.join(failing)}"
                   if failing else "")),
        }
