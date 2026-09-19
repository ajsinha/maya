"""
Child-side entry point of the sandbox (§17.2). Run as a *separate interpreter*
(``python -I sandbox_runner.py``), never imported by MAYA.

Reads one JSON request on stdin, applies resource limits to itself, disables
networking, executes the artifact's entry point, and writes one JSON response
on stdout. It imports nothing from MAYA so the child carries no platform code
and no credentials.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
import sys
from typing import Any


def _limit(cpu_seconds: int, memory_mb: int) -> list[str]:
    applied = []
    try:
        import resource
    except ImportError:  # Windows: caps come from the parent's wall clock only
        return applied
    pairs = [
        ("RLIMIT_CPU", (cpu_seconds, cpu_seconds + 1)),
        ("RLIMIT_AS", (memory_mb * 1024 * 1024,) * 2),
        ("RLIMIT_FSIZE", (0, 0)),
        ("RLIMIT_CORE", (0, 0)),
    ]
    for name, value in pairs:
        if hasattr(resource, name):
            try:
                resource.setrlimit(getattr(resource, name), value)
                applied.append(name)
            except (ValueError, OSError):
                pass
    return applied


def _block_network() -> None:
    import socket

    def refused(*_a: Any, **_k: Any) -> Any:
        raise PermissionError("network access is disabled inside the MAYA sandbox")

    socket.socket = refused  # type: ignore[assignment,misc]
    socket.create_connection = refused  # type: ignore[assignment]
    socket.getaddrinfo = refused  # type: ignore[assignment]


class _Ctx:
    def __init__(self, seed: int) -> None:
        self.seed = seed


def _jsonable(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _call(namespace: dict[str, Any], entry: str, payload: dict[str, Any]) -> Any:
    try:
        import numpy as np
        X = {k: np.asarray(v) for k, v in payload.get("X", {}).items()}
    except ImportError:
        X = payload.get("X", {})
    target = namespace[entry]
    ctx = _Ctx(int(payload.get("seed", 0)))
    params = payload.get("params", {})
    if isinstance(target, type):
        obj = target()
        if payload.get("mode") == "fit":
            return obj.fit(X, payload.get("y"), ctx)
        return obj.predict(X, params, ctx)
    return target(X, params)


def main() -> None:
    request = json.loads(sys.stdin.read())
    limits = request.get("limits", {})
    # heavy libraries are imported before the address-space cap bites
    for name in request.get("preload", []):
        try:
            __import__(name)
        except ImportError:
            pass
    applied = _limit(int(limits.get("cpu_seconds", 10)), int(limits.get("memory_mb", 512)))
    _block_network()
    response: dict[str, Any] = {"ok": False, "limits_applied": applied}
    try:
        namespace: dict[str, Any] = {"__name__": "maya_artifact"}
        exec(compile(request["source"], "<artifact>", "exec"), namespace)  # noqa: S102 - this IS the sandbox
        response["result"] = _jsonable(_call(namespace, request["entry"], request.get("payload", {})))
        response["ok"] = True
    except MemoryError:
        response["error"] = "MemoryError: memory cap exceeded"
    except BaseException as exc:  # noqa: BLE001 - everything the artifact raises is reported
        response["error"] = f"{type(exc).__name__}: {exc}"
    sys.stdout.write(json.dumps(response))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
