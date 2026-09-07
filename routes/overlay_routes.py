"""
MAYA — the overlay register.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Post-model adjustments: proposed, approved by somebody else, measured every
period, and escalated once they stop being temporary.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Request
from pydantic import Field

from core.overlays import KIND_MEANING, KINDS
from routes.base import Body, Routes


class OverlayIn(Body):
    urn: str
    name: str
    kind: str
    rationale: str
    owner: str
    direction: str = "increase"
    basis: Dict[str, Any] = Field(default_factory=dict)
    days: Optional[int] = None


class MeasureIn(Body):
    period: str
    base_value: float
    adjusted_value: float


class CloseIn(Body):
    status: str = "withdrawn"
    reason: str


class OverlayRoutes(Routes):
    def register(self) -> None:
        overlays, registry = self.ctx["overlays"], self.ctx["registry"]
        api = self.api

        @self.app.get(f"{api}/overlay-kinds", tags=["overlays"])
        def kinds(request: Request):
            self.principal(request)
            return {"kinds": [{"kind": k, "means": KIND_MEANING[k]} for k in KINDS]}

        @self.app.get(f"{api}/overlays", tags=["overlays"])
        def list_overlays(request: Request, urn: str):
            """How much of this model's number is the model, and how much is us."""
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "overlay:read", model=model)
            return {"model": urn, **overlays.status(model["id"])}

        @self.app.post(f"{api}/overlays", status_code=201, tags=["overlays"])
        def propose(request: Request, body: OverlayIn):
            model = self.guard(lambda: registry.require(body.urn))
            who = self.authorise(request, "overlay:propose", model=model)
            return self.guard(lambda: overlays.propose(
                model["id"], body.name, body.kind, body.rationale, body.owner,
                body.direction, body.basis, days=body.days,
                actor=self.actor(who)))

        @self.app.get(f"{api}/overlays/{{overlay_id}}", tags=["overlays"])
        def read(request: Request, overlay_id: str):
            self.authorise(request, "overlay:read")
            return self.guard(lambda: overlays.reading(overlay_id))

        @self.app.post(f"{api}/overlays/{{overlay_id}}/approve", tags=["overlays"])
        def approve(request: Request, overlay_id: str, days: Optional[int] = None):
            who = self.authorise(
                request, "overlay:approve",
                model=self.model_behind(
                    self.guard(lambda: overlays.require(overlay_id))))
            return self.guard(lambda: overlays.approve(overlay_id, self.actor(who),
                                                       days))

        @self.app.post(f"{api}/overlays/{{overlay_id}}/measure", status_code=201,
                       tags=["overlays"])
        def measure(request: Request, overlay_id: str, body: MeasureIn):
            who = self.authorise(
                request, "overlay:measure",
                model=self.model_behind(
                    self.guard(lambda: overlays.require(overlay_id))))
            return self.guard(lambda: overlays.measure(
                overlay_id, body.period, body.base_value, body.adjusted_value,
                self.actor(who)))

        @self.app.post(f"{api}/overlays/{{overlay_id}}/renew", tags=["overlays"])
        def renew(request: Request, overlay_id: str, days: Optional[int] = None,
                  period: Optional[str] = None):
            """Extend it. Refused unless its size has been measured."""
            who = self.authorise(
                request, "overlay:approve",
                model=self.model_behind(
                    self.guard(lambda: overlays.require(overlay_id))))
            return self.guard(lambda: overlays.renew(overlay_id, self.actor(who),
                                                     days, period))

        @self.app.post(f"{api}/overlays/{{overlay_id}}/close", tags=["overlays"])
        def close(request: Request, overlay_id: str, body: CloseIn):
            who = self.authorise(
                request, "overlay:approve",
                model=self.model_behind(
                    self.guard(lambda: overlays.require(overlay_id))))
            return self.guard(lambda: overlays.close(overlay_id, body.status,
                                                     body.reason, self.actor(who)))
