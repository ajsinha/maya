"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The registry's aggregate root.

Three collaborators: the catalogue holds model identity, the version service
holds immutable versions, the alias service holds the governed bindings between
them. This class wires them and is the single object the application context
carries.

Thin by intent. A decision made here instead of in a collaborator is a decision
in the wrong file.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.ports import BlockingSource, LifecycleGate
from core.registry.aliases import AliasService
from core.registry.catalogue import ModelCatalogue
from core.registry.common import RegistryError
from core.registry.versions import VersionService
from db import (AliasHistoryRepository, AliasRepository, ModelRepository,
                VersionRepository)


class ModelRegistry:
    """Models, immutable versions, and governed aliases."""

    def __init__(self, models: ModelRepository, versions: VersionRepository,
                 aliases: AliasRepository, history: AliasHistoryRepository,
                 evidence: EvidenceEngine, blocking: Optional[BlockingSource] = None,
                 gate: Optional[LifecycleGate] = None):
        self.catalogue = ModelCatalogue(models, evidence, gate)
        self.version_service = VersionService(versions, self.catalogue, evidence, gate)
        self.alias_service = AliasService(aliases, history, self.catalogue,
                                          self.version_service, evidence, blocking)
        self.evidence = evidence
        # A callable (urn, semver) -> None that raises when a quorum is required
        # and has not been reached. Injected rather than imported so the registry
        # keeps knowing nothing about lifecycle workflows.
        self.approvals: Optional[Callable[[str, str], None]] = None
        # A policy gate, consulted AFTER the checks above and only ever to
        # refuse. Policy tightens; the invariants written here are the floor.
        self.policy = None

    def attach_policy(self, gate) -> None:
        """Wire a policy gate. It adds conditions; it never removes them."""
        self.policy = gate
        self.version_service.policy = gate
        self.alias_service.policy = gate
        self.catalogue.policy = gate

    def attach_quorum(self, check) -> None:
        """Wire the version-approval quorum after construction.

        The quorum needs the registry to record its outcome, and the registry
        needs the quorum to refuse a single signature. One of the two connects
        second, and doing it explicitly beats a circular constructor.
        """
        self.approvals = check

    def attach_gate(self, gate: LifecycleGate) -> None:
        """Wire the lifecycle gate after construction.

        The lifecycle service needs the registry, and the registry needs the
        gate, so one of the two has to be connected second. Doing it explicitly
        beats a lazy import or a circular constructor.
        """
        self.catalogue.gate = gate
        self.version_service.gate = gate

    def update(self, urn: str, fields: Dict[str, Any],
               actor: str = "system") -> Dict[str, Any]:
        return self.catalogue.update(urn, fields, actor)

    def attach_blocking(self, blocking: BlockingSource) -> None:
        """Wire the gate after construction.

        The findings register needs the evidence engine, which the registry also
        needs, so one of the two has to be connected second. Doing it explicitly
        beats a lazy import or a circular constructor.
        """
        self.alias_service.blocking = blocking

    # ---------------------------------------------------------------- models
    def register(self, *a, **kw) -> Dict[str, Any]:
        return self.catalogue.register(*a, **kw)

    def get(self, urn: str) -> Optional[Dict[str, Any]]:
        return self.catalogue.get(urn)

    def require(self, urn: str) -> Dict[str, Any]:
        return self.catalogue.require(urn)

    def list(self, domain: Optional[str] = None,
             tier: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.catalogue.list(domain, tier)

    def set_tier(self, model_id: str, tier: int) -> None:
        self.catalogue.set_tier(model_id, tier)

    def set_status(self, model_id: str, status: str, actor: str = "system") -> None:
        self.catalogue.set_status(model_id, status, actor)

    # -------------------------------------------------------------- versions
    def create_version(self, *a, **kw) -> Dict[str, Any]:
        return self.version_service.create(*a, **kw)

    def versions(self, urn: str) -> List[Dict[str, Any]]:
        return self.version_service.list(urn)

    def version(self, urn: str, semver: str) -> Optional[Dict[str, Any]]:
        return self.version_service.get(urn, semver)

    def version_by_id(self, version_id: str) -> Optional[Dict[str, Any]]:
        """A version and the urn it belongs to, from its id alone.

        The quorum knows a version id and has to name the model it approves; a
        lookup by id keeps it from having to carry the urn around.
        """
        row = self.version_service.versions.one(id=version_id)
        if row is None:
            return None
        model = self.catalogue.by_id(row["model_id"])
        return {**row, "urn": model["urn"] if model else None}

    def approve_version(self, urn: str, semver: str, actor: str = "system",
                        quorum_id: Optional[str] = None) -> Dict[str, Any]:
        """Approve a version.

        Where the tier demands a quorum this is the *consequence* of one rather
        than an act in itself, so a direct call is refused and told where to go.
        A single-signature approval of a Tier 1 version is the hole this closes.
        """
        if self.approvals is not None and quorum_id is None:
            self.approvals(urn, semver)
        return self.version_service.approve(urn, semver, actor)

    # --------------------------------------------------------------- aliases
    def move_alias(self, *a, **kw) -> Dict[str, Any]:
        return self.alias_service.move(*a, **kw)

    def resolve_alias(self, urn: str, environment: str, name: str) -> Optional[Dict[str, Any]]:
        return self.alias_service.resolve(urn, environment, name)

    def alias_history(self, urn: str) -> List[Dict[str, Any]]:
        return self.alias_service.history_of(urn)
