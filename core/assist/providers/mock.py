"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A language model that is not one.

It composes sentences from the evidence it was handed, in a fixed order, with no
randomness. That makes it useless for prose and ideal for everything else: the
capability register, the oracle, the grounding gate, attestation, edit-distance
measurement and automation-bias sampling are all exercised for real, and the
only fake part is the sentence -- which is the part the platform was never going
to trust.

**It is deterministic on purpose.** Seeded from the digest of its own prompt, so
the same request drafts the same words. A mock that varied would make every test
that touches it flaky, and a demonstration that could not be repeated would be a
demonstration of nothing.

**It deliberately produces one ungroundable claim** when asked to. A mock that
only ever cited real evidence would leave the rejection path -- the control that
actually matters -- untested, and the first ungrounded claim anybody saw would
be in production. ``fabricate=True`` makes it cite something that does not
exist, so the gate can be watched doing its job.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional, Tuple

from core.assist.providers.common import Draft
from core.log import get_logger

logger = get_logger(__name__)

KEY = "mock"

# Sentence frames. Chosen so the output reads like a governance note rather than
# lorem ipsum -- somebody reviewing a mock draft should be reviewing something
# shaped like the real thing.
FRAMES = (
    "The record shows {subject} at {stamp}, established by {citation}.",
    "{subject} rests on {citation}, which was recorded rather than asserted.",
    "As of {stamp}, {citation} supports the position taken on {subject}.",
    "{citation} is the basis for {subject}; nothing further was relied on.",
)

# What an ungrounded claim looks like: a citation that reads exactly like a real
# one and names nothing. This is the shape a real model's fabrication takes.
FABRICATED = "evidence:0000000000000000000000000000000000000000000000000000000000000000"


class MockProvider:
    """Drafts from evidence, deterministically, without calling anything."""

    key = KEY

    def __init__(self, fabricate: bool = False):
        # When true, one extra claim cites evidence that does not exist. The
        # grounding gate should drop it, and a test should watch that happen.
        self.fabricate = fabricate

    def available(self) -> Optional[str]:
        return None

    def draft(self, prompt: str, *, base_model: str = "mock-1",
              evidence_ids: Tuple[str, ...] = (),
              context: Optional[Dict[str, Any]] = None) -> Draft:
        context = context or {}
        subject = context.get("subject") or "the model"
        stamp = context.get("as_of") or "the current record"
        seed = int(hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8], 16)

        claims = []
        for i, evidence_id in enumerate(evidence_ids):
            frame = FRAMES[(seed + i) % len(FRAMES)]
            claims.append({
                "text": frame.format(subject=subject, stamp=stamp,
                                     citation=self._cite(evidence_id)),
                # `citations`, which is the key core.assist.grounding reads.
                "citations": [evidence_id]})
        if self.fabricate:
            claims.append({
                "text": f"{subject} was independently confirmed by a review that "
                        f"is not in the record.",
                "citations": [FABRICATED]})

        text = " ".join(c["text"] for c in claims)
        logger.info("mock provider drafted %d claim(s) from %d evidence node(s)",
                    len(claims), len(evidence_ids))
        return Draft(text=text, claims=claims, model=base_model, provider=KEY,
                     usage={"prompt_characters": len(prompt),
                            "claims": len(claims),
                            # No tokens, and saying zero rather than inventing a
                            # number: a usage figure nobody can reconcile is
                            # worse than none.
                            "tokens": 0})

    @staticmethod
    def _cite(evidence_id: str) -> str:
        return f"evidence {evidence_id[:12]}"
