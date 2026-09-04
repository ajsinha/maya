"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Three regimes, encoded.

These are illustrative encodings, not legal advice and not complete. A
supervisory statement is forty pages of open-textured prose and turning it into
obligations is expert work that a firm must do for itself, with its own counsel,
against its own estate.

What they demonstrate is the structure: each regime reasons in **its own
vocabulary**, has its own scope, and translates into the core. Adding a fourth —
MAS, APRA, OSFI E-23, a future GenAI rule — is a signature, some sentences and a
translation. Nothing in the schema, the API or the interface moves.

Note how differently the three carve up reality. SR 26-2 asks whether something
applies quantitative theory and how material it is. The EU AI Act asks what the
system is *for* and whether a natural person is affected. SS1/23 asks about
proportionality. A single flat set of compliance fields cannot represent that,
which is the argument for signatures.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

from core.regimes.sentences import Sentence, forbids, implies, requires
from core.regimes.signature import Signature
from core.regimes.translation import Translation

# ---------------------------------------------------------------------------
# SR 26-2 / OCC — US supervisory guidance on model risk management
# ---------------------------------------------------------------------------
SR26_2 = Signature.of("sr-26-2", {
    "applies_quantitative_theory", "produces_estimate", "material_exposure",
    "identified_owner", "effective_challenge", "independent_validation",
    "ongoing_monitoring", "outcomes_analysis", "documented", "in_scope",
})

SR26_2_SENTENCES = (
    Sentence("scope", "a quantitative method producing estimates is a model",
             # `in_scope` is declared because the predicate READS it. The
             # satisfaction condition caught its absence: a sentence evaluated
             # against only its declared terms saw None and concluded the model
             # was out of scope, which is exactly the indefensible determination
             # the check exists to prevent.
             ("applies_quantitative_theory", "produces_estimate", "in_scope"),
             lambda i: not (i.truthy("applies_quantitative_theory")
                            and i.truthy("produces_estimate")) or i.truthy("in_scope"),
             "SR 26-2 §II — definition of a model"),
    implies("owner", "an in-scope model has an identified owner",
            "in_scope", "identified_owner", "SR 26-2 §V — governance"),
    implies("challenge", "an in-scope model receives effective challenge",
            "in_scope", "effective_challenge", "SR 26-2 §IV — validation"),
    implies("independence", "validation is independent of development",
            "in_scope", "independent_validation", "SR 26-2 §IV"),
    implies("monitoring", "an in-scope model is monitored on an ongoing basis",
            "in_scope", "ongoing_monitoring", "SR 26-2 §IV — ongoing monitoring"),
    implies("documentation", "an in-scope model is documented",
            "in_scope", "documented", "SR 26-2 §V — documentation"),
    implies("outcomes", "material models receive outcomes analysis",
            "material_exposure", "outcomes_analysis", "SR 26-2 §IV"),
)

SR26_2_TRANSLATION = Translation(SR26_2, {
    # A model in MAYA is by construction a parametric kernel, which is what
    # "applies quantitative theory to produce an estimate" means here.
    "applies_quantitative_theory": lambda s: True,
    "produces_estimate": lambda s: bool(s.get("has_version")),
    "in_scope": lambda s: bool(s.get("has_version")),
    "material_exposure": lambda s: (s.get("tier") or 4) <= 2,
    "identified_owner": lambda s: bool(s.get("has_owner")),
    "effective_challenge": lambda s: bool(s.get("has_validation")),
    "independent_validation": lambda s: bool(s.get("validation_independent")),
    "ongoing_monitoring": lambda s: bool(s.get("has_monitoring")),
    "outcomes_analysis": lambda s: bool(s.get("has_monitoring")),
    "documented": lambda s: bool(s.get("has_documentation")),
})

# ---------------------------------------------------------------------------
# PRA SS1/23 — UK; proportionality is the organising idea
# ---------------------------------------------------------------------------
SS1_23 = Signature.of("ss1-23", {
    "is_model", "materiality_high", "proportionate_validation", "accountable_smf",
    "model_risk_appetite", "independent_review", "vendor_model",
    "own_outcomes_analysis", "post_model_adjustment", "adjustment_justified",
})

SS1_23_SENTENCES = (
    implies("accountability", "an SMF is accountable for the model",
            "is_model", "accountable_smf", "SS1/23 Principle 1"),
    implies("proportionate", "validation is proportionate to materiality",
            "materiality_high", "proportionate_validation", "SS1/23 Principle 4"),
    implies("independent", "high-materiality models get independent review",
            "materiality_high", "independent_review", "SS1/23 Principle 4"),
    implies("vendor", "vendor models are assessed on our own outcomes",
            "vendor_model", "own_outcomes_analysis", "SS1/23 Principle 2.6"),
    implies("adjustments", "post-model adjustments are justified and reviewed",
            "post_model_adjustment", "adjustment_justified", "SS1/23 Principle 5"),
)

SS1_23_TRANSLATION = Translation(SS1_23, {
    "is_model": lambda s: True,
    "materiality_high": lambda s: (s.get("tier") or 4) <= 2,
    "accountable_smf": lambda s: bool(s.get("has_owner")),
    "proportionate_validation": lambda s: bool(s.get("has_validation")),
    "independent_review": lambda s: bool(s.get("validation_independent")),
    "model_risk_appetite": lambda s: s.get("tier") is not None,
    "vendor_model": lambda s: bool(s.get("is_opaque")),
    "own_outcomes_analysis": lambda s: bool(s.get("has_monitoring")),
    # Principle 5 is why the overlay register exists: an adjustment that is not
    # justified and reviewed is the thing this asks about.
    "post_model_adjustment": lambda s: bool(s.get("has_overlays")),
    "adjustment_justified": lambda s: not bool(s.get("overlay_persistent")),
})

# ---------------------------------------------------------------------------
# EU AI Act — reasons about purpose and about people, not about materiality
# ---------------------------------------------------------------------------
EU_AI_ACT = Signature.of("eu-ai-act", {
    "is_ai_system", "high_risk_use", "affects_natural_persons", "human_oversight",
    "technical_documentation", "logging_enabled", "accuracy_declared",
    "generative_system", "transparency_to_user",
})

EU_AI_ACT_SENTENCES = (
    implies("oversight", "high-risk systems are under human oversight",
            "high_risk_use", "human_oversight", "EU AI Act Art. 14"),
    implies("documentation", "high-risk systems keep technical documentation",
            "high_risk_use", "technical_documentation", "EU AI Act Art. 11, Annex IV"),
    implies("logging", "high-risk systems log their operation",
            "high_risk_use", "logging_enabled", "EU AI Act Art. 12"),
    implies("accuracy", "high-risk systems declare accuracy and robustness",
            "high_risk_use", "accuracy_declared", "EU AI Act Art. 15"),
    implies("transparency", "generative systems are transparent to the user",
            "generative_system", "transparency_to_user", "EU AI Act Art. 50"),
)

EU_AI_ACT_TRANSLATION = Translation(EU_AI_ACT, {
    "is_ai_system": lambda s: True,
    # Not tier alone: the Act asks what the system is FOR and who it touches.
    "high_risk_use": lambda s: (s.get("tier") or 4) <= 2 and bool(
        s.get("affects_natural_persons", s.get("domain") in ("credit", "employment"))),
    "affects_natural_persons": lambda s: s.get("domain") in ("credit", "employment",
                                                             "financial_crime"),
    "human_oversight": lambda s: bool(s.get("human_in_the_loop", True)),
    "technical_documentation": lambda s: bool(s.get("has_documentation")),
    "logging_enabled": lambda s: bool(s.get("has_warrants")),
    "accuracy_declared": lambda s: bool(s.get("has_operating_contract")),
    "generative_system": lambda s: bool(s.get("is_generative")),
    "transparency_to_user": lambda s: bool(s.get("human_in_the_loop", True)),
})


REGIMES: Dict[str, Dict[str, Any]] = {
    "sr-26-2": {"signature": SR26_2, "sentences": SR26_2_SENTENCES,
                "translation": SR26_2_TRANSLATION,
                "title": "SR 26-2 / OCC — US model risk management",
                "authority": "Federal Reserve, OCC, FDIC"},
    "ss1-23": {"signature": SS1_23, "sentences": SS1_23_SENTENCES,
               "translation": SS1_23_TRANSLATION,
               "title": "PRA SS1/23 — UK model risk management principles",
               "authority": "Bank of England, Prudential Regulation Authority"},
    "eu-ai-act": {"signature": EU_AI_ACT, "sentences": EU_AI_ACT_SENTENCES,
                  "translation": EU_AI_ACT_TRANSLATION,
                  "title": "EU AI Act — high-risk and generative obligations",
                  "authority": "European Union"},
}
