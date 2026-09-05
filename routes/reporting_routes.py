"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Risk appetite and the board pack over HTTP.

`build` computes without recording; `cut` records. The split matters: somebody
preparing for a meeting should be able to see what the pack will say without
creating the pack the committee will later be minuted against.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Request
from pydantic import BaseModel, Field

from core.reporting import NO_COMPOSITE, STATUS_MEANING
from routes.base import Routes


class AppetiteIn(BaseModel):
    metric: str
    limit: float
    rationale: str
    amber: Optional[float] = None
    scope: Dict[str, Any] = Field(default_factory=dict)
    owner: str = ""
    review_at: Optional[float] = None


class RetireIn(BaseModel):
    metric: str
    scope: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class PackIn(BaseModel):
    period: str = ""
    scope: Dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class ReportingRoutes(Routes):
    def register(self) -> None:
        api = self.api
        appetite = self.ctx["appetite"]
        packs = self.ctx["board_packs"]

        # ------------------------------------------------------- appetite
        @self.app.get(f"{api}/risk-appetite/metrics", tags=["reporting"])
        def metrics(request: Request):
            """What may be held to a limit, and what each indicator is for."""
            self.principal(request)
            return {**appetite.vocabulary(), "statuses": STATUS_MEANING}

        @self.app.get(f"{api}/risk-appetite", tags=["reporting"])
        def in_force(request: Request):
            """Every live limit, least specific scope first."""
            self.principal(request)
            return {"appetite": appetite.in_force()}

        @self.app.post(f"{api}/risk-appetite", status_code=201, tags=["reporting"])
        def declare(request: Request, body: AppetiteIn):
            """Set a limit. Setting one over an existing limit versions it."""
            who = self.authorise(request, "policy:publish")
            return self.guard(lambda: appetite.declare(
                metric=body.metric, limit=body.limit, rationale=body.rationale,
                amber=body.amber, scope=body.scope, owner=body.owner,
                review_at=body.review_at, actor=self.actor(who)))

        @self.app.post(f"{api}/risk-appetite/retire", tags=["reporting"])
        def retire(request: Request, body: RetireIn):
            who = self.authorise(request, "policy:publish")
            return self.guard(lambda: appetite.retire(
                body.metric, scope=body.scope, reason=body.reason,
                actor=self.actor(who)))

        @self.app.get(f"{api}/risk-appetite/history/{{metric}}", tags=["reporting"])
        def history(request: Request, metric: str):
            """Every version of one limit, so a relaxation is findable."""
            self.principal(request)
            return {"metric": metric, "versions": appetite.history(metric)}

        # ------------------------------------------------------ board pack
        @self.app.post(f"{api}/board-packs/preview", tags=["reporting"])
        def preview(request: Request, body: PackIn):
            """What the pack would say, without creating one.

            Somebody preparing for a meeting should be able to look before the
            committee is minuted against what they find.
            """
            self.authorise(request, "report:read")
            return self.guard(lambda: packs.build(period=body.period,
                                                  scope=body.scope))

        @self.app.post(f"{api}/board-packs", status_code=201, tags=["reporting"])
        def cut(request: Request, body: PackIn):
            """Record the pack. This is the one a minute refers to."""
            who = self.authorise(request, "report:cut")
            return self.guard(lambda: packs.cut(
                period=body.period, scope=body.scope, note=body.note,
                actor=self.actor(who)))

        @self.app.get(f"{api}/board-packs", tags=["reporting"])
        def listing(request: Request, limit: int = 12):
            self.authorise(request, "report:read")
            return {"packs": packs.history(limit=limit),
                    "no_composite": NO_COMPOSITE}

        @self.app.get(f"{api}/board-packs/{{pack_id}}", tags=["reporting"])
        def one(request: Request, pack_id: str):
            """A pack as it was read, not as it would be recomputed today."""
            self.authorise(request, "report:read")
            return self.guard(lambda: packs.get(pack_id))
