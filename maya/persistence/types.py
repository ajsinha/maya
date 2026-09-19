"""
Portable column types (§14.1). Every SQLite/PostgreSQL difference is handled
once, here, rather than wherever a column happens to be declared.

* ``PortableJSON`` — JSONB on PostgreSQL, JSON (text) on SQLite.
* ``PortableUUID`` — native UUID on PostgreSQL, 36-char text on SQLite;
  always a ``str`` in Python.
* ``UTCDateTime`` — always timezone-aware UTC in Python; SQLite values are
  normalised on the way in and out.
* ``Money`` — ``NUMERIC(38,12)`` on PostgreSQL, text on SQLite, never float.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import decimal
from typing import Any

from sqlalchemy import CHAR, JSON, DateTime, Numeric, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine

PortableJSON = JSON().with_variant(postgresql.JSONB(), "postgresql")


class PortableUUID(TypeDecorator[str]):
    """UUIDs as strings in Python, native on PostgreSQL."""

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.UUID(as_uuid=False))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        return None if value is None else str(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> str | None:
        return None if value is None else str(value)


class UTCDateTime(TypeDecorator[dt.datetime]):
    """Timezone-aware UTC timestamps on both backends."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> dt.datetime | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = dt.datetime.fromisoformat(value)
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        value = value.astimezone(dt.timezone.utc)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: Any, dialect: Dialect) -> dt.datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)


class Money(TypeDecorator[decimal.Decimal]):
    """Exact decimals: NUMERIC(38,12) on PostgreSQL, text on SQLite."""

    impl = String(64)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Numeric(38, 12))
        return dialect.type_descriptor(String(64))

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        value = decimal.Decimal(str(value))
        return value if dialect.name == "postgresql" else format(value, "f")

    def process_result_value(self, value: Any, dialect: Dialect) -> decimal.Decimal | None:
        return None if value is None else decimal.Decimal(str(value))


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)
