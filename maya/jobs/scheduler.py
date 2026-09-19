"""
A small interval scheduler for maintenance sweeps (§10.4, §9.4): SLA escalation
and execution-warrant expiry notices. Each task is idempotent, so a restart or a
second node running the same sweep sends nothing twice.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self) -> None:
        self.tasks: list[tuple[str, float, Callable[[], Any]]] = []
        self._last: dict[str, float] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def every(self, name: str, seconds: float, fn: Callable[[], Any]) -> None:
        self.tasks.append((name, seconds, fn))

    def run_due(self, now: float | None = None) -> list[str]:
        """Run every task whose interval has elapsed; returns the names that ran."""
        now = time.monotonic() if now is None else now
        ran = []
        for name, seconds, fn in self.tasks:
            if now - self._last.get(name, -1e18) >= seconds:
                self._last[name] = now
                try:
                    fn()
                    ran.append(name)
                except Exception:  # noqa: BLE001 - one failing sweep must not stop the others
                    logger.exception("scheduled task %s failed", name)
        return ran

    def start(self, tick: float = 60.0) -> None:
        def loop() -> None:
            while not self._stop.wait(tick):
                self.run_due()

        self._thread = threading.Thread(target=loop, name="maya-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(5)
