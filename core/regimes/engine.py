"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The regime engine: several supervisors at once, without flattening them.

A bank subject to the Federal Reserve, the PRA and the EU AI Act is subject to
three different *vocabularies*, not three checklists over one. The engine keeps
them apart, evaluates each in its own terms, and reports where they disagree —
which is a real and useful output, because a model in scope for one and out of
scope for another is a fact somebody needs to know rather than a bug.

Two things are enforced.

**A regime cannot be activated until its translation passes the satisfaction
condition.** An encoding whose truth does not survive translation would produce
scope determinations that cannot be defended, and those are worse than no
determinations at all.

**Determinations are derivations.** Every answer carries the terms it read and
the citation it rests on, because "why is this model in scope for the AI Act" is
the question that gets asked, and "the system said so" has never been an answer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.evidence import EvidenceEngine
from core.log import get_logger
from core.regimes.common import RegimeError
from core.regimes.library import REGIMES
from core.regimes.translation import satisfaction_condition

logger = get_logger(__name__)

# Inventory states the satisfaction condition is checked against. Deliberately
# spanning the corners: nothing, everything, and the awkward middles.
PROBE_STATES: Sequence[Dict[str, Any]] = (
    {},
    {"has_version": True, "has_owner": True, "tier": 1, "domain": "credit",
     "has_validation": True, "validation_independent": True,
     "has_monitoring": True, "has_documentation": True,
     "has_operating_contract": True, "has_warrants": True},
    {"has_version": True, "has_owner": False, "tier": 1, "domain": "credit"},
    {"has_version": True, "tier": 4, "domain": "marketing"},
    {"has_version": True, "tier": 2, "domain": "credit", "is_opaque": True,
     "has_overlays": True, "overlay_persistent": True},
    {"has_version": True, "tier": 3, "domain": "financial_crime",
     "is_generative": True, "human_in_the_loop": False},
)


class RegimeEngine:
    """Evaluates a model against every activated regime, in its own vocabulary."""

    def __init__(self, evidence: EvidenceEngine,
                 regimes: Optional[Dict[str, Dict[str, Any]]] = None):
        self.evidence = evidence
        self.library = regimes or REGIMES
        self._active: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------- activate
    def activate(self, key: str, actor: str = "system") -> Dict[str, Any]:
        """Turn a regime on — but only if its encoding is self-consistent."""
        regime = self.library.get(key)
        if regime is None:
            raise RegimeError("no_regime", f"no regime '{key}'",
                              f"known regimes are {', '.join(sorted(self.library))}")
        if untranslated := regime["translation"].missing():
            raise RegimeError(
                "incomplete_translation",
                f"{len(untranslated)} term(s) in the {key} signature have no "
                f"translation: {', '.join(untranslated)}",
                "every term a regime reasons in must map to something the "
                "platform can evaluate, or nothing can decide it")

        report = self.check(key)
        if not report["holds"]:
            raise RegimeError(
                "satisfaction_condition_failed",
                f"the {key} encoding is inconsistent: {report['detail']}",
                "truth must be invariant under translation; a regime whose "
                "encoding fails this produces determinations that cannot be "
                "defended to an examiner")

        self._active[key] = regime
        self.evidence.append("regime_activated", "regime", key,
                             {"regime": key, "title": regime["title"],
                              "sentences": len(regime["sentences"]),
                              "satisfaction_checked": report["checked"]},
                             actor=actor)
        logger.info("activated regime %s (%d sentences, satisfaction condition "
                    "checked over %d pairs)", key, len(regime["sentences"]),
                    report["checked"])
        return {"regime": key, "active": True, "satisfaction": report}

    def check(self, key: str,
              states: Optional[Sequence[Mapping[str, Any]]] = None) -> Dict[str, Any]:
        """Run the satisfaction condition for a regime, without activating it."""
        regime = self.library.get(key)
        if regime is None:
            raise RegimeError("no_regime", f"no regime '{key}'", "")
        return satisfaction_condition(regime["translation"], regime["sentences"],
                                      states or PROBE_STATES)

    def active(self) -> List[str]:
        return sorted(self._active)

    # -------------------------------------------------------------- evaluate
    def determine(self, key: str, core_state: Mapping[str, Any]) -> Dict[str, Any]:
        """One regime's verdict on one model, with its derivation."""
        regime = self.library.get(key)
        if regime is None:
            raise RegimeError("no_regime", f"no regime '{key}'", "")
        interp = regime["translation"].interpret(core_state)
        results = [s.evaluate(interp) for s in regime["sentences"]]
        unmet = [r for r in results if not r["satisfied"]]
        return {
            "regime": key, "title": regime["title"],
            "authority": regime["authority"],
            "vocabulary": sorted(regime["signature"].terms),
            "read_as": dict(interp.values),
            "obligations": results,
            "satisfied": len(results) - len(unmet), "unmet": len(unmet),
            "compliant": not unmet,
            "detail": (f"all {len(results)} obligation(s) satisfied" if not unmet
                       else f"{len(unmet)} unmet: "
                            + "; ".join(r["text"] for r in unmet)),
        }

    def determine_all(self, core_state: Mapping[str, Any]) -> Dict[str, Any]:
        """Every activated regime, kept apart rather than merged.

        Where regimes disagree — in scope for one, out for another — that is
        reported as a disagreement, because it is a fact somebody needs rather
        than an inconsistency to be resolved away.
        """
        if not self._active:
            return {"regimes": [], "detail": "no regimes are activated"}
        verdicts = [self.determine(k, core_state) for k in self.active()]
        compliant = [v["regime"] for v in verdicts if v["compliant"]]
        return {
            "regimes": verdicts,
            "compliant_under": compliant,
            "not_compliant_under": [v["regime"] for v in verdicts
                                    if not v["compliant"]],
            "disagreement": len(compliant) not in (0, len(verdicts)),
            "detail": (f"compliant under {len(compliant)} of {len(verdicts)} "
                       f"activated regime(s)"
                       + ("; the regimes disagree, which is a fact about the "
                          "estate rather than a defect"
                          if 0 < len(compliant) < len(verdicts) else "")),
        }

    @staticmethod
    def core_state(state: Mapping[str, Any]) -> Dict[str, Any]:
        """Reduce the platform's own view of a model to the core vocabulary.

        The same state dictionary the document compiler and the gap detector
        read, projected onto the terms a regime can be translated into — so all
        three agree about what a model has.
        """
        model = state.get("model") or {}
        versions = state.get("versions") or []
        latest = versions[-1] if versions else {}
        validations = state.get("validations") or []
        overlays = state.get("overlays") or {}
        lifecycle = state.get("lifecycle") or {}
        return {
            "has_owner": bool(model.get("owner")),
            "has_declared_purpose": bool(model.get("purpose")),
            "legal_entity": model.get("legal_entity"),
            "domain": model.get("domain"),
            "tier": model.get("tier"),
            "trainability_class": latest.get("trainability_class"),
            "parameter_kind": latest.get("parameter_kind"),
            "is_opaque": latest.get("parameter_kind") == "opaque",
            "is_generative": latest.get("parameter_kind") == "llm_configuration",
            "has_version": bool(versions),
            "has_artifact_digest": bool(latest.get("artifact_digest")),
            "has_operating_contract": bool(latest.get("contract")),
            "has_feature_contract": bool(state.get("feature_contract")),
            "has_validation": bool(validations),
            "validation_independent": any(
                (v.get("independence") or {}).get("independent") for v in validations),
            "has_monitoring": bool((state.get("monitoring") or {}).get("monitors")),
            "has_documentation": bool(state.get("documents")),
            "is_attested": bool(lifecycle.get("attested_at")),
            "has_warrants": bool(state.get("warrants")),
            "has_overlays": bool(overlays.get("active")),
            "overlay_persistent": bool(overlays.get("persistent")),
        }
