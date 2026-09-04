"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Commutative semirings for evidence.

Annotate base facts with elements of a semiring and the SAME traversal answers
a different question for each one: sufficiency, minimal justification,
corroboration, confidence, cost, currency.
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
