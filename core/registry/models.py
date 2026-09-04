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

from typing import Any, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.ports import BlockingSource
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
                 evidence: EvidenceEngine, blocking: Optional[BlockingSource] = None):
        self.catalogue = ModelCatalogue(models, evidence)
        self.version_service = VersionService(versions, self.catalogue, evidence)
        self.alias_service = AliasService(aliases, history, self.catalogue,
                                          self.version_service, evidence, blocking)
        self.evidence = evidence

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

    def approve_version(self, urn: str, semver: str, actor: str = "system") -> Dict[str, Any]:
        return self.version_service.approve(urn, semver, actor)

    # --------------------------------------------------------------- aliases
    def move_alias(self, *a, **kw) -> Dict[str, Any]:
        return self.alias_service.move(*a, **kw)

    def resolve_alias(self, urn: str, environment: str, name: str) -> Optional[Dict[str, Any]]:
        return self.alias_service.resolve(urn, environment, name)

    def alias_history(self, urn: str) -> List[Dict[str, Any]]:
        return self.alias_service.history_of(urn)
