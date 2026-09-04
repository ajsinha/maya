"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The registry: models, immutable versions, and governed aliases.

Alias moves are the most dangerous operation in the platform, so they are proof
obligations rather than judgement calls: the replacement's contract must refine
the incumbent's (L-7) and its schemas must satisfy variance (L-12). Consumers
bind to an alias and are therefore never redeployed and never broken.
"""
from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from core.domain import (Bound, Contract, Field, FitProcedure, OutputKind, ParameterKind,
                         ParameterObject, ParametricKernel, Schema, substitutable)
from core.evidence import EvidenceEngine
from db import AliasRepository, ModelRepository, VersionRepository
from db.database import digest as canonical_digest


class RegistryError(RuntimeError):
    """A registry operation was refused. The message always says why."""


def _schema(spec: List[Dict[str, Any]]) -> Schema:
    return Schema(tuple(Field(f["name"], f["dtype"], f.get("nullable", False),
                              f.get("minimum"), f.get("maximum")) for f in spec))


def _contract(spec: Dict[str, Any]) -> Contract:
    def bounds(items):
        return tuple(Bound(b["key"], b.get("minimum"), b.get("maximum"),
                           tuple(b.get("allowed", ()))) for b in items or [])
    return Contract(bounds(spec.get("assumptions")), bounds(spec.get("guarantees")))


class ModelRegistry:
    """Application service over the store. Emits evidence for everything it does."""

    def __init__(self, models: ModelRepository, versions: VersionRepository,
                 aliases: AliasRepository, evidence: EvidenceEngine):
        self.models, self.versions_repo = models, versions
        self.aliases, self.evidence = aliases, evidence

    # ----------------------------------------------------------------- models
    def register(self, urn: str, name: str, model_class: str, domain: str, owner: str,
                 legal_entity: str, purpose: str, description: str = "",
                 origin: str = "internal", actor: str = "system",
                 attributes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.models.by_urn(urn):
            raise RegistryError(f"a model is already registered with urn {urn}")
        row = {"urn": urn, "name": name, "description": description,
               "model_class": model_class, "domain": domain, "owner": owner,
               "legal_entity": legal_entity, "purpose": purpose, "origin": origin,
               "status": "proposed", "tier": None, "attributes": attributes or {},
               "created_at": time.time(), "created_by": actor}
        self.models.add(row)
        self.evidence.append("model_registered", "model", row["id"],
                             {"urn": urn, "owner": owner}, actor=actor)
        return row

    def get(self, urn: str) -> Optional[Dict[str, Any]]:
        return self.models.by_urn(urn)

    def require(self, urn: str) -> Dict[str, Any]:
        row = self.get(urn)
        if not row:
            raise RegistryError(f"no model registered with urn {urn}")
        return row

    def list(self, domain: Optional[str] = None, tier: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.models.list(domain, tier)

    def set_tier(self, model_id: str, tier: int) -> None:
        self.models.set_tier(model_id, tier)

    def set_status(self, model_id: str, status: str, actor: str = "system") -> None:
        self.models.set_status(model_id, status)
        self.evidence.append("status_changed", "model", model_id, {"status": status}, actor=actor)

    # --------------------------------------------------------------- versions
    def create_version(self, urn: str, semver: str, kernel_spec: Dict[str, Any],
                       contract_spec: Optional[Dict[str, Any]] = None,
                       artifact_digest: Optional[str] = None,
                       actor: str = "system") -> Dict[str, Any]:
        m = self.require(urn)
        if self.versions_repo.by_semver(m["id"], semver):
            raise RegistryError(f"version {semver} already exists for {urn}; versions are immutable")

        kernel = ParametricKernel(
            parameters=ParameterObject(ParameterKind(kernel_spec.get("parameter_kind", "none")),
                                       artifact_digest),
            input_schema=_schema(kernel_spec.get("input_schema", [])),
            output_schema=_schema(kernel_spec.get("output_schema", [])),
            output_kind=OutputKind(kernel_spec.get("output_kind", "point_estimate")),
            deterministic=bool(kernel_spec.get("deterministic", True)),
            fit=FitProcedure(kernel_spec.get("fit_procedure", "none")),
            adaptive=bool(kernel_spec.get("adaptive", False)))

        manifest = {"urn": urn, "semver": semver, "kernel": kernel_spec,
                    "contract": contract_spec or {}, "artifact_digest": artifact_digest}
        row = {"model_id": m["id"], "semver": semver, "manifest": manifest,
               "manifest_digest": canonical_digest(manifest),
               "trainability_class": kernel.trainability_class,
               "parameter_kind": kernel.parameters.kind.value,
               "fit_procedure": kernel.fit.value, "deterministic": kernel.deterministic,
               "input_schema": kernel_spec.get("input_schema", []),
               "output_schema": kernel_spec.get("output_schema", []),
               "contract": contract_spec or {}, "artifact_digest": artifact_digest,
               "status": "draft", "created_at": time.time(), "created_by": actor}
        self.versions_repo.add(row)
        self.evidence.append("version_created", "version", row["id"],
                             {"semver": semver, "digest": row["manifest_digest"],
                              "trainability_class": row["trainability_class"]}, actor=actor)
        return row

    def versions(self, urn: str) -> List[Dict[str, Any]]:
        return self.versions_repo.for_model(self.require(urn)["id"])

    def version(self, urn: str, semver: str) -> Optional[Dict[str, Any]]:
        return self.versions_repo.by_semver(self.require(urn)["id"], semver)

    def approve_version(self, urn: str, semver: str, actor: str = "system") -> Dict[str, Any]:
        v = self.version(urn, semver)
        if not v:
            raise RegistryError(f"no version {semver} for {urn}")
        self.versions_repo.set_status(v["id"], "approved")
        self.evidence.append("version_approved", "version", v["id"], {"semver": semver}, actor=actor)
        return {**v, "status": "approved"}

    # ---------------------------------------------------------------- aliases
    def move_alias(self, urn: str, environment: str, name: str, to_semver: str,
                   actor: str = "system", justification: str = "") -> Dict[str, Any]:
        """Governed version switch. Refusal names the exact clause that failed."""
        m = self.require(urn)
        new = self.version(urn, to_semver)
        if not new:
            raise RegistryError(f"no version {to_semver} for {urn}")
        if new["status"] != "approved":
            raise RegistryError(f"version {to_semver} is '{new['status']}', not approved; "
                                f"an alias may only point at an approved version")

        current = self.aliases.current(m["id"], environment, name)
        refinement = {"holds": True, "reason": "no incumbent"}
        variance = {"ok": True, "reason": "no incumbent"}

        if current:
            old = self.versions_repo.by_id(current["version_id"])
            r = _contract(new["contract"]).refines(_contract(old["contract"]))
            v = substitutable(_schema(new["input_schema"]), _schema(new["output_schema"]),
                              _schema(old["input_schema"]), _schema(old["output_schema"]))
            refinement = {"holds": r.holds, "reason": r.reason()}
            variance = {"ok": v.ok, "reason": v.reason()}
            if not (r.holds and v.ok):
                raise RegistryError(
                    f"alias move refused: {refinement['reason']} / {variance['reason']}")

        now = time.time()
        self.aliases.point(m["id"], environment, name, new["id"], now, actor)
        self.aliases.record_move({
            "model_id": m["id"], "environment": environment, "name": name,
            "from_version_id": current["version_id"] if current else None,
            "to_version_id": new["id"], "refinement": refinement, "variance": variance,
            "moved_at": now, "moved_by": actor, "justification": justification})
        self.evidence.append("alias_moved", "model", m["id"],
                             {"alias": name, "environment": environment, "to": to_semver,
                              "refinement": refinement, "variance": variance}, actor=actor)
        return {"model": urn, "environment": environment, "alias": name, "version": to_semver,
                "refinement": refinement, "variance": variance}

    def resolve_alias(self, urn: str, environment: str, name: str) -> Optional[Dict[str, Any]]:
        a = self.aliases.current(self.require(urn)["id"], environment, name)
        return self.versions_repo.by_id(a["version_id"]) if a else None

    def alias_history(self, urn: str) -> List[Dict[str, Any]]:
        return self.aliases.history(self.require(urn)["id"])
