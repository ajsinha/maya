"""
MAYA — notification.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Delivery, not a queue. The outstanding work is derived from the register; these
endpoints make it arrive somewhere rather than waiting to be looked at.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from fastapi import Request

from core.notify import CHANNEL_MEANING
from routes.base import Body, Routes



class SubscriptionIn(Body):
    name: str
    url: str
    kinds: List[str] = Field(default_factory=list)
    owner: str

class NotifyIn(Body):
    channel: Optional[str] = None
    dry_run: bool = False


class NotificationRoutes(Routes):
    def register(self) -> None:
        notifications, api = self.ctx["notifications"], self.api

        @self.app.get(f"{api}/events", tags=["events"])
        def events(request: Request, after: int = 0, limit: int = 100,
                   kind: str = ""):
            """The domain event stream, which is the evidence chain read
            forwards.

            **There is no event table.** Every act that changes this register
            already appends to the chain — hash-linked, append-only, in a total
            order — and a second event log would be a second thing to keep in
            step. The first time they disagreed nobody could say which was true,
            which is the failure a governance platform cannot afford, because
            the chain is what an examiner is shown.

            Store `cursor` and pass it back as `after`. Each event carries its
            `seq` and the node's `content_hash`: deduplicate on the second, not
            on an identifier this platform invented.
            """
            self.authorise(request, "evidence:read")
            kinds = [k.strip() for k in kind.split(",") if k.strip()]
            return self.guard(
                lambda: self.ctx["event_stream"].read(after, limit,
                                                      kinds or None))

        @self.app.get(f"{api}/events/kinds", tags=["events"])
        def event_kinds(request: Request):
            """Every kind this register has actually produced.

            Derived rather than declared: a hand-written list goes stale the
            first time somebody appends a new kind, and a subscriber filtering
            on one that no longer exists receives nothing and is told nothing.
            """
            self.authorise(request, "evidence:read")
            return {"kinds": self.ctx["event_stream"].kinds(),
                    "head": self.ctx["event_stream"].head()}

        @self.app.get(f"{api}/subscriptions", tags=["events"])
        def subscriptions(request: Request):
            """Every subscriber, and how far behind each has fallen.

            Secrets are never returned here: one a listing endpoint hands back
            is held by everybody with read access.
            """
            self.authorise(request, "principal:read")
            return self.guard(
                lambda: self.ctx["subscriptions"].across_the_estate())

        @self.app.post(f"{api}/subscriptions", status_code=201,
                       tags=["events"])
        def subscribe(request: Request, body: SubscriptionIn):
            """Register a receiver. The secret is returned once and never again.

            `kinds` is mandatory and `*` is refused. A chain node's payload
            carries model inventory, findings and exposure figures, so what
            leaves the institution is a decision somebody takes — and *we send
            you all our events* is not one anybody made.
            """
            who = self.authorise(request, "principal:manage")
            return self.guard(lambda: self.ctx["subscriptions"].subscribe(
                name=body.name, url=body.url, kinds=body.kinds,
                owner=body.owner, actor=self.actor(who)))

        @self.app.post(f"{api}/subscriptions/{{reference}}/resume",
                       tags=["events"])
        def resume_subscription(request: Request, reference: str):
            """Bring a suspended subscription back, from where it stopped."""
            who = self.authorise(request, "principal:manage")
            return self.guard(lambda: self.ctx["subscriptions"].resume(
                reference, actor=self.actor(who)))

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
