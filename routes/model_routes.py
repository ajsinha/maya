"""
MAYA — model, version, alias and risk endpoints.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from routes.base import Routes


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
    semver: str
    environment: str = "prod"
    alias: str = "champion"
    justification: str = ""


class AssessIn(BaseModel):
    exposure: float = 0.0
    purpose_class: str = "commercial"
    feature_count: int = 0
    uses_alternative_data: bool = False
    interpretable: bool = True


class ModelRoutes(Routes):
    """The inventory API. Every refusal explains itself (design rule DR-7)."""

    def register(self) -> None:
        reg, ev = self.ctx["registry"], self.ctx["evidence"]
        tiering, risk_repo = self.ctx["tiering"], self.ctx["risk_repo"]
        urn = lambda name: f"maya://model/{name}"

        @self.app.get(f"{self.api}/models", tags=["models"])
        def list_models(domain: Optional[str] = None, tier: Optional[int] = None):
            return {"models": reg.list(domain, tier)}

        @self.app.post(f"{self.api}/models", status_code=201, tags=["models"])
        def create_model(body: ModelIn):
            return self.guard(lambda: reg.register(
                body.urn, body.name, body.model_class, body.domain, body.owner,
                body.legal_entity, body.purpose, body.description, body.origin))

        @self.app.get(f"{self.api}/models/{{name:path}}", tags=["models"])
        def get_model(name: str):
            m = reg.get(urn(name))
            if not m:
                raise self.not_found(f"no model {name}")
            return {"model": m, "versions": reg.versions(m["urn"]),
                    "alias_history": reg.alias_history(m["urn"]),
                    "evidence": ev.for_subject(m["id"])}

        @self.app.post(f"{self.api}/models/{{name:path}}/versions", status_code=201,
                       tags=["versions"])
        def create_version(name: str, body: VersionIn):
            return self.guard(lambda: reg.create_version(
                urn(name), body.semver, body.kernel, body.contract, body.artifact_digest))

        @self.app.post(f"{self.api}/models/{{name:path}}/versions/{{semver}}/approve",
                       tags=["versions"])
        def approve(name: str, semver: str):
            return self.guard(lambda: reg.approve_version(urn(name), semver))

        @self.app.put(f"{self.api}/models/{{name:path}}/aliases", tags=["aliases"])
        def move_alias(name: str, body: AliasIn):
            return self.guard(lambda: reg.move_alias(
                urn(name), body.environment, body.alias, body.semver,
                justification=body.justification))

        @self.app.post(f"{self.api}/models/{{name:path}}/assess", tags=["risk"])
        def assess(name: str, body: AssessIn):
            m = self.guard(lambda: reg.require(urn(name)))
            versions = reg.versions(urn(name))
            facts = {**body.model_dump(),
                     "trainability_class": versions[-1]["trainability_class"] if versions else "T0"}
            a = tiering.assess(facts)
            tiering.persist(risk_repo, m["id"], a)
            reg.set_tier(m["id"], a.tier)
            ev.append("tier_assigned", "model", m["id"],
                      {"tier": a.tier, "rationale": a.rationale})
            return {"tier": a.tier, "materiality": a.materiality, "complexity": a.complexity,
                    "required_controls": list(a.required_controls), "rationale": a.rationale,
                    "ruleset_version": a.ruleset_version}

        @self.app.get(f"{self.api}/evidence/chain", tags=["evidence"])
        def chain():
            return ev.verify_chain()
