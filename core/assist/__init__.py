"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Machine assistance: where the platform's own AI is allowed to act.

Organised on one question — can a human check the output more cheaply than
produce it? Tier A has an oracle and the check is the control; Tier B grounds
every claim in evidence and a person approves; Tier C is a person using a chat
window and is deliberately not registrable here.
"""
from core.assist import grounding, oracles
from core.assist.capabilities import CapabilityRegistry
from core.assist.common import (AUTONOMY, TIER_A, TIER_B, TIER_MEANING, TIERS,
                                AssistError)
from core.assist.generations import GenerationLog
from core.assist.oracles import ORACLES, Oracle, Verdict

__all__ = ["CapabilityRegistry", "GenerationLog", "AssistError", "grounding",
           "oracles", "ORACLES", "Oracle", "Verdict", "TIERS", "TIER_A", "TIER_B",
           "TIER_MEANING", "AUTONOMY"]
