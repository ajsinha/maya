"""
SDK transports (§18.2.3): ``http`` (the normal, remote case) and ``inproc``
(dispatch through ASGI inside the server process — every layer still runs,
it only skips the socket). Both speak the same request specs, so a resource
method written once works on the sync and the async client alike.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

from maya.core.errors import ERRORS_BY_CODE, MayaError

CLIENT_VERSION = "0.1.0"
RETRY_STATUS = {429, 502, 503, 504}


@dataclass
class Call:
    """One request, described independently of how it is sent."""

    method: str
    path: str
    params: dict[str, Any] = field(default_factory=dict)
    json_body: Any = None
    files: dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    raw: bool = False            # return bytes + headers instead of JSON


class TransportError(MayaError):
    """The network failed — distinct from a server refusal (§18.2.3)."""

    code, status = "transport_error", 0


def raise_for(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError):
        body = {"type": "maya_error", "detail": response.text[:500]}
    cls = ERRORS_BY_CODE.get(body.get("type", ""), MayaError)
    err = cls(body.get("detail") or f"HTTP {response.status_code}", **(body.get("context") or {}))
    err.status = response.status_code
    raise err


def decode(response: httpx.Response, call: Call) -> Any:
    raise_for(response)
    if call.raw:
        manifest = response.headers.get("x-maya-manifest")
        return {"data": response.content,
                "manifest": json.loads(manifest) if manifest else {},
                "content_type": response.headers.get("content-type")}
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return response.text


def _headers(token: str | None, channel: str, extra: dict[str, str]) -> dict[str, str]:
    h = {"X-Maya-Client": f"python/{CLIENT_VERSION}", "X-Maya-Channel": channel, **extra}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


class SyncTransport:
    def __init__(self, client: httpx.Client, token: str | None, channel: str = "sdk",
                 retries: int = 3) -> None:
        self.client, self.token, self.channel, self.retries = client, token, channel, retries

    def call(self, call: Call) -> Any:
        idempotent = call.method in ("GET", "PUT", "DELETE") or "Idempotency-Key" in call.headers
        for attempt in range(self.retries + 1):
            try:
                r = self.client.request(call.method, call.path, params=_clean(call.params),
                                        json=call.json_body, files=call.files, data=call.data,
                                        headers=_headers(self.token, self.channel, call.headers))
            except httpx.TransportError as exc:
                if not idempotent or attempt == self.retries:
                    raise TransportError(f"Network failure talking to MAYA: {exc}") from exc
                time.sleep(min(2 ** attempt * 0.2, 3))
                continue
            if r.status_code in RETRY_STATUS and idempotent and attempt < self.retries:
                time.sleep(min(2 ** attempt * 0.2, 3))
                continue
            return decode(r, call)
        return None


class AsyncTransport:
    def __init__(self, client: httpx.AsyncClient, token: str | None, channel: str = "sdk") -> None:
        self.client, self.token, self.channel = client, token, channel

    async def call(self, call: Call) -> Any:
        try:
            r = await self.client.request(call.method, call.path, params=_clean(call.params),
                                          json=call.json_body, files=call.files, data=call.data,
                                          headers=_headers(self.token, self.channel, call.headers))
        except httpx.TransportError as exc:
            raise TransportError(f"Network failure talking to MAYA: {exc}") from exc
        return decode(r, call)


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None}


def seg(text: str) -> str:
    return quote(str(text), safe="")


def split_ref(ref: str, kind: str) -> tuple[str, str]:
    """``ns/name``, ``maya://kind/ns/name`` (version or pin suffixes dropped) → (ns, name)."""
    body = ref.split("://", 1)[1] if "://" in ref else ref
    if body.startswith(kind + "/"):
        body = body[len(kind) + 1:]
    body = body.split("@", 1)[0].split("#", 1)[0]
    parts = body.split("/")
    if len(parts) != 2:
        raise MayaError(f"'{ref}' must name a namespace and a name: ns/name")
    return parts[0], parts[1]
