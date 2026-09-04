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

from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates

from core.execution import CaptiveEngine
from core.evidence import EvidenceEngine
from core.log import configure, get_logger
from core.features import FeatureRegistry
from core.lifecycle import (AmendmentService, AttestationService, LifecycleService)
from core.execution import WarrantService
from core.authz import (AuthorizationPolicy, AuthzError, PrincipalService,
                        SegregationPolicy)
from core.config import PropertiesConfigurator
from core.docs import ContextBuilder, DocumentCompiler
from core.content import ContentLibrary, MarkdownRenderer
from core.monitoring import BreachRegister, MonitorRegistry, MonitoringService
from core.overlays import OverlayRegister
from core.registry import ModelRegistry
from core.risk import TieringEngine
from core.validation import (FindingRegister, Replayer, TestCatalogue,
                             ValidationService)
from db import (AliasHistoryRepository, AliasRepository, AmendmentRepository,
                AttestationRepository, BreachRepository, ContractRepository, Database,
                DocumentRepository,
                DeltaPaths, DeltaStore, EvidenceRepository, FeatureRepository,
                FeatureViewRepository, FeatureViewVersionRepository, FindingRepository,
                WarrantRepository, ModelRepository, RiskRepository, SnapshotRepository,
                MeasurementRepository, MonitorRepository, ObservationRepository,
                OverlayRepository, PrincipalRepository,
                SignatureRepository, TestResultRepository,
                ValidationRepository,
                VersionRepository)
from routes import ALL_ROUTES
from routes.base import authz_problem

ROOT = Path(__file__).resolve().parent
logger = get_logger("maya")


def _tier_map(cfg: PropertiesConfigurator, prefix: str, fallback: Dict[int, int]) -> Dict[int, int]:
    return {t: cfg.get_int(f"{prefix}.{t}", fallback[t]) for t in (1, 2, 3, 4)}


def build_context(cfg: PropertiesConfigurator) -> Dict[str, Any]:
    """Construct the services. Ordering is the dependency order, nothing more."""
    for key in ("data.dir", "data.artifacts", "data.sqlite.dir"):
        if (path := cfg.get(key)):
            Path(path).mkdir(parents=True, exist_ok=True)
    delta = DeltaPaths.from_config(cfg).ensure()

    db = Database(cfg.get("database.url", "sqlite:///data/sqlite/maya.db"),
                  cfg.get_bool("database.echo", False))
    evidence = EvidenceEngine(EvidenceRepository(db))
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
                        signing_key=cfg.get("warrants.signing_key_id", "maya-dev-key"),
                        ttl_by_tier=_tier_map(cfg, "warrants.ttl_seconds",
                                              {1: 60, 2: 300, 3: 3600, 4: 3600}),
                        grace_by_tier=_tier_map(cfg, "warrants.grace_seconds",
                                                {1: 0, 2: 0, 3: 900, 4: 900}),
                        jitter_pct=cfg.get_int("warrants.jitter_pct", 20),
                        blocking=findings)

    monitoring = MonitoringService(
        MonitorRegistry(MonitorRepository(db), catalogue, evidence),
        ObservationRepository(db),
        BreachRegister(BreachRepository(db), findings, evidence),
        catalogue, evidence)

    features = FeatureRegistry(FeatureRepository(db), FeatureViewRepository(db),
                               FeatureViewVersionRepository(db), ContractRepository(db),
                               SnapshotRepository(db), DeltaStore(delta.root), evidence)

    overlays = OverlayRegister(
        OverlayRepository(db), MeasurementRepository(db), evidence, findings,
        max_days=cfg.get_int("overlays.max_days", 180),
        renewal_limit=cfg.get_int("overlays.renewal_limit", 2))

    documents = DocumentCompiler(
        DocumentRepository(db), evidence,
        ContextBuilder(registry, evidence, RiskRepository(db), features,
                       validation, findings, monitoring, lifecycle, warrants,
                       overlays))

    ctx: Dict[str, Any] = {"config": cfg, "db": db, "delta": delta, "features": features,
                           "evidence": evidence,
                           "registry": registry, "tiering": tiering, "warrants": warrants,
                           "risk_repo": RiskRepository(db), "engine": None,
                           "findings": findings, "validation": validation,
                           "test_catalogue": catalogue,
                           "principals": principals, "authz": authz,
                           "lifecycle": lifecycle, "monitoring": monitoring,
                           "documents": documents, "overlays": overlays,
                           "renderer": MarkdownRenderer(),
                           "content": ContentLibrary(
                               Path(cfg.get("content.dir", str(ROOT / "content")))),
                           "replayer": Replayer(validation, catalogue)}
    if cfg.get_bool("execution.captive.enabled", True):
        # A consumer of the public warrant contract, nothing more.
        ctx["engine"] = CaptiveEngine(warrants, cfg.get_float("execution.captive.max_seconds", 30.0))
    return ctx


def create_app(cfg: PropertiesConfigurator = None) -> FastAPI:
    cfg = cfg or PropertiesConfigurator(str(ROOT / "config" / "application.yaml"))
    configure(cfg.get("logging.level", "INFO"))
    ctx = build_context(cfg)

    app = FastAPI(title=cfg.get("app.name", "MAYA"),
                  description=f"{cfg.get('app.tagline')} — {cfg.get('app.slogan')}",
                  version=cfg.get("app.version", "0.1.0"),
                  openapi_url="/api/v1/openapi.json")
    app.state.ctx = ctx
    app.add_middleware(SessionMiddleware,
                       secret_key=cfg.get("auth.session_secret", "maya-development-secret"),
                       max_age=cfg.get_int("auth.session_max_age", 28800),
                       same_site="strict", https_only=False)

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
