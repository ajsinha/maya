"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Monitor definitions: the standing questions asked of a model.

A monitor pairs a catalogue test with a threshold, a cadence and — for anything
that compares predictions to outcomes — the delay before those outcomes exist.

Definitions are checked when they are made, not when they run. A monitor pairing
input drift with a discrimination test is a definition error; discovering it at
three in the morning when the batch fails is strictly worse than discovering it
at the moment somebody wrote it down.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.monitoring.common import (ADMISSIBLE_TESTS, DAY, KINDS, LABEL_DEPENDENT,
                                    STATUSES, MonitorError)
from core.validation import SEVERITIES, TestCatalogue
from db import MonitorRepository


class MonitorRegistry:
    """Defines and lists monitors."""

    def __init__(self, monitors: MonitorRepository, catalogue: TestCatalogue,
                 evidence: EvidenceEngine):
        self.monitors, self.catalogue, self.evidence = monitors, catalogue, evidence

    def define(self, model_id: str, name: str, kind: str, test_key: str,
               threshold: Dict[str, Any], owner: str,
               model_version_id: Optional[str] = None,
               reference: Optional[Dict[str, Any]] = None,
               slice_: Optional[Dict[str, Any]] = None,
               cadence_days: float = 1.0, label_delay_days: float = 0.0,
               breach_severity: str = "Medium", escalate_after: int = 3,
               actor: str = "system") -> Dict[str, Any]:
        if kind not in KINDS:
            raise MonitorError("unknown_kind", f"unknown monitor kind '{kind}'",
                               f"expected one of {', '.join(KINDS)}")
        self.catalogue.definition(test_key)          # refuses an unknown test
        admissible = ADMISSIBLE_TESTS[kind]
        if test_key not in admissible:
            raise MonitorError(
                "test_not_admissible",
                f"'{test_key}' cannot answer a '{kind}' question",
                f"for {kind}, use one of {', '.join(admissible)}")
        if not threshold:
            raise MonitorError(
                "threshold_required",
                "a monitor with no threshold can never breach, so it monitors nothing",
                "declare a min, max or target threshold")
        if breach_severity not in SEVERITIES:
            raise MonitorError("unknown_severity",
                               f"unknown severity '{breach_severity}'",
                               f"expected one of {', '.join(SEVERITIES)}")
        if kind in LABEL_DEPENDENT and label_delay_days <= 0:
            raise MonitorError(
                "label_delay_required",
                f"a '{kind}' monitor compares predictions to outcomes, so it must "
                "declare how long those outcomes take to arrive",
                "set label_delay_days; for a 12-month PD model that is 365")
        if self.monitors.one(model_id=model_id, name=name):
            raise MonitorError("duplicate_monitor",
                               f"a monitor named '{name}' already exists for this model",
                               "choose another name")

        row = {"model_id": model_id, "model_version_id": model_version_id,
               "name": name, "kind": kind, "test_key": test_key,
               "threshold": threshold, "slice": slice_ or {},
               "reference": reference or {}, "cadence_days": cadence_days,
               "label_delay_days": label_delay_days,
               "breach_severity": breach_severity, "escalate_after": escalate_after,
               "status": "active", "owner": owner, "created_at": time.time(),
               "last_evaluated_at": None}
        self.monitors.add(row)
        self.evidence.append("monitor_defined", "model", model_id,
                             {"monitor_id": row["id"], "name": name, "kind": kind,
                              "test_key": test_key, "threshold": threshold}, actor=actor)
        return self.monitors.one(id=row["id"])

    # ----------------------------------------------------------------- query
    def get(self, monitor_id: str) -> Optional[Dict[str, Any]]:
        return self.monitors.one(id=monitor_id)

    def require(self, monitor_id: str) -> Dict[str, Any]:
        row = self.get(monitor_id)
        if row is None:
            raise MonitorError("no_monitor", f"no monitor {monitor_id}", "")
        return row

    def for_model(self, model_id: str) -> List[Dict[str, Any]]:
        return self.monitors.many(model_id=model_id)

    def set_status(self, monitor_id: str, status: str,
                   actor: str = "system") -> Dict[str, Any]:
        if status not in STATUSES:
            raise MonitorError("unknown_status", f"unknown status '{status}'",
                               f"expected one of {', '.join(STATUSES)}")
        row = self.require(monitor_id)
        self.monitors.set({"status": status}, id=monitor_id)
        self.evidence.append("monitor_status_changed", "model", row["model_id"],
                             {"monitor_id": monitor_id, "status": status}, actor=actor)
        return self.monitors.one(id=monitor_id)

    def due(self, model_id: str, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """Monitors whose cadence has elapsed. A never-evaluated monitor is due."""
        moment = now if now is not None else time.time()
        return [m for m in self.for_model(model_id)
                if m["status"] == "active"
                and (m["last_evaluated_at"] is None
                     or moment - m["last_evaluated_at"] >= m["cadence_days"] * DAY)]
