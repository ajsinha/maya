"""
MAYA — authentication.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Session state lives in a signed cookie. The credentials are configuration, and
the signing secret must be overridden outside a workstation: a committed secret
is a public one, and a public one lets anyone forge a session.
"""
from __future__ import annotations

import hmac

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from routes.base import Routes


class AuthRoutes(Routes):
    def register(self) -> None:
        cfg = self.ctx["config"]
        user = cfg.get("auth.username", "admin")
        password = cfg.get("auth.password", "admin123")

        @self.app.get("/login", response_class=HTMLResponse, tags=["auth"])
        def login_page(request: Request, next: str = "/dashboard"):
            return self.page(request, "login.html", next=next, error=None)

        @self.app.post("/login", tags=["auth"])
        def login_submit(request: Request, username: str = Form(...),
                         password_in: str = Form(..., alias="password"),
                         next: str = Form("/dashboard")):
            if not (hmac.compare_digest(username, user)
                    and hmac.compare_digest(password_in, password)):
                return self.page(request, "login.html", status=401, next=next,
                                 error="Those credentials were not recognised.")
            request.session["username"] = username
            return RedirectResponse(next or "/dashboard", status_code=303)

        @self.app.get("/logout", tags=["auth"])
        def logout(request: Request):
            request.session.clear()
            return RedirectResponse("/", status_code=303)
