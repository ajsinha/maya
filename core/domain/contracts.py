"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Assume-guarantee contracts. Assumptions are operating boundaries; guarantees
are the performance envelope. Outside the assumptions the guarantee is void.

Refinement (law L-7) decides whether one version may replace another, which
turns substitution from a judgement call into a proof obligation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from core.domain.schemas import explain
from core.log import get_logger, swallowed

logger = get_logger(__name__)

# --------------------------------------------------------------------- contracts
@dataclass(frozen=True)
class Bound:
    """One clause of an assumption or a guarantee."""
    key: str
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    allowed: Tuple[str, ...] = ()

    def contains(self, value: Any) -> bool:
        if self.allowed:
            return str(value) in self.allowed
        try:
            v = float(value)
        except (TypeError, ValueError) as exc:
            # Outside the assumption, so the guarantee is void — but a
            # non-numeric value where a number was declared is worth seeing.
            swallowed(logger, exc, f"bound '{self.key}' received a non-numeric value",
                      detail=f"value={value!r}; treated as outside the boundary")
            return False
        if self.minimum is not None and v < self.minimum:
            return False
        return not (self.maximum is not None and v > self.maximum)

    def weaker_than(self, other: "Bound") -> bool:
        """This bound admits everything ``other`` admits (and possibly more)."""
        if self.allowed or other.allowed:
            return set(other.allowed).issubset(set(self.allowed))
        lo = self.minimum is None or (other.minimum is not None and self.minimum <= other.minimum)
        hi = self.maximum is None or (other.maximum is not None and self.maximum >= other.maximum)
        return lo and hi

    def stronger_than(self, other: "Bound") -> bool:
        return other.weaker_than(self)


@dataclass(frozen=True)
class Contract:
    """Assume-guarantee pair. Assumptions are operating boundaries; guarantees
    are the performance envelope. Outside the assumptions the guarantee is void."""
    assumptions: Tuple[Bound, ...] = ()
    guarantees: Tuple[Bound, ...] = ()

    def _a(self) -> Dict[str, Bound]:
        return {b.key: b for b in self.assumptions}

    def _g(self) -> Dict[str, Bound]:
        return {b.key: b for b in self.guarantees}

    def check_inputs(self, values: Dict[str, Any]) -> List[str]:
        """Evaluate ``input |= A``. Returns the assumption keys that fail.

        Values are looked up **one level down as well as at the top**, because
        that is where several runtimes put them. The estimator reads
        `inputs["features"]`, so an assumption on `turnover` found no
        `turnover` key at the top level, and the clause below — which skips a
        key that is not present — passed it. A signed operating boundary was
        therefore unenforced for every runtime that nests its inputs, silently,
        with `boundary_ok: true` on the response.

        An absent key still passes, and that is deliberate: an assumption
        constrains a value that was supplied, and a caller who supplies nothing
        has not violated a band. `unchecked_inputs` reports which assumptions
        never found a value, so "the boundary held" and "the boundary did not
        apply" are answerable separately rather than looking identical.
        """
        seen = self._flatten(values)
        return [b.key for b in self.assumptions
                if b.key in seen and not b.contains(seen[b.key])]

    def unchecked_inputs(self, values: Dict[str, Any]) -> List[str]:
        """Assumption keys no supplied value reached.

        Not a violation. But a contract whose assumptions all went unchecked is
        a contract that did nothing, and the difference between that and one
        that held is invisible from `boundary_ok` alone.
        """
        seen = self._flatten(values)
        return [b.key for b in self.assumptions if b.key not in seen]

    @staticmethod
    def _flatten(values: Dict[str, Any]) -> Dict[str, Any]:
        """Top-level keys, plus one level of nesting.

        One level and no more: a deep walk would start matching an assumption
        against a value that happens to share a name several objects down, and a
        boundary that fires on the wrong field is worse than one that does not
        fire at all.

        Top level wins a collision, because that is where the caller addressed
        it.
        """
        flat: Dict[str, Any] = {}
        for key, value in (values or {}).items():
            if isinstance(value, dict):
                for inner, held in value.items():
                    flat.setdefault(inner, held)
        flat.update({k: v for k, v in (values or {}).items()
                     if not isinstance(v, dict)})
        return flat

    def refines(self, other: "Contract") -> "RefinementResult":
        """C' <= C iff A subset A' and (A and G') subset G. Law L-7."""
        mine_a, other_a = self._a(), other._a()
        mine_g, other_g = self._g(), other._g()
        # An ABSENT assumption is the weakest possible one: promising to work
        # without constraining x is stronger than promising it only on a band.
        # An absent guarantee, by contrast, is a promise withdrawn.
        weak = [k for k, b in other_a.items()
                if k in mine_a and not mine_a[k].weaker_than(b)]
        strong = [k for k, b in other_g.items()
                  if k not in mine_g or not mine_g[k].stronger_than(b)]
        return RefinementResult(holds=not weak and not strong,
                                assumption_failures=tuple(weak),
                                guarantee_failures=tuple(strong))

    def compose(self, downstream: "Contract") -> "Contract":
        """Contract of the composed system: assumptions union, guarantees union."""
        return Contract(assumptions=self.assumptions + downstream.assumptions,
                        guarantees=self.guarantees + downstream.guarantees)

    def conjoin(self, other: "Contract") -> "Contract":
        """Merge two viewpoints on one model, e.g. performance and fairness."""
        return Contract(assumptions=self.assumptions + other.assumptions,
                        guarantees=self.guarantees + other.guarantees)

    def quotient(self, have: "Contract") -> "Contract":
        """What a missing component must guarantee. A gap becomes a specification."""
        got = have._g()
        return Contract(assumptions=self.assumptions,
                        guarantees=tuple(b for b in self.guarantees if b.key not in got))


@dataclass(frozen=True)
class RefinementResult:
    holds: bool
    assumption_failures: Tuple[str, ...] = ()
    guarantee_failures: Tuple[str, ...] = ()

    def reason(self) -> str:
        return explain({"assumptions not weakened": self.assumption_failures,
                        "guarantees not preserved": self.guarantee_failures}, "refines")
