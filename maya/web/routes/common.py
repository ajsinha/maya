"""
Web-tier plumbing: the per-request SDK client, the ``page``/``action``
decorators (login, forced password change, CSRF, error-to-flash), template
rendering with the chrome context, and file responses.

The web tier is an SDK client with no private path (§13, §16): nothing here
imports anything from ``maya`` but ``maya.sdk``, ``maya.core.version`` and
``maya.core.errors``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import functools
import json
import secrets
import time
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from maya.core.errors import MayaError, NotAuthenticated
from maya.core.version import APP_NAME, APP_SLOGAN, APP_TAGLINE, BUILD_DATE, VERSION
from maya.sdk import AsyncClient

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
TEMPLATES.env.globals.update(APP_NAME=APP_NAME, APP_TAGLINE=APP_TAGLINE, APP_SLOGAN=APP_SLOGAN,
                             VERSION=VERSION, BUILD_DATE=BUILD_DATE)
TEMPLATES.env.filters["tojson_pretty"] = lambda v: json.dumps(v, indent=2, default=str,
                                                              sort_keys=True)
TEMPLATES.env.filters["short"] = lambda v, n=12: (str(v)[:n] + "…") if v and len(str(v)) > n \
    else (v or "")
TEMPLATES.env.filters["dt"] = lambda v: str(v)[:19].replace("T", " ") if v else ""
TEMPLATES.env.filters["urlq"] = lambda v: quote(str(v or ""), safe="")

_HEALTH: dict[str, Any] = {"at": 0.0, "data": None}
HEALTH_TTL = 30.0
UNSAFE = ("POST", "PUT", "PATCH", "DELETE")


class Redirect(Exception):
    def __init__(self, url: str) -> None:
        self.url = url


def client(request: Request) -> AsyncClient:
    """The SDK, bound to the logged-in user's session token, over ASGI in-process."""
    return AsyncClient(app=request.app, token=request.session.get("token"), channel="web")


def csrf_token(request: Request) -> str:
    tok = request.session.get("csrf")
    if not tok:
        tok = secrets.token_urlsafe(24)
        request.session["csrf"] = tok
    return tok


async def check_csrf(request: Request) -> bool:
    expected = request.session.get("csrf")
    if not expected:
        return False
    sent = request.headers.get("x-csrf-token")
    if not sent:
        form = await request.form()
        sent = form.get("csrf_token")
    return bool(sent) and secrets.compare_digest(str(sent), expected)


def flash(request: Request, message: str, level: str = "info") -> None:
    request.session.setdefault("flashes", []).append([level, message])


def back(request: Request, default: str = "/") -> str:
    ref = request.headers.get("referer") or default
    return ref if ref.startswith(str(request.base_url)) or ref.startswith("/") else default


def _login_redirect(request: Request) -> RedirectResponse:
    nxt = request.url.path + (("?" + request.url.query) if request.url.query else "")
    return RedirectResponse(f"/login?next={quote(nxt, safe='')}", status_code=303)


def page(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """GET page: requires login; MAYA errors render as an error page, not a traceback."""
    @functools.wraps(fn)
    async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
        if not request.session.get("token"):
            return _login_redirect(request)
        if request.session.get("must_change") and request.url.path != "/account/password":
            return RedirectResponse("/account/password", status_code=303)
        try:
            return await fn(request, *args, **kwargs)
        except Redirect as r:
            return RedirectResponse(r.url, status_code=303)
        except NotAuthenticated:
            request.session.clear()
            return _login_redirect(request)
        except MayaError as exc:
            return await render(request, "error.html", {"error": exc}, status=_status(exc))
    return wrapper


def action(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """State-changing POST: login + CSRF; errors become a flash on the previous page."""
    @functools.wraps(fn)
    async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
        if not request.session.get("token"):
            return _login_redirect(request)
        if not await check_csrf(request):
            return HTMLResponse("CSRF token missing or invalid. Reload the page and retry.",
                                status_code=403)
        try:
            return await fn(request, *args, **kwargs)
        except Redirect as r:
            return RedirectResponse(r.url, status_code=303)
        except NotAuthenticated:
            request.session.clear()
            return _login_redirect(request)
        except MayaError as exc:
            flash(request, f"{type(exc).__name__}: {exc.message}", "danger")
            return RedirectResponse(back(request), status_code=303)
    return wrapper


def api_json(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """A JSON endpoint for the page's own scripts (job polling, validation)."""
    @functools.wraps(fn)
    async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
        if not request.session.get("token"):
            return JSONResponse({"error": "not logged in"}, status_code=401)
        if request.method in UNSAFE and not await check_csrf(request):
            return JSONResponse({"error": "CSRF token missing or invalid"}, status_code=403)
        try:
            return JSONResponse(json.loads(json.dumps(await fn(request, *args, **kwargs),
                                                      default=str)))
        except MayaError as exc:
            return JSONResponse({"error": exc.message, "type": exc.code,
                                 "context": json.loads(json.dumps(exc.context, default=str))},
                                status_code=_status(exc))
    return wrapper


def _status(exc: MayaError) -> int:
    status = getattr(exc, "status", 400) or 400
    return status if 400 <= status < 600 else 400


async def _chrome(request: Request) -> dict[str, Any]:
    """Banners and badges shown on every page."""
    ctx: dict[str, Any] = {"unread": 0, "health": None}
    if not request.session.get("token"):
        return ctx
    sdk = client(request)
    try:
        inbox = await sdk.access.inbox()
        ctx["unread"] = sum(1 for n in inbox if not n.get("read_at"))
        now = time.monotonic()
        if _HEALTH["data"] is None or now - _HEALTH["at"] > HEALTH_TTL:
            h = await sdk.admin.health()
            _HEALTH.update(at=now, data={
                "environment": h["environment"], "dialect": h["database"]["dialect"],
                "default_admin_password": h["default_admin_password"],
                "lake": h["lake"]["backend"], "sandbox": h["sandbox"]["tier"],
                "typeset": h["typeset"].get("backend")})
        ctx["health"] = _HEALTH["data"]
    except MayaError:
        pass
    finally:
        await sdk.aclose()
    return ctx


def invalidate_health() -> None:
    _HEALTH.update(at=0.0, data=None)


async def render(request: Request, template: str, context: dict[str, Any] | None = None,
                 status: int = 200) -> HTMLResponse:
    ctx = dict(context or {})
    ctx.update(await _chrome(request))
    ctx.update(request=request, user=request.session.get("username"),
               my_roles=request.session.get("roles", []), csrf=csrf_token(request),
               flashes=request.session.pop("flashes", []), path=request.url.path)
    return TEMPLATES.TemplateResponse(request, template, ctx, status_code=status)


def download(result: dict[str, Any], filename: str) -> Response:
    """Stream a raw SDK download (bytes + manifest) back to the browser."""
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if result.get("manifest"):
        headers["X-Maya-Manifest"] = json.dumps(result["manifest"], default=str)
    return Response(result["data"], media_type=result.get("content_type") or
                    "application/octet-stream", headers=headers)


async def form(request: Request) -> dict[str, Any]:
    data = await request.form()
    return {k: v for k, v in data.items()}


def parse_json(text: str | None, what: str, default: Any = None) -> Any:
    from maya.core.errors import ValidationFailed
    if text is None or not str(text).strip():
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationFailed(f"{what} is not valid JSON: {exc}") from exc


def is_admin(request: Request) -> bool:
    return "admin" in request.session.get("roles", [])
