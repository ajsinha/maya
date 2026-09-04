"""
MAYA — database connection and schema application.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)
SCHEMA_DIR = Path(__file__).resolve().parent / "schema"


def new_id() -> str:
    """Sortable, non-guessable identifier: millisecond prefix plus randomness."""
    return f"{int(time.time() * 1000):012x}{secrets.token_hex(8)}"


def digest(payload: Any) -> str:
    """Stable SHA-256 over a canonical JSON encoding."""
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class DeltaPaths:
    """Where the Delta Lake tables live. Held here so that no service above the
    persistence package needs to know a filesystem path."""
    root: Path
    features: Path
    snapshots: Path
    telemetry: Path
    monitoring: Path
    retention_days: int = 400

    @classmethod
    def from_config(cls, cfg) -> "DeltaPaths":
        root = Path(cfg.get("data.delta.dir", "./data/delta"))
        return cls(root=root,
                   features=Path(cfg.get("data.delta.features", root / "features")),
                   snapshots=Path(cfg.get("data.delta.snapshots", root / "snapshots")),
                   telemetry=Path(cfg.get("data.delta.telemetry", root / "telemetry")),
                   monitoring=Path(cfg.get("data.delta.monitoring", root / "monitoring")),
                   retention_days=cfg.get_int("data.delta.retention_days", 400))

    def ensure(self) -> "DeltaPaths":
        for p in (self.root, self.features, self.snapshots, self.telemetry, self.monitoring):
            p.mkdir(parents=True, exist_ok=True)
        return self


class Database:
    """Owns the engine and applies the schema for the configured dialect."""

    def __init__(self, url: str = "sqlite:///data/sqlite/maya.db", echo: bool = False):
        self.url = url
        if url.startswith("sqlite:///") and ":memory:" not in url:
            Path(url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine(url, echo=echo, future=True)
        self.dialect = self.engine.dialect.name
        self.apply_schema()

    def schema_file(self) -> Path:
        """PostgreSQL and SQLite have hand-written schemas; no migrations exist."""
        return SCHEMA_DIR / ("postgres.sql" if self.dialect.startswith("postgres")
                             else "sqlite.sql")

    @staticmethod
    def _statements(sql: str) -> List[str]:
        """Strip comments BEFORE splitting on ';' -- prose in a comment may
        contain a semicolon, and a naive split then produces invalid SQL."""
        body = "\n".join(line for line in sql.splitlines()
                         if not line.lstrip().startswith("--"))
        return [s.strip() for s in body.split(";") if s.strip()]

    def apply_schema(self) -> None:
        path = self.schema_file()
        with self.engine.begin() as conn:
            for stmt in self._statements(path.read_text()):
                conn.execute(text(stmt))
        logger.info("schema applied from %s (%s)", path.name, self.dialect)

    # ------------------------------------------------------------------ access
    def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        with self.engine.begin() as conn:
            return conn.execute(text(sql), params or {}).rowcount

    def query(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(text(sql), params or {}).mappings()]

    def query_one(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def insert(self, table: str, row: Dict[str, Any]) -> Dict[str, Any]:
        cols = ", ".join(row)
        binds = ", ".join(f":{c}" for c in row)
        self.execute(f"INSERT INTO {table} ({cols}) VALUES ({binds})", row)
        return row

    def update(self, table: str, where: str, params: Dict[str, Any],
               values: Dict[str, Any]) -> int:
        sets = ", ".join(f"{k} = :set_{k}" for k in values)
        merged = {**params, **{f"set_{k}": v for k, v in values.items()}}
        return self.execute(f"UPDATE {table} SET {sets} WHERE {where}", merged)
