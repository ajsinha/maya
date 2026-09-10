#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Application entry point. Wires configuration, the store, the governance
services and the routes, then serves.

    python run_maya_web.py
    python run_maya_web.py --server.port=5006 --database.url=postgresql://...

MAYA manages models and issues warrants. The captive execution engine is
constructed here only if execution.captive.enabled is true, and it is handed
the public WarrantService — the same interface an external engine consumes.
"""
from __future__ import annotations

import logging
import json
import os
import sys
import hashlib
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from core.authz import csrf
from fastapi.templating import Jinja2Templates

from core.execution.invocations import InvocationLog
from core.features.pipeline import PipelineHealth
from core.lifecycle.changes import ChangeClassifier
from core.lifecycle.conditions import ApprovalConditions
from core.lifecycle.parallel import ParallelRuns
from core.artifacts.migration import FormatMigration
from core.validation.capacity import ValidationCapacity
from core.validation.supervisory import SupervisoryMatters
from core.assist.encoding import RegimeEncodingAssistant
from core.assist.remediation import RemediationPlanner
from core.assist.nlquery import NaturalLanguageQuery
from core.assist.probes import ProbeSets
from core.assist.validation_aid import ValidationAssistant
from core.monitoring.adaptive import AdaptiveChange
from core.reporting.returns import RegulatoryReturns
from core.reporting.semantics import SemanticLayer
from core.reporting.views import SavedViews
from core.monitoring.challengers import ChampionChallenger
from core.monitoring.external import ExternalObservations
from core.monitoring.health import ModelHealth
from core.validation.vendor import VendorAssessments
from core.lifecycle.profiles import LifecycleProfiles
from core.risk.immaterial import ImmaterialPath
from core.execution.reconciliation import UseReconciliation
from core.execution import (CaptiveEngine, InProcessSandbox,
                            SubprocessSandbox)
from core.estate.portfolio import Portfolio
from core.events import EventStream, Subscriptions
from core.events.subscriptions import http_sender
from core.estate import EstateSummary, WorkList
from core.evidence import EvidenceEngine
from core.evidence.anchor import ChainAnchor
from core.evidence.worm import FilesystemWORM
from core import log
from core.log import configure, get_logger, swallowed
from core.features import FeatureRegistry
from core.fibres import FibreRegistry
from core.rules import RuleSetEditor
from core.lifecycle import (AmendmentService, AttestationService,
                            LifecycleService, VersionApproval)
from core.execution import WarrantService
from core.artifacts import ArtifactStore
from core.export import ExportPacker
from core.reporting import (AppetiteRegister, BoardPackBuilder,
                            IndicatorSet)
from core.execution.profiles import WarrantProfileRegister
from core.authz.breakglass import BreakGlass
from core import concurrency
from core.concurrency import IdempotencyStore
from core.execution.inference import InferenceLog
from core.execution.quotas import GrantQuotas
from core.execution.zones import ComputeZones
from core.parameters.experiments import Experiments
from core.classification import Classification
from core.docs.search import DocumentSearch
from core.scanning import UploadScanner
from core.scanning.upload import DEFAULT_LICENCES
from core.discovery import DiscoveryRegister
from core.artifacts.bom import BillOfMaterials
from core.artifacts.provenance import ArtifactProvenance
from core.risk.approvals import RegulatoryApprovals
from core.risk.whatif import TieringWhatIf
from core.features.skew import SkewDetector
from core.plugins import ExtensionPoints
from core.retention import LegalHolds, RetentionSchedule
from core.registry.comparison import VersionComparison
from core.assist.monitoring import AssistMonitoring
from core.assist import (BudgetRegister, CanaryRegister, CapabilityRegistry,
                         DraftingService, GenerationLog)
from core.assist import providers as assist_providers
from core.attachments import AttachmentRegister, DocumentStore
from core.parameters import FittingService, ParameterRegister
from core.baseline import BaselineImporter, DebtRegister
from core.authz import (AuthorizationPolicy, AuthzError, PrincipalService,
                        SegregationPolicy)
from core.config import PropertiesConfigurator
from core.docs import (ContextBuilder, DocumentCompiler, Dossier,
                       TrainingRecordCompiler)
from core.content import ContentLibrary, MarkdownRenderer
from core.monitoring import (BreachRegister, MonitoringDefaults,
                             MonitoringPlans, MonitorRegistry,
                             MonitoringService)
from core.overlays import OverlayRegister
from core.regimes import RegimeEngine
from core.registry import ModelComposition, ModelRegistry, RegistryError
from core.registry.asat import AsAtProjection
from core.registry.uses import ModelUses
from core.validation.plans import ValidationPlans
from core.validation.recode import RecodeHarness
from core.features.serving import ServingRegister
from core.scheduler import JobContext, Scheduler, SchedulerLoop
from core.authz.oidc import build as build_oidc
from core.notify import NotificationService, build as build_channels
from core.policy import PolicyGate, PolicyRegister
from core.policy.wiring import GateFacts
from core.risk import AggregateRisk, TieringEngine
from core.telemetry import TelemetryCollector
from core.validation import (FindingRegister, FindingWorkflow, Replayer,
                             SnapshotProvider, TestCatalogue, ValidationService)
from db import table_backend
from db import (ServingAttestationRepository,
                AliasHistoryRepository, AliasRepository, AmendmentRepository,
                AttachmentRepository, DerivedFeatureRepository,
                NotificationRepository, PolicyRuleRepository,
                WarrantProfileRepository, RiskAppetiteRepository,
                BoardPackRepository,
                TelemetryBatchRepository,
                VersionApprovalRepository,
                VersionApprovalSignatureRepository,
                FeaturesetRepository, FeaturesetVersionRepository,
                ParameterSetRepository,
                AttestationRepository, BreachRepository, CapabilityRepository,
                ContractRepository, Database, DebtRepository, DeltaPaths,
                DocumentRepository, EvidenceCheckpointRepository, EvidenceRepository, ModelEdgeRepository,
                FeatureRepository, FeatureSourceRepository,
                FeatureViewRepository,
                FeatureViewVersionRepository, FindingActionRepository,
                FindingRepository,
                GenerationRepository, ImportRepository, MeasurementRepository,
                ModelRepository, MonitorRepository, ObservationRepository,
                ApiKeyRepository, AssumptionRepository,
                InvocationRepository, MonitoringPlanRepository, ModelUseRepository,
                LimitationRepository, RoleRepository, WaiverRepository,
                OverlayRepository,
                PrincipalRepository, RiskRepository,
                ApprovalConditionRepository, SubscriptionRepository,
                DiscoveryRepository, LegalHoldRepository,
                RegulatoryApprovalRepository,
                ParallelObservationRepository, ParallelRunRepository,
                VendorAssessmentRepository, VendorItemRepository,
                BreakGlassRepository, IdempotencyRepository,
                InferenceRepository,
                SavedViewRepository, ScheduledRunRepository, SignatureRepository,
                SupervisoryMatterRepository, ValidatorCapacityRepository,
                SnapshotRepository,
                SpendRepository,
                TestResultRepository, ValidationRepository, VersionRepository,
                WarrantRepository)
from fastapi.openapi.docs import get_swagger_ui_html

from core.assumptions import AssumptionRegister
from core.waivers import WaiverRegister
from core.limitations import LimitationRegister
from core.apikeys import ApiKeyRegister
from core.authz.rolestore import RoleStore
from core.references import ReferenceIndex

from routes import ALL_ROUTES

#: Sent on every response.
#:
#: There were none. The interface is entirely self-hosted — every asset is
#: vendored so it renders air-gapped — which makes a strict policy cheap to
#: state and expensive to omit: an injected `<script src>` had nothing stopping
#: it, on pages that render model names, findings and document titles supplied
#: by people.
#:
#: `'unsafe-inline'` is here for scripts and styles and it is not an oversight.
#: Several pages carry inline handlers and `<style>` blocks, and a policy that
#: broke them would be turned off within a week — which is worse than a policy
#: that blocks the external-origin case and says so. Removing it means moving
#: the inline blocks out first, which is its own change.
#: The methods an idempotency key applies to. `GET` is idempotent by
#: definition and `DELETE` is idempotent by its own semantics — but a caller
#: retrying a DELETE still wants the same ANSWER rather than a 404 the second
#: time, so it is included.
MUTATING = ("POST", "PUT", "PATCH", "DELETE")


async def _current_etag(app, request) -> Optional[str]:
    """The ETag of what a GET to this same path would return, or `None`.

    Dispatched through the app's own router rather than reconstructed, so the
    precondition is evaluated against exactly the representation the caller
    read. `None` means the path has no readable representation — and that is
    reported as a refusal rather than treated as a pass, because a precondition
    nobody can evaluate is not a precondition that holds.
    """
    from starlette.datastructures import Headers

    # A fresh scope through the WHOLE app rather than the bare router: the
    # router alone asserts on middleware state it does not have. There is no
    # recursion — this only ever runs for a mutating method, and it dispatches
    # a GET, which never reaches here.
    scope = {k: v for k, v in request.scope.items()
             if k not in ("fastapi_astack", "fastapi_middleware_astack",
                          "router", "route_handler", "endpoint", "route",
                          "path_params", "session", "starlette.exception_handlers")}
    scope.update({"method": "GET", "query_string": b"",
                  "headers": [(k, v) for k, v in request.scope["headers"]
                              if k not in (b"if-match", b"content-type",
                                           b"content-length")]})
    captured: Dict[str, Any] = {"status": 0, "body": b""}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
            captured["headers"] = Headers(raw=message.get("headers") or [])
        elif message["type"] == "http.response.body":
            captured["body"] += message.get("body") or b""

    try:
        await app(scope, receive, send)
    except Exception:
        # A path whose GET raises is a path with no representation to compare
        # against. Logged rather than swallowed, because it is also a defect.
        logger.warning("could not read %s back to evaluate If-Match",
                       request.url.path, exc_info=True)
        return None
    if captured["status"] != 200:
        return None
    try:
        return concurrency.etag_of(json.loads(captured["body"]))
    except (ValueError, UnicodeDecodeError):
        # A representation that is not JSON is one this cannot tag, so the
        # precondition is unevaluable rather than satisfied. Logged because a
        # JSON route returning non-JSON is also a defect.
        logger.warning("the representation of %s is not JSON, so If-Match "
                       "cannot be evaluated against it", request.url.path)
        return None


def _credential_scope(request) -> str:
    """A stable per-caller scope for an idempotency key, before authentication.

    The middleware runs before any route, so it cannot know who the caller *is*
    — it knows what they presented. Hashing that gives a scope no two callers
    share while storing nothing sensitive, which is the property that matters:
    a key is chosen by the caller, and a well-chosen UUID does not protect you
    from somebody else's badly chosen one.
    """
    presented = (request.headers.get("authorization")
                 or request.cookies.get("session")
                 or "anonymous")
    return hashlib.sha256(presented.encode("utf-8")).hexdigest()[:32]


SECURITY_HEADERS: Dict[str, str] = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        # Nothing here calls out. A governance platform that can be made to
        # fetch from somewhere else is one somebody can exfiltrate through.
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"),
    # Belt and braces with frame-ancestors, for the proxies that strip CSP.
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    # A URL here carries a model URN and sometimes a semver. Neither belongs in
    # somebody else's referrer log.
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}
from routes.base import STATUS as REFUSAL_STATUS
from routes.base import authz_problem

ROOT = Path(__file__).resolve().parent
logger = get_logger("maya")


def _tier_map(cfg: PropertiesConfigurator, prefix: str, fallback: Dict[int, int]) -> Dict[int, int]:
    return {t: cfg.get_int(f"{prefix}.{t}", fallback[t]) for t in (1, 2, 3, 4)}


def _tier_roles(cfg: PropertiesConfigurator, prefix: str) -> Dict[int, list]:
    """Which roles must sign, by tier. A tier with no entry needs no quorum."""
    found = {t: cfg.get_list(f"{prefix}.{t}", []) for t in (1, 2, 3, 4)}
    return {t: roles for t, roles in found.items() if roles}


def build_context(cfg: PropertiesConfigurator) -> Dict[str, Any]:
    """Construct the services. Ordering is the dependency order, nothing more."""
    for key in ("data.dir", "data.artifacts", "data.sqlite.dir", "data.worm"):
        if (path := cfg.get(key)):
            Path(path).mkdir(parents=True, exist_ok=True)
    delta = DeltaPaths.from_config(cfg).ensure()

    db = Database(cfg.get("database.url", "sqlite:///data/sqlite/maya.db"),
                  cfg.get_bool("database.echo", False))
    # Defaulted from `data.dir` rather than to a literal "./data/worm". A
    # hardcoded relative default put every instance that did not configure one —
    # including every test — on the SAME directory, so one chain's anchors were
    # compared against another chain's nodes and disagreed. An anchor root
    # shared between two chains is worse than none: it reports tampering that
    # did not happen, and a control that cries wolf is one somebody switches off.
    # `FilesystemWORM` is one implementation of the two WORM ports; the anchor
    # never learns which. A bank that needs write-once enforced rather than
    # conventional points this at S3 with Object Lock or an append-only volume,
    # and nothing above this line changes — which is the reason the seam exists
    # at all: hardening the storage must not mean editing the control.
    anchors = ChainAnchor(FilesystemWORM(
        cfg.get("data.worm") or str(Path(cfg.get("data.dir", "./data")) / "worm")))
    evidence = EvidenceEngine(EvidenceRepository(db), EvidenceCheckpointRepository(db),
                              anchors=anchors)
    registry = ModelRegistry(ModelRepository(db), VersionRepository(db),
                             AliasRepository(db), AliasHistoryRepository(db), evidence)
    tiering = TieringEngine(
        {b: cfg.get_float(f"risk.exposure_bands.{b}", 0.0)
         for b in ("negligible", "low", "moderate", "material", "critical")},
        # Read from the configuration by prefix, not from a list spelled out
        # here. Naming the four classes in code meant a fifth added to
        # `application.yaml` never reached the engine, which then refused it as
        # unknown — the configuration and the code disagreeing about the
        # vocabulary, with the configuration losing silently. The UI route that
        # offers these classes already reads them this way.
        {key[len("risk.purpose_ranks."):]: cfg.get_int(key, 1)
         for key in cfg.as_dict() if key.startswith("risk.purpose_ranks.")},
        _tier_map(cfg, "risk.review_months", {1: 12, 2: 18, 3: 24, 4: 36}))
    # Authorisation. The segregation policy reads the evidence chain, so the
    # record that proves what happened is the record that decides who may act
    # next — there is no second history to keep in step.
    principals = PrincipalService(
        PrincipalRepository(db), evidence,
        iterations=cfg.get_int("auth.kdf_iterations", 200_000),
        verification_ttl=cfg.get_float("auth.verification_ttl_seconds", 60.0))
    authz = AuthorizationPolicy(SegregationPolicy(evidence))
    # Roles live in the register, seeded from the eight this platform ships.
    # Both the policy and the principal service are pointed at the same store,
    # because two places permissions come from is the defect this argues
    # against one layer down.
    role_store = RoleStore(RoleRepository(db), evidence,
                           principals=PrincipalRepository(db),
                           # So removing a role can ask whether an open quorum
                           # still requires it: a role nobody HOLDS can still be
                           # one an attestation names, and deleting it makes
                           # that attestation unsignable by anybody.
                           db=db)
    authz.roles = role_store
    principals.roles = role_store
    bootstrap_user = cfg.get("auth.username", "admin")
    bootstrap_password = cfg.get("auth.password", "maya-admin-dev")
    principals.bootstrap(bootstrap_user, bootstrap_password)
    # Whether the SHIPPED credential still opens the door. The login page
    # carried "development credentials are set in config/application.yaml"
    # unconditionally, to anonymous visitors — true and helpful on a
    # workstation, and on a deployed instance it tells a stranger where to
    # look while saying nothing about whether there is anything to find. Asked
    # once, at start-up, so the page states a fact rather than a guess.
    default_credentials_live = principals.still_opens_the_door(
        bootstrap_user, bootstrap_password)
    if default_credentials_live:
        logger.warning(
            "the bootstrap credential from configuration still authenticates "
            "as '%s'. Change it before this instance is reachable by anybody "
            "else; until then the sign-in page says so.", bootstrap_user)

    # The register is the BlockingSource for both gates. It is built after the
    # registry because both need the evidence engine, and attached explicitly.
    findings = FindingRegister(FindingRepository(db), evidence)
    registry.attach_blocking(findings)
    # Everything between raising a finding and closing it. It writes acts and
    # derives the rest, so there is no status of its own to disagree with the
    # register it sits beside.
    finding_workflow = FindingWorkflow(
        findings, FindingActionRepository(db), evidence,
        extension_limit=cfg.get_int("findings.extension_limit", 2),
        acknowledge_days=cfg.get_float("findings.acknowledge_days", 5.0),
        escalate_days=cfg.get_float("findings.escalate_after_days", 7.0))
    # The lifecycle needs the registry, and the registry needs the lifecycle's
    # mutation gate, so the gate is attached after both exist.
    lifecycle = LifecycleService(
        registry,
        AmendmentService(AmendmentRepository(db), evidence),
        AttestationService(
            AttestationRepository(db), SignatureRepository(db), evidence,
            required_roles=cfg.get_list("lifecycle.attestation.required_roles",
                                        ["model_owner", "model_risk_manager"]),
            validity_days=cfg.get_int("lifecycle.attestation.validity_days", 365)),
        evidence)
    registry.attach_gate(lifecycle)

    catalogue = TestCatalogue()
    validation = ValidationService(ValidationRepository(db), TestResultRepository(db),
                                   registry, catalogue, evidence, findings)
    # So a named validator is resolved against the register rather than taken
    # as prose: `validators` was free text, and a validation naming
    # `person/nobody.at.all` was accepted, recorded and concluded.
    validation.principals = principals
    # And the finding register, so a validator's verdict that the tier is
    # too low becomes something somebody has to close.
    validation.findings = findings

    warrants = WarrantService(WarrantRepository(db), registry, evidence,
                        signing_key=cfg.get("warrants.signing_key", "maya-dev-key"),
                        ttl_by_tier=_tier_map(cfg, "warrants.ttl_seconds",
                                              {1: 60, 2: 300, 3: 3600, 4: 3600}),
                        grace_by_tier=_tier_map(cfg, "warrants.grace_seconds",
                                                {1: 0, 2: 0, 3: 900, 4: 900}),
                        jitter_pct=cfg.get_int("warrants.jitter_pct", 20),
                        blocking=findings)

    # Telemetry is what turns monitoring from something somebody remembers to
    # do into something the scheduler can actually run.
    # The table format, chosen once. Delta by default; Iceberg where a bank's
    # lakehouse is Iceberg and its Trino or Athena should be able to read the
    # feature store directly. Nothing above `db/` knows which.
    table_store = table_backend.build(
        delta.root, cfg.get("data.table_format", None),
        cfg.get("data.iceberg.catalog", None))

    telemetry = TelemetryCollector(table_store, registry, evidence,
                                   TelemetryBatchRepository(db))

    # `L-15`, checked before anything is served. A partial fibre found at run
    # time is found by whoever was relying on it.
    fibres = FibreRegistry()
    fibres.verify()          # L-15, before anything is served

    def _class_of(model_id: str):
        """The trainability class of a model's latest version, or None.

        A model with no version yet has no class, and the fibre check holds no
        opinion rather than guessing one — the fit and approval gates refuse
        further on for better reasons.
        """
        model = registry.by_id(model_id)
        if not model:
            return None
        versions = registry.versions(model["urn"])
        return versions[-1]["trainability_class"] if versions else None

    monitoring = MonitoringService(
        MonitorRegistry(MonitorRepository(db), catalogue, evidence,
                        fibres=fibres, class_of=_class_of),
        ObservationRepository(db),
        BreachRegister(BreachRepository(db), findings, evidence),
        catalogue, evidence, telemetry, registry)

    def _class_of_urn(urn: str):
        """The same lookup, addressed the way the defaults helper is called.

        `_class_of` above takes a model id because the monitor registry has one
        in hand; a caller asking "what should this model be watched for" has a
        urn. Two spellings of one lookup rather than two implementations.
        """
        versions = registry.versions(urn)
        return versions[-1]["trainability_class"] if versions else None

    def _tier_of_urn(urn: str):
        model = registry.get(urn)
        return (model or {}).get("tier")

    monitoring_defaults = MonitoringDefaults(
        monitoring.registry, fibres, _class_of_urn, _tier_of_urn)

    features = FeatureRegistry(FeatureRepository(db), FeatureViewRepository(db),
                               FeatureViewVersionRepository(db), ContractRepository(db),
                               SnapshotRepository(db), table_store, evidence,
                               DerivedFeatureRepository(db), FeaturesetRepository(db),
                               FeaturesetVersionRepository(db),
                               sources=FeatureSourceRepository(db),
                               credentials=_credential_resolver(cfg))

    # Assigned rather than injected: the warrant service is built before the
    # feature registry because a warrant is resolvable without features, but a
    # FIT warrant is not checkable without them.
    warrants.featuresets = features.sets

    # Parameters are recorded against the version that was fitted, only under a
    # warrant this register issued, and named by the featureset that produced them.
    parameters = ParameterRegister(ParameterSetRepository(db), registry, evidence,
                                   warrants, features.sets,
                                   snapshots=SnapshotRepository(db))
    # Late-bound in the other direction too, and for the same reason: the two
    # refer to each other. A warrant names the point of P a run is at; the
    # register knows which point is approved.
    warrants.parameters = parameters

    # The rule-set editor. It composes the register and the parameter register
    # and adds no authority of its own — publishing is `parameters.record` with
    # a validated document, so the set still lands `proposed` and still needs a
    # second person.
    rules = RuleSetEditor(registry, parameters, evidence)

    # How one model stands to another. Separate from the registry because the
    # registry is about a model in isolation and this is about the estate.
    # With versions wired, a `input_to` edge is type-checked rather than recorded:
    # what the source produces must stand in for what the target reads.
    composition = ModelComposition(ModelEdgeRepository(db), registry.catalogue,
                                   evidence, VersionRepository(db))

    # Where serialised models live, addressed by what they are rather than
    # where somebody put them.
    artifacts = ArtifactStore(Path(cfg.get("data.artifacts",
                                           str(ROOT / "data" / "artifacts"))))
    # So a version naming a digest MAYA holds is resolved against the store
    # rather than believed: the uri, the size and the format come from what is
    # actually there.
    registry.attach_artifacts(artifacts)

    # Request defaults, selected by facts the platform derives rather than by a
    # category anybody attached. A profile fills holes in a warrant request; it
    # never overrides a caller and never widens authority.
    warrant_profiles = WarrantProfileRegister(WarrantProfileRepository(db), evidence)

    capabilities = CapabilityRegistry(CapabilityRepository(db), evidence)
    generations = GenerationLog(GenerationRepository(db), capabilities, evidence)
    # Which model this instance may ask. The default is the mock, which
    # exercises the whole governed path -- capability gating, oracles,
    # grounding, attestation, sampling -- without calling anything. Every
    # other provider refuses by name until somebody has answered the
    # egress and confidentiality questions for their deployment.
    # What each capability may spend per rolling window, checked BEFORE the
    # provider is asked. A budget checked afterwards is an invoice.
    assist_budgets = BudgetRegister(capabilities, SpendRepository(db),
                                    evidence)
    drafting = DraftingService(
        generations, capabilities, evidence,
        assist_providers.build(cfg.get("assist.provider", "mock")),
        budgets=assist_budgets)

    # A base model moves underneath its own version string, and nothing else
    # here would notice. Fixed trivial probes, digested; a change puts the
    # review sample back to 1.0 rather than suspending anything.
    canaries = CanaryRegister(capabilities, drafting.provider, evidence)

    overlays = OverlayRegister(
        OverlayRepository(db), MeasurementRepository(db), evidence, findings,
        max_days=cfg.get_int("overlays.max_days", 180),
        renewal_limit=cfg.get_int("overlays.renewal_limit", 2),
        # An overlay adjusts a model's OUTPUT, and a model's output is another
        # model's input — so approving one walks the typed graph and tells the
        # owners downstream. SS1/23 3.4(d): a downstream owner whose PD feed
        # quietly gained an uplift did not change anything, will not see it in
        # their own monitoring for a quarter, and will spend that quarter
        # looking for it in their own model.
        composition=composition)

    # Activated before the compiler is built, because a document states which
    # supervisors apply and an inactive regime has nothing to say.
    regimes = RegimeEngine(evidence)
    for key in cfg.get_list("regimes.active", ["sr-26-2"]):
        regimes.activate(key)

    # What arrived from outside, looked at before it is trusted. Two of the
    # five checks the requirement names need an engine this platform does not
    # ship, and an unwired port is REPORTED rather than passed.
    upload_scanner = UploadScanner(
        licences=tuple(cfg.get("scanning.allowed_licences",
                               list(DEFAULT_LICENCES))))

    attachments = AttachmentRegister(
        AttachmentRepository(db),
        DocumentStore(Path(cfg.get("data.attachments",
                                   str(ROOT / "data" / "attachments")))),
        registry, evidence, scanner=upload_scanner)

    # Built here rather than in the context dict below, because the document
    # context builder needs them too and two instances would be two registers.
    limitations = LimitationRegister(LimitationRepository(db), registry, evidence)
    # The monitor repository is passed so an assumption claiming to be tested
    # by a monitor can be checked against the monitors that exist — and against
    # the model they are on, because a monitor watching somebody else's scores
    # would otherwise pass as coverage.
    assumptions = AssumptionRegister(AssumptionRepository(db), registry,
                                     evidence, monitors=MonitorRepository(db),
                                     findings=FindingRepository(db),
                                     overlays=OverlayRepository(db))

    # Controls this estate is not meeting, and who said so. Given the finding
    # register because a waiver renewed past its limit stops being a temporary
    # exception and becomes the framework the model is actually governed under.
    waivers = WaiverRegister(
        WaiverRepository(db), evidence, registry, findings=findings,
        max_days=cfg.get_int("waivers.max_days", 90),
        renewal_limit=cfg.get_int("waivers.renewal_limit", 3))

    invocations = InvocationLog(
        InvocationRepository(db), registry=registry, warrants=warrants,
        idle_days=cfg.get_int("warrants.idle_days", 90))

    # What each model was approved for, against what it is actually used for.
    # Every individual call is already legitimate — off-label use is a pattern
    # of good calls, and nothing was looking at the pattern.
    use_reconciliation = UseReconciliation(
        invocations, warrants, registry, findings=findings,
        attempt_threshold=cfg.get_int("warrants.off_label_attempts", 20),
        window_days=cfg.get_int("warrants.reconcile_window_days", 90))

    # The feeds under the models, judged against their own history rather than
    # against an SLA somebody set at onboarding and nobody revisited.
    def _models_using_view(view_name: str):
        """Every model whose featureset pins this view.

        A feature view is not a model and findings hang off models, so an
        upstream problem is raised against whoever actually has to act on it.
        """
        rows = db.query(
            "SELECT DISTINCT m.id, m.owner FROM model m "
            "JOIN feature_contract c ON c.model_version_id IN "
            "  (SELECT id FROM model_version WHERE model_id = m.id) "
            "JOIN feature_view v ON v.name = :v", {"v": view_name})
        return [dict(r) for r in rows]

    pipeline_health = PipelineHealth(
        features.views, findings=findings, registry=registry,
        models_using=_models_using_view)

    # Material or not, computed from the two versions rather than asked of
    # somebody who has an opinion about how much work revalidation is.
    changes = ChangeClassifier(registry, evidence, validation=validation)

    # Proportionality is not a discount: it is what makes the expensive
    # controls affordable where they are needed. This path says what an
    # immaterial model owes, what it explicitly does not, and watches for the
    # condition that would mean it is no longer immaterial.
    immaterial = ImmaterialPath(
        registry, tiering, invocations=invocations, composition=composition,
        risk_repo=RiskRepository(db), findings=findings)

    # What a model will be watched for, written down before it goes anywhere.
    # `inherited_at` is the column that carries the point: null means this
    # model has a monitoring plan and is not monitored.
    monitoring_plans = MonitoringPlans(
        MonitoringPlanRepository(db), registry, monitoring.registry, evidence,
        defaults=monitoring_defaults)

    # The register as it stood on a date that has passed — the question every
    # examination opens with. Folded from the evidence chain rather than kept
    # in a parallel history table, so the answer carries the chain hash at its
    # own sequence and is verifiable rather than merely asserted.
    as_at = AsAtProjection(evidence, registry)

    # What each model is used FOR, as a thing rather than as a string on a
    # grant. The same model used for two purposes is two risk propositions,
    # and a use with an end date is the only thing that catches the commonest
    # form of misuse: a use somebody approved, for a period that ended, which
    # nobody switched off.
    uses = ModelUses(ModelUseRepository(db), registry, evidence,
                     warrants=warrants)

    # What a validation must cover, derived from what the class owes and how
    # deeply the tier requires it answered; and when the next one is due, from
    # triggers rather than from a calendar.
    validation_plans = ValidationPlans(
        registry, fibres, validation=validation, monitoring=monitoring,
        changes=changes)

    # One number for a model and the six that made it. Nothing is stored: a
    # health score that is written down is stale, and staleness is exactly the
    # condition it exists to detect. The score is a weighted mean over what
    # could be measured; the BAND is that mean capped by conditions no amount
    # of good news elsewhere may outweigh, and when the two disagree the
    # disagreement is the finding.
    model_health = ModelHealth(
        registry, monitoring=monitoring, findings=findings, overlays=overlays,
        plans=validation_plans, pipeline_health=pipeline_health,
        catalogue=catalogue)

    # Champion against challenger, paired window by window. Significance and
    # materiality are asked separately — with enough windows any difference is
    # significant — and the strongest recommendation available is to open a
    # validation, never to promote: MAYA does not decide which model the bank
    # uses, and promotion is a second-line approval this must not pre-empt.
    challengers = ChampionChallenger(registry, monitoring, catalogue,
                                     aliases=registry.alias_service)

    # Numbers MAYA did not compute. It takes the value and refuses the verdict:
    # the threshold is this firm's and the comparison happens here, because an
    # external system that could mark its own homework is the failure mode
    # every "push your metrics to us" API has.
    external_monitoring = ExternalObservations(monitoring, registry, catalogue,
                                               evidence)

    # A matter a supervisor raised. Not a finding, in two structural ways:
    # it reaches many models at once, and it carries the date the FIRM GAVE
    # THE SUPERVISOR beside the internal remediation date every finding
    # derives from its severity. Conflating those two is how a firm discovers
    # on the day that its plan ran past its commitment.
    supervisory = SupervisoryMatters(
        SupervisoryMatterRepository(db), registry, findings, evidence)

    # The validation queue. Workload is derived and capacity is declared: a
    # platform that guessed how many validations a person can run would produce
    # a forecast nobody could dispute, which is worse than none because it
    # survives the meeting.
    validation_capacity = ValidationCapacity(
        ValidatorCapacityRepository(db), registry, validation,
        plans=validation_plans, evidence=evidence)

    # Two implementations of one model, and the shape of their disagreement —
    # which is the reading a pass rate cannot give.
    recode = RecodeHarness(validations=validation, evidence=evidence)

    # What each lifecycle move costs this class at this tier. One state graph,
    # nine sets of obligations — and the first consumer `Fibre.evidence` has
    # ever had. The chain is passed because time-in-state is folded from it
    # rather than kept in a column that would drift.
    lifecycle_profiles = LifecycleProfiles(
        registry, fibres, attachments=attachments, evidence=evidence)

    # What the platform's own generative assistance is actually doing. Almost
    # nothing new is measured: the generation log, the spend ledger and the
    # injection scan already record it, and this says what it means.
    assist_monitoring = AssistMonitoring(generations, capabilities,
                                         spend=SpendRepository(db))

    # A mutating request somebody may send twice, and the answer to the first.
    idempotency = IdempotencyStore(IdempotencyRepository(db))

    # Validating a model the firm did not build — which means validating its
    # USE of it, because you cannot validate what you cannot see.
    vendor_assessments = VendorAssessments(
        VendorAssessmentRepository(db), VendorItemRepository(db), registry,
        evidence, validation=validation)

    # A model that changes itself has no version bump for anything to notice,
    # and the parameter trajectory is the only place the change is visible.
    adaptive_change = AdaptiveChange(parameters, registry, fibres=fibres,
                                     findings=findings)

    # A challenger running beside the champion. MAYA runs neither: it takes
    # delivery of what both produced and reports the shape of the
    # disagreement — apart from the outcomes analysis, which needs labels that
    # arrive months later.
    parallel_runs = ParallelRuns(
        ParallelRunRepository(db), ParallelObservationRepository(db),
        registry, evidence, recode=recode)

    # Approving on terms, where the terms are checked by something. SR 26-2 V
    # permits use before validation with compensating controls; this is what
    # makes those controls enforced rather than promised.
    approval_conditions = ApprovalConditions(
        ApprovalConditionRepository(db), registry, evidence,
        validation=validation, warrants=warrants)
    warrants.conditions = approval_conditions

    # What one grant may spend: a rate that protects the downstream system, a
    # quota that protects the authorisation, a cost budget that protects the
    # invoice. Checked before a descriptor is signed.
    grant_quotas = GrantQuotas(warrants, invocations, evidence)
    warrants.quotas = grant_quotas
    approval_conditions.quotas = grant_quotas

    # What changed between two versions, as a diff a person reads. L-7 and
    # L-12 decide whether an alias MAY move; that is a different question.
    version_comparison = VersionComparison(
        registry, validation=validation, parameters=parameters,
        attachments=attachments)

    # Emergency elevation with a second signature, an end, and a mandatory
    # review — as opposed to the standing admin account, which is not
    # break-glass however it is described.
    break_glass = BreakGlass(BreakGlassRepository(db), principals, evidence,
                             findings=findings)

    # A feature has carried a sensitivity since the catalogue was written and
    # nothing ever read it. The join propagates it: a model is at least as
    # sensitive as the most sensitive thing it reads.
    data_classification = Classification(registry, features,
                                         parameters=parameters)

    # Comparing the runs under a version, and saying whether any of them could
    # be repeated — which is a claim about what is recorded, not a badge.
    experiments = Experiments(parameters, registry)

    # Where a fit on sensitive data may run. Enforced at warrant issue, because
    # MAYA does not run the training and cannot observe the machine.
    compute_zones = ComputeZones(
        zones=cfg.get("compute.zones", []) or [],
        classification=data_classification, evidence=evidence)
    warrants.zones = compute_zones


    # Finding the sentence in the document nobody remembered filing. Scoped
    # like everything else: a search that ignored who is asking would be a way
    # to read models a reader cannot see, one query at a time.
    document_search = DocumentSearch(attachments, registry, authz=authz)

    # The value the model was trained on against the value it was given. MAYA
    # does not hold the online store — building one would put the platform on
    # the serving path, which its own design says it must never be — so the
    # engine says what it served and this compares it against BOTH offline
    # clocks, which is what separates a stale value from a leaked one.
    skew = SkewDetector(evidence)

    # Everything a version is made of, in a form somebody else's scanner
    # reads. Derived, never authored: an authored BOM is a document that was
    # true once.
    bom = BillOfMaterials(registry, features=features, parameters=parameters)

    # Who built the artifact. A digest establishes integrity and a signature
    # establishes ORIGIN, and only the second says it came from your own build.
    # MAYA verifies attestations and does not mint them: signing belongs in a
    # build system, and a platform that signed would hold the key that forges.
    provenance = ArtifactProvenance(
        trusted=cfg.get("artifacts.trusted_builders", []) or [],
        evidence=evidence,
        require_verified=cfg.get_bool("artifacts.require_provenance", False))

    # A permission a supervisor gave, with what it covers and when it lapses.
    # Recorded BESIDE the tier and never folded into it.
    regulatory_approvals = RegulatoryApprovals(
        RegulatoryApprovalRepository(db), registry, evidence)

    # What a change to the tiering rules would do to the estate you have. The
    # tiering approach is itself a model (SS1/23 1.3(d)), and the change to it
    # is the interesting act.
    tiering_whatif = TieringWhatIf(tiering, registry, RiskRepository(db),
                                   approvals=regulatory_approvals)

    # Things a scanner found that might be models. MAYA does not crawl the
    # bank's drives — that needs the broadest read access anybody in the firm
    # holds — so it takes delivery, records the triage, and grades the scanner
    # from the dismissals as much as from the registrations.
    discovery = DiscoveryRegister(DiscoveryRepository(db), registry, evidence,
                                  findings=findings)

    # Which parts of this platform a deployment may extend. Four axes are
    # open; four are closed because a plugin there would be a removal rather
    # than an extension, and each refusal names what the closure protects.
    extensions = ExtensionPoints(evidence)

    # A matter that stops things being deleted — the one control here that
    # overrides the platform's own deletion, which is why the inference log
    # asks it from inside its own expiry rather than beside it.
    legal_holds = LegalHolds(LegalHoldRepository(db), evidence, registry)
    retention = RetentionSchedule(worm=getattr(evidence, "anchors", None),
                                  holds=legal_holds)

    # What a model was asked and answered. The digest is the default and the
    # values are the exception, because content carries personal data — so this
    # table has a sampling rate, a retention period and a classification, and
    # none of them is optional.
    inference = InferenceLog(
        InferenceRepository(db), registry,
        classification=data_classification,
        key=cfg.get("inference.digest_key", ""),
        holds=legal_holds)


    context = ContextBuilder(registry, evidence, RiskRepository(db), features,
                             validation, findings, monitoring, lifecycle,
                             warrants, overlays, regimes, attachments,
                             limitations=limitations, assumptions=assumptions)
    documents = DocumentCompiler(DocumentRepository(db), evidence, context)

    # The pack uses the SAME context builder the compiler does. Two gatherers
    # would be two answers to "what is true about this model", and the second
    # would drift from the first in exactly the places nobody looks.
    # The document a daily recalibration never had, and the graph that finds it
    # from the model it belongs to.
    training_records = TrainingRecordCompiler(
        DocumentRepository(db), parameters, registry, evidence, features)
    dossier = Dossier(registry, attachments, DocumentRepository(db),
                      ParameterSetRepository(db), features, features, validation)

    export = ExportPacker(context, documents, attachments, evidence, registry,
                          dossier)

    # Replay reads the snapshot an episode was pinned to, at the Delta version
    # it was pinned at, so the control does not depend on the caller still
    # holding the numbers.
    replayer = Replayer(validation, catalogue,
                        SnapshotProvider(SnapshotRepository(db),
                                         table_store, features))

    # The quorum records its outcome through the registry, and the registry
    # refuses a single signature where the quorum applies. Connected explicitly
    # in both directions rather than through a circular constructor.
    approvals = VersionApproval(
        VersionApprovalRepository(db), VersionApprovalSignatureRepository(db),
        registry, evidence,
        quorum=_tier_roles(cfg, "lifecycle.version_approval.quorum"))
    registry.attach_quorum(approvals.refuse_without_quorum)

    debts = DebtRegister(DebtRepository(db), evidence, findings)
    baseline = BaselineImporter(ImportRepository(db), debts, registry, evidence,
                                documents.build_context)

    # Both are derived from the services above rather than from tables of their
    # own: a task table or a summary table would be a second source of truth.
    worklist = WorkList(registry, lifecycle, findings, monitoring, overlays,
                        documents, debts, validation, finding_workflow,
                        # So a version moving beneath a model reaches the person
                        # who reads it. The blast radius answered this correctly
                        # all along and nobody was told: a pull where a change
                        # process needs a push.
                        composition=composition)

    # Telling other systems what happened, from the record of what happened.
    # A cursor over the evidence chain rather than a second event log — and off
    # unless somebody creates a subscription, because a webhook is the first
    # thing here that deliberately reaches outward.
    event_stream = EventStream(evidence)
    subscriptions = Subscriptions(
        SubscriptionRepository(db), event_stream, evidence,
        sender=http_sender(cfg.get_float("events.timeout_seconds", 10.0))
        if cfg.get_bool("events.deliver", True) else None)

    # The register cut by the dimensions somebody asks about, and the trend —
    # which is a series of as-at folds rather than a snapshot table that would
    # be wrong for every date before somebody added it.
    portfolio = Portfolio(registry, worklist=worklist, as_at=as_at,
                          risk=RiskRepository(db))

    # Delivery, not a queue: the work is derived, and this makes it arrive
    # somewhere rather than waiting to be looked at.
    # None unless an issuer is configured: local credentials only is the
    # default, because an instance that silently required a directory to be
    # reachable would lock everybody out the first time it was not.
    # Versioned gates. They TIGHTEN: every check written in the registry stays
    # where it is, and a policy runs in addition to it. A rule that could remove
    # a check would let a typo weaken the platform and look like a successful
    # deployment.
    policies = PolicyRegister(PolicyRuleRepository(db), evidence)
    # The facts the gates judge on, from the registers that hold them.
    gate_facts = GateFacts(findings=findings, documents=documents,
                           validation=validation, approvals=approvals,
                           parameters=parameters, attachments=attachments)
    registry.attach_policy(PolicyGate(policies, RegistryError), gate_facts)
    warrants.policy = PolicyGate(policies)
    warrants.facts = gate_facts

    oidc = build_oidc(cfg)

    notifications = NotificationService(
        NotificationRepository(db), worklist, principals, authz, registry,
        evidence, build_channels(cfg),
        cfg.get("notifications.channel", "log"),
        cfg.get_float("notifications.quiet_hours", 24.0),
        cfg.get_float("notifications.escalate_after_days", 7.0),
        cfg.get("notifications.base_url", ""))

    estate = EstateSummary(registry, findings, monitoring, overlays, debts,
                           baseline, lifecycle, regimes, documents)

    # Portfolio reporting reads the SAME services the estate summary and the
    # model page read. A board pack with its own numbers is a board pack that
    # disagrees with the platform, and the disagreement surfaces in a committee
    # meeting where nobody present can resolve it.
    appetite = AppetiteRegister(RiskAppetiteRepository(db), evidence)
    board_packs = BoardPackBuilder(
        BoardPackRepository(db),
        IndicatorSet(registry, findings, monitoring, overlays, baseline,
                     lifecycle),
        appetite, registry, evidence)

    # A read layer for the bank's own BI tools, and the one thing it must not
    # be. Handing out SQL is not a semantic layer, it is a database credential
    # with a nicer name: the first thing a dashboard does with table access is
    # invent its own definition of "in force", which lives ungoverned and is
    # the one on the slide. So this publishes entities and fields, computes
    # every derived field with the same code the screens use, accepts no query
    # text anywhere, and filters ROWS by the reader's scope rather than
    # refusing the call.
    semantics = SemanticLayer(db, registry, findings=findings,
                              monitoring=monitoring, lifecycle=lifecycle)

    # A saved view holds the QUERY and never the rows. Storing a result set
    # would make sharing a view a disclosure nobody realised they were making:
    # the author's scope reaches models the reader's does not.
    saved_views = SavedViews(SavedViewRepository(db), semantics, evidence)

    # Extracts for supervisory returns. MAYA extracts and does not file, and a
    # field the register cannot answer is emitted empty and named — a plausible
    # value in a box nobody knew the answer to is the one output here that gets
    # sent to a supervisor.
    regulatory_returns = RegulatoryReturns(
        registry, validation=validation, findings=findings,
        monitoring=monitoring, vendor=vendor_assessments)

    # A question in English becomes a QUERY and never a number. The
    # translation is checked against the published catalogue before anything
    # runs, the rows come from the register under the reader's own scope, and
    # the query is shown beside them — an interface that shows only the answer
    # is one where nobody can tell a misread question from a wrong number.
    nl_query = NaturalLanguageQuery(semantics, provider=None)

    # What is still owed, computed rather than proposed: the tropical
    # semiring over a published derivation gives the cheapest route to a model
    # being in force. Only acts that PRODUCE EVIDENCE are in the plan — a
    # waiver makes the claim true without making the model safer, is genuinely
    # cheaper, and a shortest-path solver with no opinion about kind would
    # recommend it every time.
    remediation = RemediationPlanner(
        registry, findings=findings, validation=validation,
        monitoring=monitoring, documents=documents,
        costs=cfg.get("remediation.costs", {}) or {})

    # Reads obligations out of regulatory prose and PROPOSES an encoding —
    # a form name and some term names, never a predicate: a language model
    # emitting code that decides what a regulation obliges is where a
    # governance platform starts making up the law. Nothing it produces is
    # activated: the check passing says the draft is self-consistent, which is
    # a far weaker claim than that it reads the regulation correctly.
    regime_encoding = RegimeEncodingAssistant()

    # Probes derived from a version's declared domain and never sampled from
    # data. The interior is where two implementations agree; they come apart at
    # the boundary. MAYA proposes them and does not run them — running a probe
    # means running the model.
    probe_sets = ProbeSets(registry)

    # An artifact converted from one format to another, and the claim that it
    # is the same model. MAYA converts nothing and runs nothing: it holds
    # somebody else's equivalence measurement to a standard and refuses.
    migration = FormatMigration(registry, probe_sets, evidence)

    # Three pieces of a validator's work, and not one of them a conclusion:
    # retrieval over filed vendor documents, questions derived from findings on
    # comparable models, and an exact filter over the assumption register —
    # each labelled with which of the three it is, because a page that mixed
    # them would get one level of trust applied to all.
    validation_aid = ValidationAssistant(
        registry, findings=findings, assumptions=assumptions,
        vendor=vendor_assessments, search=document_search,
        monitoring=monitoring)

    scheduler = Scheduler(
        ScheduledRunRepository(db), evidence,
        JobContext(registry=registry, now=0.0, lifecycle=lifecycle,
                   findings=findings, monitoring=monitoring, overlays=overlays,
                   debts=debts, documents=documents,
                   notifications=notifications,
                   finding_workflow=finding_workflow,
                   evidence=evidence, risk=RiskRepository(db),
                   waivers=waivers,
                   uses=use_reconciliation,
                   pipeline=pipeline_health,
                   immaterial=immaterial,
                   lifecycle_profiles=lifecycle_profiles,
                   canaries=canaries,
                   break_glass=break_glass,
                   idempotency=idempotency,
                   inference=inference,
                   subscriptions=subscriptions,
                   adaptive=adaptive_change,
                   discovery=discovery,
                   approvals=regulatory_approvals, health=model_health),
        # The configured cadence, so `health` can say the batch has STOPPED
        # rather than only how many hours it has been. A dead scheduler makes
        # the estate look clean, not stale, because every lapse it records is
        # derived rather than stored.
        interval_seconds=cfg.get_float("scheduler.loop.interval_seconds", 3600.0))

    # L-17: what an engine says it served, against what the contract pins.
    # MAYA does not read the online store — it does not own one, deliberately —
    # so the engine declares and the platform compares.
    serving = ServingRegister(ServingAttestationRepository(db),
                              features.contracts, registry, evidence)

    # L-14: aggregate risk, and the interaction premium that makes it lax.
    aggregate = AggregateRisk(registry.catalogue, composition)

    ctx: Dict[str, Any] = {"config": cfg, "db": db, "delta": delta, "features": features,
                           "evidence": evidence, "serving": serving,
                           # The store, so `/health` can say which table
                           # format holds the feature data without
                           # constructing a second one to ask.
                           "table_store": table_store,
                           "aggregate": aggregate,
                           "registry": registry, "composition": composition, "fibres": fibres,
                           "rules": rules,
                           "artifacts": artifacts,
                           "warrant_profiles": warrant_profiles,
                           "export": export, "dossier": dossier,
                           "training_records": training_records, "tiering": tiering, "warrants": warrants,
                           "risk_repo": RiskRepository(db), "engine": None,
                           "roles": role_store,
                           "api_keys": ApiKeyRegister(
                               ApiKeyRepository(db), principals, authz, evidence),
                           "references": ReferenceIndex(db, registry, features),
                           "limitations": limitations,
                           "assumptions": assumptions,
                           "waivers": waivers,
                           "invocations": invocations,
                           "use_reconciliation": use_reconciliation,
                           "pipeline_health": pipeline_health,
                           "changes": changes,
                           "immaterial": immaterial,
                           "monitoring_plans": monitoring_plans,
                           "as_at": as_at,
                           "uses": uses,
                           "validation_plans": validation_plans,
                           "supervisory": supervisory,
                           "validation_capacity": validation_capacity,
                           "recode": recode,
                           "lifecycle_profiles": lifecycle_profiles,
                           "findings": findings, "validation": validation,
                           "finding_workflow": finding_workflow,
                           "test_catalogue": catalogue,
                           "principals": principals, "authz": authz,
                           "lifecycle": lifecycle, "monitoring": monitoring,
                           "monitoring_defaults": monitoring_defaults,
                           "documents": documents, "attachments": attachments,
                           "parameters": parameters, "replayer": replayer,
                           "approvals": approvals, "telemetry": telemetry,
                           "notifications": notifications, "oidc": oidc,
                           "policies": policies,
                           "overlays": overlays,
                           "capabilities": capabilities, "generations": generations,
                           "drafting": drafting,
                           "assist_budgets": assist_budgets,
                           "assist_monitoring": assist_monitoring,
                           "canaries": canaries,
                           "classification": data_classification,
                           "break_glass": break_glass,
                           "version_comparison": version_comparison,
                           "idempotency": idempotency,
                           "inference": inference,
                           "legal_holds": legal_holds,
                           "document_search": document_search,
                           "upload_scanner": upload_scanner,
                           "extensions": extensions,
                           "skew": skew,
                           "discovery": discovery,
                           "regulatory_approvals": regulatory_approvals,
                           "bom": bom,
                           "artifact_provenance": provenance,
                           "tiering_whatif": tiering_whatif,
                           "retention": retention,
                           "grant_quotas": grant_quotas,
                           "approval_conditions": approval_conditions,
                           "parallel_runs": parallel_runs,
                           "adaptive_change": adaptive_change,
                           "semantics": semantics,
                           "nl_query": nl_query,
                           "regime_encoding": regime_encoding,
                           "probe_sets": probe_sets,
                           "remediation": remediation,
                           "migration": migration,
                           "validation_aid": validation_aid,
                           "saved_views": saved_views,
                           "regulatory_returns": regulatory_returns,
                           "model_health": model_health,
                           "challengers": challengers,
                           "external_monitoring": external_monitoring,
                           "experiments": experiments,
                           "compute_zones": compute_zones,
                           "vendor_assessments": vendor_assessments,
                           "portfolio": portfolio,
                           "event_stream": event_stream,
                           "subscriptions": subscriptions,
                           "debts": debts, "baseline": baseline,
                           "regimes": regimes, "worklist": worklist,
                           "estate": estate, "scheduler": scheduler,
                           "default_credentials_live": default_credentials_live,
                           "scheduler_loop_enabled": cfg.get_bool(
                               "scheduler.loop.enabled", False),
                           "appetite": appetite, "board_packs": board_packs,
                           "renderer": MarkdownRenderer(),
                           "content": ContentLibrary(
                               Path(cfg.get("content.dir", str(ROOT / "content")))),
                           }
    if cfg.get_bool("execution.captive.enabled", True):
        # A consumer of the public warrant contract, nothing more.
        chosen = cfg.get("execution.captive.sandbox", "subprocess")
        ctx["engine"] = CaptiveEngine(
            warrants, cfg.get_float("execution.captive.max_seconds", 30.0),
            artifact_dir=Path(cfg.get("data.artifacts", str(ROOT / "data" / "artifacts"))),
            sandbox=SubprocessSandbox() if chosen == "subprocess" else InProcessSandbox(),
            # So a warrant naming a point of P can be honoured: the engine reads
            # the values and checks their digest before anything runs at them.
            parameters=parameters,
            # So the estate can answer how much a model is actually used, when
            # a standing grant was last exercised, and which grants nobody has
            # ever used — the last being a security question rather than a
            # reporting one.
            invocations=invocations)
        # Fitting needs an engine to run the estimator in, so it is wired here
        # rather than beside the register: an instance with the captive engine
        # switched off can still record a fit performed elsewhere, and cannot
        # perform one itself. That is the honest shape of the dependency.
        ctx["fitting"] = FittingService(
            ctx["engine"], warrants, parameters, features,
            SnapshotRepository(db), table_store, evidence)
    return ctx


# Session secrets that ship in this repository, and are therefore public. A
# deployment on one of these can have its session cookie forged by anybody with
# a copy of the source -- no password required.
PUBLISHED_SESSION_SECRETS = frozenset({
    "maya-development-secret", "maya-development-secret-change-me", "", "changeme"})


def _session_secret(cfg) -> str:
    """The cookie-signing secret, and a loud complaint if it is a published one.

    It used to fall back silently to a constant in this file, which meant a
    deployment that simply did not set the key got a signing secret anybody
    could look up. Forging `session={"username": "admin"}` then needed no
    credentials at all. The fallback stays -- refusing to start would be worse
    for a workstation -- but it is now impossible to do by accident quietly.
    """
    secret = cfg.get("auth.session_secret", "maya-development-secret")
    if secret in PUBLISHED_SESSION_SECRETS:
        get_logger("maya").warning(
            "the session cookie is signed with a PUBLISHED secret. Anyone with "
            "a copy of this repository can forge a signed-in session as any "
            "user, including admin, with no password. Set auth.session_secret "
            "(or MAYA_SESSION_SECRET) before this instance is reachable by "
            "anybody else.")
    return secret


def _pin_writer(store: Any):
    """A filter that renders a storage version the way its format numbers them.

    Delta's are sequential and short, so `delta v3` reads well. Iceberg's are
    int64 snapshot ids, where the full number is noise on a table and the last
    digits are enough to tell two apart — the whole value is on the element's
    title for anybody who needs to quote it.
    """
    fmt = getattr(store, "format", "delta")

    def pin(value: Any) -> str:
        if value is None or value == "":
            return "—"
        if fmt == "delta":
            return f"delta v{value}"
        text = str(value)
        return f"iceberg …{text[-6:]}" if len(text) > 8 else f"iceberg {text}"

    return pin


def _credential_resolver(cfg: PropertiesConfigurator):
    """Turn a credential NAME into the keyword arguments a connector needs.

    A feature source names a credential; it never holds one. This is what turns
    that name into something usable, from `sources.credentials.<name>` in the
    configuration or from the environment — so a warehouse password lives where
    the deployment already keeps its secrets and not in a register that is
    meant to be handed to an auditor.

    An unknown name resolves to nothing rather than raising: the connector then
    tries the ambient credentials, which is right for the common case of an
    instance running with an instance profile or a local `~/.aws`.
    """
    def resolve(name: Optional[str]) -> Optional[Dict[str, Any]]:
        if not name:
            return None
        configured = cfg.get(f"sources.credentials.{name}", None)
        if isinstance(configured, dict):
            return configured
        # Environment fallback: MAYA_SOURCE_<NAME> holding a JSON object. One
        # variable per credential rather than one per field, because a
        # connector's arguments differ by kind and enumerating them here would
        # be this file knowing what a warehouse driver wants.
        raw = os.environ.get(f"MAYA_SOURCE_{name.upper().replace('-', '_')}")
        if not raw:
            logger.warning(
                "a feature source names the credential '%s' and nothing in "
                "this deployment defines it. The connector will fall back to "
                "ambient credentials, which may be right — set "
                "sources.credentials.%s, or MAYA_SOURCE_%s, to be explicit.",
                name, name, name.upper().replace("-", "_"))
            return None
        try:
            parsed = json.loads(raw)
        except ValueError as exc:
            swallowed(logger, exc, f"read the credential '{name}'",
                      detail="the environment variable is not a JSON object; "
                             "the connector falls back to ambient credentials",
                      level=logging.ERROR)
            return None
        return parsed if isinstance(parsed, dict) else None

    return resolve


def _when(epoch: Any, absent: str = "—") -> str:
    """An epoch second as a date somebody can read, in local time.

    Local rather than UTC because this renders in a browser for a person
    sitting somewhere, and the alternative — a bare float — is what these
    pages showed before, which is to say nothing.
    """
    if not epoch:
        return absent
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(epoch)))
    except (TypeError, ValueError, OSError) as exc:
        swallowed(logger, exc, "rendered a timestamp",
                  detail=f"{epoch!r} is not an epoch second; shown as-is",
                  level=logging.INFO)
        return str(epoch)


def _ago(epoch: Any, absent: str = "—") -> str:
    """How long ago, in the largest unit that is still honest.

    "3 months ago" answers the question a reader is actually asking of a
    `sealed_at`; the exact instant is on the same line for anybody who needs
    it.
    """
    if not epoch:
        return absent
    try:
        delta = time.time() - float(epoch)
    except (TypeError, ValueError) as exc:
        swallowed(logger, exc, "rendered a relative time",
                  detail=f"{epoch!r} is not an epoch second; shown as '{absent}'",
                  level=logging.INFO)
        return absent
    future = delta < 0
    delta = abs(delta)
    for size, unit in ((86400 * 365, "year"), (86400 * 30, "month"),
                       (86400, "day"), (3600, "hour"), (60, "minute")):
        if delta >= size:
            n = int(delta // size)
            return (f"in {n} {unit}{'s' if n != 1 else ''}" if future
                    else f"{n} {unit}{'s' if n != 1 else ''} ago")
    return "just now"


def create_app(cfg: PropertiesConfigurator = None) -> FastAPI:
    cfg = cfg or PropertiesConfigurator(str(ROOT / "config" / "application.yaml"))
    configure(cfg.get("logging.level", "INFO"),
              cfg.get("logging.format", log.FORMAT),
              cfg.get_bool("logging.json", False))
    # How many lines /admin/logs can show. Configurable because the right
    # number depends on how chatty the deployment is: a quiet instance wants a
    # long memory, and a busy one wants a bounded footprint more than it wants
    # an hour of history it will never scroll to.
    log.LIVE.resize(max(200, cfg.get_int("logging.ring", 2000)))
    ctx = build_context(cfg)

    # `docs_url=None` and `redoc_url=None` turn OFF the built-in pages, and
    # `/docs` is re-registered below against vendored assets.
    #
    # FastAPI's own `/docs` and `/redoc` load Swagger UI and ReDoc from
    # `cdn.jsdelivr.net`. The Content-Security-Policy here is `script-src
    # 'self'` — on purpose, because every other asset in this interface is
    # vendored so it renders air-gapped — so both pages were BLANK on every
    # instance with the headers on, which is every instance. The API reference
    # the platform actually advertises was a white screen and nothing said so.
    #
    # The fix is not a CDN exception. A hole in the policy opened for a
    # documentation page, on a platform whose argument is that nothing here
    # calls out, is the wrong trade — so Swagger UI is vendored beside bootstrap
    # and jquery. ReDoc is not: two renderings of one specification is one more
    # than anybody needs, and a second vendored bundle to maintain.
    app = FastAPI(title=cfg.get("app.name", "MAYA"),
                  description=f"{cfg.get('app.tagline')} — {cfg.get('app.slogan')}",
                  version=cfg.get("app.version", "0.1.0"),
                  openapi_url="/api/v1/openapi.json",
                  docs_url=None, redoc_url=None)

    @app.get("/docs", include_in_schema=False)
    def swagger_ui():
        """The interactive specification, served from this origin only."""
        return get_swagger_ui_html(
            openapi_url="/api/v1/openapi.json",
            title=f"{cfg.get('app.name', 'MAYA')} — API",
            swagger_js_url="/static/vendor/swagger-ui/swagger-ui-bundle.js",
            swagger_css_url="/static/vendor/swagger-ui/swagger-ui.css",
            swagger_favicon_url="/static/img/maya-mark-64.png")
    app.state.ctx = ctx
    # Registered BEFORE the session middleware, which puts it INSIDE it: an
    # `add_middleware` added later wraps outside, and a CSRF guard that runs
    # before the session is decoded has no session to compare a token against.
    # It failed loudly rather than silently, which is the only reason this is a
    # comment and not an incident.
    @app.middleware("http")
    async def csrf_guard(request, call_next):
        """Refuse a state-changing request that rides an ambient session cookie
        without proving it came from one of our pages.

        Middleware rather than a check in each route, because there are a
        hundred and fifty mutating endpoints and a control that many places have
        to remember is a control that will be missing from the next one. The
        exemptions are
        exact paths and the condition is narrow — see `core/authz/csrf.py` for
        why it applies only to cookie authority.
        """
        if csrf.required_for(request):
            supplied = request.headers.get(csrf.HEADER)
            if supplied is None and request.headers.get("content-type", "").startswith(
                    ("application/x-www-form-urlencoded", "multipart/form-data")):
                # Read once and stashed: a form body consumed here would not be
                # there for the route, and the failure would look like a
                # missing field rather than a middleware that ate the request.
                form = await request.form()
                request._maya_form = form
                supplied = form.get(csrf.FORM_FIELD)
            if not csrf.matches(request.session.get(csrf.SESSION_KEY), supplied):
                logger.warning("refused a %s to %s: no valid CSRF token on a "
                               "cookie-authenticated request", request.method,
                               request.url.path)
                return JSONResponse({
                    "error": "csrf_token_invalid",
                    "detail": "this request changes something and was "
                              "authenticated by a session cookie, but carries "
                              "no valid CSRF token",
                    # Two audiences, and the old text served neither. It said
                    # "send the token from the page's 'x-maya-csrf' meta tag",
                    # which conflates the HEADER name with the META TAG name and
                    # names a tag that does not exist -- and told a person
                    # sitting in a browser to set an HTTP header, which they
                    # cannot do. The person's instruction comes first, because
                    # a person is who usually reads this.
                    "remediation": f"reload the page and try again: this "
                                   f"usually means the page was open long "
                                   f"enough for its token to go stale. If you "
                                   f"are calling this from a script, read the "
                                   f"value of the page's <meta "
                                   f"name=\"{csrf.META}\"> tag and send it in "
                                   f"the '{csrf.HEADER}' header, or "
                                   f"authenticate with HTTP Basic, which "
                                   f"carries no ambient authority and needs no "
                                   f"token",
                }, status_code=403)
        return await call_next(request)


    app.add_middleware(SessionMiddleware,
                       secret_key=_session_secret(cfg),
                       max_age=cfg.get_int("auth.session_max_age", 28800),
                       same_site="strict",
                       # Configurable, and it was not: `https_only` was hard
                       # coded False, so the session cookie never carried
                       # `Secure` even behind TLS and there was no key to set.
                       https_only=cfg.get_bool("auth.session_https_only", False))

    @app.middleware("http")
    async def entity_tags(request, call_next):
        """Answer *is this still what I read*, and refuse to pretend otherwise.

        Two things, and the second is the one that matters.

        On a **JSON GET** the response carries a weak `ETag` derived from the
        representation itself — never a stored version column, which is a second
        thing to keep in step and says *unchanged* about something that changed
        the first time somebody writes a row without bumping it. `If-None-Match`
        then gets a 304, which is a real saving on the estate views that fold
        the whole evidence chain.

        On a **mutating request carrying `If-Match`**, the precondition is
        evaluated against the current representation of the same path — and if
        that path has no GET to evaluate against, the request is **refused by
        name**. Silently dropping a precondition header is strictly worse than
        not supporting preconditions at all: the client believes it has
        optimistic concurrency, has none, and has stopped checking for itself.
        The lost update it thinks it is preventing is the quietest failure in
        any register — two people edit, both save, the second write discards the
        first, nothing is refused and the only trace is a field nobody typed.
        """
        supplied = request.headers.get(concurrency.IF_MATCH)
        if supplied and request.method in MUTATING:
            current = await _current_etag(app, request)
            try:
                concurrency.require_match(supplied, current, request.url.path)
            except concurrency.PreconditionError as refused:
                logger.warning("refused a %s to %s (%s)", request.method,
                               request.url.path, refused.code)
                return JSONResponse(
                    refused.as_problem(),
                    status_code=REFUSAL_STATUS.get(refused.code, 412),
                    headers={"etag": current} if current else {})

        response = await call_next(request)
        # Read from the header rather than `response.media_type`, which a
        # streaming response coming back through middleware does not carry.
        content_type = response.headers.get("content-type", "")
        if (request.method != "GET" or response.status_code != 200
                or not content_type.startswith("application/json")
                or not hasattr(response, "body_iterator")):
            return response
        captured = b"".join([chunk async for chunk in response.body_iterator])
        try:
            tag = concurrency.etag_of(json.loads(captured))
        except (ValueError, UnicodeDecodeError):
            # Served without a tag rather than with a wrong one. A body
            # declaring application/json that does not parse is a defect
            # somewhere else, and a tag over bytes nobody can compare
            # semantically would be a claim this does not check.
            logger.warning("a response from %s declares JSON and does not "
                           "parse; serving it without an ETag",
                           request.url.path)
            return Response(content=captured, status_code=200,
                            headers=dict(response.headers))
        headers = {**dict(response.headers), "etag": tag}
        if concurrency.matches(request.headers.get(concurrency.IF_NONE_MATCH),
                               tag):
            headers.pop("content-length", None)
            return Response(status_code=304, headers=headers)
        return Response(content=captured, status_code=200, headers=headers)

    # Registered here, which puts it INSIDE the request-context middleware and
    # OUTSIDE the routes: a replayed response must still get a request id and a
    # log line, and the claim must be taken before any route runs.
    @app.middleware("http")
    async def idempotent_replay(request, call_next):
        """Let a client retry a mutating request without doing it twice.

        Middleware rather than a decorator on each route, for the same reason
        the CSRF guard is: there are over a hundred and fifty mutating
        endpoints, and a control that many places have to remember is a control
        that will be missing from the next one.

        **Scoped by credential rather than by principal**, and the distinction
        is not pedantry: this runs before authentication, so it cannot know who
        the caller *is*. What it has is what they presented, and a digest of
        that is a stable per-caller scope that stores nothing sensitive. Two
        callers cannot collide on a key, which is the property that matters,
        and an unauthenticated request never gets that far because the route
        refuses it and the key is released.
        """
        key = request.headers.get(concurrency.HEADER)
        if not key or request.method not in MUTATING:
            return await call_next(request)

        scope = _credential_scope(request)
        body = await request.body()
        store = ctx["idempotency"]
        try:
            replay = store.claim(key, scope, request.method,
                                 request.url.path, body)
        except concurrency.IdempotencyError as refused:
            logger.warning("refused (%s): %s", refused.code, refused)
            return JSONResponse(refused.as_problem(),
                                status_code=REFUSAL_STATUS.get(refused.code, 409))
        if replay is not None:
            logger.info("replaying idempotency key %s for %s %s", key,
                        request.method, request.url.path)
            return Response(content=replay["body"] or "",
                            status_code=replay["status"] or 200,
                            media_type="application/json",
                            headers={concurrency.REPLAYED: "true"})

        try:
            response = await call_next(request)
        except Exception:
            # A key held by a request that blew up is a key that can never be
            # retried, which turns one failure into a permanent one. Re-raised
            # after being recorded, never swallowed.
            logger.warning("releasing idempotency key %s: %s %s failed",
                           key, request.method, request.url.path)
            store.release(key, scope)
            raise

        captured = b"".join([chunk async for chunk in response.body_iterator])
        if 200 <= response.status_code < 300:
            store.complete(key, scope, response.status_code, captured)
        else:
            # Only a success is kept. A recorded failure makes the client's
            # retry replay that failure forever, and the key becomes a
            # tombstone for an act that never happened.
            store.release(key, scope)
        return Response(content=captured, status_code=response.status_code,
                        headers=dict(response.headers))

    # Registered LAST, which puts it OUTERMOST: an `add_middleware` added later
    # wraps the ones before it. That is deliberate here and the opposite of the
    # CSRF guard above — this one must see every request, including the ones the
    # guard refuses and the ones that never reach a route, or the lines with no
    # id would be exactly the lines somebody is trying to chase.
    @app.middleware("http")
    async def request_context(request, call_next):
        """Give every request an id, put it on every line it produces, and say
        how it ended.

        The id is echoed back so a caller can quote it in a bug report, and an
        inbound one is honoured when it is safe to log — that is what lets one
        trace span a gateway, a queue and this process. Honouring it unchecked
        would be log injection, so `accept_request_id` replaces anything that is
        not plainly alphanumeric rather than escaping it.
        """
        request_id = log.accept_request_id(request.headers.get(log.REQUEST_HEADER))
        log.bind_request(request_id)
        # Reset per request rather than trusting the previous one to have
        # cleared: a worker is reused, and a principal left bound would attribute
        # the next caller's lines to the last one.
        log.bind_principal(None)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Never swallowed — re-raised after being recorded, because a 500
            # with no line saying which request produced it is the one failure
            # nobody can chase.
            logger.exception("unhandled failure serving %s %s",
                             request.method, request.url.path)
            raise
        elapsed = (time.perf_counter() - started) * 1000.0
        response.headers[log.REQUEST_HEADER] = request_id
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        # One line per request, at the level its outcome deserves: a refusal is
        # a governance decision worth seeing at INFO, a fault is not routine.
        logger.log(
            logging.ERROR if response.status_code >= 500
            else logging.WARNING if response.status_code >= 400
            else logging.INFO,
            "%s %s -> %s in %.1fms", request.method, request.url.path,
            response.status_code, elapsed,
            # The principal is put on the record explicitly as well as by the
            # context filter. The filter reads a context variable that is gone
            # by the time anything inspects the record afterwards, so the access
            # line — the one an operator greps — carries it by value.
            extra={"method": request.method, "path": request.url.path,
                   "status": response.status_code,
                   "duration_ms": round(elapsed, 1),
                   "principal": log.current_principal()})
        return response


    # Vendored assets only: the interface renders with no external network.
    app.mount("/static", StaticFiles(directory=str(ROOT / "web" / "static")), name="static")
    templates = Jinja2Templates(directory=str(ROOT / "web" / "templates"))
    # Every timestamp in this platform is an epoch second, and until now every
    # page that wanted to show one computed the arithmetic inline — so most of
    # them showed nothing at all. `sealed_at`, `expires_at`, `retired_at` and
    # `created_at` were on no screen anywhere, which made sealing, expiry and
    # retirement facts the register held and could not tell anybody.
    templates.env.filters["when"] = _when
    templates.env.filters["ago"] = _ago
    # How to write a storage pin. Delta numbers versions 0, 1, 2 and Iceberg
    # uses a 19-digit snapshot id, so "delta v0" is both a wrong word and a
    # wrong shape on an Iceberg estate — and the pin is exactly what a reviewer
    # reads to know a namespace cannot move underneath them.
    templates.env.filters["pin"] = _pin_writer(ctx.get("table_store"))

    @app.exception_handler(AuthzError)
    async def refused(_request, exc: AuthzError):
        """Authorisation refusals render in the same shape as every other one."""
        problem = authz_problem(exc)
        return JSONResponse(problem.detail, status_code=problem.status_code,
                            headers=problem.headers)

    @app.exception_handler(HTTPException)
    async def problem(_request, exc: HTTPException):
        """RFC 9457 shape at the TOP level, not nested under `detail`.

        Design rule DR-6 says no failure may be unmapped and DR-7 says a refusal
        must explain itself; both are easier to honour when every error body has
        the same shape, whichever route raised it."""
        body = exc.detail if isinstance(exc.detail, dict) else {
            "error": "error", "detail": str(exc.detail)}
        return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)

    # The in-process loop is a convenience for a single-node deployment. Every
    # job is idempotent and reachable over the API, so cron is an equally
    # supported way to drive the same work.
    if cfg.get_bool("scheduler.loop.enabled", False):
        loop = SchedulerLoop(ctx["scheduler"],
                             cfg.get_float("scheduler.loop.interval_seconds", 3600.0))
        loop.start()
        ctx["scheduler_loop"] = loop
    else:
        # Said out loud, at the same volume as the secret warnings, because the
        # failure it precedes is the quietest one this platform has.
        #
        # Expiry, staleness, cohort maturity, outstanding signatures and missing
        # evidence are all DERIVED when somebody asks. The batch is what turns a
        # derived condition into a recorded consequence — an attestation lapses,
        # a monitor is marked silent, a finding goes overdue, the chain head is
        # anchored. An instance whose batch never runs therefore looks exactly
        # like an estate with nothing outstanding, and it looks that way to
        # every screen, every health probe and every digest.
        #
        # Cron is a supported answer and for more than one replica it is the
        # right one. Nobody wiring it up is the failure.
        logger.warning(
            "the in-process scheduler loop is DISABLED, so nothing in this "
            "instance will run the governance batch. Attestation lapses, silent "
            "monitors, overdue findings and evidence anchoring are all recorded "
            "by that batch — an instance where it never runs is "
            "indistinguishable from an estate with nothing outstanding. Either "
            "set scheduler.loop.enabled, or point cron at "
            "'POST %s/scheduler/run' and check /admin/scheduler afterwards to "
            "confirm it arrived.", cfg.get("api.prefix", "/api/v1"))

    for routes in ALL_ROUTES:
        routes(app, ctx, templates)
    logger.info("%s %s ready — %s database, captive engine %s",
                cfg.get("app.name"), cfg.get("app.version"), ctx["db"].dialect,
                "enabled" if ctx["engine"] else "disabled")
    return app


def config_path() -> str:
    """Which configuration file to start from.

    `--config`, then `MAYA_CONFIG`, then the one in the repository. The path was
    hard-coded, which meant a second instance — a demonstration estate, a
    training environment, a copy of production to reproduce something against —
    could only be started by editing a tracked file, and whoever did that was
    one `git commit -a` away from shipping it.
    """
    argv = sys.argv[1:]
    for i, arg in enumerate(argv):
        if arg == "--config" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--config="):
            return arg.split("=", 1)[1]
    return os.environ.get("MAYA_CONFIG") or str(ROOT / "config" / "application.yaml")


def _repair_schema(cfg: PropertiesConfigurator, apply: bool) -> None:
    """Add the columns the shipped DDL declares and this database lacks.

    `drift()` has always reported precisely what is missing and then said
    "apply the difference by hand" — which is a real chore, and the reason a
    database with months of evidence in it gets deleted rather than fixed.

    This is not a migration tool and does not become one: no version history,
    no ordering, no down-step. The consolidated schema is still the only
    description of the shape; this asks it what is missing and adds exactly
    that, with ALTER TABLE, which cannot lose a row.
    """
    from db import Database

    database = Database(cfg.get("database.url", "sqlite:///data/sqlite/maya.db"))
    plan = database.repair(dry_run=not apply)
    if not any((plan["planned"], plan["refused"], plan.get("indexes"),
                plan.get("types"), plan.get("noted"))):
        print("nothing to repair — the database matches the shipped DDL")
        return
    for step in plan["planned"]:
        print(("  applied  " if apply else "  would run  ") + step["sql"])
    for step in plan.get("types", []):
        print(("  applied  " if apply else "  would run  ") + step["sql"])
    for step in plan.get("indexes", []):
        print(("  created  " if apply else "  would create  ")
              + ("unique " if step["unique"] else "") + f"index {step['index']} "
              + f"on {step['table']}")
    for step in plan["refused"]:
        print(f"  REFUSED  {step['table']}.{step['column']}: {step['why']}")
    if (noted := plan.get("noted")):
        print(f"\n  {len(noted)} column(s) are declared differently from how "
              f"this database spells them, and need no action here:")
        for step in noted:
            print(f"    {step['table']}.{step['column']}: "
                  f"{step['from']} in the database, {step['to']} in the schema")
        print(f"    {noted[0]['why']}")
    print()
    if apply:
        print(f"{len(plan['applied'])} column(s) added, "
              f"{len(plan.get('indexes', []))} index(es) created.")
        remaining = database.drift()
        print("drift after: " + (str(remaining) if remaining else "none"))
    else:
        print(f"{plan['detail']}. Re-run with --repair-schema to apply.")


def main() -> None:
    import uvicorn
    path = config_path()
    if not Path(path).is_file():
        raise SystemExit(f"no configuration file at {path}")
    cfg = PropertiesConfigurator(path)

    # Repair, and exit. Deliberately not something start-up does on its own: a
    # process that alters the schema every time somebody runs it is one nobody
    # can reason about, and the point of the drift report is that a person
    # decides.
    if "--check-schema" in sys.argv or "--repair-schema" in sys.argv:
        _repair_schema(cfg, apply="--repair-schema" in sys.argv)
        return

    logger.info("starting from %s", path)
    uvicorn.run(create_app(cfg), host=cfg.get("server.host", "0.0.0.0"),
                port=cfg.get_int("server.port", 5006))


if __name__ == "__main__":
    main()
