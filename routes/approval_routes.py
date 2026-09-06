"""
MAYA — version approval as a quorum.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The model record was already attested by several people; the version — which is
what actually runs — was approved by one. These endpoints close that asymmetry,
with the number of signatures decided by the tier rather than by the requester.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Request
from pydantic import BaseModel

from routes.base import Body, Routes


class OpenApprovalIn(Body):
    urn: str
    semver: str
    statement: str = ""


class SignIn(Body):
    role: str
    decision: str = "approve"
    statement: str = ""


class ApprovalRoutes(Routes):
    def register(self) -> None:
        approvals, api = self.ctx["approvals"], self.api
        registry = self.ctx["registry"]

        @self.app.get(f"{api}/version-approval-quorum", tags=["versions"])
        def quorum(request: Request):
            """Who must sign, by tier. Published so nobody reads configuration."""
            self.principal(request)
            return {"quorum": approvals.describes()}

        @self.app.get(f"{api}/version-approvals", tags=["versions"])
        def needed(request: Request, urn: str, semver: str):
            """What this version's approval requires, and where it stands."""
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "model:read", model=model)
            return self.guard(lambda: approvals.needed(urn, semver))

        @self.app.post(f"{api}/version-approvals", status_code=201,
                       tags=["versions"])
        def open_approval(request: Request, body: OpenApprovalIn):
            """Open an approval. Refused where the tier needs no quorum, and
            refused where the model has no tier at all — approving before
            assessing would be choosing your own control depth."""
            model = self.guard(lambda: registry.require(body.urn))
            who = self.authorise(request, "version:approve", model=model)
            return self.guard(lambda: approvals.open(
                body.urn, body.semver, body.statement, self.actor(who)))

        @self.app.get(f"{api}/version-approvals/{{approval_id}}", tags=["versions"])
        def progress(request: Request, approval_id: str):
            self.authorise(request, "model:read")
            return self.guard(lambda: approvals.progress(approval_id))

        @self.app.post(f"{api}/version-approvals/{{approval_id}}/sign",
                       tags=["versions"])
        def sign(request: Request, approval_id: str, body: SignIn):
            """One signature, for a role you hold and that this approval needs.

            The same person may not sign twice under two hats: a quorum is a
            number of people, not a number of roles. One decline closes it.
            """
            # The subject is the VERSION, because that is what the evidence
            # chain recorded `version_created` against — and without passing it
            # the segregation check has no node to look at and permits
            # everything, which is how this path came to be unguarded.
            approval = self.guard(lambda: approvals.require(approval_id))
            who = self.authorise(request, "version:sign",
                                 subject_id=approval["model_version_id"])
            return self.guard(lambda: approvals.sign(
                approval_id, who, body.role, body.decision, body.statement))

        @self.app.post(f"{api}/version-approvals/{{approval_id}}/withdraw",
                       tags=["versions"])
        def withdraw(request: Request, approval_id: str):
            who = self.authorise(request, "version:approve")
            return self.guard(lambda: approvals.withdraw(approval_id,
                                                         self.actor(who)))
