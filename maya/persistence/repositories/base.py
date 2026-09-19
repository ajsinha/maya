"""
The repository base (§14).

A repository returns plain dictionaries, never ORM instances, so nothing
above this package ever holds a ``Session`` or a lazy relationship. Filters
are keyword arguments with Django-style suffixes (``state__in``,
``name__ilike``, ``expires_at__lt``, ``revoked_at__isnull``) — a small closed
vocabulary rather than a query builder, so every query shape has one place to
live and one place to be tested.

Optimistic concurrency: ``update`` takes the ``row_version`` the caller last
read and raises ``ConflictError`` when someone else wrote first (§14.2).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any, Generic, Iterable, TypeVar

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from maya.core.errors import ConflictError, NotFound
from maya.persistence.models.base import Base, new_id
from maya.persistence.types import utcnow

M = TypeVar("M", bound=Base)

_OPS = {
    "eq": lambda c, v: c == v,
    "ne": lambda c, v: c != v,
    "lt": lambda c, v: c < v,
    "le": lambda c, v: c <= v,
    "gt": lambda c, v: c > v,
    "ge": lambda c, v: c >= v,
    "in": lambda c, v: c.in_(list(v)),
    "notin": lambda c, v: c.not_in(list(v)),
    "isnull": lambda c, v: c.is_(None) if v else c.is_not(None),
    "ilike": lambda c, v: func.lower(c).like(f"%{str(v).lower()}%"),
}


def _row(obj: Base | None) -> dict[str, Any] | None:
    return None if obj is None else obj.to_dict()


class Repository(Generic[M]):
    """Generic CRUD over one aggregate table."""

    model: type[M]
    label: str = "object"

    def __init__(self, session: Session, actor: str | None = None) -> None:
        self.session = session
        self.actor = actor

    # -- query construction ----------------------------------------------
    def _where(self, stmt: Select[Any], filters: dict[str, Any]) -> Select[Any]:
        clauses = []
        for key, value in filters.items():
            name, _, op = key.partition("__")
            column = getattr(self.model, name)
            clauses.append(_OPS[op or "eq"](column, value))
        return stmt.where(and_(*clauses)) if clauses else stmt

    def _order(self, stmt: Select[Any], order_by: Iterable[str] | None) -> Select[Any]:
        for spec in order_by or ():
            desc = spec.startswith("-")
            column = getattr(self.model, spec.lstrip("-"))
            stmt = stmt.order_by(column.desc() if desc else column.asc())
        return stmt

    # -- reads -------------------------------------------------------------
    def get(self, obj_id: Any) -> dict[str, Any] | None:
        return _row(self.session.get(self.model, obj_id))

    def require(self, obj_id: Any) -> dict[str, Any]:
        row = self.get(obj_id)
        if row is None:
            raise NotFound(f"{self.label} '{obj_id}' does not exist", id=str(obj_id))
        return row

    def find_one(self, **filters: Any) -> dict[str, Any] | None:
        stmt = self._where(select(self.model), filters).limit(1)
        return _row(self.session.scalars(stmt).first())

    def list(self, *, order_by: Iterable[str] | None = None, limit: int | None = None,
             offset: int = 0, search: tuple[list[str], str] | None = None,
             **filters: Any) -> list[dict[str, Any]]:
        stmt = self._where(select(self.model), filters)
        if search and search[1]:
            cols, q = search
            stmt = stmt.where(or_(*[_OPS["ilike"](getattr(self.model, c), q) for c in cols]))
        stmt = self._order(stmt, order_by)
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return [o.to_dict() for o in self.session.scalars(stmt).all()]

    def count(self, **filters: Any) -> int:
        stmt = self._where(select(func.count()).select_from(self.model), filters)
        return int(self.session.execute(stmt).scalar_one())

    # -- writes ------------------------------------------------------------
    def add(self, values: dict[str, Any]) -> dict[str, Any]:
        values = dict(values)
        columns = {c.key for c in self.model.__mapper__.column_attrs}
        if "id" in columns and not values.get("id"):
            values["id"] = new_id()
        for audit_col in ("created_by", "updated_by"):
            if audit_col in columns:
                values.setdefault(audit_col, self.actor)
        obj = self.model(**values)
        self.session.add(obj)
        self.session.flush()
        return obj.to_dict()

    def update(self, obj_id: Any, changes: dict[str, Any], *,
               expected_version: int | None = None) -> dict[str, Any]:
        obj = self.session.get(self.model, obj_id, with_for_update=self._lock_rows())
        if obj is None:
            raise NotFound(f"{self.label} '{obj_id}' does not exist", id=str(obj_id))
        has_version = hasattr(obj, "row_version")
        if expected_version is not None and has_version and obj.row_version != expected_version:
            raise ConflictError(
                f"{self.label} '{obj_id}' was changed by someone else "
                f"(you read version {expected_version}, it is now {obj.row_version}). "
                "Reload and re-apply your edit.",
                expected=expected_version, actual=obj.row_version)
        for key, value in changes.items():
            setattr(obj, key, value)
        if has_version:
            obj.row_version = (obj.row_version or 0) + 1
            obj.updated_by = self.actor
            obj.updated_at = utcnow()
        self.session.flush()
        return obj.to_dict()

    def delete(self, obj_id: Any) -> None:
        obj = self.session.get(self.model, obj_id)
        if obj is not None:
            self.session.delete(obj)
            self.session.flush()

    def delete_where(self, **filters: Any) -> int:
        rows = self.session.scalars(self._where(select(self.model), filters)).all()
        for obj in rows:
            self.session.delete(obj)
        self.session.flush()
        return len(rows)

    def _lock_rows(self) -> bool:
        return self.session.get_bind().dialect.name == "postgresql"
