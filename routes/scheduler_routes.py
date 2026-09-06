"""
MAYA — the scheduler.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Running the jobs is an ordinary authenticated call, so cron, a CronJob, an
Airflow DAG or a person are all equally supported and produce identical results.
MAYA no more insists on owning the clock than it insists on owning execution.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import Request
from pydantic import BaseModel, Field

from routes.base import Body, Routes


class RunIn(Body):
    jobs: List[str] = Field(
        default_factory=list,
        description="which jobs to run; empty runs all of them")


class SchedulerRoutes(Routes):
    def register(self) -> None:
        scheduler = self.ctx["scheduler"]
        api = self.api

        @self.app.get(f"{api}/scheduler", tags=["scheduler"])
        def catalogue(request: Request):
            """The jobs, what each does and why, and when each last ran."""
            self.authorise(request, "scheduler:read")
            return {"jobs": scheduler.catalogue(),
                    "health": scheduler.health(),
                    "loop_running": bool(
                        getattr(self.ctx.get("scheduler_loop"), "running", False))}

        @self.app.post(f"{api}/scheduler/run", tags=["scheduler"])
        def run(request: Request, body: Optional[RunIn] = None):
            """Run some or all jobs. Idempotent: safe to call as often as you like.

            The body is **optional**, and that is load-bearing rather than
            convenient. The recommended deployment is cron calling this endpoint,
            the documentation says exactly that, and a body-less POST returned
            422 — so a cron entry written from the documentation failed, mailed
            its error to a mailbox nobody reads, and the entire governance batch
            never ran while every other signal stayed green.
            """
            who = self.authorise(request, "scheduler:run")
            jobs = (body.jobs if body else None) or None
            return self.guard(lambda: scheduler.run(jobs, actor=self.actor(who)))

        @self.app.get(f"{api}/scheduler/history", tags=["scheduler"])
        def history(request: Request, limit: int = 50):
            self.authorise(request, "scheduler:read")
            return {"runs": scheduler.history(limit)}
