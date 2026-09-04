"""
MAYA — repositories.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The only interface the rest of MAYA has to storage. Services receive these and
never see SQL, a connection, a dialect or a JSON encoding.

Each repository is a table name plus the columns that hold JSON or booleans;
the queries are generated. Hand-writing `SELECT * FROM t WHERE col = :v` forty
times taught nobody anything and was where the encoding rules drifted.

Booleans are stored as 0/1 because that is the representation both dialects
share, and are returned as bools, so no caller has to know that.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.log import get_logger, swallowed
from db.database import Database, new_id

logger = get_logger(__name__)

_BOOL_COLUMNS = ("deterministic", "contains_personal_data", "revoked", "pii",
                 "protected_basis", "pit_verified", "passed", "blocking")


class Repository:
    """A table, with JSON and boolean columns declared rather than handled."""

    TABLE: str = ""
    JSON: Tuple[str, ...] = ()
    ORDER: Optional[str] = None

    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------- encoding
    def _encode(self, row: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(row)
        for f in self.JSON:
            if f in out and not isinstance(out[f], str):
                out[f] = json.dumps(out[f], default=str)
        for f in _BOOL_COLUMNS:
            if isinstance(out.get(f), bool):
                out[f] = int(out[f])
        return out

    def _decode(self, row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        out = dict(row)
        for f in self.JSON:
            if isinstance(out.get(f), str):
                try:
                    out[f] = json.loads(out[f])
                except ValueError as exc:
                    swallowed(logger, exc, f"{self.TABLE}.{f} is not valid JSON",
                              detail=f"id={out.get('id')}; left as text")
        for f in _BOOL_COLUMNS:
            if out.get(f) is not None:
                out[f] = bool(out[f])
        return out

    # -------------------------------------------------------------- queries
    @staticmethod
    def _where(filters: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        if not filters:
            return "1=1", {}
        return (" AND ".join(f"{k} = :{k}" for k in filters), dict(filters))

    def one(self, **filters) -> Optional[Dict[str, Any]]:
        clause, params = self._where(filters)
        return self._decode(self.db.query_one(
            f"SELECT * FROM {self.TABLE} WHERE {clause} LIMIT 1", params))

    def many(self, order: Optional[str] = None, desc: bool = False,
             limit: Optional[int] = None, **filters) -> List[Dict[str, Any]]:
        clause, params = self._where({k: v for k, v in filters.items() if v is not None})
        sql = f"SELECT * FROM {self.TABLE} WHERE {clause}"
        by = order or self.ORDER
        if by:
            sql += f" ORDER BY {by}" + (" DESC" if desc else "")
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [self._decode(r) for r in self.db.query(sql, params)]

    def first(self, order: str, desc: bool = False, **filters) -> Optional[Dict[str, Any]]:
        rows = self.many(order=order, desc=desc, limit=1, **filters)
        return rows[0] if rows else None

    def add(self, row: Dict[str, Any]) -> Dict[str, Any]:
        row.setdefault("id", new_id())
        self.db.insert(self.TABLE, self._encode(row))
        return row

    def set(self, values: Dict[str, Any], **filters) -> int:
        clause, params = self._where(filters)
        return self.db.update(self.TABLE, clause, params, self._encode(values))

    def remove(self, **filters) -> int:
        clause, params = self._where(filters)
        return self.db.execute(f"DELETE FROM {self.TABLE} WHERE {clause}", params)


class ModelRepository(Repository):
    TABLE, JSON, ORDER = "model", ("attributes",), "urn"


class VersionRepository(Repository):
    TABLE, ORDER = "model_version", "created_at"
    JSON = ("manifest", "input_schema", "output_schema", "contract")


class AliasRepository(Repository):
    TABLE = "alias"

    def point(self, model_id: str, environment: str, name: str, version_id: str,
              moved_at: float, moved_by: str) -> None:
        keys = {"model_id": model_id, "environment": environment, "name": name}
        values = {"version_id": version_id, "moved_at": moved_at, "moved_by": moved_by}
        if self.one(**keys):
            self.set(values, **keys)
        else:
            self.add({**keys, **values})


class AliasHistoryRepository(Repository):
    TABLE, JSON, ORDER = "alias_history", ("refinement", "variance"), "moved_at"


class EvidenceRepository(Repository):
    TABLE, JSON, ORDER = "evidence_node", ("payload", "parents"), "seq"


class RiskRepository(Repository):
    TABLE, JSON, ORDER = "risk_assessment", ("facts", "required_controls"), "assessed_at"


class HookRepository(Repository):
    TABLE = "hook"


class FeatureRepository(Repository):
    TABLE, ORDER = "feature", "name"


class FeatureViewRepository(Repository):
    TABLE, ORDER = "feature_view", "name"


class FeatureViewVersionRepository(Repository):
    TABLE, JSON, ORDER = ("feature_view_version", ("features", "quality_report"), "version")


class ContractRepository(Repository):
    TABLE, JSON = "feature_contract", ("items",)

    def consumers_of(self, view_id: str, version: int) -> List[str]:
        """Which model versions pin this feature view version. Answering this is
        what makes retiring a namespace a governed act rather than a guess."""
        return [c["model_version_id"] for c in self.many()
                if any(i.get("feature_view_id") == view_id and i.get("version") == version
                       for i in c["items"])]


class SnapshotRepository(Repository):
    TABLE, JSON, ORDER = "dataset_snapshot", ("pit_report",), "created_at"


class ValidationRepository(Repository):
    TABLE, ORDER = "validation", "started_at"
    JSON = ("scope", "plan", "validators", "independence", "conditions")


class TestResultRepository(Repository):
    TABLE, ORDER = "test_result", "computed_at"
    JSON = ("parameters", "slice", "threshold")


class FindingRepository(Repository):
    TABLE, ORDER = "finding", "raised_at"
    JSON = ("closure_evidence",)

    def open_for(self, model_id: str, blocking: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Open findings for a model, optionally only the blocking ones.

        A dedicated method rather than a keyword filter because "open" is
        `status <> 'closed'`, which the generated equality queries cannot say.
        """
        sql = f"SELECT * FROM {self.TABLE} WHERE model_id = :m AND status <> 'closed'"
        params: Dict[str, Any] = {"m": model_id}
        if blocking is not None:
            sql += " AND blocking = :b"
            params["b"] = int(blocking)
        return [self._decode(r) for r in self.db.query(sql + " ORDER BY raised_at", params)]
