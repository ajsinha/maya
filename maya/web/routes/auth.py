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
from maya.web.routes.common import (action, check_csrf, client, csrf_token, flash, form, page,
                                    render)

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
    return await render(request, "login.html", {"next": request.query_params.get("next", "/"),
                                                "signin": await _sign_in_options(request)})


async def _establish(request: Request, result: dict[str, Any], nxt: str | None) -> Any:
    """Bind a fresh session to the token the API issued, then route by its state."""
    request.session.clear()
    request.session.update(token=result["token"], username=result["username"],
                           must_change=bool(result.get("must_change_password")),
                           mfa=result.get("mfa", "ok"), next=_safe_next(nxt))
    csrf_token(request)
    if request.session["mfa"] != "ok":
        return RedirectResponse("/mfa" if request.session["mfa"] == "challenge"
                                else "/account/mfa", status_code=303)
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
    anon = AsyncClient(app=request.app, channel="web")
    try:
        start = await anon.auth.sso_start()
    except MayaError as exc:
        return await render(request, "login.html", {"error": exc.message, "signin": {}},
                            status=400)
    finally:
        await anon.aclose()
    request.session.update(sso_state=start["state"], sso_nonce=start["nonce"],
                           sso_verifier=start["code_verifier"],
                           next=_safe_next(request.query_params.get("next")))
    return RedirectResponse(start["authorize_url"], status_code=303)


@router.get("/auth/sso/callback")
async def sso_callback(request: Request) -> Any:
    params = request.query_params
    expected = request.session.pop("sso_state", None)
    nonce = request.session.pop("sso_nonce", None)
    verifier = request.session.pop("sso_verifier", None)
    nxt = request.session.get("next")
    if params.get("error") or not expected or params.get("state") != expected:
        return await render(request, "login.html", {
            "error": params.get("error_description") or "Sign-in was not completed, or the "
                     "response did not match the request that started it. Try again.",
            "signin": await _sign_in_options(request)}, status=400)
    anon = AsyncClient(app=request.app, channel="web")
    try:
        result = await anon.auth.sso_callback(params.get("code", ""), verifier, nonce)
    except MayaError as exc:
        return await render(request, "login.html", {"error": exc.message,
                                                    "signin": await _sign_in_options(request)},
                            status=401)
    finally:
        await anon.aclose()
    return await _establish(request, result, nxt)


@router.get("/mfa")
async def mfa_page(request: Request) -> Any:
    if request.session.get("mfa") != "challenge":
        return RedirectResponse("/", status_code=303)
    return await render(request, "account/mfa_challenge.html", {})


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
        return await render(request, "login.html", {"error": exc.message,
                                                    "signin": await _sign_in_options(request)},
                            status=401)
    request.session["mfa"] = "ok"
    return await _enter(request)


@router.get("/account/mfa")
async def mfa_account(request: Request) -> Any:
    if not request.session.get("token"):
        return RedirectResponse("/login", status_code=303)
    async with client(request) as sdk:
        status = await sdk.auth.mfa_status()
    return await render(request, "account/mfa.html", {
        "status": status, "enrollment": request.session.pop("mfa_enrollment", None),
        "forced": request.session.get("mfa") == "enroll"})


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
    return await _enter(request) if forced else RedirectResponse("/account/mfa",
                                                                 status_code=303)


@router.post("/login")
async def login(request: Request) -> Any:
    if not await check_csrf(request):
        return await render(request, "login.html", {"error": "Your session expired. Try again.",
                                                    "signin": await _sign_in_options(request)},
                            status=403)
    data = await form(request)
    anon = AsyncClient(app=request.app, channel="web")
    try:
        result = await anon.auth.login(data.get("username", ""), data.get("password", ""))
    except MayaError as exc:
        return await render(request, "login.html", {"error": exc.message,
                                                    "username": data.get("username", ""),
                                                    "next": data.get("next", "/"),
                                                    "signin": await _sign_in_options(request)},
                            status=401)
    finally:
        await anon.aclose()
    return await _establish(request, result, data.get("next"))


@router.post("/logout")
async def logout(request: Request) -> Any:
    if request.session.get("token") and await check_csrf(request):
        async with client(request) as sdk:
            try:
                await sdk.auth.logout()
            except MayaError:
                pass
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/account/password")
@page
async def password_page(request: Request) -> Any:
    return await render(request, "account/password.html",
                        {"forced": request.session.get("must_change")})


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
    return await render(request, "account/keys.html", {
        "keys": keys, "namespaces": namespaces, "new_key": request.session.pop("new_key", None)})


@router.post("/account/keys")
@action
async def create_key(request: Request) -> Any:
    data = await request.form()
    roles = data.getlist("roles")
    namespaces = data.getlist("namespaces")
    actions = [a.strip() for a in (data.get("actions") or "").split(",") if a.strip()]
    async with client(request) as sdk:
        key = await sdk.auth.create_api_key(data.get("name", "key"), roles=roles,
                                            namespaces=namespaces, actions=actions,
                                            days=int(data.get("days") or 90))
    request.session["new_key"] = key["api_key"]
    flash(request, "API key created. Copy it now: it is shown once and stored only as a hash.",
          "warning")
    return RedirectResponse("/account/keys", status_code=303)


@router.post("/account/keys/{key_id}/revoke")
@action
async def revoke_key(request: Request, key_id: str) -> Any:
    async with client(request) as sdk:
        await sdk.auth.revoke_api_key(key_id)
    flash(request, f"Key {key_id} revoked.", "success")
    return RedirectResponse("/account/keys", status_code=303)
