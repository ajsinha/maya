"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The persistence package. This is the ONLY place in MAYA that knows how data is
stored — SQL, dialects, JSON encoding, Delta Lake paths. Everything above it
receives repositories and never sees a table, a session or a connection.

Two dialects are supported and selected by configuration alone: SQLite (the
default, under data/sqlite) and PostgreSQL. There are no migrations; the schema
is the pair of hand-written files under db/schema/, applied idempotently.
"""
from db.database import Database, DeltaPaths
from db.repositories import (AliasRepository, EvidenceRepository, HookRepository,
                             ModelRepository, RiskRepository, VersionRepository)

__all__ = ["Database", "DeltaPaths", "ModelRepository", "VersionRepository",
           "AliasRepository", "EvidenceRepository", "RiskRepository", "HookRepository"]
