"""
The typed SQLAlchemy metadata — the single source of truth for the schema.

Both shipped DDL files (``schema/sqlite.sql`` and ``schema/postgresql.sql``)
are generated from ``Base.metadata`` by ``maya.persistence.schema`` and never
hand-edited (§14.3).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from maya.persistence.models.base import Base, new_id
from maya.persistence.models import catalog, identity, operations, registry

MODELS = {
    mapper.class_.__tablename__: mapper.class_
    for mapper in Base.registry.mappers
}

__all__ = ["Base", "MODELS", "new_id", "catalog", "identity", "operations", "registry"]
