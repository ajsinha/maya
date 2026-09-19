"""
Repositories whose behaviour is more than CRUD: the hash-chained audit log,
the job queue (``SKIP LOCKED`` on PostgreSQL), lineage traversal and the
catalog search index.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any

from sqlalchemy import or_, select, text

from maya.persistence.models import catalog, identity, operations, registry
from maya.persistence.repositories.base import Repository
from maya.persistence.types import utcnow

GENESIS = "0" * 64


def audit_digest(prev_hash: str, entry: dict[str, Any]) -> str:
    """The chain link: sha256 over the previous hash and the entry's content."""
    body = {
        k: entry.get(k)
        for k in (
            "at",
            "actor",
            "principal_type",
            "channel",
            "action",
            "object_type",
            "object_ref",
            "detail",
            "request_id",
            "ip",
        )
    }
    at = body["at"]
    if isinstance(at, dt.datetime):
        body["at"] = at.astimezone(dt.timezone.utc).isoformat()
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + payload).encode("utf-8")).hexdigest()


class AuditRepository(Repository[operations.AuditEvent]):
    model = operations.AuditEvent
    label = "audit event"

    def append(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Append one entry, linked to the previous head of the chain."""
        if self.session.get_bind().dialect.name == "postgresql":
            self.session.execute(text("SELECT pg_advisory_xact_lock(727274)"))
        last = self.session.scalars(
            select(operations.AuditEvent).order_by(operations.AuditEvent.seq.desc()).limit(1)
        ).first()
        prev = last.hash if last else GENESIS
        entry = dict(entry, at=entry.get("at") or utcnow().replace(microsecond=0))
        entry["prev_hash"] = prev
        entry["hash"] = audit_digest(prev, entry)
        obj = operations.AuditEvent(**entry)
        self.session.add(obj)
        self.session.flush()
        from maya.observability.metrics import METRICS

        METRICS.inc("maya_audit_events_total")
        return obj.to_dict()

    def verify_chain(self) -> dict[str, Any]:
        """Walk the chain and report the first broken link, if any."""
        prev = GENESIS
        count = 0
        for obj in self.session.scalars(
            select(operations.AuditEvent).order_by(operations.AuditEvent.seq)
        ):
            row = obj.to_dict()
            if row["prev_hash"] != prev or audit_digest(prev, row) != row["hash"]:
                return {"ok": False, "checked": count, "broken_at": row["seq"]}
            prev = row["hash"]
            count += 1
        return {"ok": True, "checked": count, "head": prev}


class JobRepository(Repository[operations.Job]):
    model = operations.Job
    label = "job"

    def claim_next(self, worker: str) -> dict[str, Any] | None:
        """Take the oldest runnable job. PostgreSQL skips rows other workers hold."""
        now = utcnow()
        stmt = (
            select(operations.Job)
            .where(operations.Job.state == "queued")
            .where(or_(operations.Job.run_after.is_(None), operations.Job.run_after <= now))
            .order_by(operations.Job.created_at)
            .limit(1)
        )
        if self.session.get_bind().dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        job = self.session.scalars(stmt).first()
        if job is None:
            return None
        job.state, job.started_at, job.worker = "running", now, worker
        job.attempts = (job.attempts or 0) + 1
        self.session.flush()
        return job.to_dict()


class LineageRepository(Repository[operations.LineageEdge]):
    model = operations.LineageEdge
    label = "lineage edge"

    def link(self, src: str, dst: str, edge_type: str, label: str | None = None) -> None:
        if self.find_one(src_ref=src, dst_ref=dst, edge_type=edge_type) is None:
            self.add({"src_ref": src, "dst_ref": dst, "edge_type": edge_type, "label": label})

    def walk(self, root: str, *, direction: str = "both", depth: int = 3) -> list[dict[str, Any]]:
        """Breadth-first edges around ``root``. Upstream follows edges into a node."""
        seen: set[str] = {root}
        frontier = [root]
        edges: dict[str, dict[str, Any]] = {}
        for _ in range(max(depth, 0)):
            nxt: list[str] = []
            for ref in frontier:
                found: list[dict[str, Any]] = []
                if direction in ("upstream", "both"):
                    found += self.list(dst_ref=ref)
                if direction in ("downstream", "both"):
                    found += self.list(src_ref=ref)
                for e in found:
                    edges[e["id"]] = e
                    for other in (e["src_ref"], e["dst_ref"]):
                        if other not in seen:
                            seen.add(other)
                            nxt.append(other)
            frontier = nxt
        return list(edges.values())


class SearchRepository:
    """Catalog search over names, descriptions and tags (§16.1 command palette)."""

    TARGETS = (
        ("feature", catalog.Feature),
        ("featureset", catalog.FeatureSet),
        ("model", registry.Model),
        ("warrant/train", registry.TrainingWarrant),
        ("warrant/exec", registry.ExecutionWarrant),
        ("namespace", identity.Namespace),
    )

    def __init__(self, session: Any, actor: str | None = None) -> None:
        self.session = session

    def search(self, q: str, limit: int = 50) -> list[dict[str, Any]]:
        """Ranked hits from the inverted index; every query term must match (as a prefix)."""
        from maya.persistence import search_index

        hits = search_index.search(self.session, q, limit)
        models = {kind: model for kind, model in self.TARGETS}
        wanted: dict[str, list[Any]] = {}
        for kind, oid, _ in hits:
            wanted.setdefault(kind, []).append(oid)
        rows = {}  # one query per kind, not one per hit
        for kind, ids in wanted.items():
            model = models[kind]
            for obj in self.session.scalars(select(model).where(model.id.in_(ids))):
                rows[(kind, obj.id)] = obj.to_dict()
        out = []
        for kind, oid, score in hits:
            row = rows.get((kind, oid))
            if row is None:
                continue
            out.append(
                {
                    "kind": kind,
                    "id": row["id"],
                    "name": row["name"],
                    "description": row.get("description"),
                    "tags": row.get("tags") or [],
                    "namespace_id": row.get("namespace_id"),
                    "owner_id": row.get("owner_id"),
                    "score": score,
                }
            )
        return out

    def rebuild(self) -> int:
        from maya.persistence import search_index

        return search_index.rebuild(self.session)

    def ensure_current(self) -> bool:
        """Rebuild the derived index when it is empty but the catalog is not."""
        from maya.persistence import search_index

        if search_index.needs_rebuild(self.session):
            search_index.rebuild(self.session)
            return True
        return False
