"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The estate at a glance.

A model inventory answers "how many models". A model risk function needs to
answer something harder: **how much of this estate is actually governed, and
where is it going wrong**. Those are different questions and the second one is
the one that gets asked in a committee.

Everything here is derived rather than stored. There is no summary table to fall
behind the register, which matters because a stale summary is worse than none —
somebody will act on it.

Debt is kept apart from breach in every count, for the reason it is kept apart
everywhere else: a Tier 1 model that arrived last week and a Tier 1 model that
missed its validation must never contribute to the same number.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Sequence

from core.log import get_logger

logger = get_logger(__name__)


class EstateSummary:
    """Aggregates the estate from the same state everything else reads."""

    def __init__(self, registry, findings=None, monitoring=None, overlays=None,
                 debts=None, baseline=None, lifecycle=None, regimes=None,
                 documents=None):
        self.registry, self.findings = registry, findings
        self.monitoring, self.overlays = monitoring, overlays
        self.debts, self.baseline = debts, baseline
        self.lifecycle, self.regimes, self.documents = lifecycle, regimes, documents

    def of(self, models: Sequence[Dict[str, Any]],
           now: Optional[float] = None) -> Dict[str, Any]:
        moment = now if now is not None else time.time()
        by_tier: Dict[Any, int] = {}
        by_state: Dict[str, int] = {}
        for m in models:
            by_tier[m["tier"]] = by_tier.get(m["tier"], 0) + 1
            by_state[m["status"]] = by_state.get(m["status"], 0) + 1

        return {
            "models": len(models),
            "by_tier": by_tier, "by_state": by_state,
            "untiered": by_tier.get(None, 0),
            "in_force": by_state.get("attested", 0),
            "governance": self._governance(models),
            "assurance": self._assurance(models, moment),
            "adjustments": self._adjustments(models, moment),
            "cold_start": self._cold_start(models, moment),
            "detail": self._headline(models, by_state),
        }

    # ---------------------------------------------------------------- pieces
    def _headline(self, models, by_state) -> str:
        attested = by_state.get("attested", 0)
        baselined = by_state.get("baselined", 0)
        parts = [f"{len(models)} model(s) registered", f"{attested} in force"]
        if baselined:
            parts.append(f"{baselined} baselined and carrying debt")
        return "; ".join(parts)

    def _governance(self, models) -> Dict[str, Any]:
        """Is the record complete, and is anything blocked?"""
        blocking = unattested = 0
        for m in models:
            if self.findings:
                blocking += len(self.findings.blocking_for(m["id"]))
            if m["status"] not in ("attested", "retired"):
                unattested += 1
        return {"blocking_findings": blocking, "not_in_force": unattested,
                "detail": (f"{blocking} blocking finding(s) across the estate; "
                           f"{unattested} model(s) not in force")}

    def _assurance(self, models, now) -> Dict[str, Any]:
        """Is anything degrading, and would we know?"""
        monitored = breaching = unmonitored = 0
        for m in models:
            if not self.monitoring:
                continue
            status = self.monitoring.status(m["id"])
            if status["monitors"]:
                monitored += 1
            else:
                unmonitored += 1
            breaching += status["open_breaches"]
        return {"monitored": monitored, "unmonitored": unmonitored,
                "open_breaches": breaching,
                "detail": (f"{monitored} model(s) monitored, {unmonitored} not; "
                           f"{breaching} open breach(es)")}

    def _adjustments(self, models, now) -> Dict[str, Any]:
        """How much of the estate's numbers is the model, and how much is us?"""
        active = persistent = 0
        magnitude = 0.0
        for m in models:
            if not self.overlays:
                continue
            status = self.overlays.status(m["id"], now)
            active += status["active"]
            persistent += status["persistent"]
            magnitude += status["aggregate_magnitude"]
        return {"active": active, "persistent": persistent,
                "aggregate_magnitude": round(magnitude, 2),
                "detail": (f"{active} active overlay(s) adjusting the estate by "
                           f"{magnitude:,.2f} in aggregate"
                           + (f"; {persistent} have outlived their renewal limit"
                              if persistent else ""))}

    def _cold_start(self, models, now) -> Dict[str, Any]:
        """Debt, kept apart from breach."""
        if not self.baseline:
            return {"baselined": 0, "detail": "nothing has been baselined"}
        portfolio = self.baseline.portfolio()
        return {"baselined": portfolio["models_baselined"],
                "debt_open": portfolio["debt_open"],
                "debt_closed": portfolio["debt_closed"],
                "debt_breached": portfolio["debt_breached"],
                "burn_down": portfolio["burn_down"],
                "detail": portfolio["detail"]}
