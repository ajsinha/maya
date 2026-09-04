"""
MAYA — monitors, observations and breaches.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Monitoring here is not a dashboard. A breach raises a finding, a finding can
block, and a blocking finding refuses warrant resolution — so the chain from
measurement to refusal is mechanical rather than dependent on somebody watching.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Request
from pydantic import BaseModel, Field

from core.monitoring import ADMISSIBLE_TESTS, KINDS
from routes.base import Routes


class MonitorIn(BaseModel):
    urn: str
    name: str
    kind: str
    test_key: str
    threshold: Dict[str, Any]
    owner: str
    reference: Dict[str, Any] = Field(default_factory=dict)
    slice: Dict[str, Any] = Field(default_factory=dict)
    cadence_days: float = 1.0
    label_delay_days: float = 0.0
    breach_severity: str = "Medium"
    escalate_after: int = 3


class EvaluateIn(BaseModel):
    rows: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="scored_at, score, and label once the outcome is known")
    reference: Optional[List[float]] = None
    now: Optional[float] = None


class MonitoringRoutes(Routes):
    def register(self) -> None:
        monitoring, registry = self.ctx["monitoring"], self.ctx["registry"]
        monitors = monitoring.registry
        api = self.api

        @self.app.get(f"{api}/monitor-kinds", tags=["monitoring"])
        def kinds(request: Request):
            """Which questions can be asked, and which tests can answer them."""
            self.principal(request)
            return {"kinds": [{"kind": k, "tests": list(ADMISSIBLE_TESTS[k]),
                               "needs_labels": k in ("performance", "calibration")}
                              for k in KINDS]}

        @self.app.get(f"{api}/monitors", tags=["monitoring"])
        def list_monitors(request: Request, urn: str):
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "monitor:read", model=model)
            return {"model": urn, **monitoring.status(model["id"])}

        @self.app.post(f"{api}/monitors", status_code=201, tags=["monitoring"])
        def define(request: Request, body: MonitorIn):
            model = self.guard(lambda: registry.require(body.urn))
            who = self.authorise(request, "monitor:define", model=model)
            return self.guard(lambda: monitors.define(
                model["id"], body.name, body.kind, body.test_key, body.threshold,
                body.owner, reference=body.reference, slice_=body.slice,
                cadence_days=body.cadence_days, label_delay_days=body.label_delay_days,
                breach_severity=body.breach_severity, escalate_after=body.escalate_after,
                actor=self.actor(who)))

        @self.app.post(f"{api}/monitors/{{monitor_id}}/evaluate", tags=["monitoring"])
        def evaluate(request: Request, monitor_id: str, body: EvaluateIn):
            """Compute one observation. Refused over an immature cohort."""
            who = self.authorise(request, "monitor:evaluate")
            return self.guard(lambda: monitoring.evaluate(
                monitor_id, body.rows, body.reference, body.now, self.actor(who)))

        @self.app.get(f"{api}/monitors/{{monitor_id}}/observations", tags=["monitoring"])
        def history(request: Request, monitor_id: str):
            self.authorise(request, "monitor:read")
            return {"monitor": monitors.require(monitor_id),
                    "observations": monitoring.history(monitor_id),
                    "breaches": monitoring.breaches.for_monitor(monitor_id)}

        @self.app.post(f"{api}/monitors/{{monitor_id}}/status", tags=["monitoring"])
        def set_status(request: Request, monitor_id: str, status: str):
            who = self.authorise(request, "monitor:define")
            return self.guard(lambda: monitors.set_status(monitor_id, status,
                                                          self.actor(who)))
