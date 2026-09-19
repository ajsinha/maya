"""
Unit of work (§14): owns the transaction boundary.

Services write ``with uow_factory(actor) as uow:`` and call repositories via
``uow.repo("features")``. The transaction commits on a clean exit and rolls
back on any exception; services never commit inside a loop. On SQLite the
unit of work also holds the process-wide write mutex (§14.1).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import text

from maya.persistence.engine import Database
from maya.persistence.repositories import repository_class


class UnitOfWork:
    """One transaction, many repositories."""

    def __init__(self, db: Database, actor: str | None = None) -> None:
        self.db = db
        self.actor = actor
        self._repos: dict[str, Any] = {}
        self.session: Any = None
        self._after_commit: list[Any] = []
        self._durable: list[dict[str, Any]] = []

    def __enter__(self) -> "UnitOfWork":
        if self.db.is_sqlite:
            self.db.write_mutex.acquire()
        self.session = self.db.session_factory()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        try:
            if exc_type is None:
                for entry in self._durable:
                    self.repo("audit_events").append(entry)
                self.session.commit()
                for fn in self._after_commit:
                    fn()
            else:
                self.session.rollback()
                self._write_durable()
        finally:
            self.session.close()
            if self.db.is_sqlite:
                self.db.write_mutex.release()

    def _write_durable(self) -> None:
        """Refusals are evidence too: durable audit entries survive the rollback."""
        if not self._durable:
            return
        session = self.db.session_factory()
        try:
            repo = repository_class("audit_events")(session, self.actor)
            for entry in self._durable:
                repo.append(entry)
            session.commit()
        finally:
            session.close()

    def repo(self, name: str) -> Any:
        if name not in self._repos:
            self._repos[name] = repository_class(name)(self.session, self.actor)
        return self._repos[name]

    def after_commit(self, fn: Any) -> None:
        """Run ``fn`` once the transaction has committed (e.g. wake a worker)."""
        self._after_commit.append(fn)

    def lock(self, name: str) -> None:
        """A named, transaction-scoped lock (§15.3). SQLite holds the mutex already."""
        if self.db.dialect == "postgresql":
            key = int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big", signed=True)
            self.session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})

    def audit(self, action: str, *, object_type: str | None = None,
              object_ref: str | None = None, detail: dict[str, Any] | None = None,
              principal_type: str = "user", channel: str = "api",
              request_id: str | None = None, ip: str | None = None,
              durable: bool = False) -> None:
        """Append to the hash-chained audit log inside this transaction (§19).

        ``durable`` entries (refusals, denials) are also written if the transaction
        rolls back — a refusal usually *is* the exception that rolls it back.
        """
        safe = json.loads(json.dumps(detail or {}, default=str))
        entry = {
            "actor": self.actor or "system", "principal_type": principal_type,
            "channel": channel, "action": action, "object_type": object_type,
            "object_ref": object_ref, "detail": safe, "request_id": request_id, "ip": ip,
        }
        if durable:
            self._durable.append(entry)
            return
        self.repo("audit_events").append(entry)
