"""
Shared API plumbing: the platform, the authenticated principal, problem
documents (RFC 9457) and small response helpers.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import Depends, Header, Request
from fastapi.responses import JSONResponse, Response

from maya.core import djson
from maya.core.errors import MayaError, ValidationFailed
from maya.security.authz import Principal


def platform(request: Request) -> Any:
    return request.app.state.platform


def principal(request: Request, authorization: str | None = Header(default=None),
              x_maya_channel: str | None = Header(default=None)) -> Principal:
    """Resolve the bearer credential; the web tier marks its calls ``channel: web``."""
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    ip = request.client.host if request.client else None
    p = request.app.state.platform.auth.principal(token, ip=ip)
    if x_maya_channel in ("web", "cli", "sdk"):
        p.channel = x_maya_channel
    return p


Me = Depends(principal)
Plat = Depends(platform)


def problem_response(exc: MayaError) -> JSONResponse:
    return JSONResponse(djson.loads(djson.dumps(exc.to_problem())), status_code=exc.status,
                        media_type="application/problem+json")


def ok(data: Any, status: int = 200) -> JSONResponse:
    """JSON via MAYA's encoder so dates, decimals and numpy values are stable."""
    return Response(djson.dumps(data), status_code=status, media_type="application/json")


def parse_date(text: str | None, name: str) -> dt.date | None:
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text)
    except ValueError as exc:
        raise ValidationFailed(f"'{name}' must be YYYY-MM-DD") from exc


def parse_instant(text: str | None, name: str) -> dt.datetime | None:
    if not text:
        return None
    try:
        value = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationFailed(f"'{name}' must be an ISO-8601 instant") from exc
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


def ref_of(kind: str, namespace: str, name: str, suffix: str = "") -> str:
    return f"maya://{kind}/{namespace}/{name}{suffix}"
