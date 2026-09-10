"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Machine assistance: where the platform's own AI is allowed to act.

Organised on one question — can a human check the output more cheaply than
produce it? Tier A has an oracle and the check is the control; Tier B grounds
every claim in evidence and a person approves; Tier C is a person using a chat
window and is deliberately not registrable here.

MAYA can now *ask* as well as record. `providers` holds one working provider —
a deterministic mock — and three that refuse by name, because a stub returning
plausible prose into a governance register is worse than no provider at all.
`DraftingService` joins a provider to the gate, and fixes what a model may cite
BEFORE it is asked, so a fabricated citation has nowhere to land.
"""
from core.assist import grounding, oracles
from core.assist.budgets import BudgetRegister
from core.assist.canaries import CanaryRegister
from core.assist.capabilities import CapabilityRegistry
from core.assist.common import (AUTONOMY, TIER_A, TIER_B, TIER_MEANING, TIERS,
                                AssistError)
from core.assist import providers
from core.assist.drafting import DraftingService
from core.assist.generations import GenerationLog
from core.assist.oracles import ORACLES, Oracle, Verdict

__all__ = [
                                "AUTONOMY",
                                "ORACLES",
                                "TIERS",
                                "TIER_A",
                                "TIER_B",
                                "TIER_MEANING",
                                "AssistError",
                                "BudgetRegister", "CanaryRegister", "CapabilityRegistry",
                                "DraftingService",
                                "GenerationLog",
                                "Oracle",
                                "Verdict",
                                "grounding",
                                "oracles",
                                "providers",
]
