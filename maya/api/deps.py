"""
Shared API plumbing: the platform, the authenticated principal, problem
documents (RFC 9457), conditional requests and small response helpers.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

from fastapi import Depends, Header, Request
from fastapi.responses import JSONResponse, Response

from maya.core import djson
from maya.core.errors import ConflictError, MayaError, ValidationFailed
from maya.security.authz import Principal


def platform(request: Request) -> Any:
    return request.app.state.platform


def principal(
    request: Request,
    authorization: str | None = Header(default=None),
    x_maya_channel: str | None = Header(default=None),
) -> Principal:
    """Resolve the bearer credential; the web tier marks its calls ``channel: web``."""
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    ip = request.client.host if request.client else None
    p = request.app.state.platform.auth.principal(token, ip=ip, path=request.url.path)
    if x_maya_channel in ("web", "cli", "sdk"):
        p.channel = x_maya_channel
    return p


Me = Depends(principal)
Plat = Depends(platform)


def problem_response(exc: MayaError) -> JSONResponse:
    return JSONResponse(
        djson.loads(djson.dumps(exc.to_problem())),
        status_code=exc.status,
        media_type="application/problem+json",
    )


def ok(data: Any, status: int = 200) -> JSONResponse:
    """JSON via MAYA's encoder so dates, decimals and numpy values are stable."""
    return Response(djson.dumps(data), status_code=status, media_type="application/json")


# -- conditional requests (§18.1) ---------------------------------------------------------
def etag(body: str | bytes) -> str:
    """A read's validator: the hash of the bytes served.

    A row version would be cheaper and would be wrong, because a read is more than its
    row. A feature's payload carries its grants, its pins, the transitions open to *this*
    caller and the owner's name — none of which bump the feature's own version column, and
    all of which a caller who was told 304 would then be holding stale. The body is the one
    thing that cannot be stale about itself.
    """
    raw = body.encode() if isinstance(body, str) else body
    return '"' + hashlib.sha256(raw).hexdigest()[:32] + '"'


def etags_in(header: str | None) -> set[str]:
    """The validators a caller listed, weak prefixes dropped: MAYA issues strong ones."""
    return {t.strip().removeprefix("W/") for t in (header or "").split(",") if t.strip()}


def ok_if_changed(data: Any, if_none_match: str | None) -> Response:
    """The read, or 304 and no body when the caller already holds this exact answer.

    This is what makes polling cheap: a scheduler that asks for a catalog listing every
    minute pays for the round trip and the resolution, and not for the payload.
    """
    body = djson.dumps(data)
    tag = etag(body)
    if tag in etags_in(if_none_match):
        return Response(status_code=304, headers={"ETag": tag})
    return Response(body, media_type="application/json", headers={"ETag": tag})


def require_match(if_match: str | None, current: Any) -> None:
    """Honour ``If-Match`` on a write: refuse unless the object is still what the caller
    read (§18.2.5), and refuse it with the ``ConflictError`` two racing edits already
    raise — a caller who handles one handles the other.

    Only an object with an open draft is guarded this way, because only a draft has two
    writers who can lose each other's work. A pin, a sealed warrant, a parameter set and an
    audit entry are appended once and then immutable: there is no overwrite to prevent, and
    a write to a sealed object is refused outright rather than merged, so an ``If-Match``
    there would be theatre. ``current`` is the guarding read, taken again now.
    """
    if not if_match:
        return
    wanted = etags_in(if_match)
    if "*" in wanted:
        return  # "* " means "as long as it exists", and the write's own lookup proves that
    if etag(djson.dumps(current)) not in wanted:
        raise ConflictError(
            "This object changed since you read it, so your edit was not applied. "
            "Read it again and re-apply the change.",
            expected=sorted(wanted)[0],
        )


def byte_range(header: str | None, total: int) -> tuple[int, int] | None:
    """The one byte range a caller asked for, as inclusive offsets, or ``None`` for all of
    it. A header MAYA does not understand is treated as no range at all, which RFC 9110
    permits and which keeps an odd proxy from turning a download into an error; a range
    that starts past the end comes back as given, so the endpoint can answer 416.
    """
    if not header or not header.startswith("bytes=") or "," in header:
        return None  # one range or the whole object; MAYA does not serve multipart ranges
    first, _, last = header[6:].strip().partition("-")
    try:
        if not first:
            start, end = max(total - int(last), 0), total - 1  # "bytes=-500": the last 500
        else:
            start, end = int(first), int(last) if last else total - 1
    except ValueError:
        return None
    return start, min(end, total - 1)


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
