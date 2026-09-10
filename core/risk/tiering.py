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
from typing import Any, ClassVar, Dict, Iterable, List, Optional, Tuple

from core.risk.designations import extra_controls
from core.risk.lattices import (COMPLEXITY, CONTROLS, MATERIALITY, RULESET_VERSION,
                                _OPAQUE_CLASSES)
from db import RiskRepository


class RiskError(RuntimeError):
    """A refusal about a risk assessment."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, Any]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


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
        """Join: the more severe of the quantitative and qualitative readings.

        An unrecognised purpose class is **refused**, not defaulted. It used to
        fall back to rank 1 via `.get(purpose, 1)`, which meant a caller who
        wrote `credit_decision` or `clinical_decision` --- neither in the
        configured vocabulary --- got the rank of `commercial`, the lowest
        there is, and a recorded rationale that read the string back as though
        it had been understood. Nine case studies declared five such classes
        between them and every one of them silently tiered as commercially
        trivial.

        This is the same failure the register already refuses for an unknown
        kernel key and an unknown contract section: a field MAYA does not read
        is a constraint that silently does not exist, and here it does not
        merely fail to constrain --- it lowers the tier.
        """
        quant = MATERIALITY.index(self.exposure_band(exposure))
        if purpose not in self._purpose:
            raise RiskError(
                "unknown_purpose_class",
                f"purpose class '{purpose}' is not in the configured "
                f"vocabulary, so it has no materiality rank",
                "declare one of " + ", ".join(sorted(self._purpose)) +
                " — or add this one to risk.purpose_ranks, which is a policy "
                "decision about how severely the estate reads it rather than "
                "something a caller may assert in passing")
        # Purpose ranks are 1-based; materiality indices are 0-based. Rank 1
        # (commercial) must map to 'negligible', not 'low', or every model in
        # the estate is inflated by one level before exposure is even read.
        rank = self._purpose[purpose]
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
    def required_controls(tier: int,
                          designations: Optional[Iterable[str]] = None
                          ) -> Tuple[str, ...]:
        """What this model owes: its tier's controls, plus its designations'.

        Additive and orthogonal. A designation does not move a model up or down
        the lattice — two models at the same tier can owe different things
        because one of them feeds a regulatory submission, and no amount of
        re-tiering produces a reconciliation requirement.
        """
        out = list(CONTROLS[tier])
        for control in extra_controls(designations or ()):
            if control not in out:
                out.append(control)
        return tuple(out)

    @staticmethod
    def supports_tier(applied: List[str]) -> int:
        """The Galois adjoint: the strictest tier the applied controls can defend.

        Reads TIER controls and only tier controls, deliberately. An adjoint
        that also read designation controls would answer *which tier do these
        defend* with a number depending on facts the tier lattice does not
        contain, and `L-5` — which is the pair of these two being adjoint —
        would stop holding without anything obviously breaking.
        """
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
                          required_controls=self.required_controls(
                              tier, facts.get("designations")),
                          rationale=rationale, facts=dict(facts))

    #: The reading of an undeclared complexity fact that assumes the worst.
    #: `feature_count` is 51 because the band it has to cross is "> 50".
    #:
    #: `trainability_class` is here because it is not a fact the caller sends —
    #: it is read off the model's latest version, and a model with no version
    #: yet has none. That was being read as `T0`, the SIMPLEST class there is,
    #: which is how every case study in this repository tiered itself: assess
    #: first, register the version second, and receive a tier computed as
    #: though the model were an analytic formula. Re-running the same script
    #: then produced a different tier, which is the visible symptom.
    #: `T5` is the worst reading: opaque (+1) and generative (+1).
    CONSERVATIVE: ClassVar[Dict[str, Any]] = {"feature_count": 51,
                                              "uses_alternative_data": True,
                                              "interpretable": False,
                                              "trainability_class": "T5"}

    def load_bearing(self, facts: Dict[str, Any],
                     declared: Iterable[str]) -> List[str]:
        """Undeclared facts that would change the tier if read the other way.

        Three of the five complexity facts have a benign default, so a caller
        who sends only exposure and purpose — which the SDK did — silently
        declared "no alternative data, interpretable, under fifty features".
        Nobody said that; the schema did, and the recorded rationale then read
        it back as if somebody had.

        Refusing every omission would fail assessments where the omission
        cannot matter. So this asks the only question worth asking: read the
        undeclared facts at their worst, and does the tier move? If it does,
        the omission is load-bearing and the caller has to say. If it does
        not, the model is that tier either way.
        """
        missing = [f for f in self.CONSERVATIVE if f not in set(declared)]
        if not missing:
            return []
        worst = {**facts, **{f: self.CONSERVATIVE[f] for f in missing}}
        if self.assess(worst).tier == self.assess(facts).tier:
            return []
        return missing

    def refuse_a_review_that_says_nothing(self, repo: RiskRepository,
                                          model_id: str,
                                          facts: Dict[str, Any],
                                          note: Optional[str]) -> None:
        """A reassessment on last year's numbers is not a review.

        `next_review_due` is set from the moment `persist` runs, and the job
        that raises "periodic review is overdue" measures whether the formula
        was RE-RUN — not whether anybody reviewed anything. So a review was
        dischargeable by re-POSTing the previous assessment's facts: identical
        inputs, identical tier, and the due date eighteen months further out.

        Not refused outright, because "nothing has changed" is the commonest
        honest outcome of a real review. Refused unless it says what was
        examined, which is the difference between a review and a re-run.
        """
        rows = repo.many(model_id=model_id)
        if not rows:
            return
        previous = max(rows, key=lambda r: r.get("assessed_at") or 0)
        if (previous.get("facts") or {}) != facts:
            return                              # something moved; that IS the review
        if (note or "").strip():
            return
        raise RiskError(
            "review_says_nothing",
            "these are the same facts as the last assessment, so re-running "
            "the formula moves the review date without anything having been "
            "reviewed",
            "say what was examined and why the tier is unchanged, or send the "
            "facts that have moved")

    def persist(self, repo: RiskRepository, model_id: str, a: Assessment) -> Dict[str, Any]:
        months = self._review.get(a.tier, 24)
        row = {"model_id": model_id, "tier": a.tier,
               "materiality": a.materiality, "complexity": a.complexity,
               "facts": a.facts, "required_controls": list(a.required_controls),
               "rationale": a.rationale, "ruleset_version": a.ruleset_version,
               "next_review_due": time.time() + months * 30 * 86400,
               "assessed_at": time.time()}
        return repo.add(row)
