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

*Complete, now, over the union.* `covers` compares one earlier rule and is what
names a culprit. `union_covers` at the foot of this module answers the harder
question — do the earlier rules **together** cover a later one — which was for a
long time a stated limit: *no rule is shadowed by any single earlier rule*, with
`ltv > 0.8` and `ltv <= 0.8` covering everything after them as the named example
that went undetected.

The reason given for stopping there was that full coverage is satisfiability
over the theory, "decidable here but a solver, and a solver inside a governance
platform is a dependency whose failure modes nobody in the bank can debug". The
premise was right and the conclusion did not follow. A conjunction here is
already a **box** — one `Domain` per field, an interval with an excluded set and
a null state — and a condition is a finite union of boxes. *Is this box covered
by those boxes* is geometry, not satisfiability, and subtraction answers it
exactly. No solver, no dependency, and an exact answer rather than a
conservative one.

What stays bounded is the cost. Subtraction fragments, and a rule set can be
built whose fragments multiply; `MAX_FRAGMENTS` caps it and reaching the cap
raises `Undecided`. That is reported as *not checked* and never folded into
"no problems found" — a coverage check that claims a guarantee it abandoned is
the thing this whole analysis exists to find.
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

    __slots__ = ("allowed", "excluded", "hi", "hi_open", "lo", "lo_open", "null")

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
        return self._bounds_contain(other)

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
        if not negated:
            return [[condition]]
        return _negated_atom(condition)

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


def _negated_atom(atom: Condition) -> List[List[Condition]]:
    """The negation of one atom, in disjunctive normal form.

    Not simply the flipped operator, because the evaluator is three-valued about
    an absent field and this analysis has to agree with it. `_atom_holds`
    returns False for every comparison when the field is missing, and `NOT` is
    `not holds(...)` — so `not (country eq "GB")` is TRUE on a row with no
    country at all, while the flipped atom `country ne "GB"` is False there.

    Flipping alone therefore built a region SMALLER than the rule's, and small
    in the direction that matters: `covers` and `union_covers` both reported a
    later rule as shadowed when it fires on exactly the rows the earlier one
    misses. In a screening rule set that is the rule for records arriving with
    no country — the ones most worth stopping — declared dead and deleted.

    So the negation is `flip(atom) OR field is_null`, which is what the
    evaluator computes. `is_null` and `not_null` are already exact about
    nullness and flip cleanly; `between` still has no atom-sized negation and
    stays opaque.
    """
    flipped = _flip(atom)
    if atom.op in ("is_null", "not_null") or flipped.op == "__opaque__":
        return [[flipped]]
    return [[flipped],
            [Condition("atom", field=atom.field, op="is_null", value=None)]]


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
    return all(domain.contains(inner.get(field, unconstrained)) for field, domain in outer.items())


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


# ===========================================================================
# Union coverage — the completeness the analysis above deliberately lacked
# ===========================================================================
#
# `covers` compares ONE earlier rule against a later one. Two earlier rules that
# between them cover a third — `ltv > 0.8` and `ltv <= 0.8` covering everything
# after them — were not detected, and the promise was written narrowly to say so:
# *no rule is shadowed by any single earlier rule*.
#
# The stated reason for stopping there was that full coverage is satisfiability
# over the theory, "decidable here but a solver, and a solver inside a governance
# platform is a dependency whose failure modes nobody in the bank can debug".
#
# The first half was right and the conclusion did not follow. A conjunction here
# is already a **box** — one `Domain` per field, each an interval with an
# excluded set and a null state — and a condition is a finite union of boxes. Is
# one box covered by a union of boxes is a geometry question, not a satisfiability
# one, and it is answered exactly by subtraction: remove each earlier box from
# the later one and see whether anything is left.
#
# So there is no solver, no new dependency, and the answer is exact rather than
# conservative. What remains bounded is the *cost*: subtraction fragments, and a
# rule set can be built whose fragments multiply. `MAX_FRAGMENTS` caps it, and
# reaching the cap reports **undecided** rather than "no problems found" — the
# distinction this whole module exists to keep.


#: A box may split once per constrained field per subtraction, so fragments can
#: multiply. Past this the honest answer is that the analysis did not finish.
MAX_FRAGMENTS = 4096


class Undecided(Exception):
    """The union check ran out of budget. Not a verdict, and never reported as
    one: a coverage check that says "no problems found" when it gave up is the
    defect the rest of this module is written against."""


def _complement_along(domain: "Domain", field: str,
                      box: Dict[str, "Domain"]) -> List[Dict[str, "Domain"]]:
    """The parts of `box` that lie OUTSIDE `domain` on `field`.

    Up to four pieces, and each is a real constraint rather than an
    approximation: below the low bound, above the high bound, at a value the
    domain excludes, and — where the domain fixes nullness — the opposite null
    state.
    """
    pieces: List[Dict[str, "Domain"]] = []
    here = box.get(field) or Domain()

    if domain.lo is not None:
        piece = _narrowed(box, field, hi=domain.lo,
                          hi_open=not domain.lo_open)
        if piece is not None:
            pieces.append(piece)
    if domain.hi is not None:
        piece = _narrowed(box, field, lo=domain.hi,
                          lo_open=not domain.hi_open)
        if piece is not None:
            pieces.append(piece)
    if domain.allowed is not None:
        # Outside a permitted set is "excludes every member of it".
        piece = _narrowed(box, field, excluded=set(domain.allowed))
        if piece is not None:
            pieces.append(piece)
    for value in sorted(domain.excluded, key=repr):
        if here._admits(value):
            piece = _narrowed(box, field, allowed={value})
            if piece is not None:
                pieces.append(piece)
    if domain.null is not None:
        piece = _narrowed(box, field, null=not domain.null)
        if piece is not None:
            pieces.append(piece)
    return pieces


def _narrowed(box: Dict[str, "Domain"], field: str, **limits: Any
              ) -> Optional[Dict[str, "Domain"]]:
    """`box`, with one field narrowed. `None` when the result is empty."""
    fresh: Dict[str, Domain] = {f: _copy(d) for f, d in box.items()}
    domain = fresh.setdefault(field, Domain())

    if "lo" in limits:
        if domain.lo is None or _lt(domain.lo, limits["lo"]):
            domain.lo, domain.lo_open = limits["lo"], limits.get("lo_open", False)
        elif domain.lo == limits["lo"]:
            domain.lo_open = domain.lo_open or limits.get("lo_open", False)
    if "hi" in limits:
        if domain.hi is None or _gt(domain.hi, limits["hi"]):
            domain.hi, domain.hi_open = limits["hi"], limits.get("hi_open", False)
        elif domain.hi == limits["hi"]:
            domain.hi_open = domain.hi_open or limits.get("hi_open", False)
    if "excluded" in limits:
        domain.excluded = set(domain.excluded) | set(limits["excluded"])
    if "allowed" in limits:
        domain.allowed = (set(limits["allowed"]) if domain.allowed is None
                          else set(domain.allowed) & set(limits["allowed"]))
    if "null" in limits:
        if domain.null is not None and domain.null != limits["null"]:
            return None
        domain.null = limits["null"]

    return None if any(d.is_empty() for d in fresh.values()) else fresh


def _copy(domain: "Domain") -> "Domain":
    fresh = Domain()
    fresh.lo, fresh.lo_open = domain.lo, domain.lo_open
    fresh.hi, fresh.hi_open = domain.hi, domain.hi_open
    fresh.allowed = None if domain.allowed is None else set(domain.allowed)
    fresh.excluded = set(domain.excluded)
    fresh.null = domain.null
    return fresh


def _subtract(box: Dict[str, "Domain"],
              cutter: Dict[str, "Domain"]) -> List[Dict[str, "Domain"]]:
    """`box` minus `cutter`, as a list of boxes.

    If the cutter covers the box, nothing comes back. If they do not meet, the
    box comes back whole. Otherwise the box is split along every field the
    cutter constrains — which is what makes this exact rather than conservative.
    """
    if _conj_covers(cutter, box):
        return []
    remaining: List[Dict[str, Domain]] = []
    for field, domain in cutter.items():
        remaining.extend(_complement_along(domain, field, box))
    if not remaining:
        # The cutter constrains nothing, so it covers everything.
        return []
    return remaining


def union_covers(earlier: List["Condition"], later: "Condition") -> bool:
    """Do the earlier conditions, TOGETHER, fire on everything `later` fires on?

    The completeness `covers` does not have. Exact, by subtraction over boxes,
    with no solver: a conjunction is a box, a condition is a finite union of
    them, and coverage is what is left after removing each earlier box.

    Raises `Undecided` rather than answering when the fragments outrun the
    budget. A coverage check that reports "not shadowed" because it gave up is
    worse than one that does not run.
    """
    try:
        inner = disjuncts(later)
        outer: List[Dict[str, Domain]] = []
        for condition in earlier:
            for conjunction in disjuncts(condition):
                built = domains(conjunction)
                if built is None:
                    return False              # cannot analyse: stay sound
                outer.append(built)
    except Unanalysable as exc:
        logger.info("union coverage not decided: %s", exc)
        return False

    if not outer:
        return False

    for conjunction in inner:
        built = domains(conjunction)
        if built is None:
            return False
        if any(d.is_empty() for d in built.values()):
            continue                          # this branch fires on nothing
        remaining = [built]
        for cutter in outer:
            nxt: List[Dict[str, Domain]] = []
            for piece in remaining:
                nxt.extend(_subtract(piece, cutter))
                if len(nxt) > MAX_FRAGMENTS:
                    raise Undecided(
                        f"the union check exceeded {MAX_FRAGMENTS} fragments; "
                        f"the answer is unknown rather than negative")
            remaining = nxt
            if not remaining:
                break
        if remaining:
            return False                      # something is left uncovered
    return True
