"""
Declarative base and the audit columns every mutable aggregate carries (§14.2).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Integer, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from maya.persistence.types import PortableUUID, UTCDateTime, utcnow

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)

    def to_dict(self) -> dict[str, Any]:
        return {c.key: getattr(self, c.key) for c in self.__mapper__.column_attrs}


class Tracked:
    """Surrogate UUID key, audit columns and optimistic concurrency."""

    id: Mapped[str] = mapped_column(PortableUUID, primary_key=True, default=new_id)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_by: Mapped[str | None] = mapped_column(String(128))
    updated_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[str | None] = mapped_column(String(128))
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
