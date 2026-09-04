"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The monitoring vocabulary.

Monitors are grouped by what they can be computed from, because that determines
when they can be computed at all:

  * **Drift** monitors compare distributions. They need only inputs or scores,
    so they can run the day a model is deployed.
  * **Performance** monitors compare predictions to outcomes. They cannot run
    until the outcomes exist, which for a 12-month PD model is 12 months.

Conflating the two is the most common way monitoring lies. A dashboard showing
"AUC: 0.71" for a cohort scored last week is reporting a number computed from
whichever handful of outcomes happened to arrive early — which are, by
construction, the fastest defaults. The number is not merely noisy; it is
biased, and biased in the flattering direction.
"""
from __future__ import annotations

from typing import Dict, Tuple

DAY = 86400.0

# What a monitor asks, and what it needs to ask it.
INPUT_DRIFT = "input_drift"
SCORE_DRIFT = "score_drift"
PERFORMANCE = "performance"
CALIBRATION = "calibration"

KINDS: Tuple[str, ...] = (INPUT_DRIFT, SCORE_DRIFT, PERFORMANCE, CALIBRATION)

# Kinds that compare predictions against outcomes, and therefore have to wait.
LABEL_DEPENDENT: Tuple[str, ...] = (PERFORMANCE, CALIBRATION)

# Which catalogue tests are meaningful for each kind. A monitor pairing
# 'input_drift' with 'discrimination.gini' is a definition error, not a runtime
# surprise, so it is refused when the monitor is defined.
ADMISSIBLE_TESTS: Dict[str, Tuple[str, ...]] = {
    INPUT_DRIFT: ("stability.psi",),
    SCORE_DRIFT: ("stability.psi",),
    PERFORMANCE: ("discrimination.auc", "discrimination.gini", "discrimination.ks",
                  "accuracy.rmse", "accuracy.mae"),
    CALIBRATION: ("calibration.brier", "calibration.expected_vs_actual"),
}

STATUSES: Tuple[str, ...] = ("active", "paused", "retired")


class MonitorError(RuntimeError):
    """A monitoring operation was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}
