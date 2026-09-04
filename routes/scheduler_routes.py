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

from routes.base import Routes


class RunIn(BaseModel):
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
        def run(request: Request, body: RunIn):
            """Run some or all jobs. Idempotent: safe to call as often as you like."""
            who = self.authorise(request, "scheduler:run")
            return self.guard(lambda: scheduler.run(body.jobs or None,
                                                    actor=self.actor(who)))

        @self.app.get(f"{api}/scheduler/history", tags=["scheduler"])
        def history(request: Request, limit: int = 50):
            self.authorise(request, "scheduler:read")
            return {"runs": scheduler.history(limit)}
