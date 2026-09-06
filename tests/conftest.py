"""
MAYA — test fixtures.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from core.config import PropertiesConfigurator  # noqa: E402
from tests.api_helpers import quorum_approve  # noqa: E402


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
    """The control-plane database the unit fixtures run against.

    SQLite in memory by default. `MAYA_TEST_DATABASE_URL` points the same suite
    at PostgreSQL instead, which is the only way the second dialect is exercised
    at all: `db/schema/postgres.sql` is maintained column-for-column beside the
    SQLite one and, until CI, had never been run. Adversarial review found
    fourteen BOOLEAN columns in it that no insert could have succeeded against —
    a schema nobody had executed, kept in step by reading it.

    **Isolation is this fixture's job, and only PostgreSQL makes that obvious.**
    `sqlite:///:memory:` hands every test its own database for free, so the
    suite grew to depend on a fresh chain per test without anybody deciding it
    should. Pointed at PostgreSQL — one database for the whole run — evidence
    sequences accumulate across tests and thirteen assertions fail on numbers
    that were never about the dialect: `assert 467 == 1`.

    So the tables are emptied between tests. A fresh container per CI job is not
    the same guarantee and never was; that mistake is exactly the kind this
    fixture exists to stop the suite making.
    """
    import os

    from db import Database

    url = os.environ.get("MAYA_TEST_DATABASE_URL")
    if not url:
        return Database("sqlite:///:memory:")

    database = Database(url)
    _empty(database)
    return database


def _empty(database) -> None:
    """Truncate every table the schema declares.

    `TRUNCATE ... CASCADE` in one statement, so ordering does not matter and no
    partial state can survive a failure part-way through the list.
    """
    import re

    names = sorted(set(re.findall(
        r"^CREATE TABLE IF NOT EXISTS (\w+)",
        database.schema_file().read_text(encoding="utf-8"), re.M)))
    if names:
        database.execute("TRUNCATE " + ", ".join(names) + " RESTART IDENTITY CASCADE")


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
# The same model addressed by name rather than by urn, which is what the
# route paths take.
NAME = "credit.pd.smallbiz"

# Duties are separated in the fixtures because they are separated in the
# system. One account cannot walk the whole path: the person who creates a
# version may not approve it, promote it, or conclude its validation.
PEOPLE = {
    "d.raman":  (["model_developer"],    "dev-pw"),
    "j.okafor": (["model_owner"],        "owner-pw"),
    "a.mehta":  (["validator"],          "val-pw"),
    "s.iqbal":  (["model_risk_manager"], "mrm-pw"),
}


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
def finding_workflow(db, findings, evidence):
    """The acts between raising a finding and closing it. Short windows, so a
    test can reach the escalation without inventing a week of elapsed time."""
    from core.validation import FindingWorkflow
    from db import FindingActionRepository
    return FindingWorkflow(findings, FindingActionRepository(db), evidence,
                           extension_limit=2, acknowledge_days=5.0,
                           escalate_days=7.0)


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
def monitors(db, catalogue, evidence, registry):
    """Wired as the application wires it, with the fibration.

    Without `fibres` and `class_of` the registry holds no opinion about which
    questions a class can answer, which is the state the platform was in before
    `L-15` was closed — and a fixture in that state would let a test define a
    monitor the application refuses.
    """
    from core.fibres import FibreRegistry
    from core.monitoring import MonitorRegistry
    from db import MonitorRepository

    def class_of(model_id: str):
        """model_id -> the trainability class of its latest version."""
        model = registry.by_id(model_id)
        if not model:
            return None
        versions = registry.versions(model["urn"])
        return versions[-1]["trainability_class"] if versions else None

    return MonitorRegistry(MonitorRepository(db), catalogue, evidence,
                           fibres=FibreRegistry(), class_of=class_of)


@pytest.fixture
def monitoring(db, monitors, findings, catalogue, evidence, telemetry, registry):
    """Wired as the application wires it: with telemetry, so a monitor can be
    evaluated from what the platform holds rather than only from what a caller
    hands it."""
    from core.monitoring import BreachRegister, MonitoringService
    from db import BreachRepository, ObservationRepository
    return MonitoringService(monitors, ObservationRepository(db),
                             BreachRegister(BreachRepository(db), findings, evidence),
                             catalogue, evidence, telemetry, registry)


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
                monitoring, lifecycle, warrants, overlays, regimes):
    from core.docs import ContextBuilder
    for key in ("sr-26-2", "ss1-23", "eu-ai-act"):
        regimes.activate(key)
    return ContextBuilder(registry, evidence, repos["risk"], features, validation,
                          findings, monitoring, lifecycle, warrants, overlays,
                          regimes)


@pytest.fixture
def compiler(db, evidence, doc_context):
    from core.docs import DocumentCompiler
    from db import DocumentRepository
    return DocumentCompiler(DocumentRepository(db), evidence, doc_context)


# ---------------------------------------------------------------------- overlays
@pytest.fixture
def overlays(db, evidence, findings):
    from core.overlays import OverlayRegister
    from db import MeasurementRepository, OverlayRepository
    return OverlayRegister(OverlayRepository(db), MeasurementRepository(db),
                           evidence, findings, max_days=180, renewal_limit=2)


# ------------------------------------------------------------ machine assistance
@pytest.fixture
def capabilities(db, evidence):
    from core.assist import CapabilityRegistry
    from db import CapabilityRepository
    return CapabilityRegistry(CapabilityRepository(db), evidence)


@pytest.fixture
def generations(db, capabilities, evidence):
    from core.assist import GenerationLog
    from db import GenerationRepository
    return GenerationLog(GenerationRepository(db), capabilities, evidence)


# --------------------------------------------------------------- baseline import
@pytest.fixture
def debts(db, evidence, findings):
    from core.baseline import DebtRegister
    from db import DebtRepository
    return DebtRegister(DebtRepository(db), evidence, findings)


@pytest.fixture
def baseline(db, debts, registry, evidence, doc_context):
    from core.baseline import BaselineImporter
    from db import ImportRepository
    return BaselineImporter(ImportRepository(db), debts, registry, evidence,
                            doc_context)


# ----------------------------------------------------------------------- regimes
@pytest.fixture
def regimes(evidence):
    from core.regimes import RegimeEngine
    return RegimeEngine(evidence)


# ------------------------------------------------------------------ estate view
@pytest.fixture
def worklist(registry, lifecycle, findings, monitoring, overlays, compiler, debts,
             validation, finding_workflow):
    from core.estate import WorkList
    return WorkList(registry, lifecycle, findings, monitoring, overlays, compiler,
                    debts, validation, finding_workflow)


@pytest.fixture
def estate(registry, findings, monitoring, overlays, debts, baseline, lifecycle,
           regimes, compiler):
    from core.estate import EstateSummary
    return EstateSummary(registry, findings, monitoring, overlays, debts, baseline,
                         lifecycle, regimes, compiler)


# --------------------------------------------------------------------- scheduler
@pytest.fixture
def scheduler(db, evidence, registry, lifecycle, findings, monitoring, overlays,
              debts, compiler, finding_workflow):
    from core.scheduler import JobContext, Scheduler
    from db import ScheduledRunRepository
    return Scheduler(
        ScheduledRunRepository(db), evidence,
        JobContext(registry=registry, now=0.0, lifecycle=lifecycle,
                   findings=findings, monitoring=monitoring, overlays=overlays,
                   debts=debts, documents=compiler,
                   finding_workflow=finding_workflow))


@pytest.fixture
def attachments(db, tmp_path, registry, evidence):
    from core.attachments import AttachmentRegister, DocumentStore
    from db import AttachmentRepository
    return AttachmentRegister(AttachmentRepository(db),
                              DocumentStore(tmp_path / "attachments"),
                              registry, evidence)


@pytest.fixture
def full_features(db, delta, evidence):
    """A feature registry with derived features and featuresets wired in."""
    from core.features import FeatureRegistry
    from db import (ContractRepository, DerivedFeatureRepository, FeatureRepository,
                    FeatureViewRepository, FeatureViewVersionRepository,
                    FeaturesetRepository, FeaturesetVersionRepository,
                    SnapshotRepository)
    return FeatureRegistry(
        FeatureRepository(db), FeatureViewRepository(db),
        FeatureViewVersionRepository(db), ContractRepository(db),
        SnapshotRepository(db), delta, evidence,
        DerivedFeatureRepository(db), FeaturesetRepository(db),
        FeaturesetVersionRepository(db))


@pytest.fixture
def parameters(db, registry, evidence, warrants, full_features):
    from core.parameters import ParameterRegister
    from db import ParameterSetRepository
    from db import SnapshotRepository
    return ParameterRegister(ParameterSetRepository(db), registry, evidence,
                             warrants, full_features.sets)


@pytest.fixture
def snapshot_provider(db, delta, full_features):
    from core.validation import SnapshotProvider
    from db import SnapshotRepository
    return SnapshotProvider(SnapshotRepository(db), delta, full_features)


@pytest.fixture
def stored_replayer(validation, catalogue, snapshot_provider):
    from core.validation import Replayer
    return Replayer(validation, catalogue, snapshot_provider)


@pytest.fixture
def approvals(db, registry, evidence):
    from core.lifecycle import VersionApproval
    from db import VersionApprovalRepository, VersionApprovalSignatureRepository
    service = VersionApproval(VersionApprovalRepository(db),
                              VersionApprovalSignatureRepository(db),
                              registry, evidence)
    registry.attach_quorum(service.refuse_without_quorum)
    return service


def person(username, *roles):
    return {"username": username, "roles": list(roles)}


@pytest.fixture
def telemetry(db, delta, registry, evidence):
    from core.telemetry import TelemetryCollector
    from db import TelemetryBatchRepository
    return TelemetryCollector(delta, registry, evidence,
                              TelemetryBatchRepository(db))


@pytest.fixture
def notifications(db, worklist, principals, authz, registry, evidence):
    from core.notify import LogChannel, NotificationService
    from db import NotificationRepository
    return NotificationService(
        NotificationRepository(db), worklist, principals, authz, registry,
        evidence, {"log": LogChannel()}, "log", quiet_hours=24.0,
        escalate_days=7.0, base_url="http://localhost:5006")


@pytest.fixture
def policies(db, evidence):
    from core.policy import PolicyRegister
    from db import PolicyRuleRepository
    return PolicyRegister(PolicyRuleRepository(db), evidence)


@pytest.fixture
def summary(registry, findings, monitoring, overlays, debts):
    from core.estate import EstateSummary
    return EstateSummary(registry, findings, monitoring, overlays, debts)

# ---------------------------------------------------------------------------
# The application itself. These three drive every HTTP and page test, and live
# here rather than in one test module because the API suite is split by subject
# and all of the parts need them.
# ---------------------------------------------------------------------------
@pytest.fixture
def client(tmp_path, monkeypatch):
    cfg_file = tmp_path / "application.yaml"
    cfg_file.write_text(f"""
app: {{name: MAYA, version: "0.1.0", tagline: "Model & AI Lifecycle Assurance",
       slogan: "Evidence, not assertion.",
       principle: "A model is a representation of the world. Governance is knowing the difference."}}
server: {{host: 0.0.0.0, port: 5006}}
database: {{url: "sqlite:///{tmp_path}/data/sqlite/maya.db"}}
data: {{dir: "{tmp_path}/data", artifacts: "{tmp_path}/data/artifacts",
        attachments: "{tmp_path}/data/attachments",
        delta: {{dir: "{tmp_path}/data/delta", features: "{tmp_path}/data/delta/features",
                snapshots: "{tmp_path}/data/delta/snapshots",
                telemetry: "{tmp_path}/data/delta/telemetry",
                monitoring: "{tmp_path}/data/delta/monitoring"}}}}
risk:
  exposure_bands: {{negligible: 0, low: 1000000, moderate: 50000000,
                   material: 500000000, critical: 5000000000}}
  purpose_ranks: {{commercial: 1, risk_management: 2, financial_reporting: 3,
                  regulatory_capital: 4}}
  review_months: {{1: 12, 2: 18, 3: 24, 4: 36}}
warrants: {{jitter_pct: 0, signing_key: test-signing-secret,
         ttl_seconds: {{1: 60, 2: 300, 3: 3600, 4: 3600}},
         grace_seconds: {{1: 0, 2: 0, 3: 900, 4: 900}}}}
execution: {{captive: {{enabled: true, max_seconds: 5}}}}
logging: {{level: WARNING}}
""")
    PropertiesConfigurator.reset()
    from run_maya_web import create_app
    app = create_app(PropertiesConfigurator(str(cfg_file), reload_interval=0))
    with TestClient(app) as c:
        # Every API endpoint now requires an authenticated principal. The
        # bootstrap administrator is created on first start from configuration;
        # tests that care about authorisation override these credentials.
        c.auth = ("admin", "admin123")
        yield c


@pytest.fixture
def people(client):
    """Create one principal per duty and return their credentials."""
    for username, (roles, password) in PEOPLE.items():
        r = client.post("/api/v1/principals", json={
            "username": username, "display_name": username, "roles": roles,
            "password": password})
        assert r.status_code == 201, r.text
    return {u: (u, pw) for u, (roles, pw) in PEOPLE.items()}


@pytest.fixture
def registered(client, people):
    """A model taken through the whole governed path by four different people."""
    owner, dev, mrm = people["j.okafor"], people["d.raman"], people["s.iqbal"]
    client.post("/api/v1/models", auth=owner, json={
        "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
        "domain": "credit", "owner": "person/j.okafor", "legal_entity": "LE-US-01",
        "purpose": "12-month PD at origination"})
    client.post(f"/api/v1/models/{NAME}/assess", auth=owner,
                json={"exposure": 2e9, "purpose_class": "regulatory_capital"})
    client.post(f"/api/v1/models/{NAME}/versions", auth=dev,
                json={"semver": "3.2.1", "kernel": KERNEL, "contract": CONTRACT,
                      "artifact_digest": "sha256:abc"})
    quorum_approve(client, people)
    client.put(f"/api/v1/models/{NAME}/aliases", auth=mrm,
               json={"environment": "prod", "alias": "champion", "semver": "3.2.1"})
    client.post("/api/v1/warrants", auth=owner, json={
        "urn": f"{URN}#champion", "environment": "prod",
        "principal": "svc/origination", "declared_use": "origination_decision"})
    return client
