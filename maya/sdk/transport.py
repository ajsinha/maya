"""
SDK transports (§18.2.3): ``http`` (the normal, remote case) and ``inproc``
(dispatch through ASGI inside the server process — every layer still runs,
it only skips the socket). Both speak the same request specs, so a resource
method written once works on the sync and the async client alike.

Conditional requests live here rather than in each resource method, because
they are a property of the wire and not of any one call: a read goes out with
the ``If-None-Match`` of the body the client already holds, a write goes out
with the ``If-Match`` of the read that guards it, and a download resumes with
``Range`` from what is already on disk (§18.1, §18.2.3, §18.2.5).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from maya.core.errors import ERRORS_BY_CODE, MayaError

CLIENT_VERSION = "0.2.0"
RETRY_STATUS = {429, 502, 503, 504}
CHUNK = 1 << 20


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
    raw: bool = False  # return bytes + headers instead of JSON
    guard: str | None = None  # the read path whose ETag this write must match (§18.2.5)


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
        return {
            "data": response.content,
            "manifest": json.loads(manifest) if manifest else {},
            "content_type": response.headers.get("content-type"),
            "etag": response.headers.get("etag"),
            "status": response.status_code,
        }
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return response.text


def _headers(token: str | None, channel: str, extra: dict[str, str]) -> dict[str, str]:
    h = {"X-Maya-Client": f"python/{CLIENT_VERSION}", "X-Maya-Channel": channel, **extra}
    from maya.observability.tracing import current

    ctx = current()
    if ctx is not None:  # one trace from the browser through the API and its jobs
        h["traceparent"] = ctx.header()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


class SyncTransport:
    def __init__(
        self,
        client: httpx.Client,
        token: str | None,
        channel: str = "sdk",
        retries: int = 3,
        reads: Any = None,
    ) -> None:
        self.client, self.token, self.channel, self.retries = client, token, channel, retries
        self.reads = reads if reads is not None else _read_cache()

    def call(self, call: Call) -> Any:
        idempotent = call.method in ("GET", "PUT", "DELETE") or "Idempotency-Key" in call.headers
        key, headers = self.reads.prepare(call)
        for attempt in range(self.retries + 1):
            try:
                r = self.client.request(
                    call.method,
                    call.path,
                    params=_clean(call.params),
                    json=call.json_body,
                    files=call.files,
                    data=call.data,
                    headers=_headers(self.token, self.channel, headers),
                )
            except httpx.TransportError as exc:
                if not idempotent or attempt == self.retries:
                    raise TransportError(f"Network failure talking to MAYA: {exc}") from exc
                time.sleep(min(2**attempt * 0.2, 3))
                continue
            if r.status_code in RETRY_STATUS and idempotent and attempt < self.retries:
                time.sleep(min(2**attempt * 0.2, 3))
                continue
            if r.status_code == 304 and key is not None:
                return self.reads.served(key)  # MAYA has just affirmed what we already hold
            result = decode(r, call)
            self.reads.remember(key, r.headers.get("etag"), result, len(r.content))
            self.reads.wrote(call)
            return result
        return None

    def download(self, call: Call, path: str | Path, *, resume: bool = True) -> dict[str, Any]:
        """Stream a download to ``path``, continuing from whatever is already there.

        §18.2.3 asks for transfers that survive a bad network. The bytes go to disk as they
        arrive, so an interrupted download leaves a part worth keeping, and the next attempt
        asks for the rest with ``Range`` instead of starting over. ``If-Range`` carries the
        validator the part came from: if the object has moved, MAYA sends all of it and the
        part is overwritten rather than stitched onto bytes it never belonged to.
        """
        out, have, tag = _part_ready(path, resume)
        headers = _resume_headers(call, have, tag)
        try:
            with self.client.stream(
                call.method,
                call.path,
                params=_clean(call.params),
                headers=_headers(self.token, self.channel, headers),
            ) as r:
                if r.status_code >= 400:
                    r.read()
                    raise_for(r)
                resumed = r.status_code == 206 and have > 0
                with out.open("ab" if resumed else "wb") as fh:
                    written = sum(fh.write(chunk) for chunk in r.iter_bytes(CHUNK))
                summary = _part_summary(r, out, have if resumed else 0, written)
        except httpx.TransportError as exc:
            raise TransportError(f"Network failure talking to MAYA: {exc}") from exc
        return summary


class AsyncTransport:
    def __init__(
        self,
        client: httpx.AsyncClient,
        token: str | None,
        channel: str = "sdk",
        reads: Any = None,
    ) -> None:
        self.client, self.token, self.channel = client, token, channel
        self.reads = reads if reads is not None else _read_cache()

    async def call(self, call: Call) -> Any:
        key, headers = self.reads.prepare(call)
        try:
            r = await self.client.request(
                call.method,
                call.path,
                params=_clean(call.params),
                json=call.json_body,
                files=call.files,
                data=call.data,
                headers=_headers(self.token, self.channel, headers),
            )
        except httpx.TransportError as exc:
            raise TransportError(f"Network failure talking to MAYA: {exc}") from exc
        if r.status_code == 304 and key is not None:
            return self.reads.served(key)
        result = decode(r, call)
        self.reads.remember(key, r.headers.get("etag"), result, len(r.content))
        self.reads.wrote(call)
        return result

    async def download(self, call: Call, path: str | Path, *, resume: bool = True) -> Any:
        """The same resumable download, awaited, so a page render never blocks."""
        out, have, tag = _part_ready(path, resume)
        headers = _resume_headers(call, have, tag)
        try:
            async with self.client.stream(
                call.method,
                call.path,
                params=_clean(call.params),
                headers=_headers(self.token, self.channel, headers),
            ) as r:
                if r.status_code >= 400:
                    await r.aread()
                    raise_for(r)
                resumed = r.status_code == 206 and have > 0
                written = 0
                with out.open("ab" if resumed else "wb") as fh:
                    async for chunk in r.aiter_bytes(CHUNK):
                        written += fh.write(chunk)
                summary = _part_summary(r, out, have if resumed else 0, written)
        except httpx.TransportError as exc:
            raise TransportError(f"Network failure talking to MAYA: {exc}") from exc
        return summary


def _read_cache() -> Any:
    from maya.sdk.cache import ReadCache

    return ReadCache()


def validator_path(path: Path) -> Path:
    """Where the validator of a partly downloaded file is kept: beside the part, never in
    it, because the part has to stay byte for byte what the server sent."""
    return path.with_name(path.name + ".etag")


def _part_ready(path: str | Path, resume: bool) -> tuple[Path, int, str | None]:
    """The target, how much of it is already there, and the validator that part came with.
    A part whose validator was lost is not resumed: two halves that cannot be proved to
    belong to one object are worse than a download done again."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not resume or not out.exists():
        return out, 0, None
    have = out.stat().st_size
    try:
        tag = validator_path(out).read_text(encoding="utf-8").strip() or None
    except OSError:
        tag = None
    return out, (have if tag else 0), tag


def _resume_headers(call: Call, have: int, tag: str | None) -> dict[str, str]:
    headers = dict(call.headers)
    if have and tag:
        headers["Range"], headers["If-Range"] = f"bytes={have}-", tag
    return headers


def _part_summary(
    response: httpx.Response, out: Path, resumed_from: int, written: int
) -> dict[str, Any]:
    etag = response.headers.get("etag")
    if etag:
        try:
            validator_path(out).write_text(etag, encoding="utf-8")
        except OSError:
            pass  # a resume we cannot prepare for is a full download next time, not an error
    manifest = response.headers.get("x-maya-manifest")
    return {
        "path": out,
        "manifest": json.loads(manifest) if manifest else {},
        "etag": etag,
        "status": response.status_code,
        "resumed_from": resumed_from,
        "bytes": written + resumed_from,
    }


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None}


def seg(text: str) -> str:
    return quote(str(text), safe="")


def split_ref(ref: str, kind: str) -> tuple[str, str]:
    """``ns/name``, ``maya://kind/ns/name`` (version or pin suffixes dropped) → (ns, name)."""
    body = ref.split("://", 1)[1] if "://" in ref else ref
    if body.startswith(kind + "/"):
        body = body[len(kind) + 1 :]
    body = body.split("@", 1)[0].split("#", 1)[0]
    parts = body.split("/")
    if len(parts) != 2:
        raise MayaError(f"'{ref}' must name a namespace and a name: ns/name")
    return parts[0], parts[1]
