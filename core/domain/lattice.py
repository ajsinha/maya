"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The order underneath everything that asks *does this fit where that fitted*.

Four places in this platform ask that question, and until now each answered it
its own way: `substitutable` for a version replacing another, a slot loop for
`L-W10`, `refines` for operating contracts, and nothing at all for a `input_to`
edge. Four implementations of one relation will eventually disagree, and they
will disagree in the direction of permitting more — because that is the
direction in which nobody files a bug.

So the relation is written once, here, as a partial order on schemas:

    A ⊑ B   iff   A has every field B has, each accepting at least what B's did

Read it as **"A can stand in for B"**. A may have extra fields — they are simply
not read — and each shared field must accept at least the values B's accepted,
because a replacement that rejects an input its predecessor took is a
replacement that breaks a caller.

*Writing this corrected the design note.* `docs/17` said "at a type no wider",
which is backwards: standing in for something requires accepting **at least**
what it accepted, so a wider acceptance is fine and a narrower one regresses.
The prose was written from the intuition that a subtype is narrower; the
`accepts` relation had it right all along, and the note now says so.

## The structure

Order the fields by acceptance and schemas inherit a lattice on any finite set
of field names:

* **meet** (`⊓`, greatest lower bound) — the *union* of the fields, each widened
  enough to accept both. This is the schema that can stand in for either, and it
  is what a featureset must provide to serve two models at once.
* **join** (`⊔`, least upper bound) — the *intersection* of the fields, each
  narrowed to what both accepted. This is what two schemas *agree* on, and it is
  what a consumer of either can safely rely on.
* **top** is the empty schema: it demands nothing, so everything can stand in
  for it.

There is no bottom, and saying so matters: a least element would have to carry
every field name that could ever exist. The structure is a lattice on each
finite fragment, which is the only fragment anything here ever inhabits.

**Meet is partial**, and its failure is informative rather than an inconvenience.
Two schemas whose shared field has two different dtypes have no meet — no
schema can accept both a number and a string in one slot — and the honest
answer to *"can one featureset serve both these models"* is then **no**, with
the slot named.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from core.domain.schemas import Field, Schema

#: The empty schema, which demands nothing and which everything refines.
TOP = Schema(())


@dataclass(frozen=True)
class Refinement:
    """Whether `A ⊑ B`, and what regressed if not."""

    holds: bool
    missing: Tuple[str, ...] = ()          # fields B has that A does not
    narrowed: Tuple[str, ...] = ()         # fields A has that accept less than B's

    def reason(self) -> str:
        if self.holds:
            return "can stand in"
        parts = []
        if self.missing:
            parts.append(f"does not provide {', '.join(self.missing)}")
        if self.narrowed:
            parts.append(f"accepts less than before at {', '.join(self.narrowed)}")
        return "; ".join(parts)


def refines(a: Schema, b: Schema) -> Refinement:
    """`a ⊑ b` — can `a` stand in for `b`?

    Separating *missing* from *narrowed* is deliberate. They are different
    mistakes with different remedies: a missing field means somebody bound the
    wrong featureset, and a narrowed one means somebody tightened a constraint
    and did not notice it was a promise.
    """
    mine = a.by_name()
    missing, narrowed = [], []
    for field in b.fields:
        held = mine.get(field.name)
        if held is None:
            missing.append(field.name)
        elif not held.accepts(field):
            narrowed.append(field.name)
    return Refinement(not missing and not narrowed,
                      tuple(missing), tuple(narrowed))


def leq(a: Schema, b: Schema) -> bool:
    """`a ⊑ b`, as a plain boolean, for use inside the law tests."""
    return refines(a, b).holds


class NoMeet(ValueError):
    """Two schemas that no single schema can stand in for.

    Raised rather than returned as `None`, because the caller who asked for a
    meet has a decision to make — usually *these two models cannot share a
    featureset* — and a `None` threaded through three layers becomes a silent
    empty schema somewhere.
    """

    def __init__(self, conflicts: Dict[str, Tuple[str, str]]):
        self.conflicts = conflicts
        detail = "; ".join(f"{name}: {left} vs {right}"
                           for name, (left, right) in sorted(conflicts.items()))
        super().__init__(
            f"no schema can accept both, because these fields disagree on their "
            f"type: {detail}")


def meet(a: Schema, b: Schema) -> Schema:
    """`a ⊓ b` — the greatest schema that can stand in for both.

    Every field either has, widened where they disagree on how much they accept.
    A featureset serving two models must refine this.
    """
    fields: Dict[str, Field] = dict(a.by_name())
    conflicts: Dict[str, Tuple[str, str]] = {}
    for field in b.fields:
        held = fields.get(field.name)
        if held is None:
            fields[field.name] = field
            continue
        if held.dtype != field.dtype:
            conflicts[field.name] = (held.dtype, field.dtype)
            continue
        # A unit disagreement is a conflict of the same kind as a dtype
        # disagreement, and for the same reason: there is no single field that
        # is both. This rebuilt the Field without `symbol` or `unit` at all, so
        # the meet of a `ratio` schema and a `bp` schema silently declared
        # neither — and anything checked against that meet had its unit
        # constraint dropped on the way through.
        if held.unit and field.unit and held.unit != field.unit:
            conflicts[field.name] = (f"{held.dtype} in {held.unit}",
                                     f"{field.dtype} in {field.unit}")
            continue
        fields[field.name] = Field(
            field.name, field.dtype,
            nullable=held.nullable or field.nullable,
            minimum=_wider_low(held.minimum, field.minimum),
            maximum=_wider_high(held.maximum, field.maximum),
            symbol=held.symbol or field.symbol,
            unit=held.unit or field.unit)
    if conflicts:
        raise NoMeet(conflicts)
    return Schema(tuple(fields[name] for name in sorted(fields)))


def join(a: Schema, b: Schema) -> Schema:
    """`a ⊔ b` — the least schema both can stand in for.

    Only the fields they share, narrowed to what both accepted. This is what a
    consumer of *either* may rely on, which is the right answer to "what do
    these two versions have in common" and is total: fields that disagree on
    their type are simply not shared.
    """
    theirs = b.by_name()
    fields = []
    for field in a.fields:
        other = theirs.get(field.name)
        if other is None or other.dtype != field.dtype:
            continue
        # A field the two schemas measure in different units is not a field
        # they share, so it does not survive the join either.
        if field.unit and other.unit and field.unit != other.unit:
            continue
        fields.append(Field(
            field.name, field.dtype,
            nullable=field.nullable and other.nullable,
            minimum=_narrower_low(field.minimum, other.minimum),
            maximum=_narrower_high(field.maximum, other.maximum),
            symbol=field.symbol or other.symbol,
            unit=field.unit or other.unit))
    return Schema(tuple(sorted(fields, key=lambda f: f.name)))


# ---------------------------------------------------------------------------
# Bounds. `None` is unbounded, which is the widest an end can be — so widening
# takes `None` when either side has it, and narrowing takes the tighter number.
# ---------------------------------------------------------------------------
def _wider_low(x: Optional[float], y: Optional[float]) -> Optional[float]:
    return None if x is None or y is None else min(x, y)


def _wider_high(x: Optional[float], y: Optional[float]) -> Optional[float]:
    return None if x is None or y is None else max(x, y)


def _narrower_low(x: Optional[float], y: Optional[float]) -> Optional[float]:
    if x is None:
        return y
    return x if y is None else max(x, y)


def _narrower_high(x: Optional[float], y: Optional[float]) -> Optional[float]:
    if x is None:
        return y
    return x if y is None else min(x, y)


def provides(a: Schema, b: Schema) -> Tuple[str, ...]:
    """The covariant direction: fields `b` promised that `a` no longer provides.

    Outputs are judged more coarsely than inputs, and deliberately: a consumer
    reads an output's *name and type*, and narrowing the range of something you
    produce is a promise kept more tightly rather than one broken.

    The UNIT is not part of that coarseness. `Field.unit`'s own docstring says a
    replacement declaring `bp` where the incumbent declared `ratio` is a
    hundred-fold error that every type check passes — and this function, which
    is what `substitutable` actually calls, compared name and dtype only. The
    check that did compare units lived on `Schema.provides_superset_of`, which
    had no callers at all, so a version whose output changed from a ratio to
    basis points was declared a compatible substitute.
    """
    mine = a.by_name()
    return tuple(f.name for f in b.fields
                 if f.name not in mine or mine[f.name].dtype != f.dtype
                 or (f.unit and mine[f.name].unit
                     and mine[f.name].unit != f.unit))


def schema_of(slots: Dict[str, object]) -> Schema:
    """A featureset's resolved slots as a schema, so the order reaches them.

    A slot's definition is either a bare dtype string or a mapping carrying the
    dtype and its bounds. Both spellings exist in the register and both mean the
    same thing, so both are read here rather than at four call sites.
    """
    fields = []
    for name in sorted(slots):
        definition = slots[name]
        if isinstance(definition, dict):
            fields.append(Field(name, str(definition.get("dtype", "numeric")),
                                bool(definition.get("nullable", False)),
                                definition.get("minimum"),
                                definition.get("maximum"),
                                definition.get("symbol"),
                                definition.get("unit")))
        else:
            fields.append(Field(name, str(definition)))
    return Schema(tuple(fields))
