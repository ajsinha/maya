#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Application entry point. Wires configuration, the store, the governance
services and the routes, then serves.

    python run_maya_web.py
    python run_maya_web.py --server.port=5006 --database.url=postgresql://...

MAYA manages models and issues hooks. The captive execution engine is
constructed here only if execution.captive.enabled is true, and it is handed
the public HookService — the same interface an external engine consumes.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates

from core.execution import CaptiveEngine
from core.evidence import EvidenceEngine
from core.execution import HookService
from core.config import PropertiesConfigurator
from core.registry import ModelRegistry
from core.risk import TieringEngine
from db import (AliasRepository, Database, DeltaPaths, EvidenceRepository, HookRepository,
                ModelRepository, RiskRepository, VersionRepository)
from routes import AuthRoutes, HealthRoutes, HookRoutes, ModelRoutes, PublicRoutes, UIRoutes

ROOT = Path(__file__).resolve().parent
logger = logging.getLogger("maya")


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
                             AliasRepository(db), evidence)
    tiering = TieringEngine(
        {b: cfg.get_float(f"risk.exposure_bands.{b}", 0.0)
         for b in ("negligible", "low", "moderate", "material", "critical")},
        {p: cfg.get_int(f"risk.purpose_ranks.{p}", 1)
         for p in ("commercial", "risk_management", "financial_reporting", "regulatory_capital")},
        _tier_map(cfg, "risk.review_months", {1: 12, 2: 18, 3: 24, 4: 36}))
    hooks = HookService(HookRepository(db), registry, evidence,
                        signing_key=cfg.get("hooks.signing_key_id", "maya-dev-key"),
                        ttl_by_tier=_tier_map(cfg, "hooks.ttl_seconds",
                                              {1: 60, 2: 300, 3: 3600, 4: 3600}),
                        grace_by_tier=_tier_map(cfg, "hooks.grace_seconds",
                                                {1: 0, 2: 0, 3: 900, 4: 900}),
                        jitter_pct=cfg.get_int("hooks.jitter_pct", 20))

    ctx: Dict[str, Any] = {"config": cfg, "db": db, "delta": delta, "evidence": evidence,
                           "registry": registry, "tiering": tiering, "hooks": hooks,
                           "risk_repo": RiskRepository(db), "engine": None}
    if cfg.get_bool("execution.captive.enabled", True):
        # A consumer of the public hook contract, nothing more.
        ctx["engine"] = CaptiveEngine(hooks, cfg.get_float("execution.captive.max_seconds", 30.0))
    return ctx


def create_app(cfg: PropertiesConfigurator = None) -> FastAPI:
    cfg = cfg or PropertiesConfigurator(str(ROOT / "config" / "application.yaml"))
    logging.basicConfig(level=cfg.get("logging.level", "INFO"),
                        format=cfg.get("logging.format", "%(asctime)s %(levelname)s %(message)s"))
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

    HealthRoutes(app, ctx)
    ModelRoutes(app, ctx)
    HookRoutes(app, ctx)
    AuthRoutes(app, ctx, templates)
    PublicRoutes(app, ctx, templates)
    UIRoutes(app, ctx, templates)
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
