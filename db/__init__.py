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
from db.repositories import (ServingAttestationRepository,
                            AliasHistoryRepository, AliasRepository, AmendmentRepository,
                             AttachmentRepository, AttestationRepository, BreachRepository,
                             CapabilityRepository,
                             ContractRepository, DerivedFeatureRepository,
                             FeaturesetRepository, FeaturesetVersionRepository,
                             ParameterSetRepository,
                             NotificationRepository, PolicyRuleRepository,
                             WarrantProfileRepository,
                             RiskAppetiteRepository, BoardPackRepository,
                             TelemetryBatchRepository,
                             VersionApprovalRepository,
                             VersionApprovalSignatureRepository,
                             DebtRepository, DocumentRepository, EvidenceCheckpointRepository, ModelEdgeRepository, EvidenceRepository,
                             FeatureRepository,
                             FeatureViewRepository, FeatureViewVersionRepository,
                             FindingActionRepository,
                             FindingRepository, GenerationRepository, ImportRepository,
                             MeasurementRepository,
                             ModelRepository,
                             MonitorRepository,
                             ObservationRepository, OverlayRepository, PrincipalRepository,
                             Repository,
                             RiskRepository, ScheduledRunRepository, SignatureRepository,
                             SnapshotRepository,
                             TestResultRepository, ValidationRepository,
                             VersionRepository, WarrantRepository)

__all__ = [
                            "AliasHistoryRepository",
                            "AliasRepository",
                            "AmendmentRepository",
                            "AttachmentRepository",
                            "AttestationRepository",
                            "BoardPackRepository",
                            "BreachRepository",
                            "CapabilityRepository",
                            "ContractRepository",
                            "Database",
                            "DebtRepository",
                            "DeltaPaths",
                            "DeltaStore",
                            "DerivedFeatureRepository",
                            "DocumentRepository",
                            "EvidenceCheckpointRepository",
                            "EvidenceRepository",
                            "FeatureRepository",
                            "FeatureViewRepository",
                            "FeatureViewVersionRepository",
                            "FeaturesetRepository",
                            "FeaturesetVersionRepository",
                            "FindingActionRepository",
                            "FindingRepository",
                            "GenerationRepository",
                            "ImportRepository",
                            "MeasurementRepository",
                            "ModelEdgeRepository",
                            "ModelRepository",
                            "MonitorRepository",
                            "NotificationRepository",
                            "ObservationRepository",
                            "OverlayRepository",
                            "ParameterSetRepository",
                            "PolicyRuleRepository",
                            "PrincipalRepository",
                            "Repository",
                            "RiskAppetiteRepository",
                            "RiskRepository",
                            "ScheduledRunRepository",
                            "ServingAttestationRepository",
                            "SignatureRepository",
                            "SnapshotRepository",
                            "TelemetryBatchRepository",
                            "TestResultRepository",
                            "ValidationRepository",
                            "VersionApprovalRepository",
                            "VersionApprovalSignatureRepository",
                            "VersionRepository",
                            "WarrantProfileRepository",
                            "WarrantRepository",
]
