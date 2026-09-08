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
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from core.authz import csrf
from fastapi.templating import Jinja2Templates

from core.execution import (CaptiveEngine, InProcessSandbox,
                            SubprocessSandbox)
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
from core.assist import CapabilityRegistry, DraftingService, GenerationLog
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
from core.monitoring import BreachRegister, MonitorRegistry, MonitoringService
from core.overlays import OverlayRegister
from core.regimes import RegimeEngine
from core.registry import ModelComposition, ModelRegistry, RegistryError
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
                ApiKeyRepository, LimitationRepository, RoleRepository,
                OverlayRepository,
                PrincipalRepository, RiskRepository,
                ScheduledRunRepository, SignatureRepository, SnapshotRepository,
                TestResultRepository, ValidationRepository, VersionRepository,
                WarrantRepository)
from fastapi.openapi.docs import get_swagger_ui_html

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
        {p: cfg.get_int(f"risk.purpose_ranks.{p}", 1)
         for p in ("commercial", "risk_management", "financial_reporting", "regulatory_capital")},
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
    drafting = DraftingService(
        generations, capabilities, evidence,
        assist_providers.build(cfg.get("assist.provider", "mock")))

    overlays = OverlayRegister(
        OverlayRepository(db), MeasurementRepository(db), evidence, findings,
        max_days=cfg.get_int("overlays.max_days", 180),
        renewal_limit=cfg.get_int("overlays.renewal_limit", 2))

    # Activated before the compiler is built, because a document states which
    # supervisors apply and an inactive regime has nothing to say.
    regimes = RegimeEngine(evidence)
    for key in cfg.get_list("regimes.active", ["sr-26-2"]):
        regimes.activate(key)

    attachments = AttachmentRegister(
        AttachmentRepository(db),
        DocumentStore(Path(cfg.get("data.attachments",
                                   str(ROOT / "data" / "attachments")))),
        registry, evidence)

    context = ContextBuilder(registry, evidence, RiskRepository(db), features,
                             validation, findings, monitoring, lifecycle,
                             warrants, overlays, regimes, attachments)
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

    scheduler = Scheduler(
        ScheduledRunRepository(db), evidence,
        JobContext(registry=registry, now=0.0, lifecycle=lifecycle,
                   findings=findings, monitoring=monitoring, overlays=overlays,
                   debts=debts, documents=documents,
                   notifications=notifications,
                   finding_workflow=finding_workflow,
                   evidence=evidence, risk=RiskRepository(db)),
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
                           "limitations": LimitationRegister(
                               LimitationRepository(db), registry, evidence),
                           "findings": findings, "validation": validation,
                           "finding_workflow": finding_workflow,
                           "test_catalogue": catalogue,
                           "principals": principals, "authz": authz,
                           "lifecycle": lifecycle, "monitoring": monitoring,
                           "documents": documents, "attachments": attachments,
                           "parameters": parameters, "replayer": replayer,
                           "approvals": approvals, "telemetry": telemetry,
                           "notifications": notifications, "oidc": oidc,
                           "policies": policies,
                           "overlays": overlays,
                           "capabilities": capabilities, "generations": generations,
                           "drafting": drafting,
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
            parameters=parameters)
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
        hundred and four mutating endpoints and a control that many places have
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
