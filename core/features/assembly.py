"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Point-in-time training set assembly.

Most "model failures" are feature failures. A model that scored 0.47 in
development and 0.31 in production has usually not degraded; it was never
trained on the data it is now being served — a future value leaked into a past
row, and the backtest was measuring a fact the model could not have known.

So assembly is not best-effort. It is checked, and it is refused when it cannot
be shown correct. The verification deliberately does NOT reuse the assembly
path: an independent recomputation is what stops a bug hiding behind itself.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.features.common import ENTITY, INGEST_TIME, VALID_TIME, payload
from core.features.pit import (AssemblyRejected, AssemblyRequest, detect_leakage,
                               static_check, verify_sampled)
from core.features.views import ViewManager
from db import DeltaStore, SnapshotRepository
from db.database import digest as canonical_digest


class TrainingSetBuilder:
    """Assembles point-in-time-correct training sets, or refuses to."""

    def __init__(self, views: ViewManager, snapshots: SnapshotRepository,
                 delta: DeltaStore, evidence: EvidenceEngine):
        self.views, self.snapshots = views, snapshots
        self.delta, self.evidence = delta, evidence

    def build(self, name: str, spine: List[Dict[str, Any]], views: List[Dict[str, Any]],
              as_of: float, valid_time_bound: bool = True,
              transaction_time_bound: bool = True,
              actor: str = "system",
              featureset: Optional[str] = None,
              featureset_version: Optional[int] = None) -> Dict[str, Any]:
        req = AssemblyRequest(spine, views, as_of, valid_time_bound, transaction_time_bound)
        gate = static_check(req)
        if not gate.passed:
            raise AssemblyRejected(gate.detail)

        rows = self._join(spine, views, as_of)
        report = verify_sampled(rows, lambda r: self._recompute(r, views, as_of))
        report.leakage = detect_leakage(rows)
        if report.leakage:
            report.passed = False
            report.detail += f"; suspected label leakage in {', '.join(report.leakage)}"
        return self._persist(name, rows, as_of, report, actor,
                             featureset, featureset_version)

    # ------------------------------------------------------------------- join
    def _join(self, spine: List[Dict[str, Any]], views: List[Dict[str, Any]],
              as_of: float) -> List[Dict[str, Any]]:
        rows = [dict(s) for s in spine]
        for spec in views:
            # Read at the pinned Delta version, not at whatever the namespace
            # currently holds. Without this an assembly is reproducible only for
            # as long as nobody writes to the view again.
            pin = self.views.pinned(spec["view"], spec["version"])
            frame = self.delta.read(pin["namespace"], pin["delta_version"])
            by_entity: Dict[str, List[Dict[str, Any]]] = {}
            for rec in frame.to_dict("records") if not frame.empty else []:
                by_entity.setdefault(rec[ENTITY], []).append(rec)
            for row in rows:
                pick = self.latest_admissible(by_entity.get(row[ENTITY], []),
                                              row["label_ts"], as_of) or {}
                row.update(payload(pick))
        return rows

    @staticmethod
    def latest_admissible(records: List[Dict[str, Any]], label_ts: float,
                          as_of: float) -> Optional[Dict[str, Any]]:
        """The point-in-time rule: the latest fact true by `label_ts` and known
        by `label_ts` — bounded also by the assembly's own `as_of`.

        The ingest bound used to be `as_of` alone, and `as_of` is a single
        scalar for the whole assembly. So a fact that was true before the label
        and *learned afterwards* was admitted: knowable at assembly time, not
        knowable at decision time. That is a leak in the exact sense the rule
        exists to prevent, and back-filled alignment makes it concrete — a value
        first observed in April, carried back onto a March grid point, arrives
        with April's ingest stamp and is admitted into a March training row.

        Both bounds are kept because they refuse different things. `label_ts`
        is what the model could have known when the decision was made; `as_of`
        is what the platform could have known when the set was built, so a
        restatement arriving after assembly cannot creep into a re-run.

        ## As an operator

        This is the whole point-in-time read, and it is worth naming as one:

            AsOf(R, ℓ, a) = argmax over (event_ts, ingest_ts) of
                            { r ∈ R : r.event ≤ ℓ ∧ r.ingest ≤ min(ℓ, a) }

        Four properties follow, and each is asserted in `tests/test_laws.py`
        rather than argued here:

        * **Idempotent.** Reading the result again returns it.
        * **Commutes with projection.** Reading fewer columns cannot change
          which row is admissible; the choice is made on the clocks alone.
        * **Monotone in `a`.** A later `as_of` can only *widen* the admissible
          set. Nothing that was knowable stops being knowable.
        * **Saturating at `ℓ`** — and this is the reproducibility guarantee.
          Because the ingest bound is `min(ℓ, a)`, every `a ≥ ℓ` gives the
          *same answer*. A training row assembled the day the label matured and
          the same row re-assembled a year later are identical, however many
          restatements arrived in between. Without the `min`, a re-run would
          quietly improve on the original, which is the least useful kind of
          reproducibility.
        """
        knowable_by = min(label_ts, as_of)
        eligible = [r for r in records
                    if r[VALID_TIME] <= label_ts and r[INGEST_TIME] <= knowable_by]
        if not eligible:
            return None
        return max(eligible, key=lambda r: (r[VALID_TIME], r[INGEST_TIME]))

    def _recompute(self, row: Dict[str, Any], views: List[Dict[str, Any]],
                   as_of: float) -> Dict[str, Any]:
        """Independent recomputation used by verification layer 2 — a different
        route to the same answer, so agreement means something."""
        expected: Dict[str, Any] = {}
        for spec in views:
            pin = self.views.pinned(spec["view"], spec["version"])
            frame = self.delta.as_of(pin["namespace"], row["label_ts"], as_of,
                                     pin["delta_version"])
            match = frame[frame[ENTITY] == row[ENTITY]] if not frame.empty else frame
            if not match.empty:
                expected.update(payload(match.to_dict("records")[0]))
        return expected

    # ---------------------------------------------------------------- persist
    def _persist(self, name: str, rows: List[Dict[str, Any]], as_of: float,
                 report, actor: str,
                 featureset: Optional[str] = None,
                 featureset_version: Optional[int] = None) -> Dict[str, Any]:
        table = f"snapshots/{name}"
        # The pins the assembly actually read, recorded so a replay reads the
        # same bytes rather than the same paths.
        row = {"name": name, "kind": "training", "delta_table": table,
               "delta_version": self.delta.write(table, rows, mode="overwrite"),
               "row_count": len(rows), "as_of": as_of,
               "pit_verified": int(report.passed), "pit_report": report.as_dict(),
               # Stored, not returned-and-forgotten. A fit warrant pins the
               # snapshot, so "which schema did these columns come from" has to
               # survive reading the row back rather than only being known to
               # whoever happened to call the assembler.
               "featureset": featureset, "featureset_version": featureset_version,
               "digest": canonical_digest({"name": name, "as_of": as_of, "rows": len(rows)}),
               "created_at": time.time()}
        self.snapshots.add(row)
        self.evidence.append("dataset_snapshot_created", "snapshot", row["id"],
                             {"name": name, "rows": len(rows), "pit_verified": report.passed},
                             actor=actor)
        # Storage takes 0/1 because that is what both dialects share; the caller
        # gets a bool, so no consumer has to know how a boolean is persisted.
        return {**row, "pit_verified": report.passed}
