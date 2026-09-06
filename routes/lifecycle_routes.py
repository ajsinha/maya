"""
MAYA — the model record lifecycle: submission, approval, attestation, amendment.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

An attested record is immutable. Everything here is either a step towards that
state or the declared act of leaving it.

Deletion is the one endpoint with no workflow, and it is administrators only.
Everyone else retires a model, which withdraws it from use and keeps the record.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import Request
from pydantic import Field

from core.execution.urn import urn_of
from core.lifecycle import describe
from routes.base import Body, Routes


class NoteIn(Body):
    note: str = ""


class ReasonIn(Body):
    reason: str


class AmendIn(Body):
    reason: str
    scope: List[str] = Field(default_factory=list)


class SignIn(Body):
    role: str
    decision: str = "attest"
    statement: str = ""


class UpdateIn(Body):
    fields: Dict[str, Any] = Field(default_factory=dict)


class LifecycleRoutes(Routes):
    def register(self) -> None:
        registry, lifecycle = self.ctx["registry"], self.ctx["lifecycle"]
        api = self.api

        def model_of(name: str) -> Dict[str, Any]:
            return self.guard(lambda: registry.require(urn_of(name)))

        @self.app.get(f"{api}/lifecycle", tags=["lifecycle"])
        def machine(request: Request):
            """The state machine itself: who may move what, from where, to where."""
            self.principal(request)
            return {"transitions": describe()}

        @self.app.patch(f"{api}/models/{{name:path}}", tags=["lifecycle"])
        def update(request: Request, name: str, body: UpdateIn):
            """Revise an open record. Refused once it is attested."""
            model = model_of(name)
            who = self.authorise(request, "model:register", model=model)
            return self.guard(lambda: registry.update(model["urn"], body.fields,
                                                      self.actor(who)))

        @self.app.post(f"{api}/models/{{name:path}}/submit", tags=["lifecycle"])
        def submit(request: Request, name: str, body: NoteIn):
            model = model_of(name)
            who = self.authorise(request, "model:submit", model=model)
            return self.guard(lambda: lifecycle.submit(model, self.actor(who), body.note))

        @self.app.post(f"{api}/models/{{name:path}}/approve", tags=["lifecycle"])
        def approve(request: Request, name: str, body: NoteIn):
            """Approve the record and open the attestation it now needs."""
            model = model_of(name)
            who = self.authorise(request, "model:approve", model=model,
                                 subject_id=model["id"])
            return self.guard(lambda: lifecycle.approve(model, self.actor(who), body.note))

        @self.app.post(f"{api}/models/{{name:path}}/return", tags=["lifecycle"])
        def send_back(request: Request, name: str, body: ReasonIn):
            model = model_of(name)
            who = self.authorise(request, "model:approve", model=model)
            return self.guard(lambda: lifecycle.send_back(model, self.actor(who),
                                                          body.reason))

        @self.app.post(f"{api}/models/{{name:path}}/attest", tags=["lifecycle"])
        def attest(request: Request, name: str, body: SignIn):
            """Sign one role's half of the attestation. A quorum, not a button."""
            model = model_of(name)
            who = self.authorise(request, "model:attest", model=model)
            return self.guard(lambda: lifecycle.sign(model, who, body.role,
                                                     body.decision, body.statement))

        @self.app.post(f"{api}/models/{{name:path}}/amend", tags=["lifecycle"])
        def amend(request: Request, name: str, body: AmendIn):
            """The only route out of immutability."""
            model = model_of(name)
            who = self.authorise(request, "model:amend", model=model)
            return self.guard(lambda: lifecycle.amend(model, body.reason, body.scope,
                                                      self.actor(who)))

        @self.app.post(f"{api}/models/{{name:path}}/retire", tags=["lifecycle"])
        def retire(request: Request, name: str, body: ReasonIn):
            model = model_of(name)
            who = self.authorise(request, "model:retire", model=model)
            return self.guard(lambda: lifecycle.retire(model, self.actor(who), body.reason))

        @self.app.delete(f"{api}/models/{{name:path}}", tags=["lifecycle"])
        def delete(request: Request, name: str, reason: str = ""):
            """Administrators only. The evidence chain survives the deletion."""
            model = model_of(name)
            who = self.authorise(request, "model:delete", model=model)
            return self.guard(lambda: lifecycle.delete(model, who, reason))
