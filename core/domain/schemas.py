"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Input and output objects: the schema lattice and the variance rule that
decides substitutability (law L-12): contravariant in inputs, covariant in
outputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

def explain(failures: Dict[str, Any], ok: str) -> str:
    """Render a refusal so it names what failed. Design rule DR-7 in one place."""
    parts = [f"{label}: {', '.join(items)}" for label, items in failures.items() if items]
    return "; ".join(parts) or ok


@dataclass(frozen=True)
class Field:
    name: str
    dtype: str
    nullable: bool = False
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    #: How this field is written in mathematics — `\\sigma`, `\\mathrm{DSCR}`.
    #: Optional, and used only for typesetting: a name with no symbol is set
    #: upright, because `debt_service` in italics reads as nine letters
    #: multiplied together.
    symbol: Optional[str] = None
    #: What the number MEANS dimensionally — `GBP`, `ratio`, `years`, `bp`.
    #: Not parsed and not converted: MAYA is not a units library, and pretending
    #: to convert would be worse than not knowing. It is compared, which is the
    #: part that catches something — a replacement declaring `bp` where the
    #: incumbent declared `ratio` is a hundred-fold error that every type check
    #: passes, because both are numbers.
    unit: Optional[str] = None

    def accepts(self, other: "Field") -> bool:
        """True when this field can stand in for ``other`` as an INPUT."""
        if self.dtype != other.dtype:
            return False
        # A declared unit that CHANGES is a regression, and one that appears or
        # disappears is not: an incumbent that said nothing about units cannot
        # have callers relying on one, and a replacement that starts saying so
        # is adding information. Only a contradiction refuses.
        if self.unit and other.unit and self.unit != other.unit:
            return False
        if other.nullable and not self.nullable:
            return False                                  # we would reject nulls it allows
        lo_ok = self.minimum is None or (other.minimum is not None and self.minimum <= other.minimum)
        hi_ok = self.maximum is None or (other.maximum is not None and self.maximum >= other.maximum)
        return lo_ok and hi_ok


@dataclass(frozen=True)
class Schema:
    fields: Tuple[Field, ...] = ()

    def by_name(self) -> Dict[str, Field]:
        return {f.name: f for f in self.fields}

    def accepts_superset_of(self, other: "Schema") -> List[str]:
        """Contravariance in inputs. Returns the names that regress."""
        mine = self.by_name()
        return [f.name for f in other.fields
                if f.name not in mine or not mine[f.name].accepts(f)]

    def provides_superset_of(self, other: "Schema") -> List[str]:
        """Covariance in outputs. Returns the names no longer provided.

        Delegates rather than reimplementing. This method carried the unit
        comparison and had NO callers; `lattice.provides` is what
        `substitutable` asks, and it compared name and dtype only — so the one
        check that would have caught a `ratio` becoming a `bp` was written,
        correct, and never run. Two implementations of one rule is how that
        happens, so now there is one.
        """
        from core.domain.lattice import provides

        return list(provides(self, other))


@dataclass(frozen=True)
class VarianceResult:
    ok: bool
    input_regressions: Tuple[str, ...] = ()
    output_regressions: Tuple[str, ...] = ()

    def reason(self) -> str:
        return explain({"inputs no longer accepted": self.input_regressions,
                        "outputs no longer provided": self.output_regressions}, "compatible")


def substitutable(new_in: Schema, new_out: Schema, old_in: Schema, old_out: Schema) -> VarianceResult:
    """Law L-12: contravariant in inputs, covariant in outputs.

    Expressed through `core.domain.lattice.refines` rather than through its own
    loop, so that this and `L-W10` — *does this featureset provide what the
    kernel reads* — are literally the same comparison. They were the same
    relation written twice, and two implementations of one order eventually
    disagree in the direction of permitting more.
    """
    from core.domain.lattice import provides, refines            # circular at module level
    contravariant = refines(new_in, old_in)
    ins = contravariant.missing + contravariant.narrowed
    outs = provides(new_out, old_out)
    return VarianceResult(ok=not ins and not outs, input_regressions=ins, output_regressions=outs)
