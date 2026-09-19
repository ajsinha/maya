"""
The job queue and its workers (§15.2).

Every slow operation — pin, cascade pin, artifact validation, PDF render,
integrity scan, export — is a ``Job`` row. The queue is the database:

* PostgreSQL: workers claim with ``SELECT … FOR UPDATE SKIP LOCKED``.
* SQLite: the same table, claimed under the write mutex by in-process workers.

Guarantees: **idempotent** (a job with the same idempotency key is returned,
not duplicated — a double-click never pins twice), **cancellable**
(cooperative, checked between stages), **retryable** (exponential backoff
with jitter, capped attempts, then dead-letter with the failure kept),
**fair** (see below), **observable** (every job carries a trace id and a
progress log).

**Fairness** (§15.2). Strict arrival order is not fair: one person cascade-pinning
ten thousand features puts ten thousand rows in front of everyone else, and every
other user's next pin waits behind all of them. Two limits together fix that
without a priority field anyone has to set:

* a **per-user concurrency cap** — one owner may have at most
  ``jobs.per_user.max_concurrent`` jobs running at once, so a campaign cannot hold
  every worker;
* **weighted fair queueing** — a worker ranks the oldest queued rows by how much
  of the fleet their owner already holds (jobs of theirs running, plus how many of
  their own queued jobs are ahead of this one) and takes the lowest rank, oldest
  first. So somebody with nothing running is served before the second job of
  somebody already running one, and ten thousand jobs from one person interleave
  with everyone else's instead of preceding them — while a campaign still gets
  every idle worker when nobody else wants one. Turning ``jobs.fair`` off restores
  arrival order.

**Backpressure** (§15.4). Accepting work that cannot be started is a promise MAYA
cannot keep, so a submission is refused — before the row is written — when the
queue is deeper than ``jobs.queue.max_depth`` or the owner already has
``jobs.per_user.max_queued`` waiting. The refusal carries an honest wait estimate
from the queue's own depth rather than a bare "try again later".

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import random
import secrets
import threading
import traceback
from dataclasses import dataclass
from typing import Any, Callable

from maya.core import djson
from maya.core.errors import ConflictError, MayaError, QuotaExceeded
from maya.core.clock import utcnow

logger = logging.getLogger(__name__)

Handler = Callable[["JobContext", dict[str, Any]], dict[str, Any]]
CancelHook = Callable[[Any, dict[str, Any]], None]


def _current_trace() -> str | None:
    from maya.observability.tracing import current_trace_id

    return current_trace_id()


def _waited(job: dict[str, Any]) -> float | None:
    """How long the job sat in the queue: what §20 calls job wait time. A retried job
    measures from its requeue, not its original submission, so backoff is not counted
    as queueing pressure."""
    started, created = job.get("started_at"), job.get("run_after") or job.get("created_at")
    if not isinstance(started, dt.datetime) or not isinstance(created, dt.datetime):
        return None
    return max(0.0, (started - created).total_seconds())


class JobCancelled(Exception):
    """Raised inside a handler when cancellation was requested."""


class JobContext:
    """What a handler sees: progress reporting and cooperative cancellation."""

    def __init__(self, queue: "JobQueue", job: dict[str, Any]) -> None:
        self.queue = queue
        self.job = job
        self.actor = job["owner"]
        self.trace_id = job["trace_id"]

    def progress(self, pct: int, message: str) -> None:
        with self.queue.uow_factory(self.actor) as uow:
            row = uow.repo("jobs").require(self.job["id"])
            logs = list(row["logs"]) + [{"at": utcnow().isoformat(), "pct": pct, "msg": message}]
            uow.repo("jobs").update(
                self.job["id"], {"progress": pct, "message": message, "logs": logs[-200:]}
            )
            if row["cancel_requested"]:
                raise JobCancelled(message)

    def check_cancel(self) -> None:
        with self.queue.uow_factory(self.actor) as uow:
            if uow.repo("jobs").require(self.job["id"])["cancel_requested"]:
                raise JobCancelled("cancelled")


@dataclass
class Fairness:
    """The §15.2 caps, read from configuration once and passed to every claim."""

    fair: bool = True
    per_user_concurrent: int = 4
    per_user_queued: int = 200
    max_depth: int = 2000
    seconds_per_job: float = 10.0
    candidates: int = 200

    @classmethod
    def from_settings(cls, settings: Any) -> "Fairness":
        return cls(
            fair=settings.bool("jobs.fair", True),
            per_user_concurrent=settings.int("jobs.per_user.max_concurrent", 4),
            per_user_queued=settings.int("jobs.per_user.max_queued", 200),
            max_depth=settings.int("jobs.queue.max_depth", 2000),
            seconds_per_job=float(settings.get("jobs.queue.seconds_per_job", "10") or 10),
            candidates=settings.int("jobs.claim_candidates", 200),
        )


class JobQueue:
    """Submission, claiming, execution, retry and cancellation."""

    def __init__(
        self,
        uow_factory: Callable[..., Any],
        *,
        workers: int = 2,
        max_attempts: int = 3,
        fairness: Fairness | None = None,
    ) -> None:
        self.uow_factory = uow_factory
        self.handlers: dict[str, Handler] = {}
        self.cancel_hooks: dict[str, CancelHook] = {}
        self.n_workers = workers
        self.max_attempts = max_attempts
        self.fairness = fairness or Fairness()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def register(
        self, job_type: str, handler: Handler, *, on_cancel: CancelHook | None = None
    ) -> None:
        """``on_cancel(uow, params)`` runs, in the cancelling transaction, when a job of this
        type is cancelled before it ran — so what it would have finished (a pin row) is
        closed rather than left waiting for a run that will never come."""
        self.handlers[job_type] = handler
        if on_cancel is not None:
            self.cancel_hooks[job_type] = on_cancel

    # -- submission --------------------------------------------------------
    def submit(
        self,
        uow: Any,
        job_type: str,
        params: dict[str, Any],
        *,
        owner: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Enqueue inside the caller's transaction; dedupe on the idempotency key."""
        if job_type not in self.handlers:
            raise MayaError(f"No handler registered for job type '{job_type}'")
        self.check_backpressure(uow, owner)
        params_hash = djson.canonical_hash(params)
        if idempotency_key:
            # concurrent submitters of one key queue here; the second then finds the first
            uow.lock(f"job:idempotency:{idempotency_key}")
            existing = uow.repo("jobs").find_one(idempotency_key=idempotency_key)
            if existing:
                if existing["params_hash"] != params_hash:
                    raise ConflictError(
                        "Idempotency key reused with different parameters", key=idempotency_key
                    )
                return existing
        job = uow.repo("jobs").add(
            {
                "job_type": job_type,
                "owner": owner,
                "state": "queued",
                "params": params,
                "params_hash": params_hash,
                "idempotency_key": idempotency_key,
                "max_attempts": self.max_attempts,
                "logs": [],
                "trace_id": _current_trace() or secrets.token_hex(16),
            }
        )
        from maya.observability.metrics import METRICS

        METRICS.inc("maya_job_submissions_total", {"type": job_type})
        uow.after_commit(self._wake.set)
        return job

    def check_backpressure(self, uow: Any, owner: str) -> None:
        """Refuse work MAYA cannot start, before the row is written (§15.4).

        Two limits, both honest about what the caller should do next: the queue as a
        whole, and this owner's share of it. The estimate is the queue's own depth
        divided by the workers that will drain it, which is a guess — but a guess made
        from the numbers the caller can see on the jobs page, not an arbitrary delay.
        """
        f = self.fairness
        if f.max_depth <= 0 and f.per_user_queued <= 0:
            return
        depth = uow.repo("jobs").count(state="queued")
        mine = uow.repo("jobs").count(state="queued", owner=owner)
        for limit, seen, reason, what in (
            (f.max_depth, depth, "queue_depth", "MAYA's job queue is full"),
            (f.per_user_queued, mine, "per_user_queued", "You already have too many jobs waiting"),
        ):
            if 0 < limit <= seen:
                from maya.observability.metrics import METRICS

                METRICS.inc("maya_job_shed_total", {"reason": reason})
                wait = self.wait_estimate(depth)
                raise QuotaExceeded(
                    f"{what} ({seen} queued, the limit is {limit}). Nothing was queued. "
                    f"The queue should clear in about {wait} second(s); submit again then, "
                    "or cancel jobs you no longer need.",
                    reason=reason,
                    queued=seen,
                    limit=limit,
                    estimated_wait_seconds=wait,
                )

    def wait_estimate(self, depth: int) -> int:
        """Seconds the queue is expected to take to clear, given the workers draining it."""
        workers = max(1, self.n_workers)
        return int(depth * self.fairness.seconds_per_job / workers)

    def cancel(self, uow: Any, job_id: str) -> dict[str, Any]:
        job = uow.repo("jobs").require(job_id)
        if job["state"] == "queued":
            hook = self.cancel_hooks.get(job["job_type"])
            if hook is not None:
                hook(uow, job["params"])
            return uow.repo("jobs").update(
                job_id, {"state": "cancelled", "cancel_requested": True, "finished_at": utcnow()}
            )
        if job["state"] == "running":
            return uow.repo("jobs").update(job_id, {"cancel_requested": True})
        return job

    # -- execution ---------------------------------------------------------
    def run_one(self, worker: str = "inline") -> bool:
        """Claim and run a single job. Returns False when the queue is empty."""
        f = self.fairness
        with self.uow_factory("system") as uow:
            job = uow.repo("jobs").claim_next(
                worker,
                fair=f.fair,
                max_per_user=f.per_user_concurrent,
                candidates=f.candidates,
            )
        if job is None:
            return False
        self._execute(job)
        return True

    def drain(self, limit: int = 1000) -> int:
        """Run jobs inline until the queue is empty (tests, CLI, single-shot tools)."""
        n = 0
        while n < limit and self.run_one():
            n += 1
        return n

    def _execute(self, job: dict[str, Any]) -> None:
        import time
        from maya.observability import tracing
        from maya.observability.metrics import METRICS

        parent = (
            tracing.TraceContext(job["trace_id"], secrets.token_hex(8))
            if len(job["trace_id"]) == 32
            else None
        )
        started = time.perf_counter()
        with tracing.span(
            f"job {job['job_type']}", parent=parent, attributes={"maya.job_id": job["id"]}
        ):
            outcome = self._run_handler(job)
        METRICS.inc("maya_job_runs_total", {"type": job["job_type"], "outcome": outcome})
        METRICS.observe(
            "maya_job_duration_seconds", time.perf_counter() - started, {"type": job["job_type"]}
        )
        waited = _waited(job)
        if waited is not None:
            METRICS.observe("maya_job_wait_seconds", waited, {"type": job["job_type"]})

    def _run_handler(self, job: dict[str, Any]) -> str:
        from maya.observability import logs

        with logs.bound(
            request_id=job["trace_id"],
            actor=job["owner"],
            object_ref=f"maya://job/{job['id']}",
            channel="worker",
        ):
            return self._handle(job)

    def _handle(self, job: dict[str, Any]) -> str:
        ctx = JobContext(self, job)
        try:
            result = self.handlers[job["job_type"]](ctx, job["params"])
            self._finish(job["id"], "succeeded", result=result or {}, progress=100)
            return "succeeded"
        except JobCancelled:
            self._finish(job["id"], "cancelled", error="cancelled by request")
            return "cancelled"
        except MayaError as exc:
            # A deliberate refusal (quality failure, contract mismatch) is not
            # retried: running it again would refuse again.
            self._finish(
                job["id"],
                "failed",
                error=f"{type(exc).__name__}: {exc.message}",
                result={"problem": exc.to_problem()},
            )
            return "failed"
        except Exception as exc:  # noqa: BLE001 - the job boundary records everything
            logger.exception("job %s failed", job["id"])
            self._retry_or_dead_letter(
                job, f"{type(exc).__name__}: {exc}", traceback.format_exc(limit=8)
            )
            return "error"

    def _retry_or_dead_letter(self, job: dict[str, Any], error: str, tb: str) -> None:
        if job["attempts"] < job["max_attempts"]:
            delay = min(60.0, 2 ** job["attempts"]) * (0.5 + random.random())
            with self.uow_factory("system") as uow:
                uow.repo("jobs").update(
                    job["id"],
                    {
                        "state": "queued",
                        "error": error,
                        "run_after": utcnow() + dt.timedelta(seconds=delay),
                    },
                )
            return
        self._finish(job["id"], "dead_letter", error=error, result={"traceback": tb})

    def _finish(
        self,
        job_id: str,
        state: str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        progress: int | None = None,
    ) -> None:
        with self.uow_factory("system") as uow:
            changes: dict[str, Any] = {"state": state, "finished_at": utcnow()}
            if result is not None:
                changes["result"] = result
            if error is not None:
                changes["error"] = error
            if progress is not None:
                changes["progress"] = progress
            uow.repo("jobs").update(job_id, changes)
            uow.audit(
                f"job.{state}",
                object_type="job",
                object_ref=f"maya://job/{job_id}",
                detail={"error": error} if error else {},
                principal_type="system",
                channel="worker",
            )

    # -- worker threads ------------------------------------------------------
    def start(self) -> None:
        name = f"{os.getpid()}"
        for i in range(self.n_workers):
            t = threading.Thread(
                target=self._loop, args=(f"{name}-w{i}",), daemon=True, name=f"maya-worker-{i}"
            )
            t.start()
            self._threads.append(t)

    def _loop(self, worker: str) -> None:
        while not self._stop.is_set():
            try:
                if not self.run_one(worker):
                    self._wake.wait(1.0)
                    self._wake.clear()
            except Exception:  # noqa: BLE001 - a worker never dies on one bad job
                logger.exception("worker %s loop error", worker)
                self._stop.wait(1.0)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        for t in self._threads:
            t.join(timeout)

    def reap(self) -> int:
        """Requeue jobs left ``running`` by a process that died (§13.3)."""
        with self.uow_factory("system") as uow:
            stale = uow.repo("jobs").list(state="running")
            for job in stale:
                uow.repo("jobs").update(
                    job["id"],
                    {"state": "queued", "worker": None, "error": "requeued by the reaper"},
                )
            return len(stale)
