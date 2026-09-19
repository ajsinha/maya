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
**observable** (every job carries a trace id and a progress log).

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
from typing import Any, Callable

from maya.core import djson
from maya.core.errors import ConflictError, MayaError
from maya.core.clock import utcnow

logger = logging.getLogger(__name__)

Handler = Callable[["JobContext", dict[str, Any]], dict[str, Any]]
CancelHook = Callable[[Any, dict[str, Any]], None]


def _current_trace() -> str | None:
    from maya.observability.tracing import current_trace_id
    return current_trace_id()


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
            uow.repo("jobs").update(self.job["id"], {"progress": pct, "message": message,
                                                     "logs": logs[-200:]})
            if row["cancel_requested"]:
                raise JobCancelled(message)

    def check_cancel(self) -> None:
        with self.queue.uow_factory(self.actor) as uow:
            if uow.repo("jobs").require(self.job["id"])["cancel_requested"]:
                raise JobCancelled("cancelled")


class JobQueue:
    """Submission, claiming, execution, retry and cancellation."""

    def __init__(self, uow_factory: Callable[..., Any], *, workers: int = 2,
                 max_attempts: int = 3) -> None:
        self.uow_factory = uow_factory
        self.handlers: dict[str, Handler] = {}
        self.cancel_hooks: dict[str, CancelHook] = {}
        self.n_workers = workers
        self.max_attempts = max_attempts
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def register(self, job_type: str, handler: Handler, *,
                 on_cancel: CancelHook | None = None) -> None:
        """``on_cancel(uow, params)`` runs, in the cancelling transaction, when a job of this
        type is cancelled before it ran — so what it would have finished (a pin row) is
        closed rather than left waiting for a run that will never come."""
        self.handlers[job_type] = handler
        if on_cancel is not None:
            self.cancel_hooks[job_type] = on_cancel

    # -- submission --------------------------------------------------------
    def submit(self, uow: Any, job_type: str, params: dict[str, Any], *, owner: str,
               idempotency_key: str | None = None) -> dict[str, Any]:
        """Enqueue inside the caller's transaction; dedupe on the idempotency key."""
        if job_type not in self.handlers:
            raise MayaError(f"No handler registered for job type '{job_type}'")
        params_hash = djson.canonical_hash(params)
        if idempotency_key:
            # concurrent submitters of one key queue here; the second then finds the first
            uow.lock(f"job:idempotency:{idempotency_key}")
            existing = uow.repo("jobs").find_one(idempotency_key=idempotency_key)
            if existing:
                if existing["params_hash"] != params_hash:
                    raise ConflictError("Idempotency key reused with different parameters",
                                        key=idempotency_key)
                return existing
        job = uow.repo("jobs").add({
            "job_type": job_type, "owner": owner, "state": "queued", "params": params,
            "params_hash": params_hash, "idempotency_key": idempotency_key,
            "max_attempts": self.max_attempts, "logs": [],
            "trace_id": _current_trace() or secrets.token_hex(16),
        })
        uow.after_commit(self._wake.set)
        return job

    def cancel(self, uow: Any, job_id: str) -> dict[str, Any]:
        job = uow.repo("jobs").require(job_id)
        if job["state"] == "queued":
            hook = self.cancel_hooks.get(job["job_type"])
            if hook is not None:
                hook(uow, job["params"])
            return uow.repo("jobs").update(job_id, {"state": "cancelled", "cancel_requested": True,
                                                    "finished_at": utcnow()})
        if job["state"] == "running":
            return uow.repo("jobs").update(job_id, {"cancel_requested": True})
        return job

    # -- execution ---------------------------------------------------------
    def run_one(self, worker: str = "inline") -> bool:
        """Claim and run a single job. Returns False when the queue is empty."""
        with self.uow_factory("system") as uow:
            job = uow.repo("jobs").claim_next(worker)
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
        parent = tracing.TraceContext(job["trace_id"], secrets.token_hex(8)) \
            if len(job["trace_id"]) == 32 else None
        started = time.perf_counter()
        with tracing.span(f"job {job['job_type']}", parent=parent,
                          attributes={"maya.job_id": job["id"]}):
            outcome = self._run_handler(job)
        METRICS.inc("maya_job_runs_total", {"type": job["job_type"], "outcome": outcome})
        METRICS.observe("maya_job_duration_seconds", time.perf_counter() - started,
                        {"type": job["job_type"]})

    def _run_handler(self, job: dict[str, Any]) -> str:
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
            self._finish(job["id"], "failed", error=f"{type(exc).__name__}: {exc.message}",
                         result={"problem": exc.to_problem()})
            return "failed"
        except Exception as exc:  # noqa: BLE001 - the job boundary records everything
            logger.exception("job %s failed", job["id"])
            self._retry_or_dead_letter(job, f"{type(exc).__name__}: {exc}",
                                       traceback.format_exc(limit=8))
            return "error"

    def _retry_or_dead_letter(self, job: dict[str, Any], error: str, tb: str) -> None:
        if job["attempts"] < job["max_attempts"]:
            delay = min(60.0, 2 ** job["attempts"]) * (0.5 + random.random())
            with self.uow_factory("system") as uow:
                uow.repo("jobs").update(job["id"], {
                    "state": "queued", "error": error,
                    "run_after": utcnow() + dt.timedelta(seconds=delay)})
            return
        self._finish(job["id"], "dead_letter", error=error, result={"traceback": tb})

    def _finish(self, job_id: str, state: str, *, result: dict[str, Any] | None = None,
                error: str | None = None, progress: int | None = None) -> None:
        with self.uow_factory("system") as uow:
            changes: dict[str, Any] = {"state": state, "finished_at": utcnow()}
            if result is not None:
                changes["result"] = result
            if error is not None:
                changes["error"] = error
            if progress is not None:
                changes["progress"] = progress
            uow.repo("jobs").update(job_id, changes)
            uow.audit(f"job.{state}", object_type="job", object_ref=f"maya://job/{job_id}",
                      detail={"error": error} if error else {}, principal_type="system",
                      channel="worker")

    # -- worker threads ------------------------------------------------------
    def start(self) -> None:
        name = f"{os.getpid()}"
        for i in range(self.n_workers):
            t = threading.Thread(target=self._loop, args=(f"{name}-w{i}",), daemon=True,
                                 name=f"maya-worker-{i}")
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
                uow.repo("jobs").update(job["id"], {"state": "queued", "worker": None,
                                                    "error": "requeued by the reaper"})
            return len(stale)
