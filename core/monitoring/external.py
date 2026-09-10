"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Numbers MAYA did not compute.

Most banks already have monitoring. There is an MLOps platform computing PSI
nightly, a quant team with a notebook that produces the AUC the committee
actually looks at, and a vendor dashboard for the vendor's own model. A
governance platform that insisted on recomputing all of it would be asking the
firm to run everything twice and would lose, because the number on the slide
would keep coming from the other system.

So MAYA takes the number. What it does not take is the verdict.

**The threshold is the register's and the comparison is the register's.** An
ingested observation carries a value, a window, a population size and the name
of whatever computed it. It does not carry `passed`. Whoever produced the
number does not get to say whether it breached — that judgement is made here,
against the threshold on the monitor that this firm's second line set, using
the same `judge` that MAYA's own evaluations use. An external system that could
mark its own homework is the failure mode this whole module exists to avoid, and
it is the failure mode every "push your metrics to us" API has.

**Provenance travels with the number, everywhere.** An observation records
whether MAYA computed it, who did if not, and by what method. The estate view
reports the split, because a monitoring programme where 80% of the numbers
cannot be reproduced by the platform holding them is a real finding about the
programme, and one that is invisible if the two kinds of number print the same.

**What is given up is stated rather than glossed.** An external observation
cannot be replayed: MAYA does not hold the population it was computed over and
cannot re-derive the value from the evidence chain. That is a genuine loss of
assurance, it is the price of not mandating the compute, and it is named on the
observation rather than discovered by an auditor who asked for a recomputation
and was told it was not possible.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from db.database import digest as canonical_digest
from core.log import get_logger
from core.monitoring.common import MonitorError

logger = get_logger(__name__)

MAYA, EXTERNAL = "maya", "external"
SOURCES = (MAYA, EXTERNAL)


class ExternalObservations:
    """Ingests monitoring results computed elsewhere, and judges them here."""

    def __init__(self, monitoring, registry, catalogue, evidence):
        self.monitoring, self.registry = monitoring, registry
        self.catalogue, self.evidence = catalogue, evidence

    # ----------------------------------------------------------------- ingest
    def ingest(self, monitor_id: str, value: Optional[float],
               computed_by: str, method: str = "",
               sample_size: int = 0,
               window_start: Optional[float] = None,
               window_end: Optional[float] = None,
               now: Optional[float] = None,
               actor: str = "system") -> Dict[str, Any]:
        """Record a value somebody else computed, and judge it against our threshold."""
        monitor = self.monitoring.registry.require(monitor_id)
        if monitor["status"] != "active":
            raise MonitorError(
                "monitor_inactive",
                f"monitor '{monitor['name']}' is {monitor['status']}, so a "
                f"result for it would be a number against a question this firm "
                f"has stopped asking",
                "reactivate the monitor, or retire the external job feeding it")
        if not (computed_by or "").strip():
            raise MonitorError(
                "computed_by_required",
                "an ingested observation must name what computed it — a number "
                "of unknown origin in the system of record is worse than no "
                "number, because it looks like one MAYA stands behind",
                "name the system, notebook or vendor that produced this value")
        if window_start is None or window_end is None:
            raise MonitorError(
                "window_required",
                "an ingested observation must name the window it covers: "
                "without one it cannot be paired against anything, compared "
                "over time, or read as-at a date",
                "supply window_start and window_end")
        if window_end < window_start:
            raise MonitorError(
                "window_inverted",
                f"the window ends {window_start - window_end:.0f}s before it "
                f"starts", "check the window bounds")

        moment = now if now is not None else time.time()
        direction = self.catalogue.definition(monitor["test_key"]).direction
        # The judgement is ours. The caller supplies no `passed` and there is
        # deliberately no parameter for one.
        passed, verdict = self.catalogue.judge(value, monitor["threshold"] or {},
                                               direction)
        row = {
            "monitor_id": monitor_id, "value": value, "passed": passed,
            "detail": (f"{verdict} — computed by {computed_by}"
                       + (f" ({method})" if method else "")
                       + ", judged here against this firm's threshold"),
            "sample_size": int(sample_size or 0),
            "window_start": window_start, "window_end": window_end,
            "matured": True,
            "source": EXTERNAL, "computed_by": computed_by.strip(),
            "method": (method or "").strip(),
            "digest": canonical_digest(
                {"monitor": monitor_id, "value": value,
                 "threshold": monitor["threshold"], "n": int(sample_size or 0),
                 "computed_by": computed_by.strip(),
                 "window": [window_start, window_end]}),
            "computed_at": moment,
        }
        self.monitoring.observations.add(row)
        observation = self.monitoring.observations.one(id=row["id"])
        with self.evidence.recording():
            self.monitoring.registry.monitors.set({"last_evaluated_at": moment},
                                                  id=monitor_id)
            self.evidence.append(
                "monitor_result_ingested", "model", monitor["model_id"],
                {"monitor_id": monitor_id, "value": value, "passed": passed,
                 "computed_by": computed_by.strip(), "method": method,
                 "sample_size": int(sample_size or 0)}, actor=actor)
        logger.info("ingested %s result for monitor %s from %s (passed=%s)",
                    monitor["test_key"], monitor_id, computed_by, passed)
        # The same reaction as an observation MAYA computed. An external number
        # that breaches opens a breach: taking the number and not acting on it
        # would be filing it rather than monitoring with it.
        return self.monitoring.react_to(monitor, observation, actor)

    # ------------------------------------------------------------- provenance
    def provenance(self, monitor_id: str) -> Dict[str, Any]:
        """Where this monitor's numbers came from, and what that costs."""
        monitor = self.monitoring.registry.require(monitor_id)
        history = self.monitoring.history(monitor_id)
        by_source: Dict[str, int] = {}
        systems: Dict[str, int] = {}
        for row in history:
            source = row.get("source") or MAYA
            by_source[source] = by_source.get(source, 0) + 1
            if source == EXTERNAL:
                who = row.get("computed_by") or "unnamed"
                systems[who] = systems.get(who, 0) + 1
        external = by_source.get(EXTERNAL, 0)
        return {
            "monitor_id": monitor_id, "name": monitor["name"],
            "observations": len(history), "by_source": by_source,
            "systems": systems,
            "replayable": len(history) - external,
            "detail": self._provenance_detail(len(history), external, systems),
        }

    @staticmethod
    def _provenance_detail(total: int, external: int,
                           systems: Dict[str, int]) -> str:
        if not total:
            return "this monitor has never been evaluated by anybody"
        if not external:
            return (f"all {total} observation(s) were computed by MAYA and can "
                    f"be replayed from the evidence chain")
        return (f"{external} of {total} observation(s) came from "
                + ", ".join(sorted(systems))
                + ". MAYA does not hold the population they were computed over, "
                  "so they cannot be replayed — the value is the register's "
                  "record of what was asserted, and the assurance behind it is "
                  "the asserting system's, not this one's")

    # ----------------------------------------------------------------- estate
    def across_the_estate(self) -> Dict[str, Any]:
        """How much of this firm's monitoring MAYA could reproduce."""
        rows: List[Dict[str, Any]] = []
        for model in self.registry.list():
            for monitor in self.monitoring.registry.for_model(model["id"]):
                row = self.provenance(monitor["id"])
                if row["observations"]:
                    rows.append({**row, "urn": model["urn"]})
        total = sum(r["observations"] for r in rows)
        external = sum(r["by_source"].get(EXTERNAL, 0) for r in rows)
        systems = sorted({s for r in rows for s in r["systems"]})
        rows.sort(key=lambda r: -r["by_source"].get(EXTERNAL, 0))
        return {
            "monitors": rows, "count": len(rows),
            "observations": total, "external": external,
            "replayable": total - external,
            "systems": systems,
            "detail": (
                f"{total} observation(s) across {len(rows)} monitor(s); "
                f"{external} were computed elsewhere"
                + (f" by {', '.join(systems)}" if systems else "")
                + (f", so {external / total:.0%} of this firm's monitoring "
                   f"record cannot be reproduced by the platform holding it. "
                   f"That is the price of not mandating the compute, and it is "
                   f"a fact about the programme rather than about any one "
                   f"number" if external and total else
                   ". Every one of them can be replayed from the evidence chain")
                if total else
                "no monitor anywhere in the estate has been evaluated"),
        }
