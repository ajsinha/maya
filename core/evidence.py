"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The evidence engine.

Claims are derived from base evidence by conjunction (joint dependence) and
disjunction (alternative derivations). Annotate the base facts with elements of
a commutative semiring and the SAME traversal answers a different question for
each semiring — sufficiency, minimal justification, confidence, cost, currency.

The append chain is linear over the derivation DAG: the DAG says what supports
what; the seq/prev_hash chain makes deletion of a leaf and insertion into the
past detectable. See docs/00-mathematical-foundations.md §9.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generic, List, Optional, Set, Tuple, TypeVar

from db import EvidenceRepository
from db.database import digest as canonical_digest

K = TypeVar("K")

GENESIS = "sha256:" + "0" * 64
MAX_TERMS = 4096          # beyond this, degrade explicitly rather than answer partially


@dataclass(frozen=True)
class Semiring(Generic[K]):
    """(K, plus, times, zero, one). ``times`` is AND; ``plus`` is OR."""
    name: str
    zero: K
    one: K
    plus: Callable[[K, K], K]
    times: Callable[[K, K], K]


BOOLEAN = Semiring("boolean", False, True, lambda a, b: a or b, lambda a, b: a and b)
COUNTING = Semiring("counting", 0, 1, lambda a, b: a + b, lambda a, b: a * b)
TRUST = Semiring("trust", 0.0, 1.0, max, lambda a, b: a * b)
COST = Semiring("cost", float("inf"), 0.0, min, lambda a, b: a + b)
FRESHNESS = Semiring("freshness", 0.0, 0.0, max, max)


def _why_plus(a: Set[frozenset], b: Set[frozenset]) -> Set[frozenset]:
    """Union, then absorption: a OR ab == a. Keeps only minimal support sets."""
    merged = a | b
    return {s for s in merged if not any(o < s for o in merged)}


def _why_times(a: Set[frozenset], b: Set[frozenset]) -> Set[frozenset]:
    return _why_plus({x | y for x in a for y in b}, set())


WHY: Semiring = Semiring("why", set(), {frozenset()}, _why_plus, _why_times)


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
        row = self.repo.head()
        return (row["seq"], row["chain_hash"]) if row else (0, GENESIS)

    def append(self, kind: str, subject_type: str, subject_id: str,
               payload: Optional[Dict[str, Any]] = None, parents: Optional[List[str]] = None,
               *, personal_data: bool = False, trust: float = 1.0,
               actor: str = "system") -> Dict[str, Any]:
        payload, parents = payload or {}, sorted(parents or [])
        content_hash = canonical_digest(
            {"kind": kind, "subject": [subject_type, subject_id], "payload": payload,
             "parents": parents})
        prev_seq, prev_hash = self.head()
        seq = prev_seq + 1
        node = {
            "seq": seq, "kind": kind,
            "subject_type": subject_type, "subject_id": subject_id,
            # Law L-18: personal data is never inline, only an erasable pointer.
            "payload": {} if personal_data else payload,
            "parents": parents, "contains_personal_data": personal_data,
            "content_hash": content_hash, "prev_hash": prev_hash,
            "chain_hash": canonical_digest([seq, prev_hash, content_hash, parents]),
            "trust": trust, "recorded_at": time.time(), "recorded_by": actor,
        }
        return self.repo.add(node)

    def verify_chain(self) -> Dict[str, Any]:
        """Walk the chain. Reports the first break, if any."""
        nodes = self.repo.all_ordered()
        prev_hash, expected_seq = GENESIS, 1
        for n in nodes:
            if n["seq"] != expected_seq:
                return {"valid": False, "broken_at": n["seq"], "reason": "sequence gap"}
            if n["prev_hash"] != prev_hash:
                return {"valid": False, "broken_at": n["seq"], "reason": "prev_hash mismatch"}
            recomputed = canonical_digest([n["seq"], n["prev_hash"], n["content_hash"], n["parents"]])
            if recomputed != n["chain_hash"]:
                return {"valid": False, "broken_at": n["seq"], "reason": "chain_hash mismatch"}
            prev_hash, expected_seq = n["chain_hash"], expected_seq + 1
        return {"valid": True, "length": len(nodes), "head": prev_hash}

    def for_subject(self, subject_id: str) -> List[Dict[str, Any]]:
        return self.repo.for_subject(subject_id)

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
