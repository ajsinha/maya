"""
MAYA — public pages: the landing page, about, and help.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

These are reachable without a session. Everything behind them is not.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from routes.auth_routes import current_user


class PublicRoutes:
    def __init__(self, app: FastAPI, ctx: Dict[str, Any], templates: Jinja2Templates):
        self.app, self.ctx, self.templates = app, ctx, templates
        self._register()

    def _ctx(self, request: Request) -> Dict[str, Any]:
        c = self.ctx["config"]
        return {"app_name": c.get("app.name", "MAYA"), "tagline": c.get("app.tagline", ""),
                "slogan": c.get("app.slogan", ""), "version": c.get("app.version", ""),
                "user": current_user(request)}

    def _register(self) -> None:
        @self.app.get("/", response_class=HTMLResponse, tags=["public"])
        def landing(request: Request):
            return self.templates.TemplateResponse(
                request, "landing.html",
                {"model_count": len(self.ctx["registry"].list()), **self._ctx(request)})

        @self.app.get("/about", response_class=HTMLResponse, tags=["public"])
        def about(request: Request):
            return self.templates.TemplateResponse(request, "about.html", self._ctx(request))

        @self.app.get("/help", response_class=HTMLResponse, tags=["public"])
        def help_page(request: Request):
            return self.templates.TemplateResponse(request, "help.html", self._ctx(request))
