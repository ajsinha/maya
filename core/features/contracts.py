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
from core.log import get_logger
from db import ContractRepository, FeatureViewVersionRepository
from db.database import digest as canonical_digest

logger = get_logger(__name__)


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
        digest = canonical_digest(items)

        # A version binds ONE contract, and what happens on a second call is a
        # governance question rather than a plumbing one.
        #
        # It used to be neither: `add` went straight at a table with a unique
        # index on `model_version_id`, so re-binding raised an IntegrityError
        # and the caller got a 500. Case study 15 found it by being run twice.
        #
        # The same contract again is a no-op: the caller is asking for a state
        # the register is already in, and that is not an error. A DIFFERENT
        # contract is refused, and this is the half that matters — the contract
        # is what `L-17` compares serving against and what the approval was
        # given on. Letting it be rewritten in place would change what a version
        # reads without changing the version, which is the shape of every
        # silent-change failure in this repository.
        existing = self.contracts.one(model_version_id=model_version_id)
        if existing is not None:
            if existing.get("digest") == digest:
                logger.info("contract for %s is already bound to %s",
                            model_version_id, digest[:12])
                return existing
            raise FeatureError(
                f"version {model_version_id} is already bound to a different "
                f"feature contract",
                remediation="a contract says what this version reads and is "
                            "what the approval was given on, so it does not "
                            "change in place. Create a new version, or open an "
                            "amendment if the model record is attested")

        row = {"model_version_id": model_version_id, "digest": digest,
               "items": items, "created_at": time.time()}
        with self.evidence.recording():
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
