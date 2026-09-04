"""
MAYA — hook issuance, resolution and revocation.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

This is the boundary of the product. MAYA hands out a signed execution
contract; an execution engine acts on it. The captive engine is exposed here
too, but only as one CONSUMER of the same endpoints an external engine uses.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.hooks import HookError


class IssueIn(BaseModel):
    urn: str
    environment: str = "prod"
    principal: str
    declared_use: str
    flavour: str = "descriptor_only"


class ResolveIn(BaseModel):
    urn: str
    environment: str = "prod"
    principal: str
    declared_use: str


class RevokeIn(BaseModel):
    urn: str
    reason: str


class ExecuteIn(BaseModel):
    urn: str
    environment: str = "prod"
    principal: str
    declared_use: str
    inputs: Dict[str, Any] = Field(default_factory=dict)


_STATUS = {"not_found": 404, "no_entitlement": 403, "use_not_approved": 403,
           "restricted": 423, "revoked": 410, "validation_failed": 422,
           "boundary_violation": 422, "expired": 410, "signature_invalid": 403,
           "no_runtime": 501}


class HookRoutes:
    def __init__(self, app: FastAPI, ctx: Dict[str, Any]):
        self.app, self.hooks, self.engine = app, ctx["hooks"], ctx.get("engine")
        self._register()

    @staticmethod
    def _problem(exc: HookError) -> JSONResponse:
        """RFC 9457-shaped. Every refusal carries a remediation hint."""
        return JSONResponse(exc.as_problem(), status_code=_STATUS.get(exc.code, 400))

    def _register(self) -> None:
        api = "/api/v1"

        @self.app.post(f"{api}/hooks", status_code=201, tags=["hooks"])
        def issue(body: IssueIn):
            try:
                return self.hooks.issue(body.urn, body.environment, body.principal,
                                        body.declared_use, body.flavour)
            except HookError as exc:
                return self._problem(exc)

        @self.app.post(f"{api}/resolve", tags=["hooks"])
        def resolve(body: ResolveIn):
            """The hot path. Returns a signed descriptor, or refuses with a reason."""
            try:
                return self.hooks.resolve(body.urn, body.environment, body.principal,
                                          body.declared_use)
            except HookError as exc:
                return self._problem(exc)

        @self.app.post(f"{api}/hooks/revoke", tags=["hooks"])
        def revoke(body: RevokeIn):
            try:
                n = self.hooks.revoke_model(body.urn, body.reason)
                return {"revoked": n, "urn": body.urn, "reason": body.reason,
                        "epoch": self.hooks._epoch}
            except Exception as exc:
                raise HTTPException(404, {"error": "not_found", "detail": str(exc)}) from exc

        @self.app.post(f"{api}/execute", tags=["execution"])
        def execute(body: ExecuteIn):
            """Convenience only: the captive engine, reached through the same
            contract an external engine uses. Disable it in configuration and
            nothing else about MAYA changes."""
            if self.engine is None:
                raise HTTPException(501, {"error": "captive_engine_disabled",
                                          "detail": "no captive engine is configured",
                                          "remediation": "resolve the hook and run the model "
                                                         "in your own execution engine"})
            try:
                r = self.engine.execute(body.urn, body.environment, body.principal,
                                        body.declared_use, body.inputs)
                return r.__dict__
            except HookError as exc:
                return self._problem(exc)
