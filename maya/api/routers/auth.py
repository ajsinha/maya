"""
Credentials as endpoints (§12): password reset by single-use token, API-key
rotation and its reminder report, and OAuth2 client credentials for service
accounts.

Sign-in, MFA, SSO and the key list live in the ``admin`` and ``identity`` routers;
what is here is everything a credential's *life* needs after it exists. Three routes
are deliberately unauthenticated — asking for a reset, redeeming a reset token and the
token endpoint — because each is used by someone who has no session by definition.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from maya.api.deps import Me, Plat, ok
from maya.security.authz import Principal

router = APIRouter(tags=["auth"])


class UsernameIn(BaseModel):
    username: str


class ResetTokenIn(BaseModel):
    token: str
    new_password: str


class RotateIn(BaseModel):
    overlap_days: int | None = None
    days: int | None = None


class ClientCredentialIn(BaseModel):
    username: str
    name: str = "client credential"
    roles: list[str] = Field(default_factory=list)
    namespaces: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    days: int = 90
    rate_per_minute: int = 0


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/auth/password-reset", status_code=202)
def request_password_reset(body: UsernameIn, request: Request, plat: Any = Plat) -> Response:
    """Ask for a password reset. The answer is the same whether or not the account
    exists, so this cannot be used to find out who has an account."""
    plat.auth.request_password_reset(body.username, ip=_ip(request), channel="web")
    return ok({"ok": True, "detail": "An administrator has been asked to issue a reset."}, 202)


@router.post("/auth/password-reset/token", status_code=201)
def issue_password_reset(body: UsernameIn, me: Principal = Me, plat: Any = Plat) -> Response:
    """Issue the token, shown once, for an administrator to hand over out of band."""
    return ok(plat.auth.issue_password_reset(me, body.username), 201)


@router.post("/auth/password-reset/complete")
def complete_password_reset(body: ResetTokenIn, request: Request, plat: Any = Plat) -> Response:
    """Redeem a reset token: once, before it expires, and never again."""
    return ok(plat.auth.complete_password_reset(body.token, body.new_password, ip=_ip(request)))


@router.post("/auth/token")
def client_credentials_token(
    request: Request,
    grant_type: str = Form(default="client_credentials"),
    client_id: str = Form(default=""),
    client_secret: str = Form(default=""),
    plat: Any = Plat,
) -> Response:
    """The OAuth2 client-credentials grant (RFC 6749 §4.4), form encoded as that
    specification requires, for a service account holding a client credential."""
    from maya.core.errors import ValidationFailed

    if grant_type != "client_credentials":
        raise ValidationFailed(
            f"unsupported_grant_type: '{grant_type}'; MAYA issues tokens for "
            "grant_type=client_credentials"
        )
    return ok(plat.auth.client_credentials_token(client_id, client_secret, ip=_ip(request)))


@router.get("/auth/api-keys/report")
def api_key_report(all: bool = False, me: Principal = Me, plat: Any = Plat) -> Response:
    """Keys to rotate or revoke, each with its reason."""
    return ok(plat.auth.api_key_report(me, all_users=all))


@router.post("/auth/api-keys/{key_id}/rotate", status_code=201)
def rotate_api_key(key_id: str, body: RotateIn, me: Principal = Me, plat: Any = Plat) -> Response:
    """Issue a successor, keep both working for the overlap window, retire this one."""
    return ok(
        plat.auth.rotate_api_key(me, key_id, overlap_days=body.overlap_days, days=body.days),
        201,
    )


@router.get("/auth/client-credentials")
def client_credentials(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.auth.list_client_credentials(me))


@router.post("/auth/client-credentials", status_code=201)
def create_client_credential(
    body: ClientCredentialIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    """A client credential for a service account: the secret is shown once."""
    return ok(plat.auth.create_client_credential(me, **body.model_dump()), 201)
