"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The feature platform.

Most "model failures" are feature failures. A model that scored 0.47 in
development and 0.31 in production has usually not degraded; it was never
trained on the data it is now being served.

Two guarantees are enforced here rather than documented:

  * Assemblies are point-in-time correct, or they are refused (see pit.py).
  * A feature view version is PINNED by the contract. Serving reads the pinned
    version, never "latest" — the defect that adversarial review found as C-2,
    where a model bound to v7 would have been served v8 values with the contract
    digest still matching and every monitor green.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from core.evidence import EvidenceEngine
from core.features.pit import (AssemblyRejected, AssemblyRequest, PitReport, detect_leakage,
                               static_check, verify_sampled)
from db import (ContractRepository, DeltaStore, FeatureRepository, FeatureViewRepository,
                FeatureViewVersionRepository, SnapshotRepository)
from db.database import digest as canonical_digest

VALID_TIME, INGEST_TIME, ENTITY = "event_ts", "ingest_ts", "entity_id"


class FeatureError(RuntimeError):
    """A feature operation was refused. The message always says why."""


class FeatureRegistry:
    """Features, views, materialisation, contracts and PIT assembly."""

    def __init__(self, features: FeatureRepository, views: FeatureViewRepository,
                 view_versions: FeatureViewVersionRepository, contracts: ContractRepository,
                 snapshots: SnapshotRepository, delta: DeltaStore, evidence: EvidenceEngine):
        self.features, self.views, self.view_versions = features, views, view_versions
        self.contracts, self.snapshots = contracts, snapshots
        self.delta, self.evidence = delta, evidence

    # ---------------------------------------------------------------- features
    def define(self, name: str, entity: str, dtype: str, description: str, owner: str,
               business_definition: str = "", source_system: str = "",
               sensitivity: str = "internal", pii: bool = False,
               protected_basis: bool = False, proxy_risk: str = "none",
               actor: str = "system") -> Dict[str, Any]:
        if self.features.one(name=name):
            raise FeatureError(f"feature '{name}' is already defined")
        row = {"name": name, "entity": entity, "dtype": dtype, "description": description,
               "business_definition": business_definition, "owner": owner,
               "source_system": source_system, "sensitivity": sensitivity,
               "pii": int(pii), "protected_basis": int(protected_basis),
               "proxy_risk": proxy_risk, "certification": "experimental",
               "created_at": time.time()}
        self.features.add(row)
        self.evidence.append("feature_defined", "feature", row["id"],
                             {"name": name, "entity": entity}, actor=actor)
        return {**row, "pii": pii, "protected_basis": protected_basis}

    def similar(self, name: str, description: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Cheap duplicate detection. Feature sprawl is what makes a large store
        unusable, so a near-duplicate must be visible at the moment of creation."""
        words = set(description.lower().split()) | set(name.lower().replace("_", " ").split())
        scored = []
        for f in self.features.many():
            other = set(f["description"].lower().split()) | \
                    set(f["name"].lower().replace("_", " ").split())
            overlap = len(words & other) / max(len(words | other), 1)
            if overlap > 0.25:
                scored.append((overlap, f))
        return [f for _, f in sorted(scored, key=lambda t: -t[0])[:limit]]

    def certify(self, name: str, level: str = "certified") -> Dict[str, Any]:
        if level not in ("experimental", "certified", "deprecated"):
            raise FeatureError(f"unknown certification level '{level}'")
        if not self.features.one(name=name):
            raise FeatureError(f"no feature '{name}'")
        self.features.set({"certification": level}, name=name)
        return self.features.one(name=name)

    # ------------------------------------------------------------------- views
    def create_view(self, name: str, entity: str, owner: str, feature_names: List[str],
                    description: str = "", actor: str = "system") -> Dict[str, Any]:
        if self.views.one(name=name):
            raise FeatureError(f"feature view '{name}' already exists")
        missing = [f for f in feature_names if not self.features.one(name=f)]
        if missing:
            raise FeatureError(f"undefined features: {', '.join(missing)}")
        row = {"name": name, "entity": entity, "owner": owner, "description": description,
               "delta_table": f"features/{entity}/{name}", "created_at": time.time()}
        self.views.add(row)
        self.evidence.append("feature_view_created", "feature_view", row["id"],
                             {"name": name, "features": feature_names}, actor=actor)
        return row

    def materialise(self, view_name: str, rows: List[Dict[str, Any]],
                    feature_names: Optional[List[str]] = None,
                    actor: str = "system") -> Dict[str, Any]:
        """Write bitemporal rows and pin the resulting Delta version as a new
        feature view version. Each version is its own serving namespace."""
        view = self.views.one(name=view_name)
        if not view:
            raise FeatureError(f"no feature view '{view_name}'")
        for r in rows:
            for required in (ENTITY, VALID_TIME, INGEST_TIME):
                if required not in r:
                    raise FeatureError(
                        f"row is missing '{required}'; feature rows carry two clocks — "
                        f"{VALID_TIME} (when it was true) and {INGEST_TIME} (when we learned it)")
        latest = self.view_versions.first("version", desc=True, feature_view_id=view["id"])
        number = (latest["version"] + 1) if latest else 1
        table = f"{view['delta_table']}/v{number}"          # C-2: version IS the namespace
        delta_version = self.delta.write(table, rows)
        names = feature_names or sorted(
            {k for r in rows for k in r} - {ENTITY, VALID_TIME, INGEST_TIME})
        row = {"feature_view_id": view["id"], "version": number, "features": names,
               "delta_version": delta_version, "valid_time_column": VALID_TIME,
               "ingest_time_column": INGEST_TIME, "row_count": len(rows),
               "quality_report": self._quality(rows, names), "materialised_at": time.time()}
        self.view_versions.add(row)
        self.evidence.append("feature_view_materialised", "feature_view", view["id"],
                             {"version": number, "rows": len(rows), "table": table}, actor=actor)
        return row

    @staticmethod
    def _quality(rows: List[Dict[str, Any]], names: List[str]) -> Dict[str, Any]:
        vals = {n: [r.get(n) for r in rows] for n in names}
        return {n: {"null_rate": round(sum(v is None for v in vs) / max(len(vs), 1), 4),
                    "distinct": len({v for v in vs if v is not None})}
                for n, vs in vals.items()}

    def namespace(self, view_name: str, version: int) -> str:
        """The serving namespace for a pinned version. Never 'latest'."""
        view = self.views.one(name=view_name)
        if not view:
            raise FeatureError(f"no feature view '{view_name}'")
        if not self.view_versions.one(feature_view_id=view["id"], version=version):
            raise FeatureError(f"feature view '{view_name}' has no version {version}")
        return f"{view['delta_table']}/v{version}"

    # --------------------------------------------------------------- contracts
    def bind_contract(self, model_version_id: str, items: List[Dict[str, Any]],
                      actor: str = "system") -> Dict[str, Any]:
        """Pin a model version to exact feature view versions."""
        for item in items:
            view = self.views.one(name=item["view"])
            if not view:
                raise FeatureError(f"no feature view '{item['view']}'")
            if not self.view_versions.one(feature_view_id=view["id"],
                                          version=item["version"]):
                raise FeatureError(f"'{item['view']}' has no version {item['version']}")
            item["feature_view_id"] = view["id"]
            item["namespace"] = f"{view['delta_table']}/v{item['version']}"
        row = {"model_version_id": model_version_id, "digest": canonical_digest(items),
               "items": items, "created_at": time.time()}
        self.contracts.add(row)
        self.evidence.append("feature_contract_bound", "version", model_version_id,
                             {"digest": row["digest"], "views": [i["view"] for i in items]},
                             actor=actor)
        return row

    def serving_namespaces(self, model_version_id: str) -> Dict[str, str]:
        """What serving MUST read. Law L-17 compares this against what it did read."""
        contract = self.contracts.one(model_version_id=model_version_id)
        if not contract:
            raise FeatureError(f"no feature contract for version {model_version_id}")
        return {i["view"]: i["namespace"] for i in contract["items"]}

    def can_retire(self, view_name: str, version: int) -> Tuple[bool, List[str]]:
        """A namespace may only be retired when no contract still pins it."""
        view = self.views.one(name=view_name)
        if not view:
            raise FeatureError(f"no feature view '{view_name}'")
        consumers = self.contracts.consumers_of(view["id"], version)
        return not consumers, consumers

    # ---------------------------------------------------------------- assembly
    def build_training_set(self, name: str, spine: List[Dict[str, Any]],
                           views: List[Dict[str, Any]], as_of: float,
                           valid_time_bound: bool = True, transaction_time_bound: bool = True,
                           actor: str = "system") -> Dict[str, Any]:
        """Assemble a point-in-time-correct training set, or refuse."""
        req = AssemblyRequest(spine, views, as_of, valid_time_bound, transaction_time_bound)
        gate = static_check(req)
        if not gate.passed:
            raise AssemblyRejected(gate.detail)

        rows = [dict(s) for s in spine]
        for spec in views:
            ns = self.namespace(spec["view"], spec["version"])
            frame = self.delta.read(ns)
            by_entity: Dict[str, List[Dict[str, Any]]] = {}
            for rec in frame.to_dict("records") if not frame.empty else []:
                by_entity.setdefault(rec[ENTITY], []).append(rec)
            for row in rows:
                pick = self._latest_admissible(by_entity.get(row[ENTITY], []),
                                               row["label_ts"], as_of) or {}
                row.update({k: v for k, v in pick.items()
                            if k not in (ENTITY, VALID_TIME, INGEST_TIME)})

        report = verify_sampled(rows, lambda r: self._recompute(r, views, as_of))
        report.leakage = detect_leakage(rows)
        if report.leakage:
            report.passed = False
            report.detail += f"; suspected label leakage in {', '.join(report.leakage)}"

        table = f"snapshots/{name}"
        delta_version = self.delta.write(table, rows, mode="overwrite")
        row = {"name": name, "kind": "training", "delta_table": table,
               "delta_version": delta_version, "row_count": len(rows), "as_of": as_of,
               "pit_verified": int(report.passed), "pit_report": report.as_dict(),
               "digest": canonical_digest({"name": name, "as_of": as_of, "rows": len(rows)}),
               "created_at": time.time()}
        self.snapshots.add(row)
        self.evidence.append("dataset_snapshot_created", "snapshot", row["id"],
                             {"name": name, "rows": len(rows), "pit_verified": report.passed},
                             actor=actor)
        # Storage takes 0/1 because that is what both dialects share; the caller
        # gets a bool, so no consumer has to know how a boolean is persisted.
        return {**row, "pit_verified": report.passed}

    def _recompute(self, row: Dict[str, Any], views: List[Dict[str, Any]],
                   as_of: float) -> Dict[str, Any]:
        """Independent recomputation used by layer 2 — deliberately not sharing
        the assembly path, so a bug there does not hide behind itself."""
        expected: Dict[str, Any] = {}
        for spec in views:
            frame = self.delta.as_of(self.namespace(spec["view"], spec["version"]),
                                     row["label_ts"], as_of)
            match = frame[frame[ENTITY] == row[ENTITY]] if not frame.empty else frame
            if match.empty:
                continue
            expected.update({k: v for k, v in match.to_dict("records")[0].items()
                             if k not in (ENTITY, VALID_TIME, INGEST_TIME)})
        return expected

    @staticmethod
    def _latest_admissible(records: List[Dict[str, Any]], label_ts: float,
                           as_of: float) -> Optional[Dict[str, Any]]:
        """The point-in-time rule: latest fact true by label_ts AND known by as_of."""
        eligible = [r for r in records
                    if r[VALID_TIME] <= label_ts and r[INGEST_TIME] <= as_of]
        if not eligible:
            return None
        return max(eligible, key=lambda r: (r[VALID_TIME], r[INGEST_TIME]))
