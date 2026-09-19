"""
Engine construction and dialect selection (§14, §14.1).

``db.dialect`` in configuration decides everything: the URL, the pool, the
SQLite pragmas (WAL, busy_timeout, foreign keys) and which generated schema
file creates the database. Nothing outside this package ever sees an engine.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from maya.persistence import schema


class Database:
    """One engine, one session factory, and the SQLite write mutex."""

    def __init__(
        self,
        url: str,
        *,
        echo: bool = False,
        pool_size: int = 10,
        max_overflow: int = 10,
        busy_timeout_ms: int = 30000,
        slow_query_ms: int = 500,
    ) -> None:
        kwargs: dict[str, Any] = {"echo": echo, "future": True}
        self.is_sqlite = url.startswith("sqlite")
        if self.is_sqlite:
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": busy_timeout_ms / 1000}
        else:
            kwargs.update(pool_size=pool_size, max_overflow=max_overflow, pool_pre_ping=True)
        self.engine: Engine = create_engine(url, **kwargs)
        if self.is_sqlite:
            event.listen(self.engine, "connect", _sqlite_pragmas(busy_timeout_ms))
        _count_slow_queries(self.engine, slow_query_ms)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        from maya.persistence import search_index

        search_index.install()
        # SQLite admits one writer. Every unit of work takes this mutex so
        # concurrent requests queue here instead of failing with "database is
        # locked" (§14.1). PostgreSQL uses row and advisory locks instead.
        self.write_mutex = threading.RLock()
        # called after a commit that queued webhook deliveries (wakes the dispatcher)
        self.on_event: Any = None
        # called after a commit that changed who may do what (users, roles, groups,
        # grants, keys, or a session's revocation or second factor)
        self.on_identity_change: Any = None

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    def is_initialized(self) -> bool:
        return schema.stored_hash(self.engine) is not None

    def schema_hash(self) -> str | None:
        """The schema hash stamped when this database was created from its schema file."""
        return schema.stored_hash(self.engine)

    def init_schema(self, *, force: bool = False) -> str:
        return schema.create_all(self.engine, force=force)

    def verify_schema(self) -> str:
        return schema.verify_identity(self.engine)

    def pool_status(self) -> dict[str, int]:
        """Pool utilization for /metrics (§20). SQLite's pool is a single connection
        MAYA serialises behind its own write mutex, so it reports the mutex's shape
        rather than pretending to have a pool."""
        pool = self.engine.pool
        if self.is_sqlite:
            return {"in_use": 0, "available": 1, "overflow": 0, "size": 1, "max_overflow": 0}
        overflow = int(getattr(pool, "overflow", lambda: 0)())
        return {
            "in_use": int(getattr(pool, "checkedout", lambda: 0)()),
            "available": int(getattr(pool, "checkedin", lambda: 0)()),
            "overflow": max(0, overflow),
            "size": int(getattr(pool, "size", lambda: 0)()),
            "max_overflow": int(getattr(pool, "_max_overflow", 0)),
        }

    def dispose(self) -> None:
        self.engine.dispose()


def _sqlite_pragmas(busy_timeout_ms: int):  # type: ignore[no-untyped-def]
    def on_connect(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    return on_connect


def _count_slow_queries(engine: Engine, slow_query_ms: int) -> None:
    """Count statements, and those over the threshold, for §20's slow-query metric.

    The alternative — logging every statement over the threshold — needs ``db.echo`` and
    a human reading it. A counter says "the slow-query rate tripled at 14:05" on a graph
    beside the latency histogram, which is the question an operator actually asks. The
    statement text is never recorded: it would carry literal values, and §20 forbids
    logging data values.
    """
    from maya.observability.metrics import METRICS

    threshold = max(1, int(slow_query_ms)) / 1000.0
    # Start both series at zero: `rate(maya_db_slow_queries_total[5m])` on a series that does
    # not exist yet is an empty result, not a zero, so an alert on it never evaluates.
    METRICS.inc("maya_db_slow_queries_total", value=0.0)
    METRICS.inc("maya_db_statements_total", value=0.0)

    def before(conn: Any, *_: Any) -> None:
        conn.info["maya_started"] = time.perf_counter()

    def after(conn: Any, *_: Any) -> None:
        started = conn.info.pop("maya_started", None)
        METRICS.inc("maya_db_statements_total")
        if started is not None and time.perf_counter() - started >= threshold:
            METRICS.inc("maya_db_slow_queries_total")

    event.listen(engine, "before_cursor_execute", before)
    event.listen(engine, "after_cursor_execute", after)


def database_from_settings(settings: Any) -> Database:
    """Build the Database for the configured dialect (``maya.config.Settings``)."""
    return Database(
        settings.database_url(),
        echo=settings.bool("db.echo", False),
        pool_size=settings.int("db.postgresql.pool_size", 10),
        max_overflow=settings.int("db.postgresql.max_overflow", 10),
        busy_timeout_ms=settings.int("db.sqlite.busy_timeout_ms", 30000),
        slow_query_ms=settings.int("observability.slow_query_ms", 500),
    )
