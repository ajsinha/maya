"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The vocabulary of an export pack.

An export pack answers one question — *show me everything about this model* —
asked by somebody who is not going to be given a login: a supervisor, an internal
auditor, an acquirer's diligence team. Everything below follows from that
audience.

They cannot query the platform, so the pack has to be **self-contained**. They
cannot take the platform's word for it, so every member is **digested** and the
manifest is digested over the members. They will read it months later, so it
records the **chain head** it was cut against, which is what makes *"has anything
changed since?"* a question with an answer rather than an assurance.

And they must be able to tell a gap from a silence. A pack that omits what it
could not gather looks complete, and a document that looks complete is worse than
one that says where it is thin — so an absence is recorded as an absence, the
same discipline the document compiler applies to a lens that cannot fill its
section.
"""
from __future__ import annotations

from typing import Dict, Tuple

from core.docs.common import KINDS

#: Bumped when the layout changes in a way that would confuse a reader who
#: learned the old one. It is in the manifest so a pack says what shape it is
#: rather than leaving somebody to infer it from what happens to be present.
PACK_VERSION = "1.0"

MANIFEST = "manifest.json"
README = "README.md"
GAPS = "gaps.md"

#: What a pack holds, and what each part answers. Published rather than
#: described, because a reader who does not know what is missing cannot tell a
#: thin model from a thin export.
CONTENTS: Dict[str, str] = {
    MANIFEST: "what this pack is, when it was cut, and the digest of every file in it",
    README: "how to read it and how to verify it, in prose",
    "model.json": "the register record: identity, ownership, purpose, tier and its derivation",
    "versions.json": "every version, its kernel, its status and its approvals",
    "documents/": "the compiled documents, each with the evidence it rests on",
    "attachments/": "the documents somebody filed, as the bytes that were accepted",
    "evidence/chain.json": "the evidence for this model and its versions, with the verification result",
    "validations.json": "validation episodes and their test results",
    "findings.json": "the findings register, open and closed, with the acts that moved them",
    "monitoring.json": "monitors, their status, and the breaches they raised",
    "overlays.json": "post-model adjustments, their magnitude and their ageing",
    "warrants.json": "who was entitled to run it, for what, and what was revoked",
    "documentation/dossier.json": "the documentation graph: which training "
        "record belongs to which fit, and which featureset VERSION each fit read",
    GAPS: "what could not be included, and why — an absence is recorded, never omitted",
}

#: Kinds of document compiled into every pack unless the caller narrows it.
#: All four, because the audience differs per document and a pack cut for one
#: reader is a pack the next reader has to ask for again.
#: Taken from the compiler's own vocabulary rather than retyped, because a copy
#: of a list is a copy that goes stale — and it would go stale silently, as a
#: pack quietly missing a document kind somebody added.
DEFAULT_DOCUMENTS: Tuple[str, ...] = KINDS

#: The zip member timestamp. Fixed rather than "now" so that two packs of the
#: same state differ only where their content differs — a pack whose bytes move
#: because a clock moved cannot be compared to the one before it.
FIXED_TIMESTAMP = (2026, 1, 1, 0, 0, 0)

#: A pack that would be larger than this is refused rather than streamed. An
#: export is meant to be read; one that arrives as forty gigabytes is one nobody
#: opens, and the honest answer is to narrow what was asked for.
MAX_BYTES = 2 * 1024 * 1024 * 1024


class ExportError(RuntimeError):
    """An export was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}
