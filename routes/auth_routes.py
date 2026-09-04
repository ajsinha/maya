"""
MAYA — authentication.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Credentials are checked against the principal register, not against
configuration. Session state lives in a signed cookie, and the signing secret
must be overridden outside a workstation: a committed secret is a public one,
and a public one lets anyone forge a session.

The failure message never distinguishes an unknown username from a wrong
password. The user list of a model risk platform is an organisational chart, and
a login form that confirms who exists hands it over one guess at a time.
"""
from __future__ import annotations

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from routes.base import Routes


class AuthRoutes(Routes):
    def register(self) -> None:
        people = self.ctx["principals"]

        @self.app.get("/login", response_class=HTMLResponse, tags=["auth"])
        def login_page(request: Request, next: str = "/dashboard"):
            return self.page(request, "login.html", next=next, error=None)

        @self.app.post("/login", tags=["auth"])
        def login_submit(request: Request, username: str = Form(...),
                         password_in: str = Form(..., alias="password"),
                         next: str = Form("/dashboard")):
            principal = people.authenticate(username, password_in)
            if principal is None:
                return self.page(request, "login.html", http_status=401, next=next,
                                 error="Those credentials were not recognised.")
            request.session["username"] = principal["username"]
            return RedirectResponse(next or "/dashboard", status_code=303)

        @self.app.get("/logout", tags=["auth"])
        def logout(request: Request):
            request.session.clear()
            return RedirectResponse("/", status_code=303)
