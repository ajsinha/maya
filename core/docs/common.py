"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The documentation vocabulary.

A model development document is the artifact a supervisor reads, and in most
banks it is the artifact that has drifted furthest from the model. It is written
once, by hand, for a version that has since been replaced — and nothing connects
the prose to the thing it describes.

So here documents are **compiled**, and two properties follow from that which a
written document cannot have. Every section says which evidence it rested on, so
support is checkable. And the compiler records how far the evidence chain had
got, so staleness is *computed* rather than remembered.
"""
from __future__ import annotations

from typing import Dict, Tuple

MODEL_DEVELOPMENT = "model_development_document"
VALIDATION_REPORT = "validation_report"
MODEL_CARD = "model_card"
ANNEX_IV = "annex_iv"

KINDS: Tuple[str, ...] = (MODEL_DEVELOPMENT, VALIDATION_REPORT, MODEL_CARD, ANNEX_IV)

TITLES: Dict[str, str] = {
    MODEL_DEVELOPMENT: "Model Development Document",
    VALIDATION_REPORT: "Validation Report",
    MODEL_CARD: "Model Card",
    ANNEX_IV: "EU AI Act — Annex IV Technical Documentation",
}

PURPOSE: Dict[str, str] = {
    MODEL_DEVELOPMENT: "what the model is, how it was built, and under what "
                       "assumptions it may be relied on",
    VALIDATION_REPORT: "what independent challenge was performed and what it found",
    MODEL_CARD: "a short, plain description for anyone deciding whether to use it",
    ANNEX_IV: "the technical documentation an EU AI Act high-risk system must keep",
}


class DocumentError(RuntimeError):
    """A documentation operation was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}
