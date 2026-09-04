"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

An in-process loop, offered as a convenience.

This is the least important file in the package, deliberately. Every job is
idempotent and reachable over the API, so cron, a Kubernetes CronJob, an
Airflow DAG or a person pressing a button are all equally supported and produce
identical results. The loop exists so that a fresh deployment does something
sensible without anyone wiring up a scheduler first.

It is off by default in anything but a single-node deployment, because two
replicas both running it is two runs — harmless, since the jobs are idempotent,
but wasteful and confusing in a log.

The thread is a daemon and swallows nothing: a job that fails is already caught
and recorded by the runner, and a failure in the loop itself is logged loudly
rather than silently ending the thread.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from core.log import get_logger
from core.scheduler.runner import Scheduler

logger = get_logger(__name__)


class SchedulerLoop:
    """Runs the scheduler on an interval, in a daemon thread."""

    def __init__(self, scheduler: Scheduler, interval_seconds: float = 3600.0,
                 actor: str = "scheduler"):
        self.scheduler = scheduler
        self.interval = max(interval_seconds, 60.0)
        self.actor = actor
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="maya-scheduler",
                                        daemon=True)
        self._thread.start()
        logger.info("scheduler loop started; every %.0f seconds. It is a "
                    "convenience: the same jobs are reachable over the API and "
                    "are idempotent either way.", self.interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
            logger.info("scheduler loop stopped")

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        # Wait once before the first pass so a restart loop cannot turn into a
        # run loop, and so startup is not competing with the first requests.
        while not self._stop.wait(self.interval):
            try:
                report = self.scheduler.run(actor=self.actor)
                logger.info("scheduler pass: %s", report["detail"])
            except Exception as exc:      # the thread must survive, and be heard
                logger.exception("scheduler pass failed, continuing: %s", exc)
