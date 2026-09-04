"""
MAYA — test fixtures.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import PropertiesConfigurator  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Every test gets a clean configurator; the singleton must not leak."""
    PropertiesConfigurator.reset()
    yield
    PropertiesConfigurator.reset()


@pytest.fixture
def write_yaml(tmp_path):
    def _write(name: str, body: str) -> str:
        p = tmp_path / name
        p.write_text(body)
        return str(p)
    return _write


@pytest.fixture
def db():
    from db import Database
    return Database("sqlite:///:memory:")


@pytest.fixture
def repos(db):
    from db import (AliasHistoryRepository, AliasRepository, EvidenceRepository,
                    WarrantRepository, ModelRepository, RiskRepository, VersionRepository)
    return {"models": ModelRepository(db), "versions": VersionRepository(db),
            "aliases": AliasRepository(db), "history": AliasHistoryRepository(db),
            "evidence": EvidenceRepository(db), "risk": RiskRepository(db),
            "warrants": WarrantRepository(db)}


@pytest.fixture
def evidence(repos):
    from core.evidence import EvidenceEngine
    return EvidenceEngine(repos["evidence"])


@pytest.fixture
def registry(repos, evidence):
    from core.registry import ModelRegistry
    return ModelRegistry(repos["models"], repos["versions"], repos["aliases"],
                         repos["history"], evidence)


@pytest.fixture
def tiering():
    from core.risk import TieringEngine
    return TieringEngine(
        {"negligible": 0, "low": 1e6, "moderate": 5e7, "material": 5e8, "critical": 5e9},
        {"commercial": 1, "risk_management": 2, "financial_reporting": 3,
         "regulatory_capital": 4},
        {1: 12, 2: 18, 3: 24, 4: 36})


KERNEL = {"parameter_kind": "estimated_coefficients", "fit_procedure": "estimate",
          "input_schema": [{"name": "dscr", "dtype": "float", "minimum": -5, "maximum": 20}],
          "output_schema": [{"name": "pd_12m", "dtype": "float"}]}
CONTRACT = {"assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
            "guarantees": [{"key": "gini", "minimum": 0.42}],
            "on_boundary_violation": "reject"}
URN = "maya://model/credit.pd.smallbiz"


@pytest.fixture
def kernel_spec():
    import copy
    return copy.deepcopy(KERNEL)


@pytest.fixture
def contract_spec():
    import copy
    return copy.deepcopy(CONTRACT)


@pytest.fixture
def a_model(registry):
    registry.register(URN, "SB PD", "credit.pd.scorecard", "credit",
                      "person/j.okafor", "LE-US-01", "12m PD at origination")
    registry.set_tier(registry.get(URN)["id"], 1)
    return registry.get(URN)


@pytest.fixture
def approved_version(registry, a_model, kernel_spec, contract_spec):
    registry.create_version(URN, "3.2.1", kernel_spec, contract_spec, artifact_digest="sha256:abc")
    return registry.approve_version(URN, "3.2.1")


@pytest.fixture
def warrants(repos, registry, evidence):
    from core.execution import WarrantService
    return WarrantService(repos["warrants"], registry, evidence, jitter_pct=0)


@pytest.fixture
def delta(tmp_path):
    from db import DeltaStore
    return DeltaStore(tmp_path / "delta")


@pytest.fixture
def features(db, delta, evidence):
    from core.features import FeatureRegistry
    from db import (ContractRepository, FeatureRepository, FeatureViewRepository,
                    FeatureViewVersionRepository, SnapshotRepository)
    return FeatureRegistry(FeatureRepository(db), FeatureViewRepository(db),
                           FeatureViewVersionRepository(db), ContractRepository(db),
                           SnapshotRepository(db), delta, evidence)


@pytest.fixture
def sb_view(features):
    """A materialised view with a restatement in it: the borrower's Q1 figure is
    revised months later, which is the case point-in-time correctness exists for."""
    features.define("dscr", "customer", "float", "Debt service coverage ratio", "person/d.raman")
    features.define("revenue", "customer", "float", "Trailing twelve month revenue", "person/d.raman")
    features.create_view("sb_financials", "customer", "person/d.raman", ["dscr", "revenue"])
    features.materialise("sb_financials", [
        # C1: filed 31 Mar (t=100), landed 20 May (t=110)
        {"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 110.0, "dscr": 1.20, "revenue": 5.0},
        # C1: the SAME period, restated downward in August (t=900)
        {"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 900.0, "dscr": 0.40, "revenue": 3.0},
        {"entity_id": "C2", "event_ts": 100.0, "ingest_ts": 110.0, "dscr": 2.10, "revenue": 9.0},
        {"entity_id": "C3", "event_ts": 100.0, "ingest_ts": 110.0, "dscr": 0.90, "revenue": 4.0},
    ])
    return features


# --------------------------------------------------------------------- validation
@pytest.fixture
def findings(db, evidence):
    from core.validation import FindingRegister
    from db import FindingRepository
    return FindingRegister(FindingRepository(db), evidence)


@pytest.fixture
def gated_registry(repos, evidence, findings):
    """A registry whose alias moves are gated on the findings register."""
    from core.registry import ModelRegistry
    return ModelRegistry(repos["models"], repos["versions"], repos["aliases"],
                         repos["history"], evidence, blocking=findings)


@pytest.fixture
def catalogue():
    from core.validation import TestCatalogue
    return TestCatalogue()


@pytest.fixture
def validation(db, registry, catalogue, evidence, findings):
    from core.validation import ValidationService
    from db import TestResultRepository, ValidationRepository
    return ValidationService(ValidationRepository(db), TestResultRepository(db),
                             registry, catalogue, evidence, findings)


@pytest.fixture
def replayer(validation, catalogue):
    from core.validation import Replayer
    return Replayer(validation, catalogue)


@pytest.fixture
def scored():
    """A separable but imperfect sample — realistic, not a toy perfect split."""
    labels = [0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1, 1]
    scores = [0.02, 0.05, 0.09, 0.12, 0.18, 0.21, 0.24, 0.33,
              0.41, 0.48, 0.52, 0.61, 0.70, 0.78, 0.85, 0.94]
    return labels, scores


# ------------------------------------------------------------------ authorisation
@pytest.fixture
def principals(db, evidence):
    from core.authz import PrincipalService
    from db import PrincipalRepository
    # A cheap KDF: these tests are about the decision, not about the key derivation.
    return PrincipalService(PrincipalRepository(db), evidence, iterations=1000)


@pytest.fixture
def segregation(evidence):
    from core.authz import SegregationPolicy
    return SegregationPolicy(evidence)


@pytest.fixture
def authz(segregation):
    from core.authz import AuthorizationPolicy
    return AuthorizationPolicy(segregation)


@pytest.fixture
def staff(principals):
    """One principal per duty, as a real deployment would have."""
    principals.create("d.raman", "D Raman", ["model_developer"], "dev-pw")
    principals.create("j.okafor", "J Okafor", ["model_owner"], "owner-pw")
    principals.create("a.mehta", "A Mehta", ["validator"], "val-pw")
    principals.create("s.iqbal", "S Iqbal", ["model_risk_manager"], "mrm-pw")
    return {u: principals.get(u) for u in ("d.raman", "j.okafor", "a.mehta", "s.iqbal")}


# --------------------------------------------------------------------- lifecycle
@pytest.fixture
def lifecycle(db, registry, evidence):
    from core.lifecycle import AmendmentService, AttestationService, LifecycleService
    from db import AmendmentRepository, AttestationRepository, SignatureRepository
    service = LifecycleService(
        registry,
        AmendmentService(AmendmentRepository(db), evidence),
        AttestationService(AttestationRepository(db), SignatureRepository(db), evidence),
        evidence)
    registry.attach_gate(service)
    return service


@pytest.fixture
def owner():
    return {"username": "j.okafor", "roles": ["model_owner"]}


@pytest.fixture
def mrm():
    return {"username": "s.iqbal", "roles": ["model_risk_manager"]}


@pytest.fixture
def ready_model(registry, lifecycle, a_model, kernel_spec, contract_spec):
    """A registered, versioned, tiered model sitting in draft."""
    registry.create_version(URN, "1.0.0", kernel_spec, contract_spec,
                            artifact_digest="sha256:abc", actor="d.raman")
    return registry.get(URN)


@pytest.fixture
def attested_model(registry, lifecycle, ready_model, owner, mrm):
    """Taken all the way through to attested, by two different people."""
    lifecycle.submit(ready_model, "j.okafor")
    lifecycle.approve(registry.get(URN), "s.iqbal")
    lifecycle.sign(registry.get(URN), owner, "model_owner")
    lifecycle.sign(registry.get(URN), mrm, "model_risk_manager")
    return registry.get(URN)


# -------------------------------------------------------------------- monitoring
@pytest.fixture
def monitors(db, catalogue, evidence):
    from core.monitoring import MonitorRegistry
    from db import MonitorRepository
    return MonitorRegistry(MonitorRepository(db), catalogue, evidence)


@pytest.fixture
def monitoring(db, monitors, findings, catalogue, evidence):
    from core.monitoring import BreachRegister, MonitoringService
    from db import BreachRepository, ObservationRepository
    return MonitoringService(monitors, ObservationRepository(db),
                             BreachRegister(BreachRepository(db), findings, evidence),
                             catalogue, evidence)


@pytest.fixture
def drift_monitor(monitors, a_model):
    return monitors.define(a_model["id"], "score drift", "score_drift",
                           "stability.psi", {"max": 0.25}, "person/j.okafor")


@pytest.fixture
def performance_monitor(monitors, a_model):
    return monitors.define(a_model["id"], "discrimination", "performance",
                           "discrimination.gini", {"min": 0.40}, "person/j.okafor",
                           label_delay_days=365, escalate_after=3)


# --------------------------------------------------------------------- documents
@pytest.fixture
def doc_context(registry, evidence, repos, features, validation, findings,
                monitoring, lifecycle, warrants):
    from core.docs import ContextBuilder
    return ContextBuilder(registry, evidence, repos["risk"], features, validation,
                          findings, monitoring, lifecycle, warrants)


@pytest.fixture
def compiler(db, evidence, doc_context):
    from core.docs import DocumentCompiler
    from db import DocumentRepository
    return DocumentCompiler(DocumentRepository(db), evidence, doc_context)
