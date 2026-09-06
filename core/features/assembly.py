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

from dataclasses import dataclass

from core.evidence import EvidenceEngine
from core.features.common import ENTITY, INGEST_TIME, VALID_TIME, payload
from core.features.pit import (AssemblyRejected, AssemblyRequest, PitReport, screen_leakage,
                               static_check, verify_sampled)
from core.features.views import ViewManager
from db import DeltaStore, SnapshotRepository
from db.database import digest as canonical_digest


@dataclass(frozen=True)
class Column:
    """One column of the assembled frame: where it is read from, and what it is
    called once it arrives.

    This type exists because the assembler used to take a list of *views* and
    copy every column of each of them into the row by name, last write winning.
    A featureset's whole purpose is to say which feature fills which slot — the
    binding was published, signed into the fit warrant and rendered on four
    screens, and then discarded one call before it was used. A frame assembled
    that way is not the frame the featureset describes, and nothing downstream
    can tell.

    `slot` and `feature` differ whenever a featureset names a slot for something
    other than the feature filling it, which is the ordinary case in a set
    composed from parents.
    """
    slot: str
    feature: str
    view: str
    view_version: int

    @property
    def source(self) -> tuple:
        return (self.view, self.view_version)


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
              featureset_version: Optional[int] = None,
              columns: Optional[List[Column]] = None,
              label_slot: Optional[str] = None) -> Dict[str, Any]:
        """Assemble, verify, and persist — or refuse.

        `columns` is the authority on what the frame contains when the caller
        has one, which a featureset always does. Without it the columns are
        derived from the named views, which is the honest reading of a request
        that named views and nothing else.
        """
        req = AssemblyRequest(spine, views, as_of, valid_time_bound, transaction_time_bound)
        gate = static_check(req)
        if not gate.passed:
            raise AssemblyRejected(gate.detail)

        plan = columns if columns is not None else self._columns_of(views)
        self._refuse_ambiguous(plan)
        rows = self._join(spine, plan, as_of)
        report = verify_sampled(rows, lambda r: self._recompute(r, plan, as_of))
        self._screen_for_leakage(report, rows, label_slot)
        return self._persist(name, rows, as_of, report, actor,
                             featureset, featureset_version)

    @staticmethod
    def _screen_for_leakage(report: "PitReport", rows: List[Dict[str, Any]],
                            label_slot: Optional[str]) -> None:
        """Run the leakage screen under the column the label actually occupies.

        It used to call `detect_leakage(rows)`, which looks for a column named
        `label` — and on the featureset path the label sits under whatever slot
        the author named it, `defaulted_12m` or `charged_off`. `detect_leakage`
        returns `[]` the moment that key is missing, so on the path the platform
        recommends the screen never ran. Every snapshot came back with no
        suspected leakage, which is indistinguishable from a clean one.

        Two things follow. The slot travels here from the featureset plan; and
        when there is no label column to screen against, the report SAYS the
        screen did not run rather than reporting an empty list of suspects.
        """
        key = label_slot or "label"
        report.label_column = key if rows and key in rows[0] else None
        report.leakage, why_not = screen_leakage(rows, key)
        report.leakage_screened = why_not is None
        if why_not is not None:
            report.detail += f"; the leakage screen did not run: {why_not}"
            return
        if report.leakage:
            report.passed = False
            report.detail += f"; suspected label leakage in {', '.join(report.leakage)}"

    # ---------------------------------------------------------------- columns
    def _columns_of(self, views: List[Dict[str, Any]]) -> List[Column]:
        """The columns a views-only request asks for.

        A caller who names views and no bindings is asking for everything those
        views carry, under its own name — so slot and feature are the same
        thing. Deriving the list explicitly rather than copying whatever turns
        up means the collision check below applies to this path too.
        """
        plan: List[Column] = []
        for spec in views:
            pin = self.views.pinned(spec["view"], spec["version"])
            for name in pin["features"]:
                plan.append(Column(name, name, spec["view"], spec["version"]))
        return plan

    @staticmethod
    def _refuse_ambiguous(columns: List[Column]) -> None:
        """Two sources for one output column is not a preference, it is a
        question nobody answered.

        The old join resolved this by letting whichever view happened to be
        processed last win — silently, and differently depending on sort order.
        A frame whose contents depend on iteration order is not reproducible,
        which is the one property this whole module exists to provide.
        """
        seen: Dict[str, set] = {}
        for column in columns:
            seen.setdefault(column.slot, set()).add((column.feature, *column.source))
        clashing = sorted(slot for slot, sources in seen.items() if len(sources) > 1)
        if clashing:
            raise AssemblyRejected(
                "two different sources are mapped onto the same column, so the "
                f"frame would depend on which was read last: {', '.join(clashing)}. "
                "Bind each slot to one feature in one view version.")

    # ------------------------------------------------------------------- join
    def _join(self, spine: List[Dict[str, Any]], columns: List[Column],
              as_of: float) -> List[Dict[str, Any]]:
        """Read each view once, and take from it only the columns asked for.

        Grouped by source so a view holding six features is read once rather
        than six times; selected by name so a view holding six features
        contributes only the ones bound to a slot.
        """
        rows = [dict(s) for s in spine]
        by_source: Dict[tuple, List[Column]] = {}
        for column in columns:
            by_source.setdefault(column.source, []).append(column)

        for (view, version), wanted in by_source.items():
            # Read at the pinned Delta version, not at whatever the namespace
            # currently holds. Without this an assembly is reproducible only for
            # as long as nobody writes to the view again.
            pin = self.views.pinned(view, version)
            frame = self.delta.read(pin["namespace"], pin["delta_version"])
            by_entity: Dict[str, List[Dict[str, Any]]] = {}
            for rec in frame.to_dict("records") if not frame.empty else []:
                by_entity.setdefault(rec[ENTITY], []).append(rec)
            for row in rows:
                pick = self.latest_admissible(by_entity.get(row[ENTITY], []),
                                              row["label_ts"], as_of) or {}
                values = payload(pick)
                for column in wanted:
                    # `.get`, so a bound feature absent from this version of the
                    # view arrives as a null rather than as a missing key. A
                    # missing key would make the frame ragged and the mistake
                    # would surface as a KeyError somewhere else entirely.
                    row[column.slot] = values.get(column.feature)
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

    def _recompute(self, row: Dict[str, Any], columns: List[Column],
                   as_of: float) -> Dict[str, Any]:
        """Independent recomputation used by verification layer 2.

        Two things make it independent, and both are load-bearing.

        **A different point-in-time route.** `_join` bulk-reads a view and picks
        the admissible record in Python; this asks the store for the as-of frame
        directly. That is the check on the clock arithmetic, and it is subtle
        enough to have been wrong once already: this bounded the ingest clock by
        `as_of` alone while `latest_admissible` bounds it by
        `min(label_ts, as_of)`, so the two disagreed whenever a set was assembled
        after its labels matured — the ordinary case — and the verifier reported
        a mismatch on a *correct* assembly. A false positive in the control that
        verifies a control is worse than no control: it teaches whoever reads it
        to discount the report.

        **A different resolution order.** Every column is resolved on its own,
        from its own binding, one read per column. `_join` groups columns by
        source and reads each view once, which is right for cost and is exactly
        the step that can go wrong — a mis-grouped source, or two columns of one
        view landing in the wrong slots. Grouping here as well would reproduce
        that mistake faithfully and agree with it.

        That second property is why this method exists at all. It previously
        walked the same list of views the same way and did the same
        `update(payload(...))`, so it agreed with the assembler by construction:
        a binding the assembler ignored was a binding the verifier could not
        notice, and `pit_verified: true` could not fail on it.
        """
        expected: Dict[str, Any] = {}
        knowable_by = min(row["label_ts"], as_of)
        for column in columns:
            pin = self.views.pinned(column.view, column.view_version)
            frame = self.delta.as_of(pin["namespace"], row["label_ts"],
                                     knowable_by, pin["delta_version"])
            match = frame[frame[ENTITY] == row[ENTITY]] if not frame.empty else frame
            if match.empty:
                continue
            expected[column.slot] = payload(
                match.to_dict("records")[0]).get(column.feature)
        return expected


    @staticmethod
    def content_digest(rows: List[Dict[str, Any]]) -> str:
        """A hash of what is in the frame.

        This was computed from the snapshot's NAME, its `as_of` and its ROW
        COUNT. Nothing about the contents entered it, so every 60-row set built
        under one name at one instant had one digest — a developer reproduced
        the digest published in the shipped tutorial on completely different
        data, then produced a second, different 60-row set and got it a third
        time.

        This value is what a fit warrant pins in order to say *this model was
        trained on this data*. Reproducibility, replay and the training record
        all rest on it, and it identified nothing.

        Rows are canonicalised before hashing: each row's keys are sorted, and
        the rows themselves are sorted by their own serialisation. Two
        assemblies that produced the same facts in a different order are the
        same dataset and must digest alike, or a replay that legitimately
        reorders reports tampering.
        """
        canonical = sorted(
            [{k: r[k] for k in sorted(r)} for r in rows],
            key=lambda r: repr(sorted(r.items())))
        return canonical_digest({"rows": canonical})

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
               "digest": self.content_digest(rows),
               "created_at": time.time()}
        self.snapshots.add(row)
        self.evidence.append("dataset_snapshot_created", "snapshot", row["id"],
                             {"name": name, "rows": len(rows), "pit_verified": report.passed},
                             actor=actor)
        # Storage takes 0/1 because that is what both dialects share; the caller
        # gets a bool, so no consumer has to know how a boolean is persisted.
        return {**row, "pit_verified": report.passed}
