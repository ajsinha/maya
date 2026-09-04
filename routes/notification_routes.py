"""
MAYA — notification.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Delivery, not a queue. The outstanding work is derived from the register; these
endpoints make it arrive somewhere rather than waiting to be looked at.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Request
from pydantic import BaseModel

from core.notify import CHANNEL_MEANING
from routes.base import Routes


class NotifyIn(BaseModel):
    channel: Optional[str] = None
    dry_run: bool = False


class NotificationRoutes(Routes):
    def register(self) -> None:
        notifications, api = self.ctx["notifications"], self.api

        @self.app.get(f"{api}/notifications", tags=["notifications"])
        def status(request: Request):
            """Which channels work, and whether anything is reaching anybody."""
            self.principal(request)
            return {**notifications.status(),
                    "channel_meanings": [{"channel": k, "means": v}
                                         for k, v in CHANNEL_MEANING.items()]}

        @self.app.get(f"{api}/notifications/history", tags=["notifications"])
        def history(request: Request, principal: Optional[str] = None,
                    limit: int = 50):
            """What was sent, suppressed and failed. Failures are kept."""
            self.authorise(request, "principal:read")
            return {"deliveries": notifications.history(principal, limit)}

        @self.app.get(f"{api}/notifications/preview", tags=["notifications"])
        def preview(request: Request):
            """The digest this principal would receive, without sending it."""
            who = self.principal(request)
            return self.guard(lambda: notifications.digest_for(who))

        @self.app.post(f"{api}/notifications/run", tags=["notifications"])
        def run(request: Request, body: NotifyIn):
            """Notify everybody with outstanding work, once.

            An ordinary authenticated call, like every other scheduled act here:
            cron, a CronJob or a person produce identical results. A worklist
            unchanged since the last message is suppressed rather than repeated.
            """
            who = self.authorise(request, "scheduler:run")
            return self.guard(lambda: notifications.run(
                channel=body.channel, dry_run=body.dry_run,
                actor=self.actor(who)))
