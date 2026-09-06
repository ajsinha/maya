"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The tiering engine.

tau maps materiality x complexity to a tier and is monotone (law L-4).
required_controls is its Galois adjoint (law L-5), so "what must I do at this
tier" and "what tier can these controls defend" are one definition.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from core.risk.lattices import (COMPLEXITY, CONTROLS, MATERIALITY, RULESET_VERSION,
                                _OPAQUE_CLASSES)
from db import RiskRepository


@dataclass(frozen=True)
class Assessment:
    tier: int
    materiality: str
    complexity: str
    required_controls: Tuple[str, ...]
    rationale: str
    facts: Dict[str, Any]
    ruleset_version: str = RULESET_VERSION


class TieringEngine:
    """Derives a tier, and stores the derivation alongside it (design rule DR-4)."""

    def __init__(self, exposure_bands: Dict[str, float], purpose_ranks: Dict[str, int],
                 review_months: Dict[int, int]):
        self._bands = sorted(exposure_bands.items(), key=lambda kv: kv[1])
        self._purpose = purpose_ranks
        self._review = review_months

    # ---------------------------------------------------------- the lattices
    def exposure_band(self, exposure: float) -> str:
        band = MATERIALITY[0]
        for name, floor in self._bands:
            if exposure >= floor:
                band = name
        return band

    def materiality(self, exposure: float, purpose: str) -> str:
        """Join: the more severe of the quantitative and qualitative readings."""
        quant = MATERIALITY.index(self.exposure_band(exposure))
        # Purpose ranks are 1-based; materiality indices are 0-based. Rank 1
        # (commercial) must map to 'negligible', not 'low', or every model in
        # the estate is inflated by one level before exposure is even read.
        rank = self._purpose.get(purpose, 1)
        qual = max(0, min(rank - 1, len(MATERIALITY) - 1))
        return MATERIALITY[max(quant, qual)]

    def complexity(self, trainability_class: str, feature_count: int = 0,
                   uses_alternative_data: bool = False, interpretable: bool = True) -> str:
        """Meet over the declared components. Interpretability and data provenance
        are first-class factors, per SS1/23 1.3(c)."""
        score = 0
        if trainability_class in _OPAQUE_CLASSES:
            score += 1
        if trainability_class in {"T4", "T5"}:
            score += 1                       # adaptive or generative: higher uncertainty
        if feature_count > 50:
            score += 1
        if uses_alternative_data:
            score += 1
        if not interpretable:
            score += 1
        return COMPLEXITY[min(score, len(COMPLEXITY) - 1)]

    # ------------------------------------------------------------- the map
    @staticmethod
    def tau(materiality: str, complexity: str) -> int:
        """Monotone in both arguments (law L-4). Materiality dominates: a
        critical-exposure model is never below Tier 2 however simple it is."""
        m, c = MATERIALITY.index(materiality), COMPLEXITY.index(complexity)
        score = m * 2 + c
        if m >= 4:
            return 1
        if score >= 7:
            return 1
        if score >= 5:
            return 2
        if score >= 2:
            return 3
        return 4

    @staticmethod
    def required_controls(tier: int) -> Tuple[str, ...]:
        return tuple(CONTROLS[tier])

    @staticmethod
    def supports_tier(applied: List[str]) -> int:
        """The Galois adjoint: the strictest tier the applied controls can defend."""
        got = set(applied)
        for tier in (1, 2, 3, 4):
            if set(CONTROLS[tier]).issubset(got):
                return tier
        return 4

    # ------------------------------------------------------------- assess
    def assess(self, facts: Dict[str, Any]) -> Assessment:
        exposure = float(facts.get("exposure", 0) or 0)
        purpose = facts.get("purpose_class", "commercial")
        m = self.materiality(exposure, purpose)
        c = self.complexity(facts.get("trainability_class", "T0"),
                            int(facts.get("feature_count", 0) or 0),
                            bool(facts.get("uses_alternative_data", False)),
                            bool(facts.get("interpretable", True)))
        tier = self.tau(m, c)
        rationale = (f"materiality={m} (exposure {exposure:,.0f} in band "
                     f"'{self.exposure_band(exposure)}', purpose '{purpose}'); "
                     f"complexity={c} (class {facts.get('trainability_class', 'T0')}); "
                     f"tau({m},{c})=Tier {tier} under ruleset {RULESET_VERSION}")
        return Assessment(tier=tier, materiality=m, complexity=c,
                          required_controls=self.required_controls(tier),
                          rationale=rationale, facts=dict(facts))

    def persist(self, repo: RiskRepository, model_id: str, a: Assessment) -> Dict[str, Any]:
        months = self._review.get(a.tier, 24)
        row = {"model_id": model_id, "tier": a.tier,
               "materiality": a.materiality, "complexity": a.complexity,
               "facts": a.facts, "required_controls": list(a.required_controls),
               "rationale": a.rationale, "ruleset_version": a.ruleset_version,
               "next_review_due": time.time() + months * 30 * 86400,
               "assessed_at": time.time()}
        return repo.add(row)
