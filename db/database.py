"""
MAYA — database connection and schema application.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from sqlalchemy.engine import Engine

from core.log import get_logger

logger = get_logger(__name__)

# The connection a transaction() is running on, if any. A ContextVar
# rather than a thread local so it is correct under async as well.
_CONNECTION: ContextVar = ContextVar("maya_db_connection", default=None)
SCHEMA_DIR = Path(__file__).resolve().parent / "schema"


def new_id() -> str:
    """Sortable, non-guessable identifier: millisecond prefix plus randomness."""
    return f"{int(time.time() * 1000):012x}{secrets.token_hex(8)}"


def digest(payload: Any) -> str:
    """Stable SHA-256 over a canonical JSON encoding."""
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class DeltaPaths:
    """Where the Delta tables live. Held here so that no service above the
    persistence package needs to know a filesystem path."""

    AREAS = ("features", "snapshots", "telemetry", "monitoring")

    def __init__(self, root: Path, retention_days: int = 400, **areas: Path):
        self.root, self.retention_days = Path(root), retention_days
        for area in self.AREAS:
            setattr(self, area, Path(areas.get(area) or self.root / area))

    @classmethod
    def from_config(cls, cfg) -> "DeltaPaths":
        root = Path(cfg.get("data.delta.dir", "./data/delta"))
        return cls(root, cfg.get_int("data.delta.retention_days", 400),
                   **{a: cfg.get(f"data.delta.{a}") for a in cls.AREAS})

    def ensure(self) -> "DeltaPaths":
        for p in (self.root, *(getattr(self, a) for a in self.AREAS)):
            p.mkdir(parents=True, exist_ok=True)
        return self


class Database:
    """Owns the engine and applies the schema for the configured dialect."""

    def __init__(self, url: str = "sqlite:///data/sqlite/maya.db", echo: bool = False):
        self.url = url
        options: Dict[str, Any] = {}
        if url.startswith("sqlite:///") and ":memory:" not in url:
            Path(url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
        if ":memory:" in url:
            # An in-memory SQLite database belongs to its CONNECTION, so the
            # default pool hands every caller a different, empty database. That
            # is not a smaller version of production -- it is a topology in
            # which two callers can never contend for anything, and it is why a
            # read-then-write race in the evidence chain survived a suite of
            # eighteen hundred tests.
            #
            # StaticPool keeps one connection, so `:memory:` means ONE database
            # the way a file or a Postgres server does. Tests that need genuine
            # parallel connections use a file-backed URL; see
            # tests/test_concurrency.py.
            options = {"poolclass": StaticPool,
                       "connect_args": {"check_same_thread": False}}
        self.engine: Engine = create_engine(url, echo=echo, future=True, **options)
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

    # ------------------------------------------------------------- transaction
    @contextmanager
    def transaction(self):
        """Run several statements on one connection, committed or rolled back
        together.

        Without this there was no way to make a read and a write atomic, because
        every statement opened its own connection: `execute` began a transaction
        and ended it, and `query` opened a second one that could not see inside
        the first. Anything shaped read-then-write was therefore a race, and the
        evidence chain is exactly that shape -- read the head, insert head+1.

        Re-entrant. A nested call joins the transaction already running rather
        than opening a second one and deadlocking against it, so a service can
        wrap a whole governance act without knowing what its collaborators do.
        """
        existing = _CONNECTION.get()
        if existing is not None:
            yield existing
            return
        with self.engine.begin() as conn:
            token = _CONNECTION.set(conn)
            try:
                yield conn
            finally:
                _CONNECTION.reset(token)

    # ------------------------------------------------------------------ access
    def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        conn = _CONNECTION.get()
        if conn is not None:
            return conn.execute(text(sql), params or {}).rowcount
        with self.engine.begin() as conn:
            return conn.execute(text(sql), params or {}).rowcount

    def query(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        conn = _CONNECTION.get()
        if conn is not None:
            return [dict(r) for r in conn.execute(text(sql), params or {}).mappings()]
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
