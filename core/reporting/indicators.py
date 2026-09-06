"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Computing the indicators, from the register and nowhere else.

Every number here is derived from the same services the model page and the
worklist read. That is the point: a board pack with its own numbers is a board
pack that disagrees with the platform, and the disagreement surfaces in a
committee meeting where nobody can resolve it.

Two things are deliberately not here.

**No caching.** An indicator is cheap to compute and expensive to be wrong
about, and a cached figure that lags the register is a figure somebody will read
as current.

**No composite.** There is no `model_risk_score`, and there will not be one:
aggregating requires the parts to compose, and two models fed by the same curve
are not two independent risks. Any single figure either double-counts the shared
dependency or ignores it, and a committee cannot decompose it to find out which.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from core.log import get_logger
from core.reporting.common import METRICS

logger = get_logger(__name__)


class IndicatorSet:
    """Computes every metric over a set of models."""

    def __init__(self, registry, findings=None, monitoring=None, overlays=None,
                 baseline=None, lifecycle=None):
        self.registry = registry
        self.findings = findings
        self.monitoring = monitoring
        self.overlays = overlays
        self.baseline = baseline
        self.lifecycle = lifecycle

    # ------------------------------------------------------------------ read
    def compute(self, models: Sequence[Dict[str, Any]],
                now: Optional[float] = None) -> Dict[str, Any]:
        """Every metric, with the gaps named rather than defaulted to zero.

        A metric this instance cannot compute — because the service it reads is
        not wired — comes back as `None` with a reason, never as `0`. A zero is
        a measurement; an absent service is not, and reporting one as the other
        is how a committee is told an estate is clean when it is unmeasured.
        """
        moment = now if now is not None else time.time()
        values: Dict[str, Any] = {}
        unmeasured: Dict[str, str] = {}

        for metric in METRICS:
            fn: Callable = getattr(self, f"_{metric.key}")
            try:
                value = fn(models, moment)
            except Exception as exc:
                # Never swallowed. One indicator that cannot be computed must
                # not take the pack down, and must not be reported as clean.
                logger.warning("indicator %s could not be computed: %s",
                               metric.key, exc)
                values[metric.key] = None
                unmeasured[metric.key] = f"could not be computed: {exc}"
                continue
            if value is None:
                unmeasured[metric.key] = (
                    "this instance has no service wired to answer it")
            values[metric.key] = value

        return {"values": values, "unmeasured": unmeasured,
                "models": len(models), "as_at": moment}

    # ------------------------------------------------------------- the count
    @staticmethod
    def _models_untiered(models, now) -> int:
        return sum(1 for m in models if m.get("tier") is None)

    @staticmethod
    def _models_not_in_force(models, now) -> int:
        return sum(1 for m in models
                   if m.get("status") not in ("attested", "retired"))

    def _blocking_findings(self, models, now) -> Optional[int]:
        if self.findings is None:
            return None
        return sum(len(self.findings.blocking_for(m["id"])) for m in models)

    def _findings_overdue(self, models, now) -> Optional[int]:
        if self.findings is None:
            return None
        return sum(len(self.findings.overdue(m["id"], now)) for m in models)

    def _models_unmonitored(self, models, now) -> Optional[int]:
        if self.monitoring is None:
            return None
        # Counted over models IN FORCE only. A draft nobody is running does not
        # need a monitor, and counting it would make the indicator move when
        # somebody registers a model rather than when the estate degrades.
        return sum(1 for m in self._in_force(models)
                   if not self.monitoring.status(m["id"])["monitors"])

    def _open_breaches(self, models, now) -> Optional[int]:
        if self.monitoring is None:
            return None
        return sum(self.monitoring.status(m["id"])["open_breaches"]
                   for m in models)

    def _overlay_magnitude(self, models, now) -> Optional[float]:
        if self.overlays is None:
            return None
        return round(sum(self.overlays.status(m["id"], now)["aggregate_magnitude"]
                         for m in models), 2)

    def _overlays_persistent(self, models, now) -> Optional[int]:
        if self.overlays is None:
            return None
        return sum(self.overlays.status(m["id"], now)["persistent"]
                   for m in models)

    def _attestations_lapsed(self, models, now) -> Optional[int]:
        if self.lifecycle is None:
            return None
        lapsed = 0
        for m in models:
            state = self.lifecycle.state(m["urn"]) or {}
            if state.get("attestation_lapsed") or state.get("lapsed"):
                lapsed += 1
        return lapsed

    def _baseline_debt(self, models, now) -> Optional[int]:
        if self.baseline is None:
            return None
        return int((self.baseline.portfolio() or {}).get("open_debt", 0))

    # ------------------------------------------------------------- the ratios
    def _monitored_share(self, models, now) -> Optional[float]:
        if self.monitoring is None:
            return None
        in_force = self._in_force(models)
        if not in_force:
            # No denominator. `None` rather than 1.0: an estate with nothing in
            # force is not fully monitored, it is unmeasurable, and reporting a
            # perfect ratio over an empty set is the most flattering possible
            # lie.
            return None
        monitored = sum(1 for m in in_force
                        if self.monitoring.status(m["id"])["monitors"])
        return round(monitored / len(in_force), 4)

    @staticmethod
    def _in_force_share(models, now) -> Optional[float]:
        if not models:
            return None
        in_force = sum(1 for m in models if m.get("status") == "attested")
        return round(in_force / len(models), 4)

    # ------------------------------------------------------------------ parts
    @staticmethod
    def _in_force(models: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [m for m in models if m.get("status") == "attested"]


def within_scope(model: Dict[str, Any], scope: Dict[str, Any]) -> bool:
    """Whether a model falls under a scoped limit.

    Equality on each declared dimension, and nothing cleverer. A scope somebody
    has to reason about is a scope that will be read two ways in the room where
    it matters.
    """
    return all(model.get(dimension) == wanted for dimension, wanted in (scope or {}).items())
