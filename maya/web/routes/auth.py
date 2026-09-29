"""
Login, logout, password change and personal API keys.

Login goes through the SDK like everything else: the web tier asks the API
for a session token bound to this person, keeps it in the signed session
cookie, and uses it for every later call — never a shared key (§12, §18.2.2).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from maya.core.errors import MayaError
from maya.sdk import AsyncClient
from maya.web.routes.common import (
    action,
    api_json,
    check_csrf,
    client,
    csrf_token,
    flash,
    form,
    page,
    render,
)

router = APIRouter()


def _safe_next(target: str | None) -> str:
    return target if target and target.startswith("/") and not target.startswith("//") else "/"


async def _sign_in_options(request: Request) -> dict[str, Any]:
    anon = AsyncClient(app=request.app, channel="web")
    try:
        return await anon.auth.sso_config()
    finally:
        await anon.aclose()


@router.get("/login")
async def login_page(request: Request) -> Any:
    if request.session.get("token") and request.session.get("mfa", "ok") == "ok":
        return RedirectResponse("/", status_code=303)
    if "signed_out" in request.query_params:
        # somebody who has just signed out (an identity provider returning them here after
        # its own sign-out) goes to the landing page, not back to a sign-in form
        return RedirectResponse("/?signed_out=1", status_code=303)
    signin = await _sign_in_options(request)
    if "break-glass" in request.query_params and not signin.get("password_login"):
        # §13.3: under auth.mode: sso the password form is hidden because it is refused for
        # everyone but the designated break-glass accounts. /login?break-glass=1 shows it, so
        # an administrator has a way in through the browser while the IdP is down. Showing
        # the form grants nothing: the refusal is decided by the server (maya.security.
        # breakglass), and every use is audited loudly.
        signin = {**signin, "password_login": True, "break_glass": True}
    return await render(
        request,
        "login.html",
        {"next": request.query_params.get("next", "/"), "signin": signin},
    )


async def _establish(request: Request, result: dict[str, Any], nxt: str | None) -> Any:
    """Bind a fresh session to the token the API issued, then route by its state."""
    request.session.clear()
    request.session.update(
        token=result["token"],
        username=result["username"],
        must_change=bool(result.get("must_change_password")),
        mfa=result.get("mfa", "ok"),
        next=_safe_next(nxt),
    )
    csrf_token(request)
    if request.session["mfa"] != "ok":
        return RedirectResponse(
            "/mfa" if request.session["mfa"] == "challenge" else "/account/mfa", status_code=303
        )
    return await _enter(request)


async def _enter(request: Request) -> Any:
    async with client(request) as sdk:
        me = await sdk.auth.me()
    request.session["roles"] = me.get("roles", [])
    if request.session.get("must_change"):
        flash(request, "You must change your password before continuing.", "warning")
        return RedirectResponse("/account/password", status_code=303)
    return RedirectResponse(request.session.pop("next", "/") or "/", status_code=303)


@router.get("/auth/sso/login")
async def sso_login(request: Request) -> Any:
    nxt = _safe_next(request.query_params.get("next"))
    if (await _sign_in_options(request)).get("protocol") == "saml2":
        return await _saml_login(request, nxt)
    anon = AsyncClient(app=request.app, channel="web")
    try:
        start = await anon.auth.sso_start()
    except MayaError as exc:
        return await render(request, "login.html", {"error": exc.message, "signin": {}}, status=400)
    finally:
        await anon.aclose()
    request.session.update(
        sso_state=start["state"],
        sso_nonce=start["nonce"],
        sso_verifier=start["code_verifier"],
        next=_safe_next(request.query_params.get("next")),
    )
    return RedirectResponse(start["authorize_url"], status_code=303)


async def _saml_login(request: Request, nxt: str) -> Any:
    """SAML: the request is recorded server-side; the next page rides in RelayState."""
    anon = AsyncClient(app=request.app, channel="web")
    try:
        start = await anon.auth.saml_start(relay_state=nxt)
    except MayaError as exc:
        return await render(request, "login.html", {"error": exc.message, "signin": {}}, status=400)
    finally:
        await anon.aclose()
    return RedirectResponse(start["redirect_url"], status_code=303)


@router.post("/auth/sso/saml/acs")
async def saml_acs(request: Request) -> Any:
    """The IdP's cross-site POST. No session cookie and no CSRF token can come with it;
    what makes it safe is server-side: the signed assertion answers an outstanding,
    single-use request MAYA made (see maya.services.sso)."""
    data = await form(request)
    anon = AsyncClient(app=request.app, channel="web")
    try:
        result = await anon.auth.saml_acs(data.get("SAMLResponse", ""))
    except MayaError as exc:
        return await render(
            request,
            "login.html",
            {"error": exc.message, "signin": await _sign_in_options(request)},
            status=401,
        )
    finally:
        await anon.aclose()
    return await _establish(request, result, data.get("RelayState"))


@router.get("/auth/sso/saml/sls")
async def saml_sls(request: Request) -> Any:
    """SAML single logout, both directions, by redirect. The IdP's LogoutResponse ends a
    sign-out MAYA began; its signed LogoutRequest ends every session of that sign-in —
    this browser's included — and is answered with a LogoutResponse."""
    anon = AsyncClient(app=request.app, channel="web")
    try:
        result = await anon.auth.saml_sls(request.url.query)
    except MayaError as exc:
        return await render(
            request,
            "login.html",
            {"error": exc.message, "signin": await _sign_in_options(request)},
            status=400,
        )
    finally:
        await anon.aclose()
    if result["outcome"] == "idp_logout":
        request.session.clear()
    else:
        flash(request, "You are signed out of MAYA and of your identity provider.", "info")
    return RedirectResponse(result["redirect_url"], status_code=303)


@router.get("/auth/sso/callback")
async def sso_callback(request: Request) -> Any:
    params = request.query_params
    expected = request.session.pop("sso_state", None)
    nonce = request.session.pop("sso_nonce", None)
    verifier = request.session.pop("sso_verifier", None)
    nxt = request.session.get("next")
    if params.get("error") or not expected or params.get("state") != expected:
        return await render(
            request,
            "login.html",
            {
                "error": params.get("error_description")
                or "Sign-in was not completed, or the "
                "response did not match the request that started it. Try again.",
                "signin": await _sign_in_options(request),
            },
            status=400,
        )
    anon = AsyncClient(app=request.app, channel="web")
    try:
        result = await anon.auth.sso_callback(params.get("code", ""), verifier, nonce)
    except MayaError as exc:
        return await render(
            request,
            "login.html",
            {"error": exc.message, "signin": await _sign_in_options(request)},
            status=401,
        )
    finally:
        await anon.aclose()
    return await _establish(request, result, nxt)


@router.get("/mfa")
async def mfa_page(request: Request) -> Any:
    if request.session.get("mfa") != "challenge":
        return RedirectResponse("/", status_code=303)
    async with client(request) as sdk:
        status = await sdk.auth.mfa_status()
    return await render(request, "account/mfa_challenge.html", {"status": status})


async def _roles_and_next(request: Request) -> str:
    """After a second factor passes from a script: the roles, then where to go."""
    async with client(request) as sdk:
        me = await sdk.auth.me()
    request.session["roles"] = me.get("roles", [])
    if request.session.get("must_change"):
        return "/account/password"
    return request.session.pop("next", "/") or "/"


@router.post("/mfa/key/options")
@api_json
async def mfa_key_options(request: Request) -> Any:
    async with client(request) as sdk:
        return await sdk.auth.security_key_options()


@router.post("/mfa/key")
@api_json
async def mfa_key_verify(request: Request) -> Any:
    body = await request.json()
    try:
        async with client(request) as sdk:
            await sdk.auth.security_key_verify(body.get("credential") or {})
    except MayaError:
        request.session.clear()  # the server ended that sign-in attempt
        raise
    request.session["mfa"] = "ok"
    return {"next": await _roles_and_next(request)}


@router.post("/account/security-keys/options")
@api_json
async def security_key_options(request: Request) -> Any:
    async with client(request) as sdk:
        return await sdk.auth.security_key_register_options()


@router.post("/account/security-keys")
@api_json
async def security_key_register(request: Request) -> Any:
    body = await request.json()
    async with client(request) as sdk:
        await sdk.auth.register_security_key(
            body.get("credential") or {}, name=str(body.get("name") or "security key")
        )
    flash(request, "Security key registered.", "success")
    if request.session.get("mfa") == "enroll":
        request.session["mfa"] = "ok"
        return {"next": await _roles_and_next(request)}
    return {"next": "/account/mfa"}


@router.post("/account/security-keys/{key_id}/delete")
@action
async def security_key_delete(request: Request, key_id: str) -> Any:
    async with client(request) as sdk:
        await sdk.auth.remove_security_key(key_id)
    flash(request, "Security key removed.", "info")
    return RedirectResponse("/account/mfa", status_code=303)


@router.post("/mfa")
async def mfa_verify(request: Request) -> Any:
    if request.session.get("mfa") != "challenge" or not await check_csrf(request):
        return RedirectResponse("/login", status_code=303)
    data = await form(request)
    try:
        async with client(request) as sdk:
            await sdk.auth.mfa_verify(data.get("code", ""))
    except MayaError as exc:
        request.session.clear()
        return await render(
            request,
            "login.html",
            {"error": exc.message, "signin": await _sign_in_options(request)},
            status=401,
        )
    request.session["mfa"] = "ok"
    return await _enter(request)


@router.get("/account/mfa")
async def mfa_account(request: Request) -> Any:
    if not request.session.get("token"):
        return RedirectResponse("/login", status_code=303)
    async with client(request) as sdk:
        status = await sdk.auth.mfa_status()
        keys = await sdk.auth.security_keys() if request.session.get("mfa") == "ok" else []
    return await render(
        request,
        "account/mfa.html",
        {
            "status": status,
            "enrollment": request.session.pop("mfa_enrollment", None),
            "forced": request.session.get("mfa") == "enroll",
            "keys": keys,
        },
    )


@router.post("/account/mfa/enroll")
async def mfa_enroll(request: Request) -> Any:
    if not request.session.get("token") or not await check_csrf(request):
        return RedirectResponse("/login", status_code=303)
    try:
        async with client(request) as sdk:
            request.session["mfa_enrollment"] = await sdk.auth.mfa_enroll()
    except MayaError as exc:
        flash(request, exc.message, "danger")
    return RedirectResponse("/account/mfa", status_code=303)


@router.post("/account/mfa/confirm")
async def mfa_confirm(request: Request) -> Any:
    if not request.session.get("token") or not await check_csrf(request):
        return RedirectResponse("/login", status_code=303)
    data = await form(request)
    try:
        async with client(request) as sdk:
            await sdk.auth.mfa_confirm(data.get("code", ""))
    except MayaError as exc:
        flash(request, exc.message, "danger")
        return RedirectResponse("/account/mfa", status_code=303)
    forced = request.session.get("mfa") == "enroll"
    request.session["mfa"] = "ok"
    flash(request, "Two-factor authentication is on.", "success")
    return await _enter(request) if forced else RedirectResponse("/account/mfa", status_code=303)


@router.post("/login")
async def login(request: Request) -> Any:
    if not await check_csrf(request):
        return await render(
            request,
            "login.html",
            {
                "error": "Your session expired. Try again.",
                "signin": await _sign_in_options(request),
            },
            status=403,
        )
    data = await form(request)
    anon = AsyncClient(app=request.app, channel="web")
    try:
        result = await anon.auth.login(data.get("username", ""), data.get("password", ""))
    except MayaError as exc:
        return await render(
            request,
            "login.html",
            {
                "error": exc.message,
                "username": data.get("username", ""),
                "next": data.get("next", "/"),
                "signin": await _sign_in_options(request),
            },
            status=401,
        )
    finally:
        await anon.aclose()
    return await _establish(request, result, data.get("next"))


@router.post("/logout")
async def logout(request: Request) -> Any:
    slo = None
    if request.session.get("token") and await check_csrf(request):
        async with client(request) as sdk:
            try:
                slo = (await sdk.auth.logout()).get("slo_redirect")
            except MayaError:
                pass
    request.session.clear()
    # Out to the landing page, not to a sign-in form: somebody who has just left is not
    # halfway through arriving, and the form implies they should try again.
    return RedirectResponse(slo or "/?signed_out=1", status_code=303)


@router.get("/account/password")
@page
async def password_page(request: Request) -> Any:
    return await render(
        request, "account/password.html", {"forced": request.session.get("must_change")}
    )


@router.post("/account/password")
@action
async def change_password(request: Request) -> Any:
    data = await form(request)
    if data.get("new_password") != data.get("confirm_password"):
        flash(request, "The two new passwords differ.", "danger")
        return RedirectResponse("/account/password", status_code=303)
    async with client(request) as sdk:
        await sdk.auth.change_password(data.get("old_password", ""), data.get("new_password", ""))
    request.session["must_change"] = False
    from maya.web.routes.common import invalidate_health

    invalidate_health()
    flash(request, "Password changed.", "success")
    return RedirectResponse("/", status_code=303)


@router.get("/account/keys")
@page
async def keys_page(request: Request) -> Any:
    async with client(request) as sdk:
        keys = await sdk.auth.api_keys()
        namespaces = await sdk.namespaces.list()
    return await render(
        request,
        "account/keys.html",
        {"keys": keys, "namespaces": namespaces, "new_key": request.session.pop("new_key", None)},
    )


@router.post("/account/keys")
@action
async def create_key(request: Request) -> Any:
    data = await request.form()
    roles = data.getlist("roles")
    namespaces = data.getlist("namespaces")
    actions = [a.strip() for a in (data.get("actions") or "").split(",") if a.strip()]
    async with client(request) as sdk:
        key = await sdk.auth.create_api_key(
            data.get("name", "key"),
            roles=roles,
            namespaces=namespaces,
            actions=actions,
            days=int(data.get("days") or 90),
        )
    request.session["new_key"] = key["api_key"]
    flash(
        request,
        "API key created. Copy it now: it is shown once and stored only as a hash.",
        "warning",
    )
    return RedirectResponse("/account/keys", status_code=303)


@router.post("/account/keys/{key_id}/revoke")
@action
async def revoke_key(request: Request, key_id: str) -> Any:
    async with client(request) as sdk:
        await sdk.auth.revoke_api_key(key_id)
    flash(request, f"Key {key_id} revoked.", "success")
    return RedirectResponse("/account/keys", status_code=303)


# -- credentials: rotation, the reminder report, and service accounts (§12) ----------
@router.get("/account/credentials")
@page
async def credentials_page(request: Request) -> Any:
    """Everything a credential needs after it exists: which keys want rotating or
    revoking, and — for an administrator — the service accounts' client credentials and
    the password-reset tokens only an administrator can issue."""
    admin = "admin" in request.session.get("roles", [])
    async with client(request) as sdk:
        keys = await sdk.auth.api_keys()
        report = await sdk.auth.api_key_report(all=admin)
        clients = await sdk.auth.client_credentials() if admin else []
        users = await sdk.admin.users() if admin else []
    return await render(
        request,
        "auth/credentials.html",
        {
            "keys": keys,
            "report": report,
            "clients": clients,
            "services": [u for u in users if u.get("is_service")],
            "is_admin": admin,
            "issued": request.session.pop("issued_credential", None),
        },
    )


@router.post("/account/credentials/keys/{key_id}/rotate")
@action
async def rotate_key(request: Request, key_id: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        new = await sdk.auth.rotate_api_key(key_id, overlap_days=int(data.get("overlap_days") or 7))
    request.session["issued_credential"] = {
        "title": f"Successor to {key_id} — copy it now, it is shown once",
        "secret": new["api_key"],
        "note": f"{key_id} keeps working until {new['retires_at']}.",
    }
    flash(request, f"Key {key_id} rotated; its successor is {new['key_id']}.", "success")
    return RedirectResponse("/account/credentials", status_code=303)


@router.post("/account/credentials/clients")
@action
async def create_client_credential(request: Request) -> Any:
    data = await request.form()
    created = None
    async with client(request) as sdk:
        created = await sdk.auth.create_client_credential(
            str(data.get("username") or ""),
            name=str(data.get("name") or "client credential"),
            roles=data.getlist("roles"),
            namespaces=data.getlist("namespaces"),
            days=int(data.get("days") or 90),
            rate_per_minute=int(data.get("rate_per_minute") or 0),
        )
    request.session["issued_credential"] = {
        "title": "Client credential — the secret is shown once",
        "secret": f"client_id={created['client_id']}\nclient_secret={created['client_secret']}",
        "note": "Exchange it at POST /api/v1/auth/token with "
        "grant_type=client_credentials for a bearer token.",
    }
    flash(request, f"Client credential issued for {created['username']}.", "success")
    return RedirectResponse("/account/credentials", status_code=303)


@router.post("/account/credentials/reset-token")
@action
async def issue_reset_token(request: Request) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        issued = await sdk.auth.issue_password_reset(str(data.get("username") or ""))
    request.session["issued_credential"] = {
        "title": f"Password-reset link for {issued['username']} — shown once",
        "secret": f"/login/reset?token={issued['token']}",
        "note": f"Single use, and it expires at {issued['expires_at']}. Hand it over in "
        "person, not by email.",
    }
    flash(request, "Reset link issued.", "success")
    return RedirectResponse("/account/credentials", status_code=303)


# -- forgotten passwords: no session by definition, so no @page or @action -----------
@router.get("/login/forgot")
async def forgot_page(request: Request) -> Any:
    return await render(request, "auth/forgot.html", {})


@router.post("/login/forgot")
async def forgot(request: Request) -> Any:
    if not await check_csrf(request):
        return RedirectResponse("/login/forgot", status_code=303)
    data = await form(request)
    anon = AsyncClient(app=request.app, channel="web")
    try:
        await anon.auth.request_password_reset(data.get("username", ""))
    finally:
        await anon.aclose()
    # the same answer either way: this page must not say who has an account
    return await render(
        request,
        "auth/forgot.html",
        {"sent": True, "username": data.get("username", "")},
    )


@router.get("/login/reset")
async def reset_page(request: Request) -> Any:
    return await render(
        request, "auth/reset.html", {"token": request.query_params.get("token", "")}
    )


@router.post("/login/reset")
async def reset(request: Request) -> Any:
    if not await check_csrf(request):
        return RedirectResponse("/login/reset", status_code=303)
    data = await form(request)
    token = data.get("token", "")
    if data.get("new_password") != data.get("confirm_password"):
        return await render(
            request,
            "auth/reset.html",
            {"token": token, "error": "The two new passwords differ."},
            status=400,
        )
    anon = AsyncClient(app=request.app, channel="web")
    try:
        await anon.auth.complete_password_reset(token, data.get("new_password", ""))
    except MayaError as exc:
        return await render(
            request, "auth/reset.html", {"token": token, "error": exc.message}, status=400
        )
    finally:
        await anon.aclose()
    request.session.clear()
    flash(request, "Your password is set. Sign in with it.", "success")
    return RedirectResponse("/login", status_code=303)
