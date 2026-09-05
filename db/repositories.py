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
                 "protected_basis", "pit_verified", "passed", "blocking", "matured", "sampled", "ok", "text_indexed",
                 "ephemeral")


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


class ModelEdgeRepository(Repository):
    TABLE, ORDER = "model_edge", "created_at"


class EvidenceCheckpointRepository(Repository):
    TABLE, ORDER = "evidence_checkpoint", "seq"


class EvidenceRepository(Repository):
    TABLE, JSON, ORDER = "evidence_node", ("payload", "parents"), "seq"

    def since(self, seq: int) -> List[Dict[str, Any]]:
        """Nodes after this sequence, filtered in SQL.

        Filtering in Python after `many()` reads the whole table, so the
        incremental verification cost the same as the full walk and the probe
        got no faster -- the hashing was never the expensive part; the read
        was.
        """
        return [self._decode(r) for r in self.db.query(
            f"SELECT * FROM {self.TABLE} WHERE seq > :s ORDER BY seq",
            {"s": seq})]


class RiskRepository(Repository):
    TABLE, JSON, ORDER = "risk_assessment", ("facts", "required_controls"), "assessed_at"


class WarrantRepository(Repository):
    TABLE = "warrant"


class FeatureRepository(Repository):
    TABLE, ORDER = "feature", "name"
    JSON = ("shape", "components", "composes", "operations", "defaults")


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


class DerivedFeatureRepository(Repository):
    """Definitions of features computed from other features."""
    TABLE, JSON, ORDER = "derived_feature", ("inputs",), "created_at"

    def current(self, name: str):
        """The newest definition of a name. A definition is corrected by adding
        a version, never by editing one somebody already trained against."""
        return self.first("definition_version", desc=True, name=name)

    def depending_on(self, feature_name: str):
        """Every derived definition that reads this feature, at any version.
        Answering it is what makes retiring a primitive a governed act."""
        return [d for d in self.many() if feature_name in (d["inputs"] or [])]


class FeaturesetRepository(Repository):
    TABLE, ORDER = "featureset", "created_at"
    JSON = ("slots", "composes", "operations", "defaults")


class FeaturesetVersionRepository(Repository):
    TABLE, JSON = "featureset_version", ("bindings", "label_binding")

    def latest(self, featureset_id: str):
        return self.first("version", desc=True, featureset_id=featureset_id)

    def consumers_of_view(self, view_id: str, version: int) -> List[str]:
        """Featureset versions pinning this view version. The retirement guard
        now walks contracts -> featuresets -> views rather than scanning."""
        return [v["id"] for v in self.many()
                if any(b.get("feature_view_id") == view_id and b.get("view_version") == version
                       for b in (v["bindings"] or {}).values())]


class ParameterSetRepository(Repository):
    """Inhabitants of P. A fit produces one of these, not a model version."""
    TABLE = "parameter_set"
    JSON = ("values_inline", "diagnostics")
    ORDER = "created_at"

    def for_version(self, model_version_id: str) -> List[Dict[str, Any]]:
        return self.many(model_version_id=model_version_id)

    def approved_for(self, model_version_id: str) -> List[Dict[str, Any]]:
        return [p for p in self.for_version(model_version_id) if p["state"] == "approved"]

    def next_version(self, model_version_id: str, name: str) -> int:
        prior = self.first("version", desc=True,
                           model_version_id=model_version_id, name=name)
        return (prior["version"] + 1) if prior else 1


class PolicyRuleRepository(Repository):
    """Versioned gates, with the cases each one carries."""
    TABLE, ORDER = "policy_rule", "created_at"
    JSON = ("cases", "facts_read", "test_report")


class WarrantProfileRepository(Repository):
    """Named, versioned request defaults, ordered so the most specific is last."""
    TABLE, ORDER = "warrant_profile", "specificity"
    JSON = ("when_facts", "defaults")

    def next_version(self, name: str) -> int:
        prior = self.first("version", desc=True, name=name)
        return (prior["version"] + 1) if prior else 1


class RiskAppetiteRepository(Repository):
    """Declared limits, versioned per metric and scope."""
    TABLE, ORDER = "risk_appetite", "created_at"
    JSON = ("scope",)

    def next_version(self, metric: str, scope_key: str) -> int:
        prior = self.first("version", desc=True, metric=metric,
                           scope_key=scope_key)
        return (prior["version"] + 1) if prior else 1


class BoardPackRepository(Repository):
    """Packs as they were read, never recomputed."""
    TABLE, ORDER = "board_pack", "as_at"
    JSON = ("scope", "indicators", "exceptions", "unmeasured")


class NotificationRepository(Repository):
    """Deliveries attempted, and what came of them."""
    TABLE, ORDER = "notification", "sent_at"


class TelemetryBatchRepository(Repository):
    """Which batches have been taken in, so redelivery is a no-op."""
    TABLE, ORDER = "telemetry_batch", "at"


class VersionApprovalRepository(Repository):
    """Approvals that need more than one signature."""
    TABLE, JSON, ORDER = "version_approval", ("required_roles",), "opened_at"

    def open_for(self, model_version_id: str):
        return self.one(model_version_id=model_version_id, status="open")

    def history(self, model_version_id: str):
        return self.many(model_version_id=model_version_id)


class VersionApprovalSignatureRepository(Repository):
    TABLE, ORDER = "version_approval_signature", "signed_at"


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


class FindingActionRepository(Repository):
    """What happened to a finding between raising it and closing it.

    Append-only. Nothing here is ever updated, because the point of it is that
    the acts cannot be made to say something other than what happened — the
    workflow's state is derived from these rows rather than stored beside them.
    """
    TABLE, ORDER = "finding_action", "acted_at"

    def for_finding(self, finding_id: str) -> List[Dict[str, Any]]:
        """In the order they happened, which is the order they must be read in:
        an acknowledgement before a handover is not an acknowledgement now."""
        return self.many(finding_id=finding_id, order="acted_at")


class PrincipalRepository(Repository):
    TABLE, ORDER = "principal", "username"
    JSON = ("roles", "legal_entities", "domains")


class AmendmentRepository(Repository):
    TABLE, JSON, ORDER = "amendment", ("scope",), "opened_at"


class AttestationRepository(Repository):
    TABLE, JSON, ORDER = "attestation", ("required_roles",), "opened_at"


class SignatureRepository(Repository):
    TABLE, ORDER = "attestation_signature", "signed_at"


class MonitorRepository(Repository):
    TABLE, ORDER = "monitor", "created_at"
    JSON = ("threshold", "slice", "reference")


class ObservationRepository(Repository):
    TABLE, ORDER = "observation", "computed_at"


class BreachRepository(Repository):
    TABLE, ORDER = "breach", "opened_at"

    def open_for(self, model_id: str) -> List[Dict[str, Any]]:
        return [self._decode(r) for r in self.db.query(
            f"SELECT * FROM {self.TABLE} WHERE model_id = :m AND status = 'open' "
            "ORDER BY opened_at", {"m": model_id})]


class DocumentRepository(Repository):
    TABLE, ORDER = "document", "compiled_at"
    JSON = ("sections", "citations", "coverage", "subjects")

    def about(self, subject_type: str, subject_id: str) -> List[Dict[str, Any]]:
        """Compiled documents about one thing, latest first.

        The dossier's read. `subjects` is the list a document was compiled FROM,
        which is a different question and stays where it is: this one is what
        the document is *about*.
        """
        rows = self.many(subject_type=subject_type, subject_id=subject_id)
        return sorted(rows, key=lambda r: r.get("compiled_at") or 0, reverse=True)


class OverlayRepository(Repository):
    TABLE, JSON, ORDER = "overlay", ("basis",), "created_at"


class MeasurementRepository(Repository):
    TABLE, ORDER = "overlay_measurement", "measured_at"


class CapabilityRepository(Repository):
    TABLE, ORDER = "ai_capability", "created_at"


class GenerationRepository(Repository):
    TABLE, ORDER = "ai_generation", "created_at"
    JSON = ("output", "claims", "rejected_claims", "oracle_verdict")


class ImportRepository(Repository):
    TABLE, ORDER = "baseline_import", "imported_at"


class DebtRepository(Repository):
    TABLE, ORDER = "compliance_debt", "raised_at"

    def open_for(self, model_id: str) -> List[Dict[str, Any]]:
        return [self._decode(r) for r in self.db.query(
            f"SELECT * FROM {self.TABLE} WHERE model_id = :m AND status = 'open' "
            "ORDER BY expires_at", {"m": model_id})]


class ScheduledRunRepository(Repository):
    TABLE, JSON, ORDER = "scheduled_run", ("outcome",), "ran_at"


class AttachmentRepository(Repository):
    TABLE, ORDER = "attachment", "attached_at"

    def for_version(self, version_id: str) -> List[Dict[str, Any]]:
        return [self._decode(r) for r in self.db.query(
            f"SELECT * FROM {self.TABLE} WHERE model_version_id = :v "
            "AND state <> 'superseded' ORDER BY attached_at", {"v": version_id})]

    def current_for_model(self, model_id: str) -> List[Dict[str, Any]]:
        return [self._decode(r) for r in self.db.query(
            f"SELECT * FROM {self.TABLE} WHERE model_id = :m "
            "AND state <> 'superseded' ORDER BY attached_at", {"m": model_id})]
