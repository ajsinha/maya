"""
Record and replay (§18.2.3, §18.2.7): SDK fixtures for tests, with no server.

``Client.record(path, …)`` sends every call for real and writes each request
and its response to a JSON *cassette*; ``Client.replay(path)`` serves the
cassette back with no network at all. A test that recorded once replays in
milliseconds, on a machine that has never seen MAYA. ``AsyncClient.record`` and
``AsyncClient.replay`` do the same for the asynchronous client, and a cassette
recorded by either replays in either.

* A request is matched by method, path, query parameters and a hash of its
  body and uploaded files. Identical requests replay their recorded responses
  in order, so polling a job replays its progress.
* A refusal is recorded as its typed error and replays as the same class with
  the same context — ``PermissionDenied`` stays ``PermissionDenied``.
* Binary downloads are kept (base64). Credentials never are: request headers
  are not recorded, and any response field named like a token or secret is
  redacted.
* A request with no recording raises, naming it: a replay never guesses.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from maya.core.errors import ERRORS_BY_CODE, MayaError
from maya.sdk.transport import Call

FORMAT = "maya-cassette/1"
SECRET_KEYS = {"token", "access_token", "refresh_token", "id_token", "secret", "api_key",
               "password", "mfa_secret", "client_secret", "otpauth_uri"}


class ReplayMiss(MayaError):
    """The cassette has no (further) recording for a request."""

    code, status = "replay_miss", 0


def request_key(call: Call) -> str:
    body = hashlib.sha256()
    body.update(json.dumps(call.json_body, sort_keys=True, default=str).encode())
    body.update(json.dumps(call.data or {}, sort_keys=True, default=str).encode())
    for name, spec in sorted((call.files or {}).items()):
        content = spec[1] if isinstance(spec, tuple) else spec
        body.update(name.encode() + hashlib.sha256(
            content if isinstance(content, bytes) else str(content).encode()).digest())
    params = json.dumps({k: v for k, v in (call.params or {}).items() if v is not None},
                        sort_keys=True, default=str)
    return f"{call.method} {call.path} {params} {body.hexdigest()[:16]}"


def _is_secret(key: str) -> bool:
    k = key.lower()
    return k in SECRET_KEYS or k.endswith(("_secret", "_token"))


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("<redacted>" if isinstance(v, str) and _is_secret(k) else _redact(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _encode(result: Any) -> dict[str, Any]:
    if isinstance(result, dict) and isinstance(result.get("data"), bytes):
        return {"raw": {**{k: v for k, v in result.items() if k != "data"},
                        "data": base64.b64encode(result["data"]).decode()}}
    return {"json": _redact(result)}


def _decode(entry: dict[str, Any]) -> Any:
    if "error" in entry:
        e = entry["error"]
        cls = ERRORS_BY_CODE.get(e["code"], MayaError)
        err = cls(e["message"], **(e.get("context") or {}))
        err.status = e.get("status", 0)
        raise err
    if "raw" in entry:
        raw = dict(entry["raw"])
        raw["data"] = base64.b64decode(raw["data"])
        return raw
    return entry["json"]


class RecordingTransport:
    """Wraps a real transport and writes every exchange to ``path``."""

    def __init__(self, inner: Any, path: str | Path) -> None:
        self.inner, self.path = inner, Path(path)
        self.entries: list[dict[str, Any]] = []
        self._save()

    def call(self, call: Call) -> Any:
        try:
            result = self.inner.call(call)
        except MayaError as exc:
            self._failed(call, exc)
            raise
        return self._answered(call, result)

    def _answered(self, call: Call, result: Any) -> Any:
        self.entries.append({"key": request_key(call), **_encode(result)})
        self._save()
        return result

    def _failed(self, call: Call, exc: MayaError) -> None:
        self.entries.append({"key": request_key(call), "error": {
            "code": exc.code, "status": getattr(exc, "status", 0), "message": exc.message,
            "context": _redact(exc.context)}})
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"format": FORMAT, "entries": self.entries},
                                        indent=1, default=str), encoding="utf-8")


class AsyncRecordingTransport(RecordingTransport):
    """The same recording around an asynchronous transport."""

    async def call(self, call: Call) -> Any:  # type: ignore[override]
        try:
            result = await self.inner.call(call)
        except MayaError as exc:
            self._failed(call, exc)
            raise
        return self._answered(call, result)


class ReplayTransport:
    """Serves a cassette; identical requests get their recorded responses in order."""

    def __init__(self, path: str | Path) -> None:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        if doc.get("format") != FORMAT:
            raise MayaError(f"{path} is not a MAYA cassette ({FORMAT})")
        self.queues: dict[str, list[dict[str, Any]]] = {}
        for entry in doc["entries"]:
            self.queues.setdefault(entry["key"], []).append(entry)
        self.last: dict[str, dict[str, Any]] = {}

    def call(self, call: Call) -> Any:
        return _decode(self._next(call))

    def _next(self, call: Call) -> dict[str, Any]:
        key = request_key(call)
        queue = self.queues.get(key)
        if queue:
            entry = queue.pop(0)
            self.last[key] = entry
            return entry
        if call.method == "GET" and key in self.last:
            return self.last[key]          # a read polled more often than it was recorded
        raise ReplayMiss(f"No recorded response for {call.method} {call.path}"
                         + (" (every recording of it was used)" if key in self.last
                            else ""), request=key)


class AsyncReplayTransport(ReplayTransport):
    """The same cassette served to the asynchronous client."""

    async def call(self, call: Call) -> Any:  # type: ignore[override]
        return _decode(self._next(call))
