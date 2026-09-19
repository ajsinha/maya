"""
What one caller may ask of one process (§13.2, §21.1, §24.4).

Four limits, each a plain ASGI layer so they apply to the web UI as well as the API:

* **Body size** — a request body is refused at the configured size, before it is read into
  memory. A declared `Content-Length` is refused outright; a chunked body is counted as it
  arrives and cut off at the limit, so a client cannot beat the check by omitting the
  header.
* **Rate** — a token bucket per caller per minute. The caller is the API key id, else the
  session cookie or bearer token, else the peer address; a token identifies a caller
  without being stored or logged here.
* **Concurrency** — above so many requests in flight, MAYA sheds load with `503` and
  `Retry-After` instead of queueing until everything is slow.
* **Time** — a request that outlives the deadline is answered `504`; the work it started
  is not cancelled if it is already in the database, because a half-written transaction is
  worse than a slow one.

All four count per process. With several web processes the effective rate and concurrency
are the configured figures times the number of processes, which the configuration
reference states; a shared counter would need a shared store MAYA does not require.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Generous on purpose: these bound a runaway or hostile caller, and a person clicking
# through the UI, a busy SDK script or the benchmarks must never meet them. 0 turns one off.
DEFAULTS = {
    "max_body_bytes": 256 * 1024 * 1024,
    "requests_per_minute": 6000,
    "burst": 1200,
    "max_concurrent": 128,
    "timeout_seconds": 120,
}


def settings_for(settings: Any) -> dict[str, int]:
    """The limits in force. 0 turns one off, which the configuration reference documents."""
    return {
        key: settings.int(f"api.limits.{key}", default) if settings is not None else default
        for key, default in DEFAULTS.items()
    }


async def _problem(send: Send, status: int, code: str, detail: str, retry: int = 0) -> None:
    import json

    body = json.dumps(
        {"type": code, "title": code, "status": status, "detail": detail, "context": {}}
    ).encode()
    headers = [
        (b"content-type", b"application/problem+json"),
        (b"content-length", str(len(body)).encode()),
    ]
    if retry:
        headers.append((b"retry-after", str(retry).encode()))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class _TooLarge(Exception):
    """Raised inside the receive chain when a streamed body passes the limit."""


class BodyLimit:
    """Refuse a body past ``max_body_bytes`` — by its header, or as it arrives."""

    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app, self.limit = app, limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.limit <= 0:
            await self.app(scope, receive, send)
            return
        declared = Headers(scope=scope).get("content-length")
        if declared and declared.isdigit() and int(declared) > self.limit:
            await _problem(
                send,
                413,
                "payload_too_large",
                f"The request body is {int(declared) / 1e6:.0f} MB; this MAYA accepts "
                f"{self.limit / 1e6:.0f} MB",
            )
            return
        seen = 0
        started = False

        async def counted() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.limit:
                    raise _TooLarge
            return message

        async def watched(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted, watched)
        except _TooLarge:
            if not started:  # nothing has been written yet, so the refusal still fits
                await _problem(
                    send,
                    413,
                    "payload_too_large",
                    f"The request body passed the {self.limit / 1e6:.0f} MB this MAYA accepts",
                )


class RateLimit:
    """A token bucket per caller: ``per_minute`` tokens a minute, ``burst`` in hand."""

    def __init__(self, app: ASGIApp, per_minute: int, burst: int) -> None:
        self.app, self.rate, self.burst = app, per_minute / 60.0, max(1, burst)
        self.buckets: dict[str, tuple[float, float]] = {}

    def caller(self, scope: Scope) -> str:
        headers = Headers(scope=scope)
        auth = headers.get("authorization", "")
        if auth.startswith("Bearer maya_") and auth.count("_") >= 3:
            return "key:" + auth.split("_")[2]  # the key id, never the secret
        if auth:
            return "auth:" + str(hash(auth))
        cookie = headers.get("cookie", "")
        if cookie:
            return "session:" + str(hash(cookie))
        client = scope.get("client") or ("anonymous", 0)
        return f"peer:{client[0]}"

    def take(self, who: str, now: float) -> float:
        """Seconds to wait, 0 when the request may proceed."""
        tokens, stamp = self.buckets.get(who, (float(self.burst), now))
        tokens = min(self.burst, tokens + (now - stamp) * self.rate)
        if tokens < 1.0:
            self.buckets[who] = (tokens, now)
            return max(1.0, (1.0 - tokens) / self.rate) if self.rate else 60.0
        self.buckets[who] = (tokens - 1.0, now)
        if len(self.buckets) > 10_000:  # a long-lived process must not grow a bucket per peer
            cutoff = now - 300
            self.buckets = {k: v for k, v in self.buckets.items() if v[1] > cutoff}
        return 0.0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.rate <= 0:
            await self.app(scope, receive, send)
            return
        wait = self.take(self.caller(scope), time.monotonic())
        if wait:
            await _problem(
                send,
                429,
                "rate_limited",
                "Too many requests from this caller; slow down and retry",
                retry=int(wait) + 1,
            )
            return
        await self.app(scope, receive, send)


class Shed:
    """Above ``max_concurrent`` requests in flight, say so instead of queueing."""

    def __init__(self, app: ASGIApp, max_concurrent: int, timeout: int) -> None:
        self.app, self.limit, self.timeout = app, max_concurrent, timeout
        self.in_flight = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if 0 < self.limit <= self.in_flight:
            await _problem(
                send,
                503,
                "overloaded",
                "This MAYA process is at its concurrency limit; retry shortly",
                retry=1,
            )
            return
        self.in_flight += 1
        try:
            if self.timeout > 0:
                await asyncio.wait_for(self.app(scope, receive, send), timeout=self.timeout)
            else:
                await self.app(scope, receive, send)
        except (TimeoutError, asyncio.TimeoutError):
            await _problem(
                send,
                504,
                "request_timeout",
                f"This request passed the {self.timeout}s limit and was abandoned; "
                "work already committed is not undone",
            )
        finally:
            self.in_flight -= 1


def install(app: Any, settings: Any) -> None:
    """Wrap ``app`` in all four. Starlette wraps with the last added outermost, so load
    shedding sees a request first and the body limit last, closest to the route."""
    caps = settings_for(settings)
    app.add_middleware(BodyLimit, limit=caps["max_body_bytes"])
    app.add_middleware(RateLimit, per_minute=caps["requests_per_minute"], burst=caps["burst"])
    app.add_middleware(Shed, max_concurrent=caps["max_concurrent"], timeout=caps["timeout_seconds"])


__all__ = ["BodyLimit", "DEFAULTS", "RateLimit", "Shed", "install", "settings_for"]
