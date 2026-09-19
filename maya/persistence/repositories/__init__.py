"""
Repository registry: one repository per aggregate root, addressed by table name.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any

from maya.persistence.models import MODELS
from maya.persistence.repositories.base import Repository
from maya.persistence.repositories.special import (AuditRepository, JobRepository,
                                                   LineageRepository, SearchRepository)

SPECIAL: dict[str, type[Any]] = {
    "audit_events": AuditRepository,
    "jobs": JobRepository,
    "lineage_edges": LineageRepository,
    "search": SearchRepository,
}


def repository_class(name: str) -> type[Any]:
    """The repository for a table, generating a plain one where no special exists."""
    if name in SPECIAL:
        return SPECIAL[name]
    model = MODELS[name]
    label = name.rstrip("s").replace("_", " ")
    return type(f"{model.__name__}Repository", (Repository,), {"model": model, "label": label})


__all__ = ["Repository", "repository_class", "AuditRepository", "JobRepository",
           "LineageRepository", "SearchRepository"]
