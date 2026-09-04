"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The feature catalogue: definitions, duplicate detection, certification.

Feature sprawl is what makes a large store unusable — the fourth
``customer_income_v2_final`` is not a data problem, it is a discovery problem.
So near-duplicates surface at the moment of creation, when renaming is still
cheap, rather than in an audit two years later.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from core.evidence import EvidenceEngine
from core.features.common import FeatureError
from db import FeatureRepository

LEVELS = ("experimental", "certified", "deprecated")
SIMILARITY_FLOOR = 0.25


class FeatureCatalogue:
    """Feature definitions and their certification state."""

    def __init__(self, features: FeatureRepository, evidence: EvidenceEngine):
        self.features, self.evidence = features, evidence

    def define(self, name: str, entity: str, dtype: str, description: str, owner: str,
               business_definition: str = "", source_system: str = "",
               sensitivity: str = "internal", pii: bool = False,
               protected_basis: bool = False, proxy_risk: str = "none",
               actor: str = "system") -> Dict[str, Any]:
        if self.features.one(name=name):
            raise FeatureError(f"feature '{name}' is already defined")
        row = {"name": name, "entity": entity, "dtype": dtype, "description": description,
               "business_definition": business_definition, "owner": owner,
               "source_system": source_system, "sensitivity": sensitivity,
               "pii": int(pii), "protected_basis": int(protected_basis),
               "proxy_risk": proxy_risk, "certification": "experimental",
               "created_at": time.time()}
        self.features.add(row)
        self.evidence.append("feature_defined", "feature", row["id"],
                             {"name": name, "entity": entity}, actor=actor)
        return {**row, "pii": pii, "protected_basis": protected_basis}

    def get(self, name: str) -> Dict[str, Any]:
        return self.features.one(name=name)

    def require(self, name: str) -> Dict[str, Any]:
        row = self.get(name)
        if not row:
            raise FeatureError(f"no feature '{name}'")
        return row

    def list(self, **filters) -> List[Dict[str, Any]]:
        return self.features.many(**filters)

    def missing(self, names: List[str]) -> List[str]:
        """Which of these features are not defined. Used before building a view."""
        return [n for n in names if not self.features.one(name=n)]

    def similar(self, name: str, description: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Cheap duplicate detection by token overlap.

        Deliberately not embeddings: the point is to be fast enough to run on
        every keystroke of a definition form, and explainable enough that a
        steward can see why two features were called alike.
        """
        words = self._tokens(name, description)
        scored = []
        for f in self.features.many():
            overlap = self._jaccard(words, self._tokens(f["name"], f["description"]))
            if overlap > SIMILARITY_FLOOR:
                scored.append((overlap, f))
        return [f for _, f in sorted(scored, key=lambda t: -t[0])[:limit]]

    @staticmethod
    def _tokens(name: str, description: str) -> set:
        return set(description.lower().split()) | set(name.lower().replace("_", " ").split())

    @staticmethod
    def _jaccard(a: set, b: set) -> float:
        return len(a & b) / max(len(a | b), 1)

    def certify(self, name: str, level: str = "certified") -> Dict[str, Any]:
        if level not in LEVELS:
            raise FeatureError(f"unknown certification level '{level}'; "
                               f"expected one of {', '.join(LEVELS)}")
        self.require(name)
        self.features.set({"certification": level}, name=name)
        return self.features.one(name=name)
