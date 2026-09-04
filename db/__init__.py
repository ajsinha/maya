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
from db.delta_store import DeltaStore
from db.repositories import (AliasHistoryRepository, AliasRepository, AmendmentRepository,
                             AttestationRepository, BreachRepository, CapabilityRepository,
                             ContractRepository,
                             DocumentRepository, EvidenceRepository, FeatureRepository,
                             FeatureViewRepository, FeatureViewVersionRepository,
                             FindingRepository, GenerationRepository, MeasurementRepository,
                             ModelRepository,
                             MonitorRepository,
                             ObservationRepository, OverlayRepository, PrincipalRepository,
                             Repository,
                             RiskRepository, SignatureRepository, SnapshotRepository,
                             TestResultRepository, ValidationRepository,
                             VersionRepository, WarrantRepository)

__all__ = ["Database", "DeltaPaths", "DeltaStore", "Repository", "ModelRepository",
           "VersionRepository", "AliasRepository", "AliasHistoryRepository",
           "EvidenceRepository", "RiskRepository", "WarrantRepository", "FeatureRepository",
           "FeatureViewRepository", "FeatureViewVersionRepository", "ContractRepository",
           "SnapshotRepository", "ValidationRepository",
           "TestResultRepository", "FindingRepository", "PrincipalRepository", "AmendmentRepository",
           "AttestationRepository", "SignatureRepository", "MonitorRepository",
           "ObservationRepository", "BreachRepository", "DocumentRepository", "OverlayRepository",
           "MeasurementRepository", "CapabilityRepository",
           "GenerationRepository"]
