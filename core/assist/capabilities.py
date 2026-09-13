"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The capability registry: what the platform's own AI is allowed to do.

Registering a capability is a governance act, and two rules are enforced at that
moment rather than at the moment of use.

**Tier A requires a named oracle.** A capability claiming that its output is
mechanically checkable must say what checks it. "We validate the output" without
naming the check is the sentence that precedes every AI incident.

**Tier C cannot be registered.** A capability whose output can be neither checked
nor grounded is advisory, and advisory AI is a person using a chat window — not
something the platform runs. Allowing it into the registry would mean allowing
something into the registry that will one day be wired into a decision path,
because everything in a registry eventually is.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.assist import oracles
from core.assist.common import (AUTONOMY, DEFAULT_REVIEW_SAMPLE, TIER_A, TIER_MEANING, TIERS, AssistError)
from core.evidence import EvidenceEngine
from core.log import get_logger
from db import CapabilityRepository

logger = get_logger(__name__)


class CapabilityRegistry:
    """Registers and lists the platform's machine-assistance capabilities."""

    def __init__(self, capabilities: CapabilityRepository, evidence: EvidenceEngine):
        self.capabilities, self.evidence = capabilities, evidence

    def register(self, capability_key: str, description: str, tier: str,
                 base_model: str, prompt_digest: str, owner: str,
                 oracle_key: Optional[str] = None,
                 autonomy: str = "human_approved_automation",
                 review_sample: float = DEFAULT_REVIEW_SAMPLE,
                 actor: str = "system") -> Dict[str, Any]:
        # Normalised before the comparison, so the same mistake gets the same
        # answer. `tier == "C"` was case-sensitive, and a lower-case `c` fell
        # through to `unknown_tier` — "expected A or B" — so somebody who
        # typed the wrong case never learned that C is a deliberate refusal
        # with an argument behind it, and would go looking for a typo.
        tier = (tier or "").strip().upper()
        if tier == "C":
            raise AssistError(
                "advisory_not_registrable",
                "a capability whose output can be neither checked nor grounded is "
                "advisory, and advisory AI is a person using a chat window",
                "if the output can be checked, name the oracle and register it as "
                "Tier A; if its claims can cite evidence, register it as Tier B")
        if tier not in TIERS:
            raise AssistError("unknown_tier", f"unknown assistance tier '{tier}'",
                              f"expected {' or '.join(TIERS)}: "
                              + "; ".join(f"{t} — {TIER_MEANING[t]}" for t in TIERS))
        if tier == TIER_A and not oracle_key:
            raise AssistError(
                "oracle_required",
                "a Tier A capability claims its output is mechanically checkable "
                "and must name the check",
                "name an oracle, or register this as Tier B and ground its claims "
                "in evidence instead")
        if oracle_key and not oracles.get(oracle_key):
            raise AssistError(
                "unknown_oracle", f"no oracle '{oracle_key}'",
                "known oracles are "
                + ", ".join(o["key"] for o in oracles.describe()))
        # A review sample is the FRACTION of generations a person checks, so
        # it lives in 0..1. Nothing checked it: 1.5 and -1 were both stored.
        #
        # A negative one is the dangerous value. Every screen that shows this
        # renders a number beside "reviewed", and -1 reads as a control that
        # is switched on while meaning that nothing is ever sampled.
        if not isinstance(review_sample, (int, float)) or isinstance(
                review_sample, bool) or not 0.0 <= float(review_sample) <= 1.0:
            raise AssistError(
                "review_sample_out_of_range",
                f"a review sample of {review_sample!r} is not a fraction; it "
                f"is the proportion of this capability's generations a person "
                f"reads, so it lies between 0 and 1",
                "0.0 means nobody samples and 1.0 means everything is read; "
                "say which")
        if autonomy not in AUTONOMY:
            raise AssistError("unknown_autonomy", f"unknown autonomy '{autonomy}'",
                              f"expected one of {', '.join(AUTONOMY)}")
        if self.capabilities.one(capability_key=capability_key):
            raise AssistError("duplicate_capability",
                              f"'{capability_key}' is already registered", "")

        row = {"capability_key": capability_key, "description": description,
               "tier": tier, "oracle_key": oracle_key, "autonomy": autonomy,
               "base_model": base_model, "prompt_digest": prompt_digest,
               "review_sample": review_sample, "status": "active", "owner": owner,
               "created_at": time.time()}
        with self.evidence.recording():
            self.capabilities.add(row)
            self.evidence.append("ai_capability_registered", "capability", row["id"],
                                 {"capability_key": capability_key, "tier": tier,
                                  "oracle_key": oracle_key, "base_model": base_model},
                                 actor=actor)
        logger.info("registered machine-assistance capability %s at tier %s",
                    capability_key, tier)
        return self.capabilities.one(id=row["id"])

    # ----------------------------------------------------------------- query
    def get(self, capability_key: str) -> Optional[Dict[str, Any]]:
        return self.capabilities.one(capability_key=capability_key)

    def require(self, capability_key: str) -> Dict[str, Any]:
        row = self.get(capability_key)
        if row is None:
            raise AssistError("no_capability",
                              f"no capability '{capability_key}'", "")
        return row

    def by_id(self, capability_id: str) -> Optional[Dict[str, Any]]:
        return self.capabilities.one(id=capability_id)

    def list(self) -> List[Dict[str, Any]]:
        return self.capabilities.many()

    def suspend(self, capability_key: str, reason: str,
                actor: str = "system") -> Dict[str, Any]:
        row = self.require(capability_key)
        with self.evidence.recording():
            self.capabilities.set({"status": "suspended"}, id=row["id"])
            self.evidence.append("ai_capability_suspended", "capability", row["id"],
                                 {"capability_key": capability_key, "reason": reason},
                                 actor=actor)
        return self.capabilities.one(id=row["id"])
