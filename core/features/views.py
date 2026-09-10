"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Feature views and their materialised versions.

The load-bearing rule lives here: **a version IS a serving namespace**. Writing
v2 of a view does not touch what v1 serves, because they are different Delta
paths. Adversarial review found the alternative (one table, "latest" semantics)
as finding C-2 — a model pinned to v7 would quietly have been served v8 values
with its contract digest still matching and every monitor green.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.features.catalogue import FeatureCatalogue
from core.log import get_logger, swallowed
from core.features.assertions import check as check_assertions
from core.features.common import ENTITY, INGEST_TIME, RESERVED, VALID_TIME, FeatureError
from db import DeltaStore, FeatureViewRepository, FeatureViewVersionRepository


logger = get_logger(__name__)


class ViewManager:
    """Creates views, materialises versions, and resolves serving namespaces."""

    def __init__(self, views: FeatureViewRepository,
                 view_versions: FeatureViewVersionRepository,
                 catalogue: FeatureCatalogue, delta: DeltaStore, evidence: EvidenceEngine):
        self.views, self.view_versions = views, view_versions
        self.catalogue, self.delta, self.evidence = catalogue, delta, evidence

    # ------------------------------------------------------------------ views
    def create(self, name: str, entity: str, owner: str, feature_names: List[str],
               description: str = "", actor: str = "system") -> Dict[str, Any]:
        if self.views.one(name=name):
            raise FeatureError(f"feature view '{name}' already exists")
        if missing := self.catalogue.missing(feature_names):
            raise FeatureError(f"undefined features: {', '.join(missing)}")
        row = {"name": name, "entity": entity, "owner": owner, "description": description,
               "delta_table": f"features/{entity}/{name}", "created_at": time.time()}
        with self.evidence.recording():
            self.views.add(row)
            self.evidence.append("feature_view_created", "feature_view", row["id"],
                                 {"name": name, "features": feature_names}, actor=actor)
        return row

    def require(self, name: str) -> Dict[str, Any]:
        view = self.views.one(name=name)
        if not view:
            raise FeatureError(f"no feature view '{name}'")
        return view

    # ---------------------------------------------------------- materialisation
    def materialise(self, view_name: str, rows: List[Dict[str, Any]],
                    feature_names: Optional[List[str]] = None,
                    actor: str = "system") -> Dict[str, Any]:
        """Write bitemporal rows and pin the resulting Delta version as a new
        feature view version, in its own namespace."""
        view = self.require(view_name)
        self._check_clocks(rows)
        latest = self.view_versions.first("version", desc=True, feature_view_id=view["id"])
        number = (latest["version"] + 1) if latest else 1
        target = self._path(view, number)
        # An ORPHAN from an attempt that died between the two writes.
        #
        # Delta is written first and the control-plane row second, and they
        # cannot share a transaction — one is a table on a volume, the other is
        # a row in the register. If the row write fails, the Delta table for
        # version N exists and nothing records it; `number` is recomputed from
        # `view_versions` next time and comes back as N again, and
        # `DeltaStore.write` defaults to `mode="append"` — so the abandoned rows
        # merge into what is then recorded as version N, and `row_count`
        # disagrees with the table it describes.
        #
        # Overwriting is safe precisely because the orphan was never recorded:
        # no version row, no contract and no warrant can be pinned to it. Said
        # out loud, because rows disappearing silently is the other way to get
        # this wrong.
        if self.delta.exists(target):
            logger.warning(
                "'%s' already holds data that no feature view version records "
                "— an earlier materialisation wrote Delta and did not record "
                "it. Overwriting: nothing can be pinned to a version that was "
                "never registered.", target)
            delta_version = self.delta.write(target, rows, mode="overwrite",
                                             dtypes=self._dtypes(view))
        else:
            delta_version = self.delta.write(target, rows,
                                             dtypes=self._dtypes(view))
        names = feature_names or sorted({k for r in rows for k in r} - set(RESERVED))
        # The declared assertions, checked against what is being recorded. A
        # failing load is QUARANTINED rather than refused: the rows are
        # written, the version is recorded and the report says which assertion
        # failed and by how much, because deleting the evidence of a bad load
        # is how nobody finds out what arrived. What quarantine buys is that
        # nothing may pin it.
        report = check_assertions(rows, self._assertions_for(names))
        row = {"feature_view_id": view["id"], "version": number, "features": names,
               "delta_version": delta_version, "valid_time_column": VALID_TIME,
               "ingest_time_column": INGEST_TIME, "row_count": len(rows),
               "quarantined": not report["passed"],
               "assertion_report": report,
               "quality_report": self.quality(rows, names), "materialised_at": time.time()}
        with self.evidence.recording():
            self.view_versions.add(row)
            self.evidence.append("feature_view_materialised", "feature_view", view["id"],
                                 {"version": number, "rows": len(rows),
                                  "table": target,
                                  "assertions_checked": report["checked"],
                                  "quarantined": not report["passed"],
                                  "failed": report["failed"]}, actor=actor)
            if not report["passed"]:
                logger.warning(
                    "feature view '%s' version %s is QUARANTINED: %s",
                    view_name, number, report["detail"])
        return row

    @staticmethod
    def _check_clocks(rows: List[Dict[str, Any]]) -> None:
        for r in rows:
            for required in (ENTITY, VALID_TIME, INGEST_TIME):
                if required not in r:
                    raise FeatureError(
                        f"row is missing '{required}'; feature rows carry two clocks — "
                        f"{VALID_TIME} (when it was true) and {INGEST_TIME} (when we learned it)")

    def _assertions_for(self, names: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Each named feature's declared assertions, if it has any.

        Read from the FEATURE rather than the view: a null rate unacceptable in
        one table is unacceptable in the next, and an assertion attached to a
        view would have to be restated every time somebody built another one.
        """
        out: Dict[str, List[Dict[str, Any]]] = {}
        for name in names:
            row = self.catalogue.get(name)
            if row and row.get("assertions"):
                out[name] = list(row["assertions"])
        return out

    @staticmethod
    def quality(rows: List[Dict[str, Any]], names: List[str]) -> Dict[str, Any]:
        """Null rate and distinct count per column.

        `distinct` counts by CONTENT rather than by hash, because a feature may
        be shaped: `shape: [12]` for a balance history, `shape: [3, 3]` for a
        correlation matrix. Both arrive as lists, and a list is unhashable — so
        `len({v for v in vs})` raised TypeError and materialising any array
        feature answered 500. The register accepts shaped features, the
        contract algebra reasons about their shape, and this one line meant no
        data could ever be loaded into one.
        """
        def distinct(values: List[Any]) -> int:
            seen: List[Any] = []
            for value in values:
                if value is None:
                    continue
                try:
                    if value not in seen:
                        seen.append(value)
                except (TypeError, ValueError) as exc:
                    # A value that will not compare to the ones already seen.
                    # Counted as distinct, which over-counts rather than
                    # under-counts — a quality report that hides variety is the
                    # more dangerous direction.
                    swallowed(logger, exc, "counted distinct feature values",
                              detail="a value would not compare; counted as "
                                     "distinct rather than dropped",
                              level=logging.DEBUG)
                    seen.append(value)
            return len(seen)

        vals = {n: [r.get(n) for r in rows] for n in names}
        return {n: {"null_rate": round(sum(v is None for v in vs) / max(len(vs), 1), 4),
                    "distinct": distinct(vs)}
                for n, vs in vals.items()}

    def versions_of(self, view_name: str) -> List[Dict[str, Any]]:
        """Every materialised version of a view, oldest first."""
        return self.view_versions.many(feature_view_id=self.require(view_name)["id"])

    # ------------------------------------------------------------- namespacing
    def _dtypes(self, view: Dict[str, Any]) -> Dict[str, str]:
        """Each feature's declared dtype, for the columns that arrive empty.

        Arrow infers a type from the values, and cannot when every value in a
        column is null — which happens legitimately: a feature with nothing in
        this window, or a restatement that withdraws a figure. MAYA knows the
        answer and simply was not passing it, so Delta stored a null-typed
        column that reads back as nothing and Iceberg refused the write.
        """
        out: Dict[str, str] = {}
        for name in (view.get("features") or []):
            feature = self.catalogue.get(name)
            if feature and feature.get("dtype"):
                out[name] = feature["dtype"]
        return out

    @staticmethod
    def _path(view: Dict[str, Any], version: int) -> str:
        return f"{view['delta_table']}/v{version}"

    def namespace(self, view_name: str, version: int) -> str:
        """The serving namespace for a pinned version. Never 'latest'."""
        view = self.require(view_name)
        if not self.view_versions.one(feature_view_id=view["id"], version=version):
            raise FeatureError(f"feature view '{view_name}' has no version {version}")
        return self._path(view, version)

    def namespace_of(self, view: Dict[str, Any], version: int) -> str:
        """Namespace for a view row already in hand, without a second lookup."""
        return self._path(view, version)

    # ------------------------------------------------------------ time travel
    def pinned(self, view_name: str, version: int) -> Dict[str, Any]:
        """The namespace AND the Delta version it was materialised at.

        A namespace is a path; a path is a mutable thing. Two writes to the same
        namespace produce two Delta versions, and a read that names only the path
        gets whichever is current. For serving that is correct — the namespace is
        the contract. For *reproducing* an assembly it is not: the whole point of
        a snapshot is that re-running it returns what it returned before.
        """
        view = self.require(view_name)
        row = self.view_versions.one(feature_view_id=view["id"], version=version)
        if row is None:
            raise FeatureError(f"feature view '{view_name}' has no version {version}")
        # The single choke point for pinning, which is why the quarantine check
        # is here rather than in each caller: every path that binds a version
        # to a featureset, a contract or a snapshot comes through this method,
        # and a check in three of the four would make the assertion advisory in
        # the fourth.
        if row.get("quarantined"):
            report = row.get("assertion_report") or {}
            raise FeatureError(
                f"feature view '{view_name}' version {version} is QUARANTINED: "
                f"{report.get('detail', 'a declared assertion failed')}. The "
                f"rows are recorded and readable — the load is evidence of "
                f"what arrived — but nothing may pin a version whose declared "
                f"assertions did not hold, because a featureset that could "
                f"bind one would make every assertion advisory. Load again, or "
                f"change the assertion if it was wrong")
        return {"namespace": self._path(view, version),
                "delta_version": row["delta_version"],
                "row_count": row["row_count"],
                # Which columns this version actually carries. The assembler
                # needs it to select a named feature out of a view rather than
                # copying every column the view happens to hold.
                "features": list(row["features"] or []),
                "materialised_at": row["materialised_at"]}

    def restated(self, view_name: str, version: int) -> Dict[str, Any]:
        """Whether the namespace has moved since this version was pinned.

        A namespace whose current Delta version is ahead of the pinned one has
        been written to again. That is not automatically wrong — a correction to
        a stale row is a legitimate act — but it means a read without the pin
        returns something other than what was assembled, and anybody comparing
        two runs needs to know which case they are in.
        """
        pin = self.pinned(view_name, version)
        current = self.delta.version(pin["namespace"])
        moved = current > pin["delta_version"]
        return {**pin, "current_delta_version": current, "restated": moved,
                "detail": (f"{pin['namespace']} has been written to since it was "
                           f"pinned: v{pin['delta_version']} then, v{current} now"
                           if moved else
                           f"{pin['namespace']} is unchanged since it was pinned")}
