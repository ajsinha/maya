"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Model versions: immutable, digested, and classified on arrival.

A version is created once and never edited. That is not fastidiousness — it is
what makes a manifest digest worth computing, and what lets a warrant descriptor
name a version and mean something six months later.

The trainability class is DERIVED here rather than declared. Asking an owner to
self-report "is this trained?" invites the answer that requires least work; the
class falls out of how the parameter object is inhabited, which is a fact about
the artifact instead of an opinion about it.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.domain import (FitProcedure, OutputKind, ParameterKind, ParameterObject,
                         ParametricKernel)
from core.evidence import EvidenceEngine
from core.ports import LifecycleGate
from core.registry.catalogue import ModelCatalogue
from core.registry.common import RegistryError
from core.registry.specs import schema_of
from db import VersionRepository
from db.database import digest as canonical_digest


class VersionService:
    """Creates and approves immutable model versions."""

    def __init__(self, versions: VersionRepository, catalogue: ModelCatalogue,
                 evidence: EvidenceEngine, gate: Optional[LifecycleGate] = None):
        self.versions, self.catalogue, self.evidence = versions, catalogue, evidence
        self.gate = gate
        self.policy = None

    @staticmethod
    def kernel_of(spec: Dict[str, Any], artifact_digest: Optional[str]) -> ParametricKernel:
        return ParametricKernel(
            parameters=ParameterObject(ParameterKind(spec.get("parameter_kind", "none")),
                                       artifact_digest),
            input_schema=schema_of(spec.get("input_schema", [])),
            output_schema=schema_of(spec.get("output_schema", [])),
            output_kind=OutputKind(spec.get("output_kind", "point_estimate")),
            deterministic=bool(spec.get("deterministic", True)),
            fit=FitProcedure(spec.get("fit_procedure", "none")),
            adaptive=bool(spec.get("adaptive", False)))

    def create(self, urn: str, semver: str, kernel_spec: Dict[str, Any],
               contract_spec: Optional[Dict[str, Any]] = None,
               artifact_digest: Optional[str] = None,
               artifact_uri: Optional[str] = None,
               actor: str = "system") -> Dict[str, Any]:
        m = self.catalogue.require(urn)
        # A new version IS a change to the model. Adding one to an attested
        # record without an amendment is how the record quietly stops describing
        # what runs.
        self._check_open(m)
        if self.versions.one(model_id=m["id"], semver=semver):
            raise RegistryError(
                f"version {semver} already exists for {urn}; versions are immutable")

        kernel = self.kernel_of(kernel_spec, artifact_digest)
        manifest = {"urn": urn, "semver": semver, "kernel": kernel_spec,
                    "contract": contract_spec or {},
                    "artifact_digest": artifact_digest, "artifact_uri": artifact_uri}
        row = {"model_id": m["id"], "semver": semver, "manifest": manifest,
               "manifest_digest": canonical_digest(manifest),
               "trainability_class": kernel.trainability_class,
               "parameter_kind": kernel.parameters.kind.value,
               "fit_procedure": kernel.fit.value, "deterministic": kernel.deterministic,
               "input_schema": kernel_spec.get("input_schema", []),
               "output_schema": kernel_spec.get("output_schema", []),
               "contract": contract_spec or {}, "artifact_digest": artifact_digest,
               "artifact_uri": artifact_uri,
               "status": "draft", "created_at": time.time(), "created_by": actor}
        self.versions.add(row)
        self.evidence.append("version_created", "version", row["id"],
                             {"semver": semver, "digest": row["manifest_digest"],
                              "trainability_class": row["trainability_class"]}, actor=actor)
        return row

    def _check_open(self, model: Dict[str, Any]) -> None:
        if self.gate is None:
            return
        allowed, why = self.gate.may_mutate(model["id"])
        if not allowed:
            raise RegistryError(f"cannot add a version to {model['urn']}: {why}")

    def list(self, urn: str) -> List[Dict[str, Any]]:
        return self.versions.many(model_id=self.catalogue.require(urn)["id"])

    def get(self, urn: str, semver: str) -> Optional[Dict[str, Any]]:
        return self.versions.one(model_id=self.catalogue.require(urn)["id"], semver=semver)

    def by_id(self, version_id: str) -> Optional[Dict[str, Any]]:
        return self.versions.one(id=version_id)

    def require(self, urn: str, semver: str) -> Dict[str, Any]:
        v = self.get(urn, semver)
        if not v:
            raise RegistryError(f"no version {semver} for {urn}")
        return v

    def approve(self, urn: str, semver: str, actor: str = "system") -> Dict[str, Any]:
        v = self.require(urn, semver)
        if self.policy is not None:
            model = self.catalogue.require(urn)
            self.policy.check("version:approve", {
                "tier": model.get("tier"), "status": v["status"],
                "has_artifact_digest": bool(v.get("artifact_digest")),
                "has_contract": bool(v.get("contract"))},
                f"{urn}@{semver}")
        self.versions.set({"status": "approved"}, id=v["id"])
        self.evidence.append("version_approved", "version", v["id"],
                             {"semver": semver}, actor=actor)
        return {**v, "status": "approved"}
