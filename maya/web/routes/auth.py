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


@router.get("/login")
async def login_page(request: Request) -> Any:
    if request.session.get("token"):
        return RedirectResponse("/", status_code=303)
    return await render(request, "login.html", {"next": request.query_params.get("next", "/")})


@router.post("/login")
async def login(request: Request) -> Any:
    if not await check_csrf(request):
        return await render(request, "login.html", {"error": "Your session expired. Try again."},
                            status=403)
    data = await form(request)
    anon = AsyncClient(app=request.app, channel="web")
    try:
        result = await anon.auth.login(data.get("username", ""), data.get("password", ""))
    except MayaError as exc:
        return await render(request, "login.html", {"error": exc.message,
                                                    "username": data.get("username", ""),
                                                    "next": data.get("next", "/")}, status=401)
    finally:
        await anon.aclose()
    request.session.clear()
    request.session.update(token=result["token"], username=result["username"],
                           must_change=bool(result.get("must_change_password")))
    csrf_token(request)
    async with client(request) as sdk:
        me = await sdk.auth.me()
    request.session["roles"] = me.get("roles", [])
    if request.session["must_change"]:
        flash(request, "You must change your password before continuing.", "warning")
        return RedirectResponse("/account/password", status_code=303)
    return RedirectResponse(_safe_next(data.get("next")), status_code=303)


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
