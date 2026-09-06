"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The scheduler: where a computed condition becomes a recorded consequence.

Everything here is idempotent and derives its own work from the register, so a
run is an ordinary authenticated call — from an in-process loop, from cron, or
from a person. MAYA no more insists on owning the clock than it insists on
owning execution.
"""
from core.scheduler.jobs import JOBS, Job, JobContext
from core.scheduler.loop import SchedulerLoop
from core.scheduler.runner import Scheduler, SchedulerError

__all__ = ["JOBS", "Job", "JobContext", "Scheduler", "SchedulerError", "SchedulerLoop"]
