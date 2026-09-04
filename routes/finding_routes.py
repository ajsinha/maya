"""
MAYA — the workflow around a finding.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Raising and closing a finding live next door in ``validation_routes``. This is
everything in between: handing one over, accepting one, planning it, moving its
date — and the ageing profile a risk committee asks for, which is derived from
those acts rather than kept anywhere.

Two of these endpoints exist to be refused. Acknowledgement is refused to
anybody but the owner, and extension is refused *to* the owner, so the person
with the deadline cannot set it and the person setting it has to be somebody
else. That is the same shape as the overlay register's proposer/approver split
and the finding register's owner/verifier split, for the same reason.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Request
from pydantic import BaseModel, Field

from core.validation import ACT_MEANING, ACTS
from routes.base import Routes


class AssignIn(BaseModel):
    to: str = Field(description="who is taking the finding on")
    reason: str = Field(description="why ownership is moving")


class AcknowledgeIn(BaseModel):
    committed_at: Optional[float] = Field(
        default=None, description="the date you will close it by; defaults to the "
                                  "finding's own remediation date")
    days: Optional[float] = Field(
        default=None, description="or the same date as a number of days from now")
    plan: str = Field(default="", description="what will be done; required unless "
                                              "a plan is already recorded")


class PlanIn(BaseModel):
    plan: str


class ExtendIn(BaseModel):
    reason: str
    days: Optional[float] = None
    due_at: Optional[float] = None


class FindingWorkflowRoutes(Routes):
    def register(self) -> None:
        workflow, registry = self.ctx["finding_workflow"], self.ctx["registry"]
        findings = self.ctx["findings"]
        api = self.api

        @self.app.get(f"{api}/finding-acts", tags=["findings"])
        def acts(request: Request):
            """The acts a finding can go through, and what each one means."""
            self.principal(request)
            return {"acts": [{"act": a, "means": ACT_MEANING[a]} for a in ACTS]}

        # Registered before `/findings/{finding_id}` because a literal segment
        # behind a path parameter is a route that is never reached.
        @self.app.get(f"{api}/findings/ageing", tags=["findings"])
        def ageing(request: Request, urn: Optional[str] = None):
            """The ageing profile: severity, age, overdue and extension counts.

            Without a URN this is the estate, filtered to the models the caller
            can see — a committee pack for a population somebody cannot look at
            is a number they cannot check.
            """
            if urn:
                model = self.guard(lambda: registry.require(urn))
                self.authorise(request, "finding:read", model=model)
                return {"model": model["urn"], **workflow.ageing(model["id"])}
            who = self.authorise(request, "finding:read")
            visible = self.ctx["authz"].visible(who, registry.list())
            return {"model": None, "scope": len(visible),
                    **workflow.across([m["id"] for m in visible])}

        @self.app.get(f"{api}/findings/escalated", tags=["findings"])
        def escalated(request: Request, urn: Optional[str] = None):
            """What is no longer only its owner's problem — by role, not hierarchy.

            MAYA does not know who reports to whom, so an escalation names a
            role. The same reasoning, and the same role, as the notification
            service's escalation.
            """
            if urn:
                model = self.guard(lambda: registry.require(urn))
                self.authorise(request, "finding:read", model=model)
                models = [model]
            else:
                who = self.authorise(request, "finding:read")
                models = self.ctx["authz"].visible(who, registry.list())
            rows, opened = [], 0
            for m in models:
                rows.extend(workflow.escalated(m["id"]))
                opened += len(findings.open_for(m["id"]))
            return {"models": len(models), "escalated": rows, "open": opened,
                    "detail": (f"{len(rows)} of {opened} open finding(s) are past "
                               "what their owner alone can be left with"
                               if rows else
                               f"none of the {opened} open finding(s) need escalating")}

        @self.app.get(f"{api}/findings/{{finding_id}}", tags=["findings"])
        def read(request: Request, finding_id: str):
            """One finding and everything derived from what has happened to it."""
            self.authorise(request, "finding:read")
            return self.guard(lambda: workflow.reading(finding_id))

        @self.app.post(f"{api}/findings/{{finding_id}}/assign", tags=["findings"])
        def assign(request: Request, finding_id: str, body: AssignIn):
            """Hand a finding to somebody else, with the handover on the record."""
            finding = self.guard(lambda: workflow.open_finding(finding_id))
            who = self.authorise(request, "finding:assign",
                                 subject_id=finding["model_id"], about=finding_id)
            return self.guard(lambda: workflow.assign(
                finding_id, body.to, body.reason, actor=self.actor(who)))

        @self.app.post(f"{api}/findings/{{finding_id}}/acknowledge",
                       tags=["findings"])
        def acknowledge(request: Request, finding_id: str, body: AcknowledgeIn):
            """The owner accepts it and names the date. Nobody may do this for them."""
            finding = self.guard(lambda: workflow.open_finding(finding_id))
            who = self.authorise(request, "finding:acknowledge",
                                 subject_id=finding["model_id"], about=finding_id)
            return self.guard(lambda: workflow.acknowledge(
                finding_id, self.actor(who), body.committed_at, body.days,
                body.plan))

        @self.app.post(f"{api}/findings/{{finding_id}}/plan", tags=["findings"])
        def plan(request: Request, finding_id: str, body: PlanIn):
            """What will be done to close it, and by when."""
            finding = self.guard(lambda: workflow.open_finding(finding_id))
            who = self.authorise(request, "finding:plan",
                                 subject_id=finding["model_id"], about=finding_id)
            return self.guard(lambda: workflow.plan_for(
                finding_id, body.plan, actor=self.actor(who)))

        @self.app.post(f"{api}/findings/{{finding_id}}/extend", tags=["findings"])
        def extend(request: Request, finding_id: str, body: ExtendIn):
            """Move the remediation date. Not by its owner, and never silently."""
            finding = self.guard(lambda: workflow.open_finding(finding_id))
            # The evidence lives on the model and `about` narrows it to this
            # finding, so acknowledging one finding does not disqualify somebody
            # from extending every other finding on the same model.
            who = self.authorise(request, "finding:extend",
                                 subject_id=finding["model_id"], about=finding_id)
            return self.guard(lambda: workflow.extend(
                finding_id, self.actor(who), body.reason, body.days, body.due_at))

        @self.app.get(f"{api}/findings/{{finding_id}}/escalation", tags=["findings"])
        def escalation(request: Request, finding_id: str):
            """Whether this has stopped being only its owner's problem, and why."""
            self.authorise(request, "finding:read")
            reading = self.guard(lambda: workflow.reading(finding_id))
            return {"finding_id": finding_id, "title": reading["title"],
                    "owner": reading["owner"], **reading["escalation"]}

