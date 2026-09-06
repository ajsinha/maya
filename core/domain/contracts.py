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

from dataclasses import dataclass
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

    # The two lattice operations the algebra below is written in terms of.
    # Both are PARTIAL, and both say so by returning `None` rather than
    # returning an approximation. An interval algebra that widens `[0,1] ∪
    # [5,6]` to `[0,6]` is claiming a contract holds at 3, where neither of the
    # contracts it came from says anything at all.
    def meet(self, other: "Bound") -> Optional["Bound"]:
        """The strongest bound admitting exactly what BOTH admit.

        `None` when nothing does — two guarantees that cannot both hold — or
        when one is a set of categories and the other a numeric band, which is
        not a disagreement about width but about kind.
        """
        if bool(self.allowed) != bool(other.allowed):
            return None
        if self.allowed:
            shared = tuple(v for v in self.allowed if v in set(other.allowed))
            return Bound(self.key, allowed=shared) if shared else None
        low = _widest(self.minimum, other.minimum, max)
        high = _widest(self.maximum, other.maximum, min)
        if low is not None and high is not None and low > high:
            return None
        return Bound(self.key, minimum=low, maximum=high)

    def join(self, other: "Bound") -> Optional["Bound"]:
        """The weakest bound admitting exactly what EITHER admits.

        `None` when the union is not itself a band. Two disjoint intervals have
        no join here, and inventing the interval that spans them would be the
        one thing this whole file exists to prevent.
        """
        if bool(self.allowed) != bool(other.allowed):
            return None
        if self.allowed:
            merged = tuple(dict.fromkeys(self.allowed + other.allowed))
            return Bound(self.key, allowed=merged)
        if self._disjoint_from(other):
            return None
        low = _widest(self.minimum, other.minimum, min, unbounded_wins=True)
        high = _widest(self.maximum, other.maximum, max, unbounded_wins=True)
        return Bound(self.key, minimum=low, maximum=high)

    def _disjoint_from(self, other: "Bound") -> bool:
        """No value satisfies both, so their union has a hole in it."""
        if self.maximum is not None and other.minimum is not None:
            if self.maximum < other.minimum:
                return True
        if other.maximum is not None and self.minimum is not None:
            if other.maximum < self.minimum:
                return True
        return False


def _widest(a: Optional[float], b: Optional[float], pick,
            unbounded_wins: bool = False) -> Optional[float]:
    """Combine two endpoints, one of which may be absent.

    An absent endpoint means *unbounded on that side*. Which way that cuts
    depends on the operation, and getting it backwards is silent: for a meet an
    absent endpoint is no constraint and the other one stands; for a join it
    admits everything and swallows the other.
    """
    if a is None or b is None:
        if unbounded_wins:
            return None
        return a if b is None else b
    return pick(a, b)


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
        for _key, value in (values or {}).items():
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

    # ------------------------------------------------------------- the algebra
    #
    # `⊗`, `∧` and `/` were three names for one line of code: concatenate both
    # tuples. Three operations that answer three different questions returned
    # the same answer to all of them, which is worse than having only one, and
    # `/` additionally discharged a requirement whenever the partner MENTIONED
    # the key — so a challenger promising `gini ≥ 0.2` satisfied a target of
    # `gini ≥ 0.4` and the residual specification came back empty.
    #
    # They are written below in terms of `Bound.meet` and `Bound.join`, and
    # each one refuses where the operation genuinely does not exist rather than
    # returning something adjacent to it.

    def compose(self, downstream: "Contract") -> "Contract":
        """`C₁ ⊗ C₂` — what the wired pair promises, and of whom.

        The composite's guarantees are both, together. Its assumptions are what
        the **caller** must still supply: a downstream assumption that this
        model's own guarantee already implies is discharged internally and is
        not asked of anybody outside.

        That discharge is the entire difference between composition and
        conjunction, and it is the question a reader of a model chain actually
        has — *what do I still have to guarantee?* — which is why the same
        phrase, `still_supplied_by_the_caller`, names the answer in
        `core/registry/composition.py`.
        """
        return self.composed_with(downstream).contract

    def composed_with(self, downstream: "Contract") -> "Composition":
        """`compose`, with the working shown: what was discharged, and what
        could not be."""
        mine_g = self._g()
        discharged, unmet, kept = [], [], []
        for bound in downstream.assumptions:
            guarantee = mine_g.get(bound.key)
            if guarantee is None:
                kept.append(bound)
            elif guarantee.stronger_than(bound):
                discharged.append(bound.key)
            else:
                # The upstream speaks to this key and does NOT settle it. That
                # is a finding rather than a detail: somebody wired two models
                # together believing the boundary was covered.
                unmet.append(bound.key)
                kept.append(bound)

        assumptions = _meet_assumptions(self.assumptions, tuple(kept))
        guarantees = _meet_guarantees(self.guarantees, downstream.guarantees)
        return Composition(contract=Contract(assumptions=assumptions,
                                             guarantees=guarantees),
                           discharged=tuple(discharged), unmet=tuple(unmet))

    def conjoin(self, other: "Contract") -> "Contract":
        """`C₁ ∧ C₂` — two viewpoints on ONE model: performance and fairness.

        Both promises are made, so the guarantees **meet**: where each names a
        key, the conjoined contract promises the stronger of the two.

        The assumptions **join**, which is the half that reads backwards until
        it is said out loud. A contract promises nothing outside its
        assumptions, so a model holding two contracts is entitled to the union
        of the environments they cover — and an assumption only one of them
        makes constrains nothing, because the other viewpoint promised its
        guarantee without it. Intersecting the assumptions here would silently
        narrow where the model may be used every time somebody added a
        viewpoint.
        """
        mine_a, other_a = self._a(), other._a()
        shared = [mine_a[k].join(other_a[k]) for k in mine_a if k in other_a]
        if any(b is None for b in shared):
            missing = sorted(k for k in mine_a if k in other_a
                             and mine_a[k].join(other_a[k]) is None)
            raise ContractError(
                "no_assumption_join",
                "these viewpoints assume bands with a gap between them, and no "
                f"single band covers both: {', '.join(missing)}",
                "state the viewpoints over a shared operating region, or hold "
                "them as separate contracts — widening to span the gap would "
                "claim the model works where neither viewpoint says it does")
        guarantees = _meet_guarantees(self.guarantees, other.guarantees)
        return Contract(assumptions=tuple(b for b in shared if b is not None),
                        guarantees=guarantees)

    def quotient(self, have: "Contract") -> "Contract":
        """`C / C₁` — what the missing component must deliver.

        A guarantee is discharged only where what we have **implies** it. A
        partner that speaks to the key without meeting it discharges nothing,
        and the residual carries the requirement in full: relying on a promise
        of `gini ≥ 0.2` to satisfy a target of `gini ≥ 0.4` is how a validation
        gap comes to read as closed.

        The residual may **rely** on what the partner guarantees, so those
        become assumptions of the missing component alongside the target's own.
        """
        got = have._g()
        residual = tuple(b for b in self.guarantees
                         if not (b.key in got and got[b.key].stronger_than(b)))
        assumptions = _meet_assumptions(self.assumptions, have.guarantees)
        return Contract(assumptions=assumptions, guarantees=residual)


@dataclass(frozen=True)
class Composition:
    """A composed contract, and what composing it settled.

    `discharged` is what the upstream's guarantee took off the caller's hands.
    `unmet` is the more interesting list: keys the upstream speaks to and does
    not settle, which is a wiring somebody believed was covered.
    """
    contract: "Contract"
    discharged: Tuple[str, ...] = ()
    unmet: Tuple[str, ...] = ()


def _combine(left: Tuple[Bound, ...], right: Tuple[Bound, ...],
             operation) -> Tuple[Tuple[Bound, ...], List[str]]:
    """Merge two clause tuples key by key.

    Returns the merged clauses and the keys where the operation does not exist.
    It does not raise: the two callers below refuse with different codes, and a
    code assembled inside a shared helper is invisible to the discipline test
    that checks every refusal is mapped to a status — an unmapped refusal
    reaches a caller as a bare 400 saying nothing about who must act.

    Order follows `left`, then whatever `right` adds, so the result is stable
    rather than set-ordered.
    """
    merged: Dict[str, Bound] = {b.key: b for b in left}
    impossible: List[str] = []
    for bound in right:
        existing = merged.get(bound.key)
        if existing is None:
            merged[bound.key] = bound
            continue
        combined = operation(existing, bound)
        if combined is None:
            impossible.append(bound.key)
        else:
            merged[bound.key] = combined
    return tuple(merged.values()), impossible


def _meet_assumptions(left: Tuple[Bound, ...],
                      right: Tuple[Bound, ...]) -> Tuple[Bound, ...]:
    """Both operating boundaries must hold, so they intersect."""
    merged, impossible = _combine(left, right, Bound.meet)
    if impossible:
        raise ContractError(
            "no_assumption_meet",
            "these contracts assume bands that no value satisfies at once: "
            f"{', '.join(sorted(impossible))}",
            "reconcile the operating boundary on those keys; combining them by "
            "dropping one would produce a contract neither side agreed to")
    return merged


def _meet_guarantees(left: Tuple[Bound, ...],
                     right: Tuple[Bound, ...]) -> Tuple[Bound, ...]:
    """Both promises are made, so they intersect — and where they exclude each
    other there is no combined promise to make."""
    merged, impossible = _combine(left, right, Bound.meet)
    if impossible:
        raise ContractError(
            "no_guarantee_meet",
            "these contracts promise things that cannot both hold: "
            f"{', '.join(sorted(impossible))}",
            "reconcile the guarantee on those keys before combining the "
            "contracts; a combination that kept only one of them would promise "
            "less than one side committed to, silently")
    return merged


class ContractError(ValueError):
    """Two contracts that no single contract can express.

    Raised rather than returned, for the reason `NoMeet` gives: the caller has
    a decision to make — usually *these two models cannot be wired together* —
    and a `None` threaded through three layers becomes a silently empty
    contract, which is a contract that promises nothing and refuses nothing.
    """

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


@dataclass(frozen=True)
class RefinementResult:
    holds: bool
    assumption_failures: Tuple[str, ...] = ()
    guarantee_failures: Tuple[str, ...] = ()

    def reason(self) -> str:
        return explain({"assumptions not weakened": self.assumption_failures,
                        "guarantees not preserved": self.guarantee_failures}, "refines")
