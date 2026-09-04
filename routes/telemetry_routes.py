"""
MAYA — telemetry ingestion.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Two streams because they arrive at different times. Ingestion is idempotent
because real collectors deliver at least once, and a monitor that double-counts
a redelivered batch reports a population that never existed.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Request
from pydantic import BaseModel

from core.telemetry import STREAM_MEANING
from routes.base import Routes


class IngestIn(BaseModel):
    urn: str
    semver: str
    stream: str = "scores"
    rows: List[Dict[str, Any]]
    sample_rate: float = 1.0
    source: str = "unknown"


class EvaluateIn(BaseModel):
    since: Optional[float] = None
    until: Optional[float] = None
    reference_from: Optional[float] = None
    reference_to: Optional[float] = None


class TelemetryRoutes(Routes):
    def register(self) -> None:
        telemetry, api = self.ctx["telemetry"], self.api
        monitoring, registry = self.ctx["monitoring"], self.ctx["registry"]

        @self.app.get(f"{api}/telemetry-streams", tags=["telemetry"])
        def streams(request: Request):
            self.principal(request)
            return {"streams": [{"stream": k, "means": v}
                                for k, v in STREAM_MEANING.items()]}

        @self.app.post(f"{api}/telemetry", status_code=201, tags=["telemetry"])
        def ingest(request: Request, body: IngestIn):
            """Take delivery of a batch. Delivering it twice changes nothing."""
            model = self.guard(lambda: registry.require(body.urn))
            who = self.authorise(request, "monitor:observe", model=model)
            return self.guard(lambda: telemetry.ingest(
                body.urn, body.semver, body.stream, body.rows,
                body.sample_rate, body.source, self.actor(who)))

        @self.app.get(f"{api}/telemetry", tags=["telemetry"])
        def status(request: Request, urn: str, semver: str):
            """What this version has sent, and whether anything is arriving."""
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "monitor:read", model=model)
            return self.guard(lambda: telemetry.status(urn, semver))

        @self.app.get(f"{api}/telemetry/cohort", tags=["telemetry"])
        def cohort(request: Request, urn: str, semver: str,
                   since: Optional[float] = None, until: Optional[float] = None,
                   known_by: Optional[float] = None):
            """Scores joined to the outcomes known by a moment.

            Rows with no outcome yet come back unlabelled rather than dropped:
            the monitor decides maturity per row, and a join that discarded them
            would hand it a cohort that looks complete and is not.
            """
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "monitor:read", model=model)
            rows = self.guard(
                lambda: telemetry.cohort(urn, semver, since, until, known_by))
            return {"urn": urn, "semver": semver, "rows": len(rows),
                    "labelled": sum(1 for r in rows if "label" in r),
                    "cohort": rows}

        @self.app.post(f"{api}/monitors/{{monitor_id}}/evaluate-from-telemetry",
                       tags=["monitoring"])
        def evaluate(request: Request, monitor_id: str, body: EvaluateIn):
            """Evaluate against telemetry the platform already holds.

            The window is read at the moment it names, not at the moment the
            read happens, so a review of last quarter sees the population last
            quarter saw.
            """
            who = self.authorise(request, "monitor:observe")
            return self.guard(lambda: monitoring.evaluate_from_telemetry(
                monitor_id, body.since, body.until, body.reference_from,
                body.reference_to, actor=self.actor(who)))
