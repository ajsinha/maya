"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Can this rule ever fire, and does it say the same thing as that one.

Rule sets are evaluated **first match wins**, which is what makes them readable
and also what makes them quietly wrong: a rule an earlier rule already covers can
never fire, and nothing about reading the document tells you so. Somebody
believes that rule is in force. It appears in the model card, gets cited in a
committee paper, and survives every review, because a rule that never fires also
never produces a wrong answer.

That is the `docs/11 §3` pattern — a control reporting success while doing
nothing — arrived at from the model side rather than the platform side, and it
is the single best argument for holding rule sets in a governance platform at
all. No spreadsheet tells you this.

## What this actually decides, and what it does not

Each condition is put into disjunctive normal form — a list of conjunctions of
atoms, with negation pushed down to the leaves — and each conjunction is reduced
to a **domain per field**: an interval, a permitted set, an excluded set and a
null state. Emptiness and containment are then arithmetic.

**The analysis is sound and incomplete, and the distinction matters.**

*Sound*: when it reports a rule unreachable, the rule is unreachable. It never
cries wolf, because a check that produces false alarms is a check somebody turns
off, and then the real ones go with it.

*Incomplete*: it reports a rule unreachable when a **single** earlier rule
covers it. Two earlier rules that between them cover a third — `ltv > 0.8` and
`ltv <= 0.8` covering everything — are not detected. Full coverage checking is
satisfiability over the theory, which is decidable here but is a solver, and a
solver inside a governance platform is a dependency whose failure modes nobody
in the bank can debug.

So the promise is exact: *"no rule is shadowed by any single earlier rule"*, and
`docs/02` says that rather than "no rule is unreachable". A check that claims
more than it delivers is the thing this whole analysis exists to find.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from core.log import get_logger, swallowed
from core.rules.common import ALL, ANY, NOT
from core.rules.conditions import Condition

logger = get_logger(__name__)

#: Beyond this a condition's DNF is large enough that expanding it costs more
#: than the answer is worth, and the honest response is to say the analysis did
#: not run rather than to run it partially and report "no problems found".
MAX_DISJUNCTS = 256


class Unanalysable(Exception):
    """The DNF grew past what is worth expanding. Reported, never swallowed."""


class Domain:
    """The values one field may take for a conjunction to hold.

    `None` bounds mean unbounded. `allowed is None` means any value; an empty
    `allowed` set means no value, which is how an unsatisfiable equality shows
    up. `null` is three-valued because "must be absent", "must be present" and
    "either" are three different constraints and collapsing them loses the one
    that matters.
    """

    __slots__ = ("lo", "lo_open", "hi", "hi_open", "allowed", "excluded", "null")

    def __init__(self) -> None:
        self.lo: Optional[Any] = None
        self.lo_open = False                  # True for a strict '>' bound
        self.hi: Optional[Any] = None
        self.hi_open = False
        self.allowed: Optional[Set[Any]] = None
        self.excluded: Set[Any] = set()
        self.null: Optional[bool] = None      # True: must be null. False: must not be.

    # ------------------------------------------------------------- narrowing
    def constrain(self, op: str, value: Any) -> None:
        """Add one atom's constraint. Conjunction, so this only narrows."""
        if op == "is_null":
            self.null = True if self.null is None else self.null and True
            if self.null is not True:
                self.allowed = set()          # must be null and must not be
            return
        if op == "not_null":
            if self.null is True:
                self.allowed = set()
            self.null = False
            return

        # Any comparison implies the field is present.
        if self.null is True:
            self.allowed = set()
        self.null = False

        if op == "eq":
            self.allowed = ({value} if self.allowed is None
                            else self.allowed & {value})
        elif op == "ne":
            self.excluded.add(value)
        elif op == "in":
            members = set(value)
            self.allowed = members if self.allowed is None else self.allowed & members
        elif op == "not_in":
            self.excluded |= set(value)
        elif op == "between":
            self._lower(value[0], False)
            self._upper(value[1], False)
        elif op == "ge":
            self._lower(value, False)
        elif op == "gt":
            self._lower(value, True)
        elif op == "le":
            self._upper(value, False)
        elif op == "lt":
            self._upper(value, True)

    def _lower(self, value: Any, strict: bool) -> None:
        if self.lo is None or _gt(value, self.lo) or (value == self.lo and strict):
            self.lo, self.lo_open = value, strict

    def _upper(self, value: Any, strict: bool) -> None:
        if self.hi is None or _lt(value, self.hi) or (value == self.hi and strict):
            self.hi, self.hi_open = value, strict

    # -------------------------------------------------------------- decide
    def is_empty(self) -> bool:
        """No value satisfies this. The rule carrying it can never fire."""
        if self.allowed is not None and not self.allowed:
            return True
        if self.allowed is not None and self.allowed <= self.excluded:
            return True
        if self.lo is not None and self.hi is not None:
            if _lt(self.hi, self.lo):
                return True
            if self.lo == self.hi and (self.lo_open or self.hi_open):
                return True
        if self.allowed is not None:
            return not any(self._admits(v) for v in self.allowed)
        return False

    def _admits(self, value: Any) -> bool:
        if value in self.excluded:
            return False
        if self.lo is not None:
            if _lt(value, self.lo) or (value == self.lo and self.lo_open):
                return False
        if self.hi is not None:
            if _gt(value, self.hi) or (value == self.hi and self.hi_open):
                return False
        return True

    def contains(self, other: "Domain") -> bool:
        """Every value `other` admits, this admits too.

        Conservative throughout: any question whose answer is not certain
        returns False, so a rule is only ever called unreachable when it is.
        """
        if self.null is not None and self.null != other.null:
            return False
        if self.allowed is not None:
            if other.allowed is None:
                return False                          # other is unbounded here
            if not other.allowed <= self.allowed:
                return False
        if self.excluded:
            # Everything I exclude, `other` must exclude or never produce.
            for value in self.excluded:
                if other.allowed is not None and value not in other.allowed:
                    continue                          # other cannot produce it
                if value in other.excluded:
                    continue
                if other._excluded_by_bounds(value):
                    continue
                return False
        if not self._bounds_contain(other):
            return False
        return True

    def _excluded_by_bounds(self, value: Any) -> bool:
        if self.lo is None and self.hi is None:
            return False
        return not self._admits_ignoring_exclusions(value)

    def _admits_ignoring_exclusions(self, value: Any) -> bool:
        if self.lo is not None:
            if _lt(value, self.lo) or (value == self.lo and self.lo_open):
                return False
        if self.hi is not None:
            if _gt(value, self.hi) or (value == self.hi and self.hi_open):
                return False
        return True

    def _bounds_contain(self, other: "Domain") -> bool:
        if self.lo is not None:
            if other.allowed is not None:
                if not all(self._admits_ignoring_exclusions(v) for v in other.allowed):
                    return False
            elif other.lo is None:
                return False
            elif _lt(other.lo, self.lo):
                return False
            elif other.lo == self.lo and self.lo_open and not other.lo_open:
                return False
        if self.hi is not None:
            if other.allowed is not None:
                if not all(self._admits_ignoring_exclusions(v) for v in other.allowed):
                    return False
            elif other.hi is None:
                return False
            elif _gt(other.hi, self.hi):
                return False
            elif other.hi == self.hi and self.hi_open and not other.hi_open:
                return False
        return True


# ------------------------------------------------------------------- the DNF
def disjuncts(condition: Condition, negated: bool = False) -> List[List[Condition]]:
    """Disjunctive normal form: a list of conjunctions of atoms.

    Negation is pushed to the leaves rather than represented, so a conjunction
    is always a plain list of positive atoms and a domain can be built from it
    by narrowing.
    """
    kind = condition.kind
    if kind == NOT:
        return disjuncts(condition.children[0], not negated)
    if kind == "atom":
        return [[_flip(condition) if negated else condition]]

    # De Morgan: negating an 'all' gives an 'any' of negations, and vice versa.
    effective = kind if not negated else (ANY if kind == ALL else ALL)
    parts = [disjuncts(child, negated) for child in condition.children]

    if effective == ANY:
        out: List[List[Condition]] = []
        for part in parts:
            out.extend(part)
        _guard(len(out))
        return out

    product: List[List[Condition]] = [[]]
    for part in parts:
        product = [conj + extra for conj in product for extra in part]
        _guard(len(product))
    return product


def _guard(size: int) -> None:
    if size > MAX_DISJUNCTS:
        raise Unanalysable(
            f"the condition expands to more than {MAX_DISJUNCTS} disjunctions")


_FLIP = {"eq": "ne", "ne": "eq", "lt": "ge", "ge": "lt", "le": "gt", "gt": "le",
         "in": "not_in", "not_in": "in", "is_null": "not_null",
         "not_null": "is_null"}


def _flip(atom: Condition) -> Condition:
    """The atom's negation, as a positive atom.

    `between` has no single-atom negation — outside [a, b] is a disjunction — so
    it is represented as a marker the domain builder refuses to reason about.
    Returning something *approximately* right here would make the analysis
    unsound, and unsound is the one thing it must not be.
    """
    if atom.op == "between":
        return Condition("atom", field=atom.field, op="__opaque__", value=None)
    return Condition("atom", field=atom.field, op=_FLIP[atom.op], value=atom.value)


def domains(conjunction: List[Condition]) -> Optional[Dict[str, Domain]]:
    """The per-field domain a conjunction implies, or None if it contains
    something the analysis will not reason about."""
    built: Dict[str, Domain] = {}
    for atom in conjunction:
        if atom.op == "__opaque__":
            return None
        built.setdefault(atom.field, Domain()).constrain(atom.op, atom.value)  # type: ignore[arg-type]
    return built


# ----------------------------------------------------------------- the answers
def satisfiable(condition: Condition) -> bool:
    """Could any input make this condition true.

    An unsatisfiable condition — `ltv > 0.9 and ltv < 0.5` — is a rule that can
    never fire on its own, before any question of ordering. Almost always a
    typo, and always worth refusing rather than storing.
    """
    try:
        forms = disjuncts(condition)
    except Unanalysable as exc:
        logger.info("satisfiability not decided: %s", exc)
        return True                        # not decided, so not refused
    for conjunction in forms:
        built = domains(conjunction)
        if built is None:
            return True                    # contains an opaque atom: not decided
        if not any(d.is_empty() for d in built.values()):
            return True
    return False


def covers(earlier: Condition, later: Condition) -> bool:
    """Does `earlier` fire on every input `later` fires on.

    If so, and `earlier` is ordered first, `later` can never fire.

    Sound and incomplete, as the module docstring says: a single earlier rule
    is compared, never a union of them.
    """
    try:
        outer, inner = disjuncts(earlier), disjuncts(later)
    except Unanalysable as exc:
        logger.info("coverage not decided: %s", exc)
        return False
    outer_domains = [domains(c) for c in outer]
    if any(d is None for d in outer_domains):
        return False
    for conjunction in inner:
        built = domains(conjunction)
        if built is None:
            return False
        if any(d.is_empty() for d in built.values()):
            continue                       # this branch fires on nothing anyway
        if not any(_conj_covers(o, built) for o in outer_domains if o is not None):
            return False
    return True


def _conj_covers(outer: Dict[str, Domain], inner: Dict[str, Domain]) -> bool:
    """Every field the outer conjunction constrains must be at least as loose."""
    unconstrained = Domain()
    for field, domain in outer.items():
        if not domain.contains(inner.get(field, unconstrained)):
            return False
    return True


# Two values of different types reaching a comparison means a rule set mixes
# them on one field — `ltv > 0.8` beside `ltv eq "high"`. The analysis cannot
# order them, so it declines to conclude anything, which keeps it sound: an
# undecided comparison must never become a claim that a rule is unreachable.
#
# Logged at DEBUG rather than WARNING because these run inside the domain
# arithmetic and a mixed-type rule set would otherwise produce one line per
# comparison. The rule set itself is refused elsewhere, by `conforms`, with a
# message naming the field.
def _lt(a: Any, b: Any) -> bool:
    try:
        return bool(a < b)
    except TypeError as exc:
        swallowed(logger, exc, "ordered two rule values",
                  detail=f"{a!r} and {b!r} are not comparable, so the analysis "
                         f"draws no conclusion from this pair",
                  level=logging.DEBUG)
        return False


def _gt(a: Any, b: Any) -> bool:
    try:
        return bool(a > b)
    except TypeError as exc:
        swallowed(logger, exc, "ordered two rule values",
                  detail=f"{a!r} and {b!r} are not comparable, so the analysis "
                         f"draws no conclusion from this pair",
                  level=logging.DEBUG)
        return False
