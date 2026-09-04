"""
MAYA — model, version, alias and risk endpoints.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from core.registry import RegistryError


class ModelIn(BaseModel):
    urn: str
    name: str
    model_class: str
    domain: str
    owner: str
    legal_entity: str
    purpose: str
    description: str = ""
    origin: str = "internal"


class VersionIn(BaseModel):
    semver: str
    kernel: Dict[str, Any] = Field(default_factory=dict)
    contract: Dict[str, Any] = Field(default_factory=dict)
    artifact_digest: Optional[str] = None


class AliasIn(BaseModel):
    environment: str = "prod"
    alias: str = "champion"
    semver: str
    justification: str = ""


class AssessIn(BaseModel):
    exposure: float = 0.0
    purpose_class: str = "commercial"
    feature_count: int = 0
    uses_alternative_data: bool = False
    interpretable: bool = True


class ModelRoutes:
    """The inventory API. Every refusal explains itself (design rule DR-7)."""

    def __init__(self, app: FastAPI, ctx: Dict[str, Any]):
        self.app, self.registry = app, ctx["registry"]
        self.tiering, self.risk_repo = ctx["tiering"], ctx["risk_repo"]
        self.evidence = ctx["evidence"]
        self._register()

    @staticmethod
    def _guard(fn):
        try:
            return fn()
        except RegistryError as exc:
            raise HTTPException(status_code=409,
                                detail={"error": "registry_refused", "detail": str(exc)}) from exc

    def _register(self) -> None:
        api = "/api/v1"

        @self.app.get(f"{api}/models", tags=["models"])
        def list_models(domain: Optional[str] = None, tier: Optional[int] = None):
            return {"models": self.registry.list(domain, tier)}

        @self.app.post(f"{api}/models", status_code=201, tags=["models"])
        def create_model(body: ModelIn):
            return self._guard(lambda: self.registry.register(
                body.urn, body.name, body.model_class, body.domain, body.owner,
                body.legal_entity, body.purpose, body.description, body.origin))

        @self.app.get(f"{api}/models/{{name:path}}", tags=["models"])
        def get_model(name: str):
            m = self.registry.get(f"maya://model/{name}")
            if not m:
                raise HTTPException(404, {"error": "not_found", "detail": f"no model {name}"})
            urn = m["urn"]
            return {"model": m, "versions": self.registry.versions(urn),
                    "alias_history": self.registry.alias_history(urn),
                    "evidence": self.evidence.for_subject(m["id"])}

        @self.app.post(f"{api}/models/{{name:path}}/versions", status_code=201, tags=["versions"])
        def create_version(name: str, body: VersionIn):
            return self._guard(lambda: self.registry.create_version(
                f"maya://model/{name}", body.semver, body.kernel, body.contract,
                body.artifact_digest))

        @self.app.post(f"{api}/models/{{name:path}}/versions/{{semver}}/approve", tags=["versions"])
        def approve(name: str, semver: str):
            return self._guard(lambda: self.registry.approve_version(
                f"maya://model/{name}", semver))

        @self.app.put(f"{api}/models/{{name:path}}/aliases", tags=["aliases"])
        def move_alias(name: str, body: AliasIn):
            return self._guard(lambda: self.registry.move_alias(
                f"maya://model/{name}", body.environment, body.alias, body.semver,
                justification=body.justification))

        @self.app.post(f"{api}/models/{{name:path}}/assess", tags=["risk"])
        def assess(name: str, body: AssessIn):
            urn = f"maya://model/{name}"
            m = self._guard(lambda: self.registry.require(urn))
            versions = self.registry.versions(urn)
            facts = body.model_dump()
            facts["trainability_class"] = versions[-1]["trainability_class"] if versions else "T0"
            a = self.tiering.assess(facts)
            self.tiering.persist(self.risk_repo, m["id"], a)
            self.registry.set_tier(m["id"], a.tier)
            self.evidence.append("tier_assigned", "model", m["id"],
                                 {"tier": a.tier, "rationale": a.rationale})
            return {"tier": a.tier, "materiality": a.materiality, "complexity": a.complexity,
                    "required_controls": list(a.required_controls), "rationale": a.rationale,
                    "ruleset_version": a.ruleset_version}

        @self.app.get(f"{api}/evidence/chain", tags=["evidence"])
        def chain():
            return self.evidence.verify_chain()
