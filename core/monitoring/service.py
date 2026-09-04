"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The monitoring service: evaluate a monitor, record the answer, act on it.

Two properties are enforced here rather than documented.

**A performance monitor is refused over an immature cohort.** Not warned about,
not annotated — refused, with the date the cohort becomes measurable. A number
computed from the outcomes that arrived early is biased towards whichever tail
matures first, and publishing it next to properly-computed numbers is how a
monitoring dashboard becomes untrustworthy in a way nobody notices.

**A breach raises a finding.** That is the loop: measurement to obligation to
refusal. A blocking finding stops warrant resolution, so a model whose
discrimination has collapsed becomes unservable mechanically rather than because
somebody was watching.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.evidence import EvidenceEngine
from core.monitoring.breaches import BreachRegister
from core.monitoring.common import LABEL_DEPENDENT, MonitorError
from core.monitoring.definitions import MonitorRegistry
from core.monitoring.labels import OutcomeWindow, labelled
from core.validation import TestCatalogue, worst
from db import ObservationRepository
from db.database import digest as canonical_digest


class MonitoringService:
    """Evaluates monitors and turns breaches into findings."""

    def __init__(self, registry: MonitorRegistry, observations: ObservationRepository,
                 breaches: BreachRegister, catalogue: TestCatalogue,
                 evidence: EvidenceEngine, telemetry=None, models=None):
        self.registry, self.observations = registry, observations
        self.breaches, self.catalogue, self.evidence = breaches, catalogue, evidence
        # Optional. Without them a monitor can only be handed its rows, which is
        # how monitoring stays a thing somebody remembers to do; with them the
        # scheduler can actually run one.
        self.telemetry, self.models = telemetry, models

    # ------------------------------------------------------------- evaluate
    def evaluate(self, monitor_id: str, rows: Sequence[Dict[str, Any]],
                 reference: Optional[Sequence[float]] = None,
                 now: Optional[float] = None,
                 actor: str = "system") -> Dict[str, Any]:
        """Compute one observation and act on it.

        rows carry scored_at, score and — once known — label.
        reference is the development distribution a drift monitor compares
        against.
        """
        monitor = self.registry.require(monitor_id)
        if monitor["status"] != "active":
            raise MonitorError("monitor_inactive",
                               f"monitor '{monitor['name']}' is {monitor['status']}",
                               "reactivate it before evaluating")
        moment = now if now is not None else time.time()

        if monitor["kind"] in LABEL_DEPENDENT:
            outcome = self._performance(monitor, rows, moment)
        else:
            outcome = self._drift(monitor, rows, reference)

        record = self._record(monitor, outcome, rows, moment, actor)
        return self._react(monitor, record, actor)

    # ----------------------------------------------------- from stored telemetry
    def evaluate_from_telemetry(self, monitor_id: str,
                                since: Optional[float] = None,
                                until: Optional[float] = None,
                                reference_from: Optional[float] = None,
                                reference_to: Optional[float] = None,
                                now: Optional[float] = None,
                                actor: str = "system") -> Dict[str, Any]:
        """Evaluate a monitor against telemetry the platform already holds.

        The window is read at the moment it names, not at the moment the read
        happens: outcomes that arrived after ``until`` are excluded, because a
        review of last quarter should see the population last quarter saw.

        A drift monitor's reference distribution is drawn from a *stated* earlier
        window rather than passed in, so "what is this drifting from" is part of
        the record instead of part of whoever ran it.
        """
        if self.telemetry is None:
            raise MonitorError(
                "no_telemetry",
                "this service was built without a telemetry collector, so a "
                "monitor can only be evaluated against rows supplied by the caller",
                "ingest telemetry for this version, or pass the rows in")
        monitor = self.registry.require(monitor_id)
        urn, semver = self._subject_of(monitor)
        moment = now if now is not None else time.time()

        rows = self.telemetry.cohort(urn, semver, since, until, known_by=until)
        if not rows:
            raise MonitorError(
                "no_telemetry_in_window",
                f"no telemetry for {urn}@{semver} in this window",
                "widen the window, or check that the model is still sending")

        reference = None
        if reference_from is not None or reference_to is not None:
            earlier = self.telemetry.cohort(urn, semver, reference_from,
                                            reference_to, known_by=reference_to)
            reference = [r["score"] for r in earlier if r.get("score") is not None]
            if not reference:
                raise MonitorError(
                    "empty_reference_window",
                    "the reference window holds no scored rows, so there is "
                    "nothing to compare against",
                    "name a window in which this version was actually running")
        return self.evaluate(monitor_id, rows, reference, moment, actor)

    def _subject_of(self, monitor: Dict[str, Any]) -> tuple:
        """Which model version's telemetry this monitor watches."""
        if self.models is None:
            raise MonitorError(
                "no_registry",
                "this service cannot resolve which model version a monitor "
                "watches", "wire the model registry")
        version = self.models.version_by_id(monitor["model_version_id"]) \
            if monitor.get("model_version_id") else None
        if version is None or not version.get("urn"):
            raise MonitorError(
                "monitor_has_no_version",
                f"monitor '{monitor['name']}' is not bound to a model version, "
                f"so there is no telemetry stream to read",
                "define the monitor against a version")
        return version["urn"], version["semver"]

    def _performance(self, monitor: Dict[str, Any], rows: Sequence[Dict[str, Any]],
                     now: float) -> Dict[str, Any]:
        """Refuse over an immature cohort; measure over the matured part."""
        window = OutcomeWindow(monitor["label_delay_days"])
        report = window.report(rows, now)
        mature, _ = window.split(rows, now)
        labels, scores = labelled(mature)

        if not labels:
            raise MonitorError(
                "cohort_immature",
                f"no outcomes have matured yet — {report['detail']}",
                ("wait for the outcome window to close; the earliest maturity is "
                 + (time.strftime('%Y-%m-%d', time.gmtime(report['next_maturity_at']))
                    if report["next_maturity_at"] else "unknown")))

        result = self.catalogue.run(monitor["test_key"], labels, scores,
                                    monitor["threshold"], slice_=monitor["slice"])
        return {"outcome": result, "sample": len(labels), "matured": True,
                "note": report["detail"]}

    def _drift(self, monitor: Dict[str, Any], rows: Sequence[Dict[str, Any]],
               reference: Optional[Sequence[float]]) -> Dict[str, Any]:
        """Compare today's distribution against the declared reference."""
        current = [r["score"] for r in rows if r.get("score") is not None]
        baseline = list(reference or monitor["reference"].get("sample") or [])
        if not baseline:
            raise MonitorError(
                "no_reference",
                "a drift monitor needs a reference distribution to compare against",
                "supply one on the monitor definition, or pass it at evaluation")
        # PSI takes (expected, actual) and its bin edges come from the reference,
        # which is the direction that keeps the number comparable over time.
        #
        # Both series whole. This used to truncate each to the length of the
        # shorter, to satisfy an equal-length check meant for paired
        # label/score tests -- and since telemetry returns rows in write order,
        # the slice kept was the oldest, which is precisely the part of a window
        # that has not drifted yet.
        result = self.catalogue.run(monitor["test_key"], baseline, current,
                                    monitor["threshold"], slice_=monitor["slice"])
        return {"outcome": result, "sample": len(current), "matured": True,
                "note": f"{len(current)} observations against a "
                        f"{len(baseline)}-point reference"}

    # --------------------------------------------------------------- record
    def _record(self, monitor: Dict[str, Any], computed: Dict[str, Any],
                rows: Sequence[Dict[str, Any]], now: float,
                actor: str) -> Dict[str, Any]:
        result = computed["outcome"]
        stamps = [r.get("scored_at") for r in rows if r.get("scored_at") is not None]
        row = {"monitor_id": monitor["id"], "value": result.value,
               "passed": result.passed,
               "detail": f"{result.detail} — {computed['note']}",
               "sample_size": computed["sample"],
               "window_start": min(stamps) if stamps else None,
               "window_end": max(stamps) if stamps else None,
               "matured": computed["matured"],
               "digest": canonical_digest(
                   {"monitor": monitor["id"], "value": result.value,
                    "threshold": monitor["threshold"], "n": computed["sample"]}),
               "computed_at": now}
        self.observations.add(row)
        self.registry.monitors.set({"last_evaluated_at": now}, id=monitor["id"])
        self.evidence.append("monitor_evaluated", "model", monitor["model_id"],
                             {"monitor_id": monitor["id"], "value": result.value,
                              "passed": result.passed,
                              "sample_size": computed["sample"]}, actor=actor)
        return self.observations.one(id=row["id"])

    def _react(self, monitor: Dict[str, Any], observation: Dict[str, Any],
               actor: str) -> Dict[str, Any]:
        """Open a breach, or resolve the standing ones."""
        history = self.observations.many(monitor_id=monitor["id"])
        if observation["passed"]:
            resolved = self.breaches.resolve(monitor["id"], actor)
            return {"observation": observation, "breach": None,
                    "resolved_breaches": len(resolved)}
        consecutive = self.breaches.consecutive_for(monitor["id"], history)
        breach = self.breaches.open(monitor, observation, consecutive, actor)
        return {"observation": observation, "breach": breach, "resolved_breaches": 0}

    # ----------------------------------------------------------------- query
    def history(self, monitor_id: str) -> List[Dict[str, Any]]:
        return self.observations.many(monitor_id=monitor_id)

    def status(self, model_id: str) -> Dict[str, Any]:
        """What an inventory row and the model page need about monitoring."""
        monitors = self.registry.for_model(model_id)
        breaches = self.breaches.open_for(model_id)
        return {
            "monitors": len(monitors),
            "active": sum(m["status"] == "active" for m in monitors),
            "open_breaches": len(breaches),
            "worst_breach": worst(b["severity"] for b in breaches) if breaches else None,
            "detail": [{**m, "last_observation": (self.history(m["id"]) or [None])[-1]}
                       for m in monitors],
        }
