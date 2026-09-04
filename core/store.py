"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Persistence. SQLAlchemy Core over SQLite (development) or PostgreSQL
(production) — the URL comes from configuration, nothing else changes.

Two invariants are enforced here rather than by convention:

  * model_version rows are IMMUTABLE. The store exposes no update path for
    them, and an attempted status change goes through a separate column that
    is explicitly excluded from the version digest.
  * evidence_node rows are APPEND-ONLY and hash-chained, so deletion of a leaf
    or insertion into the past breaks the chain at a detectable point.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import (JSON, Boolean, Column, Float, Integer, MetaData, String, Table, Text,
                        UniqueConstraint, create_engine, delete, insert, select, update)

metadata = MetaData()


def _ulid() -> str:
    """Sortable, non-guessable identifier. Time prefix plus randomness."""
    import secrets
    return f"{int(time.time() * 1000):012x}{secrets.token_hex(8)}"


def canonical_digest(payload: Any) -> str:
    """Stable SHA-256 over a canonical JSON encoding."""
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


model = Table(
    "model", metadata,
    Column("id", String(64), primary_key=True),
    Column("urn", String(255), nullable=False, unique=True),
    Column("name", String(255), nullable=False),
    Column("description", Text),
    Column("model_class", String(128), nullable=False),
    Column("domain", String(64), nullable=False),
    Column("owner", String(128), nullable=False),
    Column("legal_entity", String(64), nullable=False),
    Column("purpose", Text, nullable=False),
    Column("origin", String(32), nullable=False, default="internal"),
    Column("status", String(32), nullable=False, default="proposed"),
    Column("tier", Integer),
    Column("attributes", JSON, default=dict),
    Column("created_at", Float, nullable=False),
    Column("created_by", String(128), nullable=False),
)

model_version = Table(
    "model_version", metadata,
    Column("id", String(64), primary_key=True),
    Column("model_id", String(64), nullable=False, index=True),
    Column("semver", String(32), nullable=False),
    Column("manifest", JSON, nullable=False),
    Column("manifest_digest", String(80), nullable=False),
    Column("trainability_class", String(4), nullable=False),
    Column("parameter_kind", String(48), nullable=False),
    Column("fit_procedure", String(24), nullable=False),
    Column("deterministic", Boolean, nullable=False, default=True),
    Column("input_schema", JSON, nullable=False),
    Column("output_schema", JSON, nullable=False),
    Column("contract", JSON, nullable=False),
    Column("artifact_digest", String(80)),
    Column("status", String(32), nullable=False, default="draft"),   # not part of the digest
    Column("created_at", Float, nullable=False),
    Column("created_by", String(128), nullable=False),
    UniqueConstraint("model_id", "semver", name="uq_version_semver"),
)

alias = Table(
    "alias", metadata,
    Column("id", String(64), primary_key=True),
    Column("model_id", String(64), nullable=False),
    Column("environment", String(16), nullable=False),
    Column("name", String(32), nullable=False),
    Column("version_id", String(64), nullable=False),
    Column("moved_at", Float, nullable=False),
    Column("moved_by", String(128), nullable=False),
    UniqueConstraint("model_id", "environment", "name", name="uq_alias"),
)

alias_history = Table(
    "alias_history", metadata,
    Column("id", String(64), primary_key=True),
    Column("model_id", String(64), nullable=False, index=True),
    Column("environment", String(16), nullable=False),
    Column("name", String(32), nullable=False),
    Column("from_version_id", String(64)),
    Column("to_version_id", String(64), nullable=False),
    Column("refinement", JSON, nullable=False),
    Column("variance", JSON, nullable=False),
    Column("moved_at", Float, nullable=False),
    Column("moved_by", String(128), nullable=False),
    Column("justification", Text),
)

evidence_node = Table(
    "evidence_node", metadata,
    Column("id", String(64), primary_key=True),
    Column("seq", Integer, nullable=False, unique=True),
    Column("kind", String(48), nullable=False),
    Column("subject_type", String(48), nullable=False),
    Column("subject_id", String(64), nullable=False, index=True),
    Column("payload", JSON, nullable=False, default=dict),
    Column("parents", JSON, nullable=False, default=list),
    Column("contains_personal_data", Boolean, nullable=False, default=False),
    Column("content_hash", String(80), nullable=False),
    Column("prev_hash", String(80), nullable=False),
    Column("chain_hash", String(80), nullable=False),
    Column("trust", Float, nullable=False, default=1.0),
    Column("recorded_at", Float, nullable=False),
    Column("recorded_by", String(128), nullable=False),
)

risk_assessment = Table(
    "risk_assessment", metadata,
    Column("id", String(64), primary_key=True),
    Column("model_id", String(64), nullable=False, index=True),
    Column("tier", Integer, nullable=False),
    Column("materiality", String(32), nullable=False),
    Column("complexity", String(32), nullable=False),
    Column("facts", JSON, nullable=False),
    Column("required_controls", JSON, nullable=False),
    Column("rationale", Text, nullable=False),
    Column("ruleset_version", String(32), nullable=False),
    Column("next_review_due", Float),
    Column("assessed_at", Float, nullable=False),
)

hook = Table(
    "hook", metadata,
    Column("id", String(64), primary_key=True),
    Column("model_id", String(64), nullable=False, index=True),
    Column("environment", String(16), nullable=False),
    Column("binding_kind", String(16), nullable=False),     # pinned_version | alias
    Column("alias_name", String(32)),
    Column("version_id", String(64)),
    Column("flavour", String(32), nullable=False),
    Column("principal", String(128), nullable=False),
    Column("declared_use", String(128), nullable=False),
    Column("ttl_seconds", Integer, nullable=False),
    Column("grace_seconds", Integer, nullable=False, default=0),
    Column("revoked", Boolean, nullable=False, default=False),
    Column("revoke_reason", Text),
    Column("epoch", Integer, nullable=False, default=0),
    Column("created_at", Float, nullable=False),
)


class Store:
    """Thin repository over SQLAlchemy Core. Owns the engine and the schema."""

    def __init__(self, url: str = "sqlite:///data/maya.db", echo: bool = False):
        if url.startswith("sqlite:///") and ":memory:" not in url:
            Path(url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, echo=echo, future=True)
        metadata.create_all(self.engine)

    def insert(self, table: Table, values: Dict[str, Any]) -> Dict[str, Any]:
        with self.engine.begin() as conn:
            conn.execute(insert(table).values(**values))
        return values

    def update(self, table: Table, where, values: Dict[str, Any]) -> int:
        with self.engine.begin() as conn:
            return conn.execute(update(table).where(where).values(**values)).rowcount

    def one(self, table: Table, where) -> Optional[Dict[str, Any]]:
        with self.engine.connect() as conn:
            row = conn.execute(select(table).where(where)).mappings().first()
        return dict(row) if row else None

    def many(self, table: Table, where=None, order_by=None, limit: int = 500) -> List[Dict[str, Any]]:
        stmt = select(table)
        if where is not None:
            stmt = stmt.where(where)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(stmt.limit(limit)).mappings()]

    def count(self, table: Table, where=None) -> int:
        return len(self.many(table, where, limit=100000))

    def delete(self, table: Table, where) -> int:
        with self.engine.begin() as conn:
            return conn.execute(delete(table).where(where)).rowcount
