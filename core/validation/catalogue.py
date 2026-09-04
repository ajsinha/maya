"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The test catalogue.

A validation is only meaningful if the tests it ran are named, versioned things
rather than a validator's notebook. So a test is a registered definition with a
key, a direction, and a computation — and running one produces a value, a
verdict against a declared threshold, and a digest over all of it.

The digest is what makes replay possible. Two runs of the same test key with the
same parameters on the same data must produce the same digest, and when they do
not, the difference is the finding.

Thresholds are declared per run rather than baked into the test, because the
Gini floor that is right for a Tier 3 marketing propensity model is not the one
that is right for a Tier 1 IRB PD model. The test is a measurement; the
threshold is a policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from core.validation.common import ValidationError
from core.validation.statistics import (auc, brier, expected_vs_actual, gini, ks, mae,
                                        psi, rmse)
from db.database import digest as canonical_digest

LABELS_SCORES = "labels_scores"      # fn(y_true, y_score)
TWO_SAMPLES = "two_samples"          # fn(expected, actual)


@dataclass(frozen=True)
class TestDefinition:
    key: str
    description: str
    fn: Callable
    direction: str                   # higher_is_better | lower_is_better | target
    inputs: str = LABELS_SCORES


@dataclass
class TestOutcome:
    key: str
    value: Optional[float]
    passed: bool
    detail: str
    threshold: Dict[str, Any]
    parameters: Dict[str, Any]
    slice: Dict[str, Any]

    def digest(self) -> str:
        """Over everything that determines the verdict, so replay can compare."""
        return canonical_digest({"key": self.key, "value": self.value,
                                 "threshold": self.threshold,
                                 "parameters": self.parameters, "slice": self.slice})

    def as_row(self) -> Dict[str, Any]:
        return {"test_key": self.key, "parameters": self.parameters, "slice": self.slice,
                "value": self.value, "threshold": self.threshold,
                "passed": self.passed, "detail": self.detail, "digest": self.digest()}


TESTS = (
    TestDefinition("discrimination.auc", "Area under the ROC curve", auc, "higher_is_better"),
    TestDefinition("discrimination.gini", "Gini coefficient (2 x AUC - 1)", gini,
                   "higher_is_better"),
    TestDefinition("discrimination.ks", "Kolmogorov-Smirnov separation", ks,
                   "higher_is_better"),
    TestDefinition("calibration.brier", "Brier score of the probability forecast", brier,
                   "lower_is_better"),
    TestDefinition("calibration.expected_vs_actual", "Predicted rate over observed rate",
                   expected_vs_actual, "target"),
    TestDefinition("stability.psi", "Population Stability Index against a reference sample",
                   psi, "lower_is_better", TWO_SAMPLES),
    TestDefinition("accuracy.rmse", "Root mean squared error", rmse, "lower_is_better"),
    TestDefinition("accuracy.mae", "Mean absolute error", mae, "lower_is_better"),
)


class TestCatalogue:
    """The registered tests, and the one place a threshold is judged."""

    def __init__(self, definitions: Sequence[TestDefinition] = TESTS):
        self._tests = {d.key: d for d in definitions}

    def keys(self) -> List[str]:
        return sorted(self._tests)

    def definition(self, key: str) -> TestDefinition:
        if key not in self._tests:
            raise ValidationError(
                f"no test '{key}' in the catalogue; known tests are {', '.join(self.keys())}")
        return self._tests[key]

    def describe(self) -> List[Dict[str, str]]:
        return [{"key": d.key, "description": d.description, "direction": d.direction,
                 "inputs": d.inputs} for d in sorted(self._tests.values(), key=lambda d: d.key)]

    # -------------------------------------------------------------------- run
    def run(self, key: str, left: Sequence, right: Sequence,
            threshold: Optional[Dict[str, Any]] = None,
            parameters: Optional[Dict[str, Any]] = None,
            slice_: Optional[Dict[str, Any]] = None) -> TestOutcome:
        """Compute one test and judge it. ``left``/``right`` are labels and
        scores, or the reference and current samples for a two-sample test."""
        definition = self.definition(key)
        if len(left) != len(right):
            raise ValidationError(
                f"{key}: got {len(left)} and {len(right)} values; the two series must align")
        parameters = dict(parameters or {})
        value = definition.fn(left, right, **parameters)
        passed, detail = self.judge(value, threshold or {}, definition.direction)
        return TestOutcome(key, value, passed, detail, dict(threshold or {}),
                           parameters, dict(slice_ or {}))

    @staticmethod
    def judge(value: Optional[float], threshold: Dict[str, Any],
              direction: str) -> tuple:
        """A verdict, and the sentence that explains it.

        No threshold means no verdict to fail: the measurement is recorded and
        passes. That is deliberate — a validator recording an exploratory number
        should not have to invent a limit for it, and a test with no declared
        limit should never look like a test that met one.
        """
        if value is None:
            return False, ("not computable on this sample — a class may be absent, "
                           "or the sample too small for the requested bins")
        if not threshold:
            return True, f"recorded {value:.6g}; no threshold declared"
        if "min" in threshold:
            floor = float(threshold["min"])
            return (value >= floor,
                    f"{value:.6g} {'meets' if value >= floor else 'is below'} the "
                    f"minimum of {floor:.6g}")
        if "max" in threshold:
            cap = float(threshold["max"])
            return (value <= cap,
                    f"{value:.6g} {'is within' if value <= cap else 'exceeds'} the "
                    f"maximum of {cap:.6g}")
        if "target" in threshold:
            target = float(threshold["target"])
            tol = float(threshold.get("tolerance", 0.0))
            ok = abs(value - target) <= tol
            return ok, (f"{value:.6g} is {abs(value - target):.6g} from the target "
                        f"{target:.6g}, tolerance {tol:.6g}" + ("" if ok else " — outside"))
        raise ValidationError(
            f"threshold {threshold} declares none of 'min', 'max' or 'target'")
