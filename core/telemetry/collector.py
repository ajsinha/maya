"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Telemetry ingestion.

Monitors could always be *evaluated*; they had to be handed their rows. That made
monitoring a thing somebody remembered to do, and the scheduler could only ever
record that a monitor had **stopped** running — it could not run one, because the
platform did not hold the data.

This holds it. Two streams per model version, both bitemporal, both in Delta.

**Ingestion is idempotent.** A batch carries the digest of its own rows, and a
digest already recorded is accepted and not written again. Real collectors
deliver at least once; a monitor that double-counts a redelivered batch reports a
population that never existed.

**Scores and outcomes are separate streams.** A score exists the moment the model
runs; an outcome is learned later, and the gap between them is the thing the
delayed-label discipline is about. Joining them is a read-time act, performed
against a stated moment, which is what makes maturity decidable per row rather
than assumed for a batch.

**A sample knows it is a sample.** High-volume models are ingested at a rate, and
the rate is recorded on every row, so a statistic computed downstream can say what
population it speaks for instead of quietly speaking for the sample.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.evidence import EvidenceEngine
from core.log import get_logger
from core.telemetry.common import (ENTITY, INGEST_TS, LABEL, LABEL_TS, MAX_BATCH,
                                   OUTCOMES, REQUIRED, SCORE, SCORED_AT, SCORES,
                                   STREAMS, TelemetryError)
from db.database import digest as canonical_digest

logger = get_logger(__name__)


class TelemetryCollector:
    """Accepts scored rows and outcomes, and serves them back to a monitor."""

    def __init__(self, delta, registry, evidence: EvidenceEngine,
                 batches=None):
        self.delta, self.registry, self.evidence = delta, registry, evidence
        # Recorded batch digests, so redelivery is a no-op rather than a
        # double count. A dict when no repository is supplied, which is enough
        # for a single process and honest about not surviving a restart.
        self.batches = batches if batches is not None else {}

    # -------------------------------------------------------------- ingestion
    def ingest(self, urn: str, semver: str, stream: str,
               rows: Sequence[Dict[str, Any]], sample_rate: float = 1.0,
               source: str = "unknown", actor: str = "system") -> Dict[str, Any]:
        """Take delivery of a batch. Delivering it twice changes nothing."""
        if stream not in STREAMS:
            raise TelemetryError("unknown_stream", f"unknown stream '{stream}'",
                                 f"expected one of {', '.join(STREAMS)}")
        if not rows:
            raise TelemetryError("empty_batch", "the batch has no rows",
                                 "send rows, or send nothing at all")
        if len(rows) > MAX_BATCH:
            raise TelemetryError(
                "batch_too_large",
                f"{len(rows)} rows; the limit is {MAX_BATCH:,} per batch",
                "split the batch; the limit exists so one delivery cannot stall "
                "every other model's ingestion")
        if not 0 < sample_rate <= 1:
            raise TelemetryError(
                "bad_sample_rate",
                f"a sample rate of {sample_rate} is not a proportion",
                "give a rate in (0, 1]; 1.0 means every row was ingested")

        version = self._version(urn, semver)
        self._check_shape(stream, rows)
        batch = canonical_digest({"stream": stream, "version": version["id"],
                                  "rows": [dict(sorted(r.items())) for r in rows]})
        table = self.table(version["id"], stream)

        if self._already_have(batch):
            logger.info("batch %s was already ingested; not writing again",
                        batch[:20])
            return {"stream": stream, "table": table, "rows": 0,
                    "batch": batch, "duplicate": True,
                    "detail": "this exact batch was already ingested; delivering "
                              "it again changes nothing"}

        now = time.time()
        stamped = [{**row, INGEST_TS: row.get(INGEST_TS, now),
                    "sample_rate": sample_rate, "source": source,
                    "batch": batch} for row in rows]
        delta_version = self.delta.write(table, stamped)
        self._remember(batch, {"delta_table": table, "row_count": len(rows),
                               "at": now})
        self.evidence.append("telemetry_ingested", "version", version["id"],
                             {"stream": stream, "rows": len(rows),
                              "batch": batch, "sample_rate": sample_rate,
                              "source": source}, actor=actor)
        return {"stream": stream, "table": table, "rows": len(stamped),
                "batch": batch, "duplicate": False,
                "delta_version": delta_version, "sample_rate": sample_rate,
                "detail": f"{len(stamped)} rows into {table}"}

    @staticmethod
    def _check_shape(stream: str, rows: Sequence[Dict[str, Any]]) -> None:
        """A row missing its clock is refused. Ingesting it and inferring the
        moment later is how a scored row acquires the timestamp of the batch it
        happened to arrive in, which makes every window wrong."""
        required = REQUIRED[stream]
        for index, row in enumerate(rows):
            if missing := [f for f in required if f not in row]:
                raise TelemetryError(
                    "malformed_row",
                    f"row {index} is missing {', '.join(missing)}",
                    f"a '{stream}' row carries {', '.join(required)}; the "
                    f"timestamp is the row's own and cannot be inferred from "
                    f"when the batch arrived")

    def _already_have(self, batch: str) -> bool:
        if isinstance(self.batches, dict):
            return batch in self.batches
        return self.batches.one(digest=batch) is not None

    def _remember(self, batch: str, meta: Dict[str, Any]) -> None:
        if isinstance(self.batches, dict):
            self.batches[batch] = meta
        else:
            self.batches.add({"digest": batch, **meta})

    # ------------------------------------------------------------------ read
    @staticmethod
    def table(version_id: str, stream: str) -> str:
        return f"telemetry/{version_id}/{stream}"

    def rows(self, urn: str, semver: str, stream: str = SCORES,
             since: Optional[float] = None, until: Optional[float] = None,
             known_by: Optional[float] = None) -> List[Dict[str, Any]]:
        """Rows in a window, optionally as they were known at a moment.

        ``known_by`` is the transaction-time bound. Without it a read of last
        quarter returns outcomes that arrived this morning, which is a different
        population from the one anybody was looking at last quarter.
        """
        version = self._version(urn, semver)
        table = self.table(version["id"], stream)
        if not self.delta.exists(table):
            return []
        frame = self.delta.read(table)
        if frame.empty:
            return []
        stamp = SCORED_AT if stream == SCORES else LABEL_TS
        if since is not None:
            frame = frame[frame[stamp] >= since]
        if until is not None:
            frame = frame[frame[stamp] <= until]
        if known_by is not None:
            frame = frame[frame[INGEST_TS] <= known_by]
        return frame.to_dict("records")

    def cohort(self, urn: str, semver: str, since: Optional[float] = None,
               until: Optional[float] = None,
               known_by: Optional[float] = None) -> List[Dict[str, Any]]:
        """Scores joined to the outcomes that are known, for a monitor to judge.

        Rows with no outcome yet are returned **with no label** rather than
        dropped. That is the point: the monitor decides maturity per row, and a
        join that silently discarded the unlabelled would hand it a cohort that
        looks complete and is not.
        """
        scores = self.rows(urn, semver, SCORES, since, until, known_by)
        outcomes = self.rows(urn, semver, OUTCOMES, known_by=known_by)
        by_entity: Dict[Any, Dict[str, Any]] = {}
        for row in sorted(outcomes, key=lambda r: (r[LABEL_TS], r[INGEST_TS])):
            by_entity[row[ENTITY]] = row
        joined = []
        for row in scores:
            outcome = by_entity.get(row[ENTITY])
            joined.append({
                ENTITY: row[ENTITY], SCORED_AT: row[SCORED_AT],
                SCORE: row[SCORE], INGEST_TS: row[INGEST_TS],
                "sample_rate": row.get("sample_rate", 1.0),
                **({LABEL: outcome[LABEL], LABEL_TS: outcome[LABEL_TS]}
                   if outcome else {})})
        return joined

    # --------------------------------------------------------------- summary
    def status(self, urn: str, semver: str,
               now: Optional[float] = None) -> Dict[str, Any]:
        """What this version has sent, and whether anything is arriving."""
        moment = now if now is not None else time.time()
        scores = self.rows(urn, semver, SCORES)
        outcomes = self.rows(urn, semver, OUTCOMES)
        latest = max((r[SCORED_AT] for r in scores), default=None)
        rates = {r.get("sample_rate", 1.0) for r in scores}
        return {
            "model": urn, "semver": semver,
            "scores": len(scores), "outcomes": len(outcomes),
            "labelled_fraction": (round(len(outcomes) / len(scores), 3)
                                  if scores else 0.0),
            "latest_score_at": latest,
            "silent_days": (round((moment - latest) / 86400.0, 1)
                            if latest else None),
            "sample_rates": sorted(rates),
            "detail": self._detail(scores, outcomes, latest, moment, rates),
        }

    @staticmethod
    def _detail(scores: List, outcomes: List, latest: Optional[float],
                now: float, rates: set) -> str:
        if not scores:
            return ("nothing has been ingested for this version, so a monitor "
                    "cannot be evaluated from storage")
        silent = (now - latest) / 86400.0 if latest else 0
        parts = [f"{len(scores):,} scores, {len(outcomes):,} outcomes"]
        if silent > 1:
            parts.append(f"nothing scored for {silent:.1f} days")
        if rates and min(rates) < 1.0:
            parts.append(f"sampled at {min(rates):.1%}, so every statistic "
                         f"speaks for the sample and not the population")
        return "; ".join(parts)

    # ---------------------------------------------------------------- subject
    def _version(self, urn: str, semver: str) -> Dict[str, Any]:
        version = self.registry.version(urn, semver)
        if version is None:
            raise TelemetryError("no_such_version",
                                 f"{urn} has no version {semver}",
                                 "send telemetry for a version that exists")
        return version
