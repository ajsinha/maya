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

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from maya.persistence.engine import Database
from maya.persistence.repositories import repository_class


IDENTITY_TABLES = {"users", "roles", "user_roles", "groups", "group_members", "group_roles",
                   "grants", "api_keys", "namespaces"}
SESSION_FIELDS = ("revoked_at", "mfa_state")


def _identity_changed(session: Any, _ctx: Any, _instances: Any) -> None:
    """Mark the transaction when it changes access; a session merely seen is not a change."""
    from sqlalchemy import inspect
    for obj in (*session.new, *session.dirty, *session.deleted):
        table = getattr(obj, "__tablename__", "")
        if table in IDENTITY_TABLES or (table == "sessions" and (
                obj in session.new or obj in session.deleted
                or any(inspect(obj).attrs[f].history.has_changes() for f in SESSION_FIELDS))):
            session.info["identity_changed"] = True
            return


event.listen(Session, "before_flush", _identity_changed)


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
                changed = self.session.info.pop("identity_changed", False)
                self.session.commit()
                changed = changed or self.session.info.pop("identity_changed", False)
                if changed and self.db.on_identity_change is not None:
                    self.db.on_identity_change()
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
        from maya.observability.tracing import current_trace_id
        safe = json.loads(json.dumps(detail or {}, default=str))
        entry = {
            "actor": self.actor or "system", "principal_type": principal_type,
            "channel": channel, "action": action, "object_type": object_type,
            "object_ref": object_ref, "detail": safe,
            "request_id": request_id or current_trace_id(), "ip": ip,
        }
        if durable:
            self._durable.append(entry)
            return
        self.repo("audit_events").append(entry)
        self._emit(entry)

    def _emit(self, entry: dict[str, Any]) -> None:
        """Write the event this audit entry announces, and queue its deliveries (§18.1)."""
        from maya.observability.events import event_type, matches
        from maya.observability.metrics import METRICS
        from maya.persistence.types import utcnow
        etype = event_type(entry)
        if etype is None:
            return
        event = self.repo("events").add({
            "at": utcnow(), "type": etype, "object_type": entry["object_type"],
            "object_ref": entry["object_ref"], "actor": entry["actor"],
            "trace_id": entry["request_id"], "payload": entry["detail"]})
        METRICS.inc("maya_events_total", {"type": etype})
        queued = False
        for hook in self.repo("webhooks").list(active=True):
            if matches(hook["event_types"], etype):
                self.repo("webhook_deliveries").add({
                    "webhook_id": hook["id"], "event_seq": event["seq"], "state": "pending",
                    "next_attempt_at": utcnow()})
                queued = True
        if queued and self.db.on_event is not None:
            self.after_commit(self.db.on_event)
