"""
MAYA — shared route scaffolding.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Every route module needs the same four things: the services, the brand context
for a template, one place that turns a domain refusal into an HTTP status, and
the login check. They were written seven times; they are written once here.

The error mapping is the important part. Design rule DR-6 says no failure may be
unmapped, and DR-7 says a refusal must explain itself — which only holds if
there is a single table to check, rather than a try/except in each module that
drifts.
"""
from __future__ import annotations

import base64
import binascii
from typing import Any, Callable, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from core.authz import AuthzError
from core.execution import WarrantError
from core.features import AssemblyRejected, FeatureError
from core.log import get_logger
from core.registry import RegistryError
from core.validation import ValidationError

API = "/api/v1"

# domain refusal -> HTTP status. One table, checked in one place.
logger = get_logger(__name__)

STATUS: Dict[str, int] = {
    "not_found": 404, "validation_failed": 422, "assembly_rejected": 422,
    "no_entitlement": 403, "use_not_approved": 403, "signature_invalid": 403,
    "registry_refused": 409, "feature_refused": 409, "restricted": 423,
    "validation_refused": 409,
    "revoked": 410, "expired": 410, "blocked": 423, "boundary_violation": 422, "no_runtime": 501,
    # authorisation
    "unauthenticated": 401, "forbidden": 403, "out_of_scope": 403,
    "segregation_of_duties": 403, "incompatible_roles": 409,
    "duplicate_principal": 409, "no_such_principal": 404, "unknown_role": 422,
    "unknown_permission": 422,
}
REMEDY: Dict[type, str] = {
    RegistryError: "the refusal names the clause that failed; satisfy it and retry",
    FeatureError: "correct the feature definition or the view version and retry",
    AssemblyRejected: "bound the assembly on both valid time and transaction time",
    ValidationError: "the refusal names the rule that was not satisfied; satisfy it and retry",
}


def current_user(request: Request) -> Optional[str]:
    return request.session.get("username")


def authz_problem(exc: AuthzError) -> HTTPException:
    """One translation of an authorisation refusal into HTTP."""
    return HTTPException(STATUS.get(exc.code, 403), {
        "error": exc.code, "detail": exc.detail, "remediation": exc.remediation})


def basic_credentials(request: Request) -> Optional[tuple]:
    """Username and password from an HTTP Basic header, or None.

    Services and scripts need a way in that is not a browser session. Basic over
    the same principal table keeps one identity store rather than two, and a
    malformed header is treated as absent rather than as an error — the caller
    is then told plainly that authentication is required.
    """
    header = request.headers.get("authorization", "")
    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return None
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        logger.info("ignoring a malformed Basic authorization header: %s", exc)
        return None
    username, sep, password = decoded.partition(":")
    return (username, password) if sep else None


def login_required(request: Request) -> Optional[RedirectResponse]:
    """A redirect when the caller is anonymous, otherwise None."""
    if current_user(request) is None:
        return RedirectResponse(f"/login?next={request.url.path}", status_code=303)
    return None


class Routes:
    """Base for every route module. Subclasses implement ``register``."""

    def __init__(self, app: FastAPI, ctx: Dict[str, Any],
                 templates: Optional[Jinja2Templates] = None):
        self.app, self.ctx, self.templates = app, ctx, templates
        self.api = API
        self.register()

    def register(self) -> None:                                # pragma: no cover
        raise NotImplementedError

    # ----------------------------------------------------------------- domain
    def guard(self, fn: Callable[[], Any]) -> Any:
        """Run a service call, mapping any domain refusal onto the taxonomy."""
        try:
            return fn()
        except WarrantError as exc:
            # A refusal is normal operation, not a fault — but it is the record of
            # a governance decision, so it is never translated without a trace.
            logger.warning("refused (%s): %s", exc.code, exc)
            raise HTTPException(STATUS.get(exc.code, 400), exc.as_problem()) from exc
        except (RegistryError, FeatureError, AssemblyRejected, ValidationError) as exc:
            code = {RegistryError: "registry_refused", FeatureError: "feature_refused",
                    AssemblyRejected: "assembly_rejected",
                    ValidationError: "validation_refused"}[type(exc)]
            logger.warning("refused (%s): %s", code, exc)
            raise HTTPException(STATUS[code], {
                "error": code, "detail": str(exc), "remediation": REMEDY[type(exc)]}) from exc

    # ---------------------------------------------------------- authorisation
    def principal(self, request: Request) -> Dict[str, Any]:
        """The acting principal, from the session or from Basic credentials.

        Raises 401 rather than returning None: every caller of this wants an
        identity, and an Optional here would eventually be used without checking.
        """
        people = self.ctx["principals"]
        if (username := current_user(request)) is not None:
            if (row := people.get(username)) and row["status"] == "active":
                return row
        if (creds := basic_credentials(request)) is not None:
            if (row := people.authenticate(*creds)) is not None:
                return row
        raise HTTPException(401, {
            "error": "unauthenticated",
            "detail": "this endpoint requires an authenticated principal",
            "remediation": "sign in, or present HTTP Basic credentials",
        }, headers={"WWW-Authenticate": 'Basic realm="MAYA"'})

    def authorise(self, request: Request, permission: str,
                  model: Optional[Dict[str, Any]] = None,
                  subject_id: Optional[str] = None) -> Dict[str, Any]:
        """Authenticate, then check permission, scope and segregation.

        Returns the principal so the caller can attribute the act to them —
        every governance act is recorded against a real identity rather than
        against 'system'.
        """
        who = self.principal(request)
        self.ctx["authz"].authorise(who, permission, model, subject_id)
        return who

    @staticmethod
    def actor(principal: Dict[str, Any]) -> str:
        return principal.get("username", "system")

    @staticmethod
    def not_found(detail: str) -> HTTPException:
        return HTTPException(404, {"error": "not_found", "detail": detail})

    # ------------------------------------------------------------------- view
    def brand(self, request: Optional[Request] = None) -> Dict[str, Any]:
        c = self.ctx["config"]
        return {"app_name": c.get("app.name", "MAYA"), "tagline": c.get("app.tagline", ""),
                "slogan": c.get("app.slogan", ""), "version": c.get("app.version", ""),
                "user": current_user(request) if request is not None else None}

    def page(self, request: Request, template: str, status: int = 200, **context):
        return self.templates.TemplateResponse(
            request, template, {**self.brand(request), **context}, status_code=status)
