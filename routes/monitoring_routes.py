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

from fastapi import HTTPException, Request
from pydantic import Field

from core.monitoring import ADMISSIBLE_TESTS, KINDS
from routes.base import Body, Routes


class MonitoringPlanIn(Body):
    urn: str
    semver: str
    #: Empty means the class-aware defaults, which is not a convenience: a
    #: blank form produces either a plan copied from the last model or a plan
    #: with one monitor on it.
    items: List[Dict[str, Any]] = Field(default_factory=list)
    rationale: str = ""


class MonitorIn(Body):
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


class EvaluateIn(Body):
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

        @self.app.get(f"{api}/adaptive-change", tags=["monitoring"])
        def adaptive_change(request: Request, urn: str = "", semver: str = ""):
            """Models that change themselves, and whether they have wandered.

            **A T4 has no version bump for anything to notice**, which is the
            whole problem: every other control here fires on a version, and an
            adaptive model changes underneath one nobody re-approved.

            Read `since_last_decision` rather than the individual steps. A model
            re-fitting nightly and moving a tenth of a percent each time has
            moved three percent in a month, and every single step passed a
            per-change threshold comfortably — which is how an adaptive model
            ends up somewhere nobody approved without any individual act being
            wrong.
            """
            self.authorise(request, "monitor:read")
            watching = self.ctx["adaptive_change"]
            if urn and semver:
                model = self.guard(
                    lambda: self.ctx["registry"].require(urn))
                self.authorise(request, "monitor:read", model=model)
                return self.guard(lambda: watching.trajectory(urn, semver))
            return self.guard(lambda: watching.sweep())

        @self.app.get(f"{api}/inference-posture", tags=["monitoring"])
        def inference_posture(request: Request):
            """What this instance is holding, and what it is not saying.

            Two lines repay reading. `keyed_digests` false means a digest of a
            small feature vector — an age, a postcode, a band — is a lookup
            table anybody with the same hash function can enumerate, which is
            worse than storing the values because it is stored under a name
            that stops anybody worrying about it. `past_retention` above zero
            means the batch has not run, and a retention period nothing
            enforces is a policy document.
            """
            self.authorise(request, "monitor:read")
            return self.guard(lambda: self.ctx["inference"].posture())

        @self.app.get(f"{api}/inference", tags=["monitoring"])
        def inference_for(request: Request, urn: str, limit: int = 100):
            """What this model was asked and answered, at the rate its tier
            selects.

            An empty answer distinguishes two different facts: a model nobody
            has called, and a model whose calls the sampler did not select.
            """
            model = self.guard(lambda: self.ctx["registry"].require(urn))
            self.authorise(request, "monitor:read", model=model)
            return self.guard(
                lambda: self.ctx["inference"].for_model(urn, limit))

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

        @self.app.get(f"{api}/monitor-defaults", tags=["monitoring"])
        def monitor_defaults(request: Request, urn: str):
            """What this model's class and tier say it should be watched for.

            And, as importantly, what it should NOT be: a model with no
            performance monitor because its class cannot answer that question,
            and one with no performance monitor because nobody got round to it,
            look identical on every coverage screen ever built.
            """
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "monitor:read", model=model)
            return self.guard(lambda: self.ctx["monitoring_defaults"].propose(
                urn, model["id"]))

        @self.app.post(f"{api}/monitor-defaults", status_code=201,
                       tags=["monitoring"])
        def seed_monitor_defaults(request: Request, urn: str,
                                  owner: str = ""):
            """Create the proposed monitors that are not already there.

            Seeding is an explicit act rather than something registration does
            for you: an estate that acquires monitors nobody asked for is an
            estate whose coverage nobody understands. Idempotent by kind and
            test, so running it twice is safe and says so.
            """
            model = self.guard(lambda: registry.require(urn))
            who = self.authorise(request, "monitor:define", model=model)
            actor = self.actor(who)
            return self.guard(lambda: self.ctx["monitoring_defaults"].seed(
                urn, model["id"], owner=owner or model.get("owner") or actor,
                actor=actor))

        @self.app.get(f"{api}/monitoring-plans", tags=["monitoring"])
        def monitoring_plans(request: Request,
                             urn: Optional[str] = None,
                             semver: Optional[str] = None):
            """One version's plan, or every plan authored and never inherited.

            The second is the report this exists for: *this model has a
            monitoring plan and is not monitored* is a sentence no institution
            wants to be able to say about itself, and almost every institution
            can.
            """
            if urn is None:
                self.authorise(request, "monitor:read",
                               estate_wide="reading every monitoring plan")
                return self.guard(
                    lambda: self.ctx["monitoring_plans"].outstanding())
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "monitor:read", model=model)
            if semver is None:
                raise HTTPException(422, {
                    "error": "semver_required",
                    "detail": "a monitoring plan is authored against a "
                              "version, not a model",
                    "remediation": "add semver=..., or omit urn for every "
                                   "outstanding plan"})
            return self.guard(
                lambda: self.ctx["monitoring_plans"].for_version(urn, semver))

        @self.app.post(f"{api}/monitoring-plans", status_code=201,
                       tags=["monitoring"])
        def author_plan(request: Request, body: MonitoringPlanIn):
            """Write the plan. With no items, the class-aware defaults."""
            model = self.guard(lambda: registry.require(body.urn))
            who = self.authorise(request, "monitor:define", model=model)
            return self.guard(lambda: self.ctx["monitoring_plans"].author(
                body.urn, body.semver, items=body.items,
                rationale=body.rationale, actor=self.actor(who)))

        @self.app.post(f"{api}/monitoring-plans/inherit", tags=["monitoring"])
        def inherit_plan(request: Request, urn: str, semver: str,
                         owner: str = ""):
            """Turn the plan into the monitors it describes.

            A separate act performed by a person rather than something
            approval does quietly: making approval create monitors would mean
            nobody looked at the plan again, and the drift between the plan and
            the monitors is the whole reason this exists.
            """
            model = self.guard(lambda: registry.require(urn))
            who = self.authorise(request, "monitor:define", model=model)
            return self.guard(lambda: self.ctx["monitoring_plans"].inherit(
                urn, semver, owner=owner, actor=self.actor(who)))

        @self.app.post(f"{api}/monitors/{{monitor_id}}/evaluate", tags=["monitoring"])
        def evaluate(request: Request, monitor_id: str, body: EvaluateIn):
            """Compute one observation. Refused over an immature cohort."""
            who = self.authorise(
                request, "monitor:evaluate",
                model=self.model_behind(
                    self.guard(lambda: monitors.require(monitor_id))))
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
            who = self.authorise(
                request, "monitor:define",
                model=self.model_behind(
                    self.guard(lambda: monitors.require(monitor_id))))
            return self.guard(lambda: monitors.set_status(monitor_id, status,
                                                          self.actor(who)))
