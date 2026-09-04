"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The model itself: a morphism in Para(Stoch). A parameter object P, an input
object X, an output object Y, and a kernel f : P (x) X -> Y.

The trainability class is DERIVED from how P is inhabited, never declared,
which is what makes "some models are never trained" a type-level fact rather
than a special case.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from core.domain.schemas import Field, Schema

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
