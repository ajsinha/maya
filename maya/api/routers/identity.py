"""
SAML 2.0 single sign-on and security keys (WebAuthn) (§12).

The SAML endpoints are public, like the OIDC ones: they are how a person with
no session gets one. The WebAuthn endpoints need a session; the ones that
answer or begin a second factor are reachable from a session still owing it
(``MFA_OPEN_PATHS``), and the services decide which session states may use each.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from maya.api import schemas as s
from maya.api.deps import Me, Plat, ok
from maya.security.authz import Principal

router = APIRouter(tags=["auth"])


def _bearer(request: Request) -> str:
    return request.headers.get("authorization", "")[7:].strip()


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# -- SAML 2.0 -------------------------------------------------------------------------------
@router.get("/auth/sso/saml/metadata")
def saml_metadata(plat: Any = Plat) -> Response:
    """Public: MAYA's service-provider metadata, for registering MAYA at the IdP."""
    return Response(plat.sso.saml_metadata(), media_type="application/samlmetadata+xml")


@router.post("/auth/sso/saml/start")
def saml_start(body: s.SamlStartIn, plat: Any = Plat) -> Response:
    """Public: the IdP URL carrying a fresh AuthnRequest, recorded server-side."""
    return ok(plat.sso.saml_start(body.relay_state))


@router.post("/auth/sso/saml/acs")
def saml_acs(body: s.SamlAcsIn, request: Request, plat: Any = Plat) -> Response:
    """Public: validate the IdP's posted Response and open a session."""
    return ok(plat.sso.saml_acs(body.saml_response, ip=_ip(request),
                                user_agent=request.headers.get("user-agent")))


# -- security keys -------------------------------------------------------------------------
@router.get("/auth/mfa/webauthn")
def webauthn_keys(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.passkeys.list(me))


@router.delete("/auth/mfa/webauthn/{key_id}")
def webauthn_remove(key_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    plat.passkeys.remove(me, key_id)
    return ok({"ok": True})


@router.post("/auth/mfa/webauthn/register/options")
def webauthn_register_options(request: Request, me: Principal = Me,
                              plat: Any = Plat) -> Response:
    return ok(plat.passkeys.register_options(me, _bearer(request)))


@router.post("/auth/mfa/webauthn/register")
def webauthn_register(body: s.WebAuthnRegisterIn, request: Request, me: Principal = Me,
                      plat: Any = Plat) -> Response:
    return ok(plat.passkeys.register(me, _bearer(request), body.credential, name=body.name,
                                     ip=_ip(request)))


@router.post("/auth/mfa/webauthn/options")
def webauthn_options(request: Request, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.passkeys.login_options(_bearer(request)))


@router.post("/auth/mfa/webauthn/verify")
def webauthn_verify(body: s.WebAuthnVerifyIn, request: Request, me: Principal = Me,
                    plat: Any = Plat) -> Response:
    return ok(plat.passkeys.login(_bearer(request), body.credential, ip=_ip(request)))
