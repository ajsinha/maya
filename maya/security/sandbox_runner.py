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


# Syscalls the artifact may never make, per architecture (Linux). Each is refused with
# EPERM: networking, tracing, mounting and namespace escapes, kernel keyrings and
# modules, kexec/reboot, cross-process memory access, and exec of anything else.
_DENY = {
    "x86_64": (
        0xC000003E,
        [
            41,
            42,
            43,
            44,
            45,
            46,
            47,
            49,
            50,
            53,
            101,
            288,
            165,
            166,
            272,
            308,
            321,
            250,
            248,
            249,
            175,
            313,
            176,
            246,
            320,
            169,
            59,
            322,
            310,
            311,
            298,
            323,
            135,
            161,
            155,
            425,
        ],
    ),
    "aarch64": (
        0xC00000B7,
        [
            198,
            199,
            200,
            201,
            202,
            203,
            204,
            206,
            207,
            211,
            212,
            242,
            117,
            40,
            39,
            97,
            268,
            280,
            219,
            217,
            218,
            105,
            273,
            106,
            104,
            294,
            142,
            221,
            281,
            270,
            271,
            241,
            282,
            92,
            51,
            41,
            425,
        ],
    ),
}


def _seccomp() -> bool:
    """Install a seccomp-bpf deny-list filter. True when the kernel accepted it."""
    import ctypes
    import platform
    import struct

    arch = _DENY.get(platform.machine())
    if arch is None or not sys.platform.startswith("linux"):
        return False
    audit_arch, denied = arch
    ld_w_abs, jeq, jge, ret = 0x20, 0x15, 0x35, 0x06
    allow, errno_eperm, kill = 0x7FFF0000, 0x00050001, 0x80000000
    prog = [(ld_w_abs, 0, 0, 4), (jeq, 1, 0, audit_arch), (ret, 0, 0, kill), (ld_w_abs, 0, 0, 0)]
    if audit_arch == 0xC000003E:  # refuse the x32 ABI outright
        prog += [(jge, 0, 1, 0x40000000), (ret, 0, 0, errno_eperm)]
    for nr in denied:
        prog += [(jeq, 0, 1, nr), (ret, 0, 0, errno_eperm)]
    prog.append((ret, 0, 0, allow))
    raw = b"".join(struct.pack("HBBI", *ins) for ins in prog)
    buf = ctypes.create_string_buffer(raw, len(raw))

    class Fprog(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.c_void_p)]

    fprog = Fprog(len(prog), ctypes.addressof(buf))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        return False
    return libc.prctl(22, 2, ctypes.byref(fprog), 0, 0) == 0  # PR_SET_SECCOMP, FILTER


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
    if hasattr(value, "columns") and hasattr(value, "to_dict"):  # a pandas DataFrame
        return {str(c): _jsonable(value[c].tolist()) for c in value.columns}
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    if hasattr(value, "isoformat"):  # date, datetime, Timestamp
        return value.isoformat()
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
    # where the parent's libraries live, which ``-I`` left out (the user site, above all)
    for path in request.get("paths", []):
        if path not in sys.path:
            sys.path.append(path)
    # heavy libraries are imported before the address-space cap bites
    for name in request.get("preload", []):
        try:
            __import__(name)
        except ImportError:
            pass
    applied = _limit(int(limits.get("cpu_seconds", 10)), int(limits.get("memory_mb", 512)))
    _block_network()
    if request.get("seccomp") and _seccomp():
        applied.append("seccomp")
    response: dict[str, Any] = {"ok": False, "limits_applied": applied}
    try:
        namespace: dict[str, Any] = {"__name__": "maya_artifact"}
        exec(compile(request["source"], "<artifact>", "exec"), namespace)  # noqa: S102  # nosec B102 - this IS the sandbox
        response["result"] = _jsonable(
            _call(namespace, request["entry"], request.get("payload", {}))
        )
        response["ok"] = True
    except MemoryError:
        response["error"] = "MemoryError: memory cap exceeded"
    except BaseException as exc:  # noqa: BLE001 - everything the artifact raises is reported
        response["error"] = f"{type(exc).__name__}: {exc}"
    sys.stdout.write(json.dumps(response))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
