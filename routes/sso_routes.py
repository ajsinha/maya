"""
MAYA — single sign-on.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The authorisation-code flow with PKCE. What is interesting here is not the flow,
which is standard, but what MAYA does with the group claims when it arrives:
maps them, refuses an incompatible pair, and records which groups produced which
roles.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

import logging

from core.authz.common import AuthzError
from core.log import get_logger, swallowed

logger = get_logger(__name__)
from routes.base import Routes

PENDING = "sso_pending"


class SsoRoutes(Routes):
    def register(self) -> None:
        api = self.api

        @self.app.get(f"{api}/sso", tags=["auth"])
        def describe(request: Request):
            """Whether SSO is configured, and exactly what it does with groups."""
            provider = self.ctx.get("oidc")
            if provider is None:
                return {"enabled": False,
                        "unavailable_because":
                            "no issuer is configured; this instance uses local "
                            "credentials only",
                        "roles": "group claims are mapped, never obeyed"}
            return provider.describe()

        @self.app.get("/auth/login", tags=["auth"])
        def begin(request: Request, next: str = "/dashboard"):
            """Send the browser to the provider, remembering what to check later."""
            provider = self._provider()
            pending = self.guard(lambda: provider.begin(next))
            request.session[PENDING] = pending
            return RedirectResponse(pending["url"], status_code=303)

        @self.app.get("/auth/callback", response_class=HTMLResponse, tags=["auth"])
        def callback(request: Request, code: Optional[str] = None,
                     state: Optional[str] = None, error: Optional[str] = None,
                     error_description: Optional[str] = None):
            """Where the provider sends the browser back."""
            provider = self._provider()
            pending = request.session.pop(PENDING, None)
            if error:
                return self.page(
                    request, "sso_failed.html", status=403,
                    reason=error_description or error,
                    remediation="the identity provider refused the sign-in; "
                                "nothing here was consulted")
            if not code or not state:
                return self.page(
                    request, "sso_failed.html", status=400,
                    reason="the provider returned no authorisation code",
                    remediation="start again from the sign-in page")
            try:
                identity = provider.complete(code, pending or {}, state)
                principal = provider.sign_in(identity, self.ctx["principals"],
                                             self.ctx["evidence"])
            except AuthzError as exc:
                # Rendered as a page rather than a JSON problem, because this
                # arrives in a browser. Logged so a refused sign-in is visible
                # to an operator and not only to whoever was refused.
                swallowed(logger, exc, "completed a single sign-on",
                          f"refused ({exc.code}); the browser is shown the reason",
                          logging.WARNING)
                return self.page(request, "sso_failed.html", status=403,
                                 reason=exc.detail,
                                 remediation=exc.remediation)
            request.session["user"] = principal["username"]
            return RedirectResponse((pending or {}).get("redirect_to", "/dashboard"),
                                    status_code=303)

        @self.app.post(f"{api}/sso/preview", tags=["auth"])
        def preview(request: Request, claims: dict):
            """What MAYA would make of these claims, without signing anybody in.

            For an administrator wiring up a mapping: it answers *which roles
            would this person get* before anybody finds out the hard way.
            """
            self.authorise(request, "principal:manage")
            provider = self._provider()
            return self.guard(lambda: provider.identity(claims))

    def _provider(self):
        provider = self.ctx.get("oidc")
        if provider is None:
            raise AuthzError(
                "sso_not_configured",
                "this instance has no identity provider configured",
                "sign in with local credentials, or set auth.oidc.issuer")
        return provider
