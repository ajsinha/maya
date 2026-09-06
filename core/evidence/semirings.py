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

from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, Set, Tuple, TypeVar


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


# ---------------------------------------------------------------------------
# The universal one.
#
# ℕ[X] — the free commutative semiring on the base facts — is what makes the
# claim above ("the SAME traversal answers a different question") a theorem
# rather than a coincidence. Evaluate a derivation once here and every other
# semiring's answer is a *substitution* into the result: a homomorphism
# h : ℕ[X] → K sending each variable to its value in K.
#
# A polynomial is a map from monomial to natural coefficient. A monomial is a
# sorted tuple of (variable, exponent), so `x²y` is `(("x", 2), ("y", 1))` and
# the empty tuple is the multiplicative identity. Coefficients count *how many
# distinct derivations* produce the same combination of facts, and exponents
# count *how many times* a fact is used in one derivation — which is the
# distinction Boolean provenance throws away and why it cannot tell a single
# supporting document from four.
# ---------------------------------------------------------------------------
Monomial = Tuple[Tuple[str, int], ...]
Polynomial = Dict[Monomial, int]

POLY_ZERO: Polynomial = {}
POLY_ONE: Polynomial = {(): 1}


def poly_variable(name: str) -> Polynomial:
    """The polynomial `x` for one base fact."""
    return {((name, 1),): 1}


def _poly_plus(a: Polynomial, b: Polynomial) -> Polynomial:
    out = dict(a)
    for monomial, coefficient in b.items():
        total = out.get(monomial, 0) + coefficient
        if total:
            out[monomial] = total
        else:                       # cannot arise over ℕ; kept so the invariant
            out.pop(monomial, None)  # "no zero coefficients" holds by construction
    return out


def _poly_times(a: Polynomial, b: Polynomial) -> Polynomial:
    out: Polynomial = {}
    for left, lc in a.items():
        for right, rc in b.items():
            merged: Dict[str, int] = dict(left)
            for variable, exponent in right:
                merged[variable] = merged.get(variable, 0) + exponent
            monomial = tuple(sorted(merged.items()))
            out[monomial] = out.get(monomial, 0) + lc * rc
    return out


POLYNOMIAL: Semiring = Semiring("polynomial", POLY_ZERO, POLY_ONE,
                                _poly_plus, _poly_times)


def pushforward(polynomial: Polynomial, valuation: Callable[[str], Any],
                semiring: Semiring) -> Any:
    """Apply the homomorphism `h : ℕ[X] → K` induced by a valuation.

    This is the whole content of L-9: evaluating a derivation directly in `K`
    and evaluating it in ℕ[X] and then pushing forward must agree, for every
    `K`. Where they disagree, one of the two is not a semiring homomorphism —
    which is a fact about the structure, not about the traversal.

    A coefficient `n` becomes `n · 1_K`, an exponent `e` becomes `e` repeated
    multiplications. In an idempotent semiring both collapse, which is correct
    and is exactly the information Boolean provenance discards.
    """
    total = semiring.zero
    for monomial, coefficient in polynomial.items():
        term = semiring.one
        for variable, exponent in monomial:
            value = valuation(variable)
            for _ in range(exponent):
                term = semiring.times(term, value)
        for _ in range(coefficient):
            total = semiring.plus(total, term)
    return total
