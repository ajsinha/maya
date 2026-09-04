"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The domain algebra. Pure: no I/O, no web framework, no database.

A model is a morphism in Para(Stoch) — a parameter object P, an input object X,
an output object Y, and a kernel f : P (x) X -> Y. The trainability class is
DERIVED from how P is inhabited, never declared, which is what makes "some
models are never trained" a type-level fact rather than a special case.

See docs/00-mathematical-foundations.md and docs/14-detailed-design.md §2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ParameterKind(str, Enum):
    NONE = "none"                       # P = I, the terminal object: nothing to fit
    CALIBRATION_SET = "calibration_set"
    ESTIMATED_COEFFICIENTS = "estimated_coefficients"
    LEARNED_WEIGHTS = "learned_weights"
    LLM_CONFIGURATION = "llm_configuration"
    RULE_SET = "rule_set"
    ELICITED_WEIGHTS = "elicited_weights"
    OPAQUE = "opaque"                   # exists, but the governing party cannot see it


class FitProcedure(str, Enum):
    NONE = "none"
    CALIBRATE = "calibrate"
    ESTIMATE = "estimate"
    TRAIN = "train"
    ELICIT = "elicit"
    CONFIGURE = "configure"
    AUTHOR = "author"


class OutputKind(str, Enum):
    POINT_ESTIMATE = "point_estimate"
    PREDICTIVE_DISTRIBUTION = "predictive_distribution"
    CLASS_PROBABILITIES = "class_probabilities"
    TEXT = "text"
    STRUCTURED = "structured"
    DECISION = "decision"


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
        parts = []
        if self.input_regressions:
            parts.append("inputs no longer accepted: " + ", ".join(self.input_regressions))
        if self.output_regressions:
            parts.append("outputs no longer provided: " + ", ".join(self.output_regressions))
        return "; ".join(parts) or "compatible"


def substitutable(new_in: Schema, new_out: Schema, old_in: Schema, old_out: Schema) -> VarianceResult:
    """Law L-12: contravariant in inputs, covariant in outputs."""
    ins = tuple(new_in.accepts_superset_of(old_in))
    outs = tuple(new_out.provides_superset_of(old_out))
    return VarianceResult(ok=not ins and not outs, input_regressions=ins, output_regressions=outs)


@dataclass(frozen=True)
class ParameterObject:
    kind: ParameterKind
    artifact_digest: Optional[str] = None
    cardinality: Optional[int] = None

    @property
    def is_terminal(self) -> bool:
        """P is isomorphic to the monoidal unit: the T0 case."""
        return self.kind is ParameterKind.NONE

    @property
    def is_accessible(self) -> bool:
        """False for a vendor black box: P exists but cannot be inspected."""
        return self.kind is not ParameterKind.OPAQUE


_FIT_TO_CLASS = {
    FitProcedure.CALIBRATE: "T1",
    FitProcedure.ESTIMATE: "T2",
    FitProcedure.TRAIN: "T3",
    FitProcedure.CONFIGURE: "T5",
    FitProcedure.ELICIT: "T7",
    FitProcedure.AUTHOR: "T8",
}


@dataclass(frozen=True)
class ParametricKernel:
    """A model: f : P (x) X -> Y."""
    parameters: ParameterObject
    input_schema: Schema
    output_schema: Schema
    output_kind: OutputKind = OutputKind.POINT_ESTIMATE
    deterministic: bool = True
    fit: FitProcedure = FitProcedure.NONE
    adaptive: bool = False

    @property
    def trainability_class(self) -> str:
        """T0-T8, derived from how P is inhabited. Never stored, never declared."""
        if not self.parameters.is_accessible:
            return "T6"
        if self.parameters.is_terminal:
            return "T0"
        if self.fit is FitProcedure.TRAIN and self.adaptive:
            return "T4"
        return _FIT_TO_CLASS.get(self.fit, "T0")

    @property
    def requires_fitting_evidence(self) -> bool:
        """False for T0 and T6: asking either for a training set is a type error."""
        return self.trainability_class not in ("T0", "T6")


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
        except (TypeError, ValueError):
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
        """Evaluate ``input |= A``. Returns the assumption keys that fail."""
        return [b.key for b in self.assumptions
                if b.key in values and not b.contains(values[b.key])]

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
        parts = []
        if self.assumption_failures:
            parts.append("assumptions not weakened: " + ", ".join(self.assumption_failures))
        if self.guarantee_failures:
            parts.append("guarantees not preserved: " + ", ".join(self.guarantee_failures))
        return "; ".join(parts) or "refines"


# ----------------------------------------------------------- probe equivalence
@dataclass(frozen=True)
class Probe:
    name: str
    inputs: Dict[str, Any]


@dataclass(frozen=True)
class EquivalenceResult:
    equivalent: bool
    probe_count: int
    coverage: float
    divergences: Tuple[str, ...] = ()


def pi_equivalent(a: Dict[str, Any], b: Dict[str, Any], probes: List[Probe],
                  tolerance: float = 0.0, declared_inputs: int = 0) -> EquivalenceResult:
    """v1 == v2 relative to a probe set. The formal content of a PATCH release.

    Equivalence is only ever as strong as the probe set is rich, so coverage is
    reported alongside it and stored with the claim.
    """
    diverged = []
    for p in probes:
        x, y = a.get(p.name), b.get(p.name)
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            if abs(x - y) > tolerance:
                diverged.append(p.name)
        elif x != y:
            diverged.append(p.name)
    touched = {k for p in probes for k in p.inputs}
    coverage = len(touched) / declared_inputs if declared_inputs else 0.0
    return EquivalenceResult(equivalent=not diverged, probe_count=len(probes),
                             coverage=round(coverage, 4), divergences=tuple(diverged))
