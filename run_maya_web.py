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
import time
from pathlib import Path
from typing import Any, Dict

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
from core import log
from core.log import configure, get_logger
from core.features import FeatureRegistry
from core.lifecycle import (AmendmentService, AttestationService,
                            LifecycleService, VersionApproval)
from core.execution import WarrantError, WarrantService
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
from core.scheduler import JobContext, Scheduler, SchedulerLoop
from core.authz.oidc import build as build_oidc
from core.notify import NotificationService, build as build_channels
from core.policy import PolicyGate, PolicyRegister
from core.risk import TieringEngine
from core.telemetry import TelemetryCollector
from core.validation import (FindingRegister, FindingWorkflow, Replayer,
                             SnapshotProvider, TestCatalogue, ValidationService)
from db import (AliasHistoryRepository, AliasRepository, AmendmentRepository,
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
                DeltaStore, DocumentRepository, EvidenceCheckpointRepository, EvidenceRepository, ModelEdgeRepository,
                FeatureRepository, FeatureViewRepository,
                FeatureViewVersionRepository, FindingActionRepository,
                FindingRepository,
                GenerationRepository, ImportRepository, MeasurementRepository,
                ModelRepository, MonitorRepository, ObservationRepository,
                OverlayRepository, PrincipalRepository, RiskRepository,
                ScheduledRunRepository, SignatureRepository, SnapshotRepository,
                TestResultRepository, ValidationRepository, VersionRepository,
                WarrantRepository)
from routes import ALL_ROUTES
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
    for key in ("data.dir", "data.artifacts", "data.sqlite.dir"):
        if (path := cfg.get(key)):
            Path(path).mkdir(parents=True, exist_ok=True)
    delta = DeltaPaths.from_config(cfg).ensure()

    db = Database(cfg.get("database.url", "sqlite:///data/sqlite/maya.db"),
                  cfg.get_bool("database.echo", False))
    evidence = EvidenceEngine(EvidenceRepository(db), EvidenceCheckpointRepository(db))
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
    principals.bootstrap(cfg.get("auth.username", "admin"),
                         cfg.get("auth.password", "admin123"))

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
    telemetry = TelemetryCollector(DeltaStore(delta.root), registry, evidence,
                                   TelemetryBatchRepository(db))

    monitoring = MonitoringService(
        MonitorRegistry(MonitorRepository(db), catalogue, evidence),
        ObservationRepository(db),
        BreachRegister(BreachRepository(db), findings, evidence),
        catalogue, evidence, telemetry, registry)

    features = FeatureRegistry(FeatureRepository(db), FeatureViewRepository(db),
                               FeatureViewVersionRepository(db), ContractRepository(db),
                               SnapshotRepository(db), DeltaStore(delta.root), evidence,
                               DerivedFeatureRepository(db), FeaturesetRepository(db),
                               FeaturesetVersionRepository(db))

    # Assigned rather than injected: the warrant service is built before the
    # feature registry because a warrant is resolvable without features, but a
    # FIT warrant is not checkable without them.
    warrants.featuresets = features.sets

    # Parameters are recorded against the version that was fitted, only under a
    # warrant this register issued, and named by the featureset that produced them.
    parameters = ParameterRegister(ParameterSetRepository(db), registry, evidence,
                                   warrants, features.sets)
    # Late-bound in the other direction too, and for the same reason: the two
    # refer to each other. A warrant names the point of P a run is at; the
    # register knows which point is approved.
    warrants.parameters = parameters

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
                                         DeltaStore(delta.root), features))

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
                        documents, debts, validation, finding_workflow)
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
    registry.attach_policy(PolicyGate(policies, RegistryError))
    warrants.policy = PolicyGate(policies)

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
                   evidence=evidence))

    ctx: Dict[str, Any] = {"config": cfg, "db": db, "delta": delta, "features": features,
                           "evidence": evidence,
                           "registry": registry, "composition": composition,
                           "artifacts": artifacts,
                           "warrant_profiles": warrant_profiles,
                           "export": export, "dossier": dossier,
                           "training_records": training_records, "tiering": tiering, "warrants": warrants,
                           "risk_repo": RiskRepository(db), "engine": None,
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
            SnapshotRepository(db), DeltaStore(delta.root), evidence)
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


def create_app(cfg: PropertiesConfigurator = None) -> FastAPI:
    cfg = cfg or PropertiesConfigurator(str(ROOT / "config" / "application.yaml"))
    configure(cfg.get("logging.level", "INFO"),
              cfg.get("logging.format", log.FORMAT),
              cfg.get_bool("logging.json", False))
    ctx = build_context(cfg)

    app = FastAPI(title=cfg.get("app.name", "MAYA"),
                  description=f"{cfg.get('app.tagline')} — {cfg.get('app.slogan')}",
                  version=cfg.get("app.version", "0.1.0"),
                  openapi_url="/api/v1/openapi.json")
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

        Middleware rather than a check in each route, because there are ninety
        mutating endpoints and a control ninety places have to remember is a
        control that will be missing from the ninety-first. The exemptions are
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
                    "remediation": f"send the token from the page's "
                                   f"'{csrf.HEADER}' meta tag in that header, "
                                   f"or authenticate with HTTP Basic, which "
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

    for routes in ALL_ROUTES:
        routes(app, ctx, templates)
    logger.info("%s %s ready — %s database, captive engine %s",
                cfg.get("app.name"), cfg.get("app.version"), ctx["db"].dialect,
                "enabled" if ctx["engine"] else "disabled")
    return app


def main() -> None:
    import uvicorn
    cfg = PropertiesConfigurator(str(ROOT / "config" / "application.yaml"))
    uvicorn.run(create_app(cfg), host=cfg.get("server.host", "0.0.0.0"),
                port=cfg.get_int("server.port", 5006))


if __name__ == "__main__":
    main()
