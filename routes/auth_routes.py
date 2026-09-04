"""
MAYA — authentication.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Session state lives in a signed cookie (Starlette SessionMiddleware). The
development credentials are configuration, not code, and the signing secret
must be overridden outside a workstation: a committed secret is a public one,
and a public one lets anyone forge a session.
"""
from __future__ import annotations

import hmac
from typing import Any, Dict, Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates


def current_user(request: Request) -> Optional[str]:
    return request.session.get("username")


def login_required(request: Request) -> Optional[RedirectResponse]:
    """Returns a redirect when the caller is anonymous, else None."""
    if current_user(request) is None:
        return RedirectResponse(f"/login?next={request.url.path}", status_code=303)
    return None


class AuthRoutes:
    def __init__(self, app: FastAPI, ctx: Dict[str, Any], templates: Jinja2Templates):
        self.app, self.ctx, self.templates = app, ctx, templates
        cfg = ctx["config"]
        self._user = cfg.get("auth.username", "admin")
        self._password = cfg.get("auth.password", "admin123")
        self._register()

    def _brand(self) -> Dict[str, str]:
        c = self.ctx["config"]
        return {"app_name": c.get("app.name", "MAYA"), "tagline": c.get("app.tagline", ""),
                "slogan": c.get("app.slogan", ""), "version": c.get("app.version", "")}

    def _register(self) -> None:
        @self.app.get("/login", response_class=HTMLResponse, tags=["auth"])
        def login_page(request: Request, next: str = "/dashboard"):
            return self.templates.TemplateResponse(
                request, "login.html", {"next": next, "error": None, **self._brand()})

        @self.app.post("/login", tags=["auth"])
        def login_submit(request: Request, username: str = Form(...),
                         password: str = Form(...), next: str = Form("/dashboard")):
            ok = (hmac.compare_digest(username, self._user)
                  and hmac.compare_digest(password, self._password))
            if not ok:
                return self.templates.TemplateResponse(
                    request, "login.html",
                    {"next": next, "error": "Those credentials were not recognised.",
                     **self._brand()}, status_code=401)
            request.session["username"] = username
            return RedirectResponse(next or "/dashboard", status_code=303)

        @self.app.get("/logout", tags=["auth"])
        def logout(request: Request):
            request.session.clear()
            return RedirectResponse("/", status_code=303)
