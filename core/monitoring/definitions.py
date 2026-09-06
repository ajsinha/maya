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
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.monitoring.common import (ADMISSIBLE_TESTS, DAY, KINDS, LABEL_DEPENDENT,
                                    STATUSES, MonitorError)
from core.validation import SEVERITIES, TestCatalogue
from db import MonitorRepository

if TYPE_CHECKING:                        # pragma: no cover
    # Type-only. `core.fibres.library` reads this package's vocabulary, so a
    # runtime import here would close a cycle: monitoring names the questions,
    # the fibre says which class may ask them, and neither owns the other.
    from core.fibres import FibreRegistry


class MonitorRegistry:
    """Defines and lists monitors."""

    def __init__(self, monitors: MonitorRepository, catalogue: TestCatalogue,
                 evidence: EvidenceEngine,
                 fibres: Optional["FibreRegistry"] = None,
                 class_of: Optional[Callable[[str], Optional[str]]] = None):
        self.monitors, self.catalogue, self.evidence = monitors, catalogue, evidence
        # The fibre says which questions this class can answer at all. Passed as
        # a lookup rather than a registry reference so monitoring does not
        # import the register it is monitoring — see `test_import_discipline`.
        self.fibres, self.class_of = fibres, class_of

    def _refuse_unanswerable(self, model_id: str, kind: str) -> None:
        """A monitor asking a question this class cannot answer.

        `test_key` was already checked against `kind` — pairing input drift with
        a discrimination test is a definition error. What was never checked is
        `kind` against the *model*: a `performance` monitor on a **T0** pricer
        has no parameters and no fitted relationship to lose, and a
        `calibration` monitor on a **T5** generative assembly is asking for a
        Brier score over text.

        Both were accepted, and both produce a monitor that runs forever without
        ever meaning anything — which reads on the estate screen as coverage.
        That is worse than an absent monitor, because an absent monitor is
        visible in the worklist and a meaningless one is not.

        The answer comes from the fibre (`L-15`), which is the point of having
        one: the class already knew what it could answer, in a table in
        `docs/02` that nothing could read.
        """
        if self.fibres is None or self.class_of is None:
            return                       # not wired: no opinion rather than a wrong one
        trainability = self.class_of(model_id)
        if not trainability:
            return                       # no version yet; the fit gate refuses later
        fibre = self.fibres.get(trainability)
        if fibre is None or fibre.admits_monitor(kind):
            return
        raise MonitorError(
            "kind_not_answerable",
            f"a '{kind}' monitor cannot answer anything about a {trainability} "
            f"model ({fibre.label}); what it can answer is: {fibre.answers}",
            f"for {trainability} use one of {', '.join(fibre.metrics)}")

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
        self._refuse_unanswerable(model_id, kind)
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
