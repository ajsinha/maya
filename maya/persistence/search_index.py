"""
Catalog search: MAYA's own inverted index (§13.4, §16.1 command palette).

One code path on SQLite and PostgreSQL. Every write to a searchable object
re-indexes it in the same transaction (a session ``after_flush`` hook), so the
index can never describe a state that did not commit. A query is tokenized the
same way as the documents; every query term must match — as a prefix, so
``adj`` finds ``adj_close`` — and hits are ranked by the weight of the fields
they matched in: name, then tags, then namespace and description.

The index is derived data: ``rebuild`` recreates it from the catalog, and
startup rebuilds it when it is empty but the catalog is not (an estate
imported, or a database from before the index existed).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import delete, event, func, insert, select
from sqlalchemy.orm import Session

from maya.persistence.models import catalog, identity, operations, registry

TARGETS: dict[type, str] = {
    catalog.Feature: "feature", catalog.FeatureSet: "featureset", registry.Model: "model",
    registry.TrainingWarrant: "warrant/train", registry.ExecutionWarrant: "warrant/exec",
    identity.Namespace: "namespace",
}
WEIGHTS = {"name": 8, "tag": 4, "namespace": 2, "description": 1}
MAX_TERM = 64
_WORD = re.compile(r"[0-9a-z]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def tokens(text: str | None) -> list[str]:
    """``adjClose_v2`` -> adjclose_v2, adj, close, v2 (the whole word, then its parts)."""
    if not text:
        return []
    out: list[str] = []
    for word in re.split(r"[\s,;:/()\[\]{}\"'`!?<>|=+*]+", text):
        if not word:
            continue
        parts = _WORD.findall(_CAMEL.sub(" ", word).lower())
        whole = word.lower().strip(".-")
        for t in ([whole] if len(parts) > 1 else []) + parts:
            if t and t not in out:
                out.append(t[:MAX_TERM])
    return out


def _fields(session: Session, obj: Any) -> list[tuple[str, str]]:
    fields = [("name", obj.name)]
    fields += [("tag", t) for t in (getattr(obj, "tags", None) or [])]
    fields.append(("description", getattr(obj, "description", None) or ""))
    ns_id = getattr(obj, "namespace_id", None)
    if ns_id:
        ns = session.get(identity.Namespace, ns_id)
        if ns is not None:
            fields.append(("namespace", ns.name))
    return fields


def _rows(session: Session, obj: Any) -> list[dict[str, Any]]:
    best: dict[str, tuple[int, str]] = {}
    for field, text in _fields(session, obj):
        for t in tokens(text):
            w = WEIGHTS[field]
            if w > best.get(t, (0, ""))[0]:
                best[t] = (w, field)
    return [{"term": t, "kind": TARGETS[type(obj)], "object_id": obj.id, "field": f,
             "weight": w} for t, (w, f) in best.items()]


def _reindex(session: Session, objs: list[Any], removed: list[Any]) -> None:
    conn = session.connection()
    ids = [o.id for o in objs + removed]
    if ids:
        conn.execute(delete(operations.SearchTerm).where(
            operations.SearchTerm.object_id.in_(ids)))
    rows = [r for o in objs for r in _rows(session, o)]
    if rows:
        conn.execute(insert(operations.SearchTerm), rows)


def _after_flush(session: Session, _ctx: Any) -> None:
    changed = [o for o in session.new if type(o) in TARGETS] + \
        [o for o in session.dirty if type(o) in TARGETS and session.is_modified(o)]
    removed = [o for o in session.deleted if type(o) in TARGETS]
    if changed or removed:
        with session.no_autoflush:
            _reindex(session, changed, removed)


def install() -> None:
    """Keep the index current on every session (idempotent)."""
    if not event.contains(Session, "after_flush", _after_flush):
        event.listen(Session, "after_flush", _after_flush)


def rebuild(session: Session) -> int:
    """Recreate the whole index from the catalog; returns the number of objects indexed."""
    session.execute(delete(operations.SearchTerm))
    objs = [o for model in TARGETS for o in session.scalars(select(model))]
    rows = [r for o in objs for r in _rows(session, o)]
    for i in range(0, len(rows), 2000):
        session.execute(insert(operations.SearchTerm), rows[i:i + 2000])
    return len(objs)


def needs_rebuild(session: Session) -> bool:
    empty = session.scalar(select(func.count()).select_from(operations.SearchTerm)) == 0
    return empty and any(session.scalar(select(func.count()).select_from(m)) for m in TARGETS)


def search(session: Session, q: str, limit: int = 50) -> list[tuple[str, str, int]]:
    """(kind, object id, score) for objects matching every query term, best first."""
    terms = tokens(q)[:8]
    if not terms:
        return []
    T = operations.SearchTerm
    per_term = []
    for t in terms:
        like = t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        per_term.append(select(T.kind, T.object_id, func.max(T.weight).label("w"))
                        .where(T.term.like(like, escape="\\"))
                        .group_by(T.kind, T.object_id).subquery())
    first = per_term[0]
    score = first.c.w
    stmt = select(first.c.kind, first.c.object_id)
    for sub in per_term[1:]:
        stmt = stmt.join(sub, (sub.c.kind == first.c.kind) & (sub.c.object_id == first.c.object_id))
        score = score + sub.c.w
    stmt = stmt.add_columns(score.label("score")).order_by(score.desc()).limit(limit)
    return [(k, oid, int(s)) for k, oid, s in session.execute(stmt)]
