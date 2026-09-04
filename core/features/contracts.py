"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Feature contracts: what a model version is entitled to read.

A contract pins exact feature view versions. That is the whole point — it turns
"this model uses the customer risk view" into a claim with a truth value, so
Law L-17 can compare what serving MUST read against what it DID read, and a
namespace cannot be retired while anything still depends on it.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from core.evidence import EvidenceEngine
from core.features.common import FeatureError
from core.features.views import ViewManager
from db import ContractRepository, FeatureViewVersionRepository
from db.database import digest as canonical_digest


class ContractBinder:
    """Binds model versions to pinned feature view versions."""

    def __init__(self, contracts: ContractRepository,
                 view_versions: FeatureViewVersionRepository,
                 views: ViewManager, evidence: EvidenceEngine):
        self.contracts, self.view_versions = contracts, view_versions
        self.views, self.evidence = views, evidence

    def bind(self, model_version_id: str, items: List[Dict[str, Any]],
             actor: str = "system") -> Dict[str, Any]:
        """Pin a model version to exact feature view versions."""
        for item in items:
            view = self.views.require(item["view"])
            if not self.view_versions.one(feature_view_id=view["id"], version=item["version"]):
                raise FeatureError(f"'{item['view']}' has no version {item['version']}")
            item["feature_view_id"] = view["id"]
            item["namespace"] = self.views.namespace_of(view, item["version"])
        row = {"model_version_id": model_version_id, "digest": canonical_digest(items),
               "items": items, "created_at": time.time()}
        self.contracts.add(row)
        self.evidence.append("feature_contract_bound", "version", model_version_id,
                             {"digest": row["digest"], "views": [i["view"] for i in items]},
                             actor=actor)
        return row

    def for_version(self, model_version_id: str) -> Optional[Dict[str, Any]]:
        """The contract bound to a version, or None. Reading is not a refusal:
        a version with no feature contract is normal, not an error."""
        return self.contracts.one(model_version_id=model_version_id)

    def serving_namespaces(self, model_version_id: str) -> Dict[str, str]:
        """What serving MUST read. Law L-17 compares this against what it did read."""
        contract = self.contracts.one(model_version_id=model_version_id)
        if not contract:
            raise FeatureError(f"no feature contract for version {model_version_id}")
        return {i["view"]: i["namespace"] for i in contract["items"]}

    def can_retire(self, view_name: str, version: int) -> Tuple[bool, List[str]]:
        """A namespace may only be retired when no contract still pins it."""
        view = self.views.require(view_name)
        consumers = self.contracts.consumers_of(view["id"], version)
        return not consumers, consumers
