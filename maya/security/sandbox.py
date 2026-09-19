"""
The per-platform sandbox, with its tier declared rather than assumed (§17.2).

Every user artifact runs in a *separate interpreter* (``python -I``), with an
empty working directory, a stripped environment, rlimit caps where the OS
provides them, a wall-clock kill, an output-size cap, and networking disabled
in the child. The tier reported here is honest about what that amounts to:

- ``strong`` would need seccomp-bpf, cgroup v2 caps, a network namespace and a
  separate OS user. MAYA does not set those up as an unprivileged process, so
  it never claims ``strong``.
- ``moderate`` on macOS when ``sandbox-exec`` is present (network denied by a
  kernel profile, plus rlimits).
- ``minimal`` otherwise: rlimits (POSIX) or the wall clock alone (Windows).
  Network blocking in the child is best-effort (the socket module is disabled
  in-process, which native code could bypass).

The tier is recorded on every validation report so a reviewer knows what a
green tick was worth.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

RUNNER = Path(__file__).with_name("sandbox_runner.py")
TIER_ORDER = ("minimal", "moderate", "strong")
_MAC_PROFILE = "(version 1)(allow default)(deny network*)(deny file-write* (subpath \"/\"))"


def sandbox_tier() -> dict[str, str]:
    """The tier this host can deliver, the mechanism, and the honest reason."""
    system = platform.system()
    if system == "Darwin" and shutil.which("sandbox-exec"):
        return {"tier": "moderate", "mechanism": "sandbox-exec profile + setrlimit",
                "reason": "network and filesystem writes denied by a kernel sandbox profile; "
                          "no separate OS user"}
    if system == "Windows":
        return {"tier": "minimal", "mechanism": "subprocess + wall-clock kill",
                "reason": "no Job Object or restricted token is configured; CPU and memory "
                          "are bounded only by the wall clock; network blocking is best-effort"}
    return {"tier": "minimal", "mechanism": "subprocess + setrlimit (CPU, address space, file size)",
            "reason": "seccomp-bpf, cgroup v2 and a network namespace are not configured for an "
                      "unprivileged process, so the tier is not claimed as strong; network "
                      "blocking in the child is best-effort"}


def tier_at_least(tier: str, minimum: str) -> bool:
    """True when ``tier`` meets the configured minimum."""
    return TIER_ORDER.index(tier) >= TIER_ORDER.index(minimum)


def _child_env() -> dict[str, str]:
    env = {"PYTHONHASHSEED": "0", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
           "MKL_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"}
    if "SYSTEMROOT" in os.environ:  # Windows cannot start Python without it
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


def _argv() -> list[str]:
    argv = [sys.executable, "-I", "-B", str(RUNNER)]
    if platform.system() == "Darwin" and shutil.which("sandbox-exec"):
        argv = ["sandbox-exec", "-p", _MAC_PROFILE, *argv]
    return argv


def run_sandboxed(source: str, entry: str, payload: dict[str, Any], *, cpu_seconds: int = 10,
                  memory_mb: int = 512, wall_seconds: int = 20,
                  output_limit_bytes: int = 2_000_000,
                  preload: tuple[str, ...] = ("numpy",)) -> dict[str, Any]:
    """Run ``entry`` from ``source`` on ``payload`` in a capped child interpreter."""
    tier = sandbox_tier()
    request = json.dumps({
        "source": source, "entry": entry, "payload": payload, "preload": list(preload),
        "limits": {"cpu_seconds": cpu_seconds, "memory_mb": memory_mb},
    })
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="maya-sbx-") as cwd:
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                _argv(), input=request, capture_output=True, text=True, cwd=cwd,
                env=_child_env(), timeout=wall_seconds, check=False,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "result": None, "tier": tier["tier"],
                    "error": f"wall-clock limit of {wall_seconds}s exceeded; the process was killed",
                    "duration": time.monotonic() - started}
    duration = time.monotonic() - started
    out = proc.stdout or ""
    if len(out.encode()) > output_limit_bytes:
        return {"ok": False, "result": None, "tier": tier["tier"], "duration": duration,
                "error": f"output exceeded the {output_limit_bytes}-byte cap"}
    try:
        response = json.loads(out)
    except json.JSONDecodeError:
        why = "killed by a resource limit" if proc.returncode and proc.returncode < 0 \
            else f"exit code {proc.returncode}"
        return {"ok": False, "result": None, "tier": tier["tier"], "duration": duration,
                "error": f"sandboxed process produced no result ({why}): {(proc.stderr or '')[-500:]}"}
    return {"ok": bool(response.get("ok")), "result": response.get("result"),
            "error": response.get("error"), "tier": tier["tier"], "duration": duration,
            "limits_applied": response.get("limits_applied", [])}
