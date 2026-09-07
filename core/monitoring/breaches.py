"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Breaches, and the loop they close.

A breach is an observation outside its threshold. On its own that is a number in
a dashboard, which is where most monitoring stops and why most monitoring
changes nothing.

Here a breach **raises a finding**. A finding has an owner, a remediation window
and a severity; and a blocking finding refuses warrant resolution and alias
promotion. So a model whose discrimination has collapsed stops being servable —
not because someone noticed the dashboard, but because the chain from
measurement to refusal is mechanical.

Severity escalates with persistence. One breach is a data point; the same
monitor breaching for the *n*th consecutive evaluation is a condition, and it is
raised as one.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from core.evidence import EvidenceEngine
from core.validation import SEVERITIES, FindingRegister, severity_rank
from db import BreachRepository


class BreachRegister:
    """Opens breaches, escalates persistent ones, and raises the findings."""

    def __init__(self, breaches: BreachRepository, findings: FindingRegister,
                 evidence: EvidenceEngine):
        self.breaches, self.findings, self.evidence = breaches, findings, evidence

    @staticmethod
    def escalate(base: str, consecutive: int, escalate_after: int) -> str:
        """One breach is a data point; a run of them is a condition.

        Severity rises by one level each time the run length reaches a multiple
        of the escalation threshold, and stops at Critical.
        """
        if escalate_after <= 0:
            return base
        steps = consecutive // escalate_after
        return SEVERITIES[max(0, severity_rank(base) - steps)]

    def consecutive_for(self, monitor_id: str, observations: List[Dict[str, Any]]) -> int:
        """How many evaluations in a row this monitor has failed, latest first."""
        run = 0
        for obs in reversed(observations):
            if obs["passed"]:
                break
            run += 1
        return run

    def open(self, monitor: Dict[str, Any], observation: Dict[str, Any],
             consecutive: int, actor: str = "system") -> Dict[str, Any]:
        severity = self.escalate(monitor["breach_severity"], consecutive,
                                 monitor["escalate_after"])
        detail = (f"{monitor['name']} ({monitor['test_key']}) breached: "
                  f"{observation['detail']}"
                  + (f"; {consecutive} consecutive evaluations" if consecutive > 1 else ""))

        finding = self.findings.raise_finding(
            monitor["model_id"], severity,
            title=f"Monitor breach: {monitor['name']}",
            owner=monitor["owner"], description=detail, category="monitoring",
            source="monitoring", model_version_id=monitor.get("model_version_id"),
            affected_component=monitor["test_key"], actor=actor)

        row = {"monitor_id": monitor["id"], "model_id": monitor["model_id"],
               "observation_id": observation["id"], "severity": severity,
               "consecutive": consecutive, "detail": detail,
               "finding_id": finding["id"], "status": "open",
               "opened_at": time.time(), "closed_at": None}
        with self.evidence.recording():
            self.breaches.add(row)
            self.evidence.append("monitor_breached", "model", monitor["model_id"],
                                 {"monitor_id": monitor["id"], "breach_id": row["id"],
                                  "severity": severity, "consecutive": consecutive,
                                  "finding_id": finding["id"]}, actor=actor)
        return {**self.breaches.one(id=row["id"]), "finding": finding}

    def resolve(self, monitor_id: str, actor: str = "system") -> List[Dict[str, Any]]:
        """Close the open breaches for a monitor that has recovered.

        The breach closes; the FINDING does not. A metric coming back inside its
        threshold is not evidence that whatever moved it was understood, and
        closing the finding automatically would erase the obligation to find out.
        """
        closed = []
        for row in self.breaches.many(monitor_id=monitor_id, status="open"):
            with self.evidence.recording():
                self.breaches.set({"status": "resolved", "closed_at": time.time()},
                                  id=row["id"])
                self.evidence.append("monitor_recovered", "model", row["model_id"],
                                     {"monitor_id": monitor_id, "breach_id": row["id"],
                                      "finding_id": row["finding_id"],
                                      "finding_remains_open": True}, actor=actor)
            closed.append(self.breaches.one(id=row["id"]))
        return closed

    # ----------------------------------------------------------------- query
    def open_for(self, model_id: str) -> List[Dict[str, Any]]:
        return self.breaches.open_for(model_id)

    def for_monitor(self, monitor_id: str) -> List[Dict[str, Any]]:
        return self.breaches.many(monitor_id=monitor_id)
