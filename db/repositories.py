"""
MAYA — repositories.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The only interface the rest of MAYA has to storage. Services receive these and
never see SQL, a connection, a dialect or a JSON encoding.

JSON documents are held as TEXT so both dialects behave identically; encoding
and decoding happen here so that no caller has to remember to do it.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from db.database import Database, new_id


def _dump(row: Dict[str, Any], fields: tuple) -> Dict[str, Any]:
    out = dict(row)
    for f in fields:
        if f in out and not isinstance(out[f], str):
            out[f] = json.dumps(out[f], default=str)
    return out


def _load(row: Optional[Dict[str, Any]], fields: tuple) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    out = dict(row)
    for f in fields:
        if isinstance(out.get(f), str):
            try:
                out[f] = json.loads(out[f])
            except (ValueError, TypeError):
                pass
    for f in ("deterministic", "contains_personal_data", "revoked"):
        if f in out and out[f] is not None:
            out[f] = bool(out[f])
    return out


class _Repo:
    TABLE = ""
    JSON_FIELDS: tuple = ()

    def __init__(self, db: Database):
        self.db = db

    def _rows(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return [_load(r, self.JSON_FIELDS) for r in self.db.query(sql, params)]

    def _row(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        return _load(self.db.query_one(sql, params), self.JSON_FIELDS)

    def add(self, row: Dict[str, Any]) -> Dict[str, Any]:
        row.setdefault("id", new_id())
        self.db.insert(self.TABLE, _dump(row, self.JSON_FIELDS))
        return row


class ModelRepository(_Repo):
    TABLE, JSON_FIELDS = "model", ("attributes",)

    def by_urn(self, urn: str) -> Optional[Dict[str, Any]]:
        return self._row("SELECT * FROM model WHERE urn = :u", {"u": urn})

    def list(self, domain: Optional[str] = None, tier: Optional[int] = None) -> List[Dict[str, Any]]:
        sql, p = "SELECT * FROM model WHERE 1=1", {}
        if domain:
            sql, p["d"] = sql + " AND domain = :d", domain
        if tier is not None:
            sql, p["t"] = sql + " AND tier = :t", tier
        return self._rows(sql + " ORDER BY urn", p)

    def set_tier(self, model_id: str, tier: int) -> None:
        self.db.update("model", "id = :i", {"i": model_id}, {"tier": tier})

    def set_status(self, model_id: str, status: str) -> None:
        self.db.update("model", "id = :i", {"i": model_id}, {"status": status})


class VersionRepository(_Repo):
    TABLE = "model_version"
    JSON_FIELDS = ("manifest", "input_schema", "output_schema", "contract")

    def by_id(self, version_id: str) -> Optional[Dict[str, Any]]:
        return self._row("SELECT * FROM model_version WHERE id = :i", {"i": version_id})

    def by_semver(self, model_id: str, semver: str) -> Optional[Dict[str, Any]]:
        return self._row("SELECT * FROM model_version WHERE model_id = :m AND semver = :s",
                         {"m": model_id, "s": semver})

    def for_model(self, model_id: str) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM model_version WHERE model_id = :m ORDER BY created_at",
                          {"m": model_id})

    def set_status(self, version_id: str, status: str) -> None:
        """The only mutable column on a version; excluded from manifest_digest."""
        self.db.update("model_version", "id = :i", {"i": version_id}, {"status": status})


class AliasRepository(_Repo):
    TABLE, JSON_FIELDS = "alias", ()
    HISTORY_JSON = ("refinement", "variance")

    def current(self, model_id: str, environment: str, name: str) -> Optional[Dict[str, Any]]:
        return self._row("SELECT * FROM alias WHERE model_id = :m AND environment = :e "
                         "AND name = :n", {"m": model_id, "e": environment, "n": name})

    def point(self, model_id: str, environment: str, name: str, version_id: str,
              moved_at: float, moved_by: str) -> None:
        if self.current(model_id, environment, name):
            self.db.update("alias", "model_id = :m AND environment = :e AND name = :n",
                           {"m": model_id, "e": environment, "n": name},
                           {"version_id": version_id, "moved_at": moved_at, "moved_by": moved_by})
        else:
            self.add({"model_id": model_id, "environment": environment, "name": name,
                      "version_id": version_id, "moved_at": moved_at, "moved_by": moved_by})

    def record_move(self, row: Dict[str, Any]) -> Dict[str, Any]:
        row.setdefault("id", new_id())
        self.db.insert("alias_history", _dump(row, self.HISTORY_JSON))
        return row

    def history(self, model_id: str) -> List[Dict[str, Any]]:
        return [_load(r, self.HISTORY_JSON) for r in self.db.query(
            "SELECT * FROM alias_history WHERE model_id = :m ORDER BY moved_at", {"m": model_id})]


class EvidenceRepository(_Repo):
    TABLE, JSON_FIELDS = "evidence_node", ("payload", "parents")

    def head(self) -> Optional[Dict[str, Any]]:
        return self._row("SELECT * FROM evidence_node ORDER BY seq DESC LIMIT 1")

    def all_ordered(self) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM evidence_node ORDER BY seq")

    def for_subject(self, subject_id: str) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM evidence_node WHERE subject_id = :s ORDER BY seq",
                          {"s": subject_id})

    def remove(self, seq: int) -> int:
        """Retention and tests only. The application role has no DELETE grant."""
        return self.db.execute("DELETE FROM evidence_node WHERE seq = :s", {"s": seq})

    def corrupt(self, seq: int, content_hash: str) -> int:
        """Test-only helper used to prove the chain detects tampering."""
        return self.db.update("evidence_node", "seq = :s", {"s": seq},
                              {"content_hash": content_hash})


class RiskRepository(_Repo):
    TABLE, JSON_FIELDS = "risk_assessment", ("facts", "required_controls")

    def for_model(self, model_id: str) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM risk_assessment WHERE model_id = :m "
                          "ORDER BY assessed_at DESC", {"m": model_id})

    def latest(self, model_id: str) -> Optional[Dict[str, Any]]:
        rows = self.for_model(model_id)
        return rows[0] if rows else None


class HookRepository(_Repo):
    TABLE, JSON_FIELDS = "hook", ()

    def by_id(self, hook_id: str) -> Optional[Dict[str, Any]]:
        return self._row("SELECT * FROM hook WHERE id = :i", {"i": hook_id})

    def grant_for(self, model_id: str, environment: str, principal: str) -> Optional[Dict[str, Any]]:
        return self._row("SELECT * FROM hook WHERE model_id = :m AND environment = :e "
                         "AND principal = :p", {"m": model_id, "e": environment, "p": principal})

    def for_model(self, model_id: str) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM hook WHERE model_id = :m", {"m": model_id})

    def revoke(self, hook_id: str, reason: str, epoch: int) -> None:
        self.db.update("hook", "id = :i", {"i": hook_id},
                       {"revoked": 1, "revoke_reason": reason, "epoch": epoch})
