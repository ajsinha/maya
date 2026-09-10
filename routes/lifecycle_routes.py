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

from typing import Any, Dict, List, Optional

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

        @self.app.get(f"{api}/lifecycle-profiles", tags=["lifecycle"])
        def profiles(request: Request):
            """The reference lifecycle for every trainability class.

            One state graph and several sets of obligations. Nine graphs would
            mean nine reachability proofs, nine answers to *can this be
            changed*, and a supervisor who has to ask which machine a model is
            on before reading its status. What varies is what each move costs.
            """
            self.principal(request)
            return self.guard(lambda: self.ctx["lifecycle_profiles"].reference())

        @self.app.get(f"{api}/lifecycle-profiles/{{trainability}}",
                      tags=["lifecycle"])
        def profile(request: Request, trainability: str,
                    tier: Optional[int] = None):
            """What a model of this class owes on each move, at this tier.

            The class says which evidence kinds must be on file — `L-15`
            already makes each one declare that — and the tier says how many
            signatures a move takes and how long it may sit.
            """
            self.principal(request)
            return self.guard(
                lambda: self.ctx["lifecycle_profiles"].for_class(
                    trainability, tier))

        # A top-level path with a `urn` query rather than a suffix under
        # `/models/{name}`: the model route's path converter is greedy and
        # swallows any suffix hung off it, which is why every derived read in
        # this platform — validation plans, monitoring plans, uses — takes the
        # urn as a parameter instead.
        @self.app.get(f"{api}/lifecycle-readiness", tags=["lifecycle"])
        def readiness(request: Request, urn: str, transition: str = "attest"):
            """Whether this model can make this move, and what is missing.

            *On file but unreviewed* is reported apart from *missing*: the
            document exists and the obligation is not yet discharged, and
            collapsing the two sends somebody off to write a report that is
            already written and sitting in a queue.
            """
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "model:read", model=model)
            return self.guard(
                lambda: self.ctx["lifecycle_profiles"].check(urn, transition))

        @self.app.get(f"{api}/lifecycle-stalled", tags=["lifecycle"])
        def stalled(request: Request):
            """Records that have been mid-move longer than their tier allows.

            Nothing else here can see this. Submission succeeded, every gate
            passed, and no control is watching the clock — which is how a
            governance queue becomes a place things go to wait. Not a refusal:
            a queue is allowed to have a queue, but one with no expected
            duration is one nobody can tell is stuck.
            """
            self.principal(request)
            return self.guard(lambda: self.ctx["lifecycle_profiles"].stalled())

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
            """Administrators only, and only if nothing refers to it.

            Nineteen tables carry a `model_id`. Deleting a model with a live
            warrant, an open finding, a monitor and three parameter sets left
            every one of those rows pointing at an identifier that no longer
            resolves — and the evidence chain, which survives the deletion by
            design, then described acts against a model nobody could look up.

            The refusal names what refers to it rather than saying no: somebody
            told *why* can go and deal with it, and somebody told *no* finds
            another way.
            """
            model = model_of(name)
            who = self.authorise(request, "model:delete", model=model)
            self.guard(lambda: self.ctx["references"].refuse_if_referenced(
                "model", model["urn"], label=model["urn"]))
            return self.guard(lambda: lifecycle.delete(model, who, reason))
