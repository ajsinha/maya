"""
MAYA — server-rendered pages.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The UI holds no governance logic: it renders decisions the API computed, with
their rationale. Every asset is vendored; there is no CDN dependency, so the
interface renders in an air-gapped deployment.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from routes.auth_routes import current_user, login_required


class UIRoutes:
    def __init__(self, app: FastAPI, ctx: Dict[str, Any], templates: Jinja2Templates):
        self.app, self.ctx, self.templates = app, ctx, templates
        self._register()

    def _brand(self, request: Request) -> Dict[str, str]:
        c = self.ctx["config"]
        return {"app_name": c.get("app.name", "MAYA"),
                "tagline": c.get("app.tagline", ""),
                "slogan": c.get("app.slogan", ""),
                "version": c.get("app.version", ""),
                "user": current_user(request)}

    def _register(self) -> None:
        @self.app.get("/dashboard", response_class=HTMLResponse, tags=["ui"])
        def dashboard(request: Request):
            if (r := login_required(request)) is not None:
                return r
            models = self.ctx["registry"].list()
            chain = self.ctx["evidence"].verify_chain()
            by_tier: Dict[Any, int] = {}
            for m in models:
                by_tier[m["tier"]] = by_tier.get(m["tier"], 0) + 1
            return self.templates.TemplateResponse(
                request, "dashboard.html",
                {"models": models, "chain": chain,
                 "by_tier": by_tier, **self._brand(request)})

        @self.app.get("/model/{name:path}", response_class=HTMLResponse, tags=["ui"])
        def model_detail(request: Request, name: str):
            if (r := login_required(request)) is not None:
                return r
            urn = f"maya://model/{name}"
            registry = self.ctx["registry"]
            m = registry.get(urn)
            if not m:
                return self.templates.TemplateResponse(
                    request, "not_found.html", {"name": name, **self._brand(request)},
                    status_code=404)
            return self.templates.TemplateResponse(
                request, "model.html",
                {"model": m,
                 "versions": registry.versions(urn),
                 "history": registry.alias_history(urn),
                 "hooks": self.ctx["hooks"].grants(urn),
                 "evidence": self.ctx["evidence"].for_subject(m["id"]),
                 **self._brand(request)})
