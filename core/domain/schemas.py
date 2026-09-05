"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Input and output objects: the schema lattice and the variance rule that
decides substitutability (law L-12): contravariant in inputs, covariant in
outputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
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

    def accepts(self, other: "Field") -> bool:
        """True when this field can stand in for ``other`` as an INPUT."""
        if self.dtype != other.dtype:
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
        """Covariance in outputs. Returns the names no longer provided."""
        mine = self.by_name()
        return [f.name for f in other.fields
                if f.name not in mine or mine[f.name].dtype != f.dtype]


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
