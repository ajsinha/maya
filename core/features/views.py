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

import time
from typing import Any, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.features.catalogue import FeatureCatalogue
from core.features.common import ENTITY, INGEST_TIME, RESERVED, VALID_TIME, FeatureError
from db import DeltaStore, FeatureViewRepository, FeatureViewVersionRepository


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
        delta_version = self.delta.write(self._path(view, number), rows)
        names = feature_names or sorted({k for r in rows for k in r} - set(RESERVED))
        row = {"feature_view_id": view["id"], "version": number, "features": names,
               "delta_version": delta_version, "valid_time_column": VALID_TIME,
               "ingest_time_column": INGEST_TIME, "row_count": len(rows),
               "quality_report": self.quality(rows, names), "materialised_at": time.time()}
        self.view_versions.add(row)
        self.evidence.append("feature_view_materialised", "feature_view", view["id"],
                             {"version": number, "rows": len(rows),
                              "table": self._path(view, number)}, actor=actor)
        return row

    @staticmethod
    def _check_clocks(rows: List[Dict[str, Any]]) -> None:
        for r in rows:
            for required in (ENTITY, VALID_TIME, INGEST_TIME):
                if required not in r:
                    raise FeatureError(
                        f"row is missing '{required}'; feature rows carry two clocks — "
                        f"{VALID_TIME} (when it was true) and {INGEST_TIME} (when we learned it)")

    @staticmethod
    def quality(rows: List[Dict[str, Any]], names: List[str]) -> Dict[str, Any]:
        vals = {n: [r.get(n) for r in rows] for n in names}
        return {n: {"null_rate": round(sum(v is None for v in vs) / max(len(vs), 1), 4),
                    "distinct": len({v for v in vs if v is not None})}
                for n, vs in vals.items()}

    def versions_of(self, view_name: str) -> List[Dict[str, Any]]:
        """Every materialised version of a view, oldest first."""
        return self.view_versions.many(feature_view_id=self.require(view_name)["id"])

    # ------------------------------------------------------------- namespacing
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
        return {"namespace": self._path(view, version),
                "delta_version": row["delta_version"],
                "row_count": row["row_count"],
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
