"""
Engine construction and dialect selection (§14, §14.1).

``db.dialect`` in configuration decides everything: the URL, the pool, the
SQLite pragmas (WAL, busy_timeout, foreign keys) and which generated schema
file creates the database. Nothing outside this package ever sees an engine.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import threading
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from maya.persistence import schema


class Database:
    """One engine, one session factory, and the SQLite write mutex."""

    def __init__(self, url: str, *, echo: bool = False, pool_size: int = 10,
                 max_overflow: int = 10, busy_timeout_ms: int = 30000) -> None:
        kwargs: dict[str, Any] = {"echo": echo, "future": True}
        self.is_sqlite = url.startswith("sqlite")
        if self.is_sqlite:
            kwargs["connect_args"] = {"check_same_thread": False,
                                      "timeout": busy_timeout_ms / 1000}
        else:
            kwargs.update(pool_size=pool_size, max_overflow=max_overflow, pool_pre_ping=True)
        self.engine: Engine = create_engine(url, **kwargs)
        if self.is_sqlite:
            event.listen(self.engine, "connect", _sqlite_pragmas(busy_timeout_ms))
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        # SQLite admits one writer. Every unit of work takes this mutex so
        # concurrent requests queue here instead of failing with "database is
        # locked" (§14.1). PostgreSQL uses row and advisory locks instead.
        self.write_mutex = threading.RLock()
        # called after a commit that queued webhook deliveries (wakes the dispatcher)
        self.on_event: Any = None

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    def is_initialized(self) -> bool:
        return schema.stored_hash(self.engine) is not None

    def init_schema(self, *, force: bool = False) -> str:
        return schema.create_all(self.engine, force=force)

    def verify_schema(self) -> str:
        return schema.verify_identity(self.engine)

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


def database_from_settings(settings: Any) -> Database:
    """Build the Database for the configured dialect (``maya.config.Settings``)."""
    return Database(
        settings.database_url(),
        echo=settings.bool("db.echo", False),
        pool_size=settings.int("db.postgresql.pool_size", 10),
        max_overflow=settings.int("db.postgresql.max_overflow", 10),
        busy_timeout_ms=settings.int("db.sqlite.busy_timeout_ms", 30000),
    )
