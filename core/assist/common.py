"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Where the platform's own AI is allowed to act.

The organising question is not "is the model good enough". It is **whether a
human can check the output more cheaply than producing it**. Where such a check
exists, a language model can be wrong loudly and cheaply and the system catches
it. Where no check exists, it is wrong *quietly* — and in a governance system
quiet wrongness is the failure mode that matters.

That gives three tiers, and only two of them can exist here.

  **Tier A — verified.** A formal property acts as an oracle. The check is the
  control, so the output can be trusted once it passes.

  **Tier B — grounded.** No single formal check, but every claim can cite
  evidence and the citations can be verified. Ungrounded claims are rejected,
  and a human approves what remains.

  **Tier C — advisory.** Neither. AI may summarise and surface but never
  conclude — and that is a person using a chat window, not a platform
  capability. It is deliberately not registrable here: a Tier C capability in a
  registry is a Tier C capability that will one day be wired into a decision.
"""
from __future__ import annotations

from typing import Dict, Tuple

TIER_A = "A"   # an oracle checks it
TIER_B = "B"   # citations ground it and a human approves it

TIERS: Tuple[str, ...] = (TIER_A, TIER_B)

TIER_MEANING: Dict[str, str] = {
    TIER_A: "a formal property checks the output; the check is the control",
    TIER_B: "every claim cites evidence, citations are verified, a human approves",
}

COLLABORATIVE = "collaborative_assistance"      # a person is doing the work
HUMAN_APPROVED = "human_approved_automation"    # the machine drafts, a person signs
AUTONOMY: Tuple[str, ...] = (COLLABORATIVE, HUMAN_APPROVED)

# A generation's life. It is never evidence until a person has attested it.
GENERATION_STATES: Tuple[str, ...] = ("drafted", "attested", "rejected")

# Fraction of accepted generations pulled for independent review regardless of
# how good they look. Deliberate friction against automation bias: a reviewer who
# has approved forty correct drafts is not reviewing the forty-first.
DEFAULT_REVIEW_SAMPLE = 0.1


class AssistError(RuntimeError):
    """A machine-assistance operation was refused. The message says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}
