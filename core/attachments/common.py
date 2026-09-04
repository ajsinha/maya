"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Attached documents: the ones somebody wrote.

The compiler in ``core/docs`` generates documents from the register. This is the
other half, and a bank has far more of it: a model development document written
in Word, a vendor's validation report, a board paper, a model risk committee
minute, a signed attestation, an independent review commissioned from outside.

These cannot be generated and must not be ignored. A register that holds only
what it can compute is a register that quietly excludes most of the evidence a
supervisor will actually ask to see.

Two decisions shape everything here.

**A document attaches to a VERSION, not merely to a model.** "The model
development document" is about a particular version of a particular model, and
one attached at model level floats free of what it describes — which is exactly
how a bank ends up with an MDD describing v2.1 filed against a model serving
v2.4. Model-level attachment is allowed for the few things genuinely about the
model rather than a version, and it has to be asked for.

**Documents are content-addressed.** A file is stored under its digest, so the
same board paper attached to five models is stored once, and a document cannot
be edited in place — editing produces a different digest, which is a different
document, which is a supersession somebody has to declare.
"""
from __future__ import annotations

from typing import Dict, Tuple

# What a document is, which decides who should review it and what it evidences.
KINDS: Tuple[str, ...] = (
    "model_development_document",
    "validation_report",
    "independent_review",
    "vendor_documentation",
    "committee_minute",
    "board_paper",
    "evidence_of_control",
    "correspondence",
    "other",
)

KIND_MEANING: Dict[str, str] = {
    "model_development_document": "how the model was built and under what assumptions",
    "validation_report": "what independent challenge found",
    "independent_review": "a review commissioned from outside the second line",
    "vendor_documentation": "what a vendor supplied about a model we cannot open",
    "committee_minute": "what a governance forum decided, and on what basis",
    "board_paper": "what was put to the board",
    "evidence_of_control": "proof that a stated control operated",
    "correspondence": "an exchange with a supervisor, auditor or vendor",
    "other": "something the list above does not cover",
}

# attached -> accepted | rejected, and accepted -> superseded.
STATES: Tuple[str, ...] = ("attached", "accepted", "rejected", "superseded")

# Formats whose text can be read out for search, citation and — later — review
# by machine. Anything else is stored and served; its text is simply not indexed,
# and the register says so rather than pretending it was read.
TEXT_MEDIA: Dict[str, str] = {
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/json": ".json",
    "text/html": ".html",
    "application/xml": ".xml",
}

MAX_BYTES = 64 * 1024 * 1024


class AttachmentError(RuntimeError):
    """A document operation was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}
