"""
MAYA — baseline import and compliance debt.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Getting an existing estate into the register without pretending it arrived
compliant. Debt is reported separately from breach on every endpoint here, for
the same reason it must be on every view: a Tier 1 model that arrived last week
and a Tier 1 model that missed its validation are different situations.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import Request
from pydantic import BaseModel, Field

from core.baseline import gaps
from routes.base import Routes


class ImportIn(BaseModel):
    source: str
    models: List[Dict[str, Any]] = Field(default_factory=list)
    note: str = ""


class PlanIn(BaseModel):
    plan: str


class BaselineRoutes(Routes):
    def register(self) -> None:
        baseline, debts = self.ctx["baseline"], self.ctx["debts"]
        registry, documents = self.ctx["registry"], self.ctx["documents"]
        api = self.api

        @self.app.get(f"{api}/baseline/gaps", tags=["baseline"])
        def gap_catalogue(request: Request):
            """What will be checked. Gaps are computed, so this is the full list."""
            self.principal(request)
            return {"gaps": gaps.describe()}

        @self.app.get(f"{api}/baseline", tags=["baseline"])
        def portfolio(request: Request):
            """The burn-down: the number a programme is actually judged on."""
            self.authorise(request, "baseline:read")
            return {**baseline.portfolio(), "batches": baseline.batches()}

        @self.app.post(f"{api}/baseline/imports", status_code=201, tags=["baseline"])
        def import_batch(request: Request, body: ImportIn):
            who = self.authorise(request, "baseline:import")
            return self.guard(lambda: baseline.import_models(
                body.source, body.models, self.actor(who), body.note))

        @self.app.get(f"{api}/baseline/debt", tags=["baseline"])
        def model_debt(request: Request, urn: str):
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "baseline:read", model=model)
            return {"model": urn, **debts.status(model["id"]),
                    "items": debts.open_for(model["id"])}

        @self.app.post(f"{api}/baseline/debt/{{debt_id}}/plan", tags=["baseline"])
        def plan(request: Request, debt_id: str, body: PlanIn):
            who = self.authorise(request, "baseline:plan")
            return self.guard(lambda: debts.plan_for(debt_id, body.plan,
                                                     self.actor(who)))

        @self.app.post(f"{api}/baseline/reconcile", tags=["baseline"])
        def reconcile(request: Request, urn: str):
            """Close debt whose evidence has arrived; expire what is overdue.

            Idempotent, and safe to run on a schedule: it only makes the stored
            position agree with what the register can already see.
            """
            model = self.guard(lambda: registry.require(urn))
            who = self.authorise(request, "baseline:plan", model=model)
            state = documents.build_context(urn)
            return self.guard(lambda: debts.reconcile(model["id"], state,
                                                      self.actor(who)))
