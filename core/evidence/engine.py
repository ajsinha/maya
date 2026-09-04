"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The evidence engine: an append-only, hash-chained record with semiring
evaluation over the derivation DAG.

The DAG says what supports what; the linear seq/prev_hash chain makes deletion
of a leaf and insertion into the past detectable.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generic, List, Optional, Set, Tuple, TypeVar

from core.evidence.semirings import (BOOLEAN, COST, COUNTING, FRESHNESS, TRUST,
                                     WHY, MAX_TERMS, Semiring)
from db import EvidenceRepository
from db.database import digest as canonical_digest

GENESIS = "sha256:" + "0" * 64


@dataclass
class Derivation:
    """A claim: a disjunction of conjunctions over evidence identifiers."""
    key: str
    alternatives: Tuple[Tuple[str, ...], ...] = ()      # OR of ANDs

    @property
    def is_leaf(self) -> bool:
        return not self.alternatives


@dataclass
class EvaluationResult:
    value: Any
    truncated: bool = False


class EvidenceEngine:
    """Append-only, hash-chained evidence with semiring evaluation over it."""

    def __init__(self, repo: EvidenceRepository):
        self.repo = repo

    # -------------------------------------------------------------- append
    def head(self) -> Tuple[int, str]:
        row = self.repo.first("seq", desc=True)
        return (row["seq"], row["chain_hash"]) if row else (0, GENESIS)

    def append(self, kind: str, subject_type: str, subject_id: str,
               payload: Optional[Dict[str, Any]] = None, parents: Optional[List[str]] = None,
               *, personal_data: bool = False, trust: float = 1.0,
               actor: str = "system") -> Dict[str, Any]:
        payload, parents = payload or {}, sorted(parents or [])
        # Hashed over what is STORED, not over what was passed: a node carrying
        # personal data stores an empty payload (law L-18), and hashing the
        # original would make every such node fail its own verification.
        stored_payload = {} if personal_data else payload
        content_hash = self.content_hash_of(
            {"kind": kind, "subject_type": subject_type, "subject_id": subject_id,
             "payload": stored_payload, "parents": parents})
        prev_seq, prev_hash = self.head()
        seq = prev_seq + 1
        node = {
            "seq": seq, "kind": kind,
            "subject_type": subject_type, "subject_id": subject_id,
            # Law L-18: personal data is never inline, only an erasable pointer.
            "payload": stored_payload,
            "parents": parents, "contains_personal_data": personal_data,
            "content_hash": content_hash, "prev_hash": prev_hash,
            "chain_hash": canonical_digest([seq, prev_hash, content_hash, parents]),
            "trust": trust, "recorded_at": time.time(), "recorded_by": actor,
        }
        return self.repo.add(node)

    @staticmethod
    def content_hash_of(node: Dict[str, Any]) -> str:
        """The digest a node's own fields imply. One definition, two callers.

        ``append`` and ``verify_chain`` must agree exactly, and the only way to
        guarantee that is for there to be one expression of it.
        """
        return canonical_digest({
            "kind": node["kind"],
            "subject": [node["subject_type"], node["subject_id"]],
            "payload": node.get("payload") or {},
            "parents": node.get("parents") or []})

    def verify_chain(self) -> Dict[str, Any]:
        """Walk the chain. Reports the first break, if any."""
        nodes = self.repo.many()
        prev_hash, expected_seq = GENESIS, 1
        for n in nodes:
            if n["seq"] != expected_seq:
                return {"valid": False, "broken_at": n["seq"], "reason": "sequence gap"}
            if n["prev_hash"] != prev_hash:
                return {"valid": False, "broken_at": n["seq"], "reason": "prev_hash mismatch"}
            # The content hash is RECOMPUTED from the node's own fields rather
            # than trusted as stored. Re-linking a stored content_hash proves
            # only that the links are intact; it says nothing about whether the
            # thing linked is still what was recorded, so an edited payload
            # would leave a chain that verifies and a record that lies.
            if self.content_hash_of(n) != n["content_hash"]:
                return {"valid": False, "broken_at": n["seq"],
                        "reason": "content_hash mismatch: the node's payload, "
                                  "kind or subject is not what was recorded"}
            recomputed = canonical_digest([n["seq"], n["prev_hash"], n["content_hash"], n["parents"]])
            if recomputed != n["chain_hash"]:
                return {"valid": False, "broken_at": n["seq"], "reason": "chain_hash mismatch"}
            prev_hash, expected_seq = n["chain_hash"], expected_seq + 1
        return {"valid": True, "length": len(nodes), "head": prev_hash}

    def for_subject(self, subject_id: str) -> List[Dict[str, Any]]:
        return self.repo.many(subject_id=subject_id)

    # ------------------------------------------------------------ evaluate
    def evaluate(self, claim: str, derivations: Dict[str, Derivation], semiring: Semiring,
                 valuation: Callable[[str], Any]) -> EvaluationResult:
        """Memoised bottom-up evaluation of the derivation DAG."""
        memo: Dict[str, Any] = {}
        truncated = [False]

        def go(key: str, seen: frozenset) -> Any:
            if key in memo:
                return memo[key]
            if key in seen:                                  # a cycle contributes nothing
                return semiring.zero
            node = derivations.get(key)
            if node is None or node.is_leaf:
                return valuation(key)
            total = semiring.zero
            for alt in node.alternatives:
                term = semiring.one
                for dep in alt:
                    term = semiring.times(term, go(dep, seen | {key}))
                total = semiring.plus(total, term)
                if semiring is WHY and len(total) > MAX_TERMS:
                    truncated[0] = True
                    break
            memo[key] = total
            return total

        return EvaluationResult(go(claim, frozenset()), truncated[0])

    # Convenience valuations ------------------------------------------------
    def presence_valuation(self, subject_id: str) -> Callable[[str], bool]:
        kinds = {n["kind"] for n in self.for_subject(subject_id)}
        return lambda key: key in kinds

    def cited_valuation(self, cited: Set[str]) -> Callable[[str], bool]:
        """Law: a cited set supports a claim iff the derivation is true under it."""
        return lambda key: key in cited

    def why_valuation(self) -> Callable[[str], Set[frozenset]]:
        return lambda key: {frozenset({key})}

    def trust_valuation(self, subject_id: str) -> Callable[[str], float]:
        by_kind = {n["kind"]: n["trust"] for n in self.for_subject(subject_id)}
        return lambda key: by_kind.get(key, 0.0)
