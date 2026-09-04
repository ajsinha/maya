"""
MAYA — warrant issuance, resolution and revocation.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

This is the boundary of the product. MAYA hands out a signed execution contract;
an execution engine acts on it. The captive engine is exposed here too, but only
as one CONSUMER of the same endpoints an external engine uses.
"""
from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field

from routes.base import Routes


class IssueIn(BaseModel):
    urn: str
    principal: str
    declared_use: str
    environment: str = "prod"
    flavour: str = "descriptor_only"


class ResolveIn(BaseModel):
    urn: str
    principal: str
    declared_use: str
    environment: str = "prod"


class ExecuteIn(ResolveIn):
    inputs: Dict[str, Any] = Field(default_factory=dict)


class RevokeIn(BaseModel):
    urn: str
    reason: str


class WarrantRoutes(Routes):
    def register(self) -> None:
        warrants, engine = self.ctx["warrants"], self.ctx.get("engine")

        @self.app.post(f"{self.api}/warrants", status_code=201, tags=["warrants"])
        def issue(body: IssueIn):
            return self.guard(lambda: warrants.issue(
                body.urn, body.environment, body.principal, body.declared_use, body.flavour))

        @self.app.post(f"{self.api}/resolve", tags=["warrants"])
        def resolve(body: ResolveIn):
            """The hot path. A signed descriptor, or a refusal with a reason."""
            return self.guard(lambda: warrants.resolve(
                body.urn, body.environment, body.principal, body.declared_use))

        @self.app.post(f"{self.api}/warrants/revoke", tags=["warrants"])
        def revoke(body: RevokeIn):
            n = self.guard(lambda: warrants.revoke_model(body.urn, body.reason))
            return {"revoked": n, "urn": body.urn, "reason": body.reason,
                    "epoch": warrants.epoch}

        @self.app.post(f"{self.api}/execute", tags=["execution"])
        def execute(body: ExecuteIn):
            """Convenience only: the captive engine, reached through the same
            contract an external engine uses. Disable it and nothing else changes."""
            if engine is None:
                raise self.not_found("no captive engine is configured; resolve the warrant "
                                     "and run the model in your own execution engine")
            return self.guard(lambda: engine.execute(
                body.urn, body.environment, body.principal, body.declared_use,
                body.inputs).__dict__)
