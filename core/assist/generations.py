"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Recording what the platform's AI produced, and what a human did about it.

The rule the whole package rests on: **a generation is never evidence until a
person has attested it.** Not "should not be" — cannot be. A drafted generation
carries no weight anywhere in the platform, and attestation is the only
transition that gives it any.

Two measurements are taken that are not about the output at all.

**Edit distance** on attestation: how much the reviewer changed. The number is
uninteresting on its own; the *trend* is the point. A reviewer whose edit
distance falls steadily is a reviewer who has stopped reading, and that is a
control failure the platform can detect without anyone reporting it.

**A review sample**: a fraction of attested generations are pulled for
independent review regardless of how good they look. Deliberate friction. Someone
who has approved forty correct drafts is not reviewing the forty-first, and no
amount of telling them to will change that.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional, Sequence

from core.assist import grounding, oracles
from core.assist.common import TIER_A, AssistError
from core.evidence import EvidenceEngine
from core.authz.common import same_person
from core.log import get_logger
from db import GenerationRepository

logger = get_logger(__name__)


class GenerationLog:
    """Records generations, gates them, and holds them until a person attests."""

    def __init__(self, generations: GenerationRepository,
                 capabilities, evidence: EvidenceEngine):
        self.generations, self.capabilities = generations, capabilities
        self.evidence = evidence

    # -------------------------------------------------------------- generate
    def record(self, capability_key: str, subject_type: str, subject_id: str,
               claims: Sequence[Dict[str, Any]],
               known_evidence: Sequence[str],
               oracle_payload: Optional[Dict[str, Any]] = None,
               output: Optional[Dict[str, Any]] = None,
               actor: str = "system") -> Dict[str, Any]:
        """Record a generation, gated. Refused outright if its tier's check fails."""
        capability = self.capabilities.require(capability_key)
        if capability["status"] != "active":
            raise AssistError("capability_inactive",
                              f"'{capability_key}' is {capability['status']}",
                              "reactivate the capability before using it")

        verdict = self._oracle(capability, oracle_payload)
        kept, rejected = grounding.gate(claims, known_evidence)
        report = grounding.report(kept, rejected)

        if capability["tier"] == TIER_A and not verdict.get("passed", False):
            raise AssistError(
                "oracle_failed",
                f"the '{capability['oracle_key']}' oracle rejected this output: "
                f"{verdict.get('detail')}",
                "the check is the control for a Tier A capability; nothing is "
                "recorded when it fails")
        if capability["tier"] != TIER_A and not kept:
            raise AssistError(
                "nothing_grounded",
                "no claim in this generation was supported by evidence",
                "a Tier B capability's output is its grounded claims; there is "
                "nothing left to record")

        row = {"capability_id": capability["id"], "subject_type": subject_type,
               "subject_id": subject_id, "prompt_digest": capability["prompt_digest"],
               "base_model": capability["base_model"],
               "output": {**(output or {}), "text": grounding.assemble(kept),
                          "grounding": report},
               "claims": kept, "rejected_claims": rejected,
               "oracle_verdict": verdict, "state": "drafted",
               "sampled": int(self._sample(capability)),
               "attested_by": None, "attested_at": None, "edit_distance": None,
               "created_at": time.time(), "created_by": actor}
        with self.evidence.recording():
            self.generations.add(row)
            self.evidence.append("ai_generation_drafted", subject_type, subject_id,
                                 {"generation_id": row["id"],
                                  "capability": capability_key,
                                  "grounded": report["grounded"],
                                  "rejected": report["rejected"],
                                  "oracle": verdict}, actor=actor)
        return self.generations.one(id=row["id"])

    def _oracle(self, capability: Dict[str, Any],
                payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        key = capability.get("oracle_key")
        if not key:
            return {"oracle": None, "passed": None,
                    "detail": "no oracle; this capability is grounded, not verified"}
        oracle = oracles.get(key)
        verdict = oracle.check(payload or {})
        return {"oracle": key, **verdict.as_dict()}

    def _sample(self, capability: Dict[str, Any]) -> bool:
        """Deterministic sampling on the capability's own counter.

        Not random: a reviewer must not be able to learn that today's drafts are
        unsampled, and a test must be able to depend on it.

        The counter is how many generations this capability has already produced,
        so the sequence is fixed by the capability and its own history. Seeding on
        the clock — which this did until it was noticed — made the docstring false
        in both halves: the sequence was unrepeatable, so no test could depend on
        it, and a drafter watching which of their own drafts were sampled could
        infer the rate and time around it.
        """
        rate = capability.get("review_sample") or 0.0
        if rate <= 0:
            return False
        drawn = len(self.generations.many(capability_id=capability["id"]))
        seed = hashlib.sha256(
            f"{capability['id']}:{drawn}".encode()).digest()[0] / 255.0
        return seed < rate

    # --------------------------------------------------------------- attest
    def attest(self, generation_id: str, actor: str, final_text: str = "",
               accept: bool = True, note: str = "") -> Dict[str, Any]:
        """A person takes responsibility for it, or rejects it.

        Until this happens the generation carries no weight anywhere in the
        platform. Attestation is the only transition that gives it any.
        """
        row = self.require(generation_id)
        if row["state"] != "drafted":
            raise AssistError("already_decided",
                              f"this generation is already '{row['state']}'", "")
        if same_person(actor, row["created_by"]) and row["created_by"] != "system":
            raise AssistError(
                "self_attestation",
                f"{actor} requested this generation and cannot also attest it",
                "attestation is a person taking responsibility for machine output; "
                "it must be somebody other than whoever asked for it")

        state = "attested" if accept else "rejected"
        distance = self.edit_distance(row["output"].get("text", ""), final_text) \
            if accept and final_text else None
        with self.evidence.recording():
            self.generations.set({"state": state, "attested_by": actor,
                                  "attested_at": time.time(),
                                  "edit_distance": distance}, id=generation_id)
            self.evidence.append(f"ai_generation_{state}", row["subject_type"],
                                 row["subject_id"],
                                 {"generation_id": generation_id, "note": note,
                                  "edit_distance": distance}, actor=actor)
        return self.generations.one(id=generation_id)

    @staticmethod
    def edit_distance(drafted: str, final: str) -> float:
        """Fraction of the draft the reviewer changed, by token overlap.

        Crude on purpose. The absolute number means little; what matters is
        whether it falls over time for a given reviewer, and a crude measure
        detects that just as well as an expensive one.
        """
        a, b = drafted.split(), final.split()
        if not a and not b:
            return 0.0
        kept = len(set(a) & set(b))
        return round(1.0 - kept / max(len(a), len(b), 1), 4)

    # ----------------------------------------------------------------- query
    def get(self, generation_id: str) -> Optional[Dict[str, Any]]:
        return self.generations.one(id=generation_id)

    def require(self, generation_id: str) -> Dict[str, Any]:
        row = self.get(generation_id)
        if row is None:
            raise AssistError("no_generation", f"no generation {generation_id}", "")
        return row

    def for_subject(self, subject_id: str) -> List[Dict[str, Any]]:
        return self.generations.many(subject_id=subject_id)

    def automation_bias(self, reviewer: str) -> Dict[str, Any]:
        """Is this reviewer still reading?

        A steadily falling edit distance is a reviewer who has stopped
        challenging the machine — a control failure the platform can see without
        anyone reporting it.
        """
        rows = [g for g in self.generations.many(attested_by=reviewer)
                if g.get("edit_distance") is not None]
        if len(rows) < 4:
            return {"reviewer": reviewer, "attested": len(rows), "known": False,
                    "detail": "too few attestations to establish a trend"}
        half = len(rows) // 2
        early = sum(r["edit_distance"] for r in rows[:half]) / half
        late = sum(r["edit_distance"] for r in rows[half:]) / (len(rows) - half)
        falling = late < early * 0.5
        return {
            "reviewer": reviewer, "attested": len(rows), "known": True,
            "early_mean": round(early, 4), "late_mean": round(late, 4),
            "falling": falling,
            "detail": (f"edit distance fell from {early:.2f} to {late:.2f} across "
                       f"{len(rows)} attestations — this reviewer may have stopped "
                       "reading" if falling else
                       f"edit distance is steady around {late:.2f}"),
        }
