"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The feature platform's aggregate root.

Four collaborators do the work — the catalogue defines features, the view
manager materialises and namespaces them, the binder pins contracts, the builder
assembles training sets. This class is the seam they are wired through, and the
single object the application context holds.

It is deliberately thin. Anything with a decision in it belongs in one of the
four; if a method here grows a branch, that branch is in the wrong file.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.evidence import EvidenceEngine
from core.features.assembly import TrainingSetBuilder
from core.features.catalogue import FeatureCatalogue
from core.features.common import ENTITY, INGEST_TIME, VALID_TIME, FeatureError
from core.features.contracts import ContractBinder
from core.features.views import ViewManager
from db import (ContractRepository, DeltaStore, FeatureRepository, FeatureViewRepository,
                FeatureViewVersionRepository, SnapshotRepository)


class FeatureRegistry:
    """Features, views, materialisation, contracts and PIT assembly."""

    def __init__(self, features: FeatureRepository, views: FeatureViewRepository,
                 view_versions: FeatureViewVersionRepository, contracts: ContractRepository,
                 snapshots: SnapshotRepository, delta: DeltaStore, evidence: EvidenceEngine):
        self.catalogue = FeatureCatalogue(features, evidence)
        self.views = ViewManager(views, view_versions, self.catalogue, delta, evidence)
        self.contracts = ContractBinder(contracts, view_versions, self.views, evidence)
        self.assembly = TrainingSetBuilder(self.views, snapshots, delta, evidence)
        # The Delta store and the snapshot register are the platform's own
        # persistence, not a collaborator's; reading them back is part of this
        # object's surface rather than something callers reach through it for.
        self.delta, self.snapshots = delta, snapshots

    # -------------------------------------------------------------- catalogue
    def define(self, *a, **kw) -> Dict[str, Any]:
        return self.catalogue.define(*a, **kw)

    def feature(self, name: str) -> Optional[Dict[str, Any]]:
        return self.catalogue.get(name)

    def list_features(self, **filters) -> List[Dict[str, Any]]:
        return self.catalogue.list(**filters)

    def similar(self, name: str, description: str, limit: int = 3) -> List[Dict[str, Any]]:
        return self.catalogue.similar(name, description, limit)

    def certify(self, name: str, level: str = "certified") -> Dict[str, Any]:
        return self.catalogue.certify(name, level)

    # ------------------------------------------------------------------ views
    def create_view(self, *a, **kw) -> Dict[str, Any]:
        return self.views.create(*a, **kw)

    def materialise(self, *a, **kw) -> Dict[str, Any]:
        return self.views.materialise(*a, **kw)

    def namespace(self, view_name: str, version: int) -> str:
        return self.views.namespace(view_name, version)

    def view_versions_of(self, view_name: str) -> List[Dict[str, Any]]:
        return self.views.versions_of(view_name)

    # -------------------------------------------------------------- contracts
    def bind_contract(self, *a, **kw) -> Dict[str, Any]:
        return self.contracts.bind(*a, **kw)

    def contract_for(self, model_version_id: str) -> Optional[Dict[str, Any]]:
        return self.contracts.for_version(model_version_id)

    def serving_namespaces(self, model_version_id: str) -> Dict[str, str]:
        return self.contracts.serving_namespaces(model_version_id)

    def can_retire(self, view_name: str, version: int) -> Tuple[bool, List[str]]:
        return self.contracts.can_retire(view_name, version)

    # --------------------------------------------------------------- assembly
    def build_training_set(self, *a, **kw) -> Dict[str, Any]:
        return self.assembly.build(*a, **kw)

    def snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        return self.snapshots.one(id=snapshot_id)
