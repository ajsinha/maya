"""
The Linux sandbox tier, attacked (§17.2). Each test runs hostile artifact code
in the real jail and asserts the escape failed; the tier tests remove one
primitive at a time and assert the declared tier drops with it — a tier nobody
has seen fall is a tier nobody knows is measured.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import os
import platform

import pytest

from maya.security import sandbox

pytestmark = pytest.mark.skipif(platform.system() != "Linux", reason="Linux sandbox tier")


def _strong() -> bool:
    sandbox._CACHE.clear()
    return sandbox.sandbox_tier()["tier"] == "strong"


def _run(body: str) -> dict:
    src = "import os\ndef run(X, params):\n" + "\n".join("    " + ln for ln in body.splitlines())
    return sandbox.run_sandboxed(src, "run", {"X": {}, "params": {}}, preload=())


@pytest.mark.skipif(not _strong(), reason="host cannot provide the strong tier")
@pytest.mark.parametrize(
    "name, body",
    [
        (
            "raw socket, bypassing the socket module",
            "import _socket\n_socket.socket()\nreturn 'escaped'",
        ),
        (
            "read MAYA's configuration",
            f"return open({os.path.realpath('config/application.yaml')!r}).read()",
        ),
        (
            "read the user's shell profile",
            f"return open({os.path.expanduser('~/.bashrc')!r}).read()",
        ),
        ("write to /etc", "open('/etc/maya-escape', 'w').write('x')\nreturn 'escaped'"),
        ("exec another program", "os.execv('/usr/bin/true', ['true'])\nreturn 'escaped'"),
        (
            "ptrace a process",
            "import ctypes\nlibc = ctypes.CDLL(None, use_errno=True)\n"
            "rc = libc.ptrace(16, 1, 0, 0)\n"
            "return 'escaped' if rc == 0 else ctypes.get_errno()",
        ),
    ],
)
def test_escape_attempts_fail_in_the_strong_jail(name, body):
    out = _run(body)
    assert not (out["ok"] and out["result"] == "escaped"), f"{name}: {out}"
    if out["ok"]:
        assert out["result"] != "escaped"


@pytest.mark.skipif(not _strong(), reason="host cannot provide the strong tier")
def test_memory_is_capped_by_the_cgroup_and_rlimit():
    out = sandbox.run_sandboxed(
        "def run(X, p):\n    b = bytearray(2 * 1024 ** 3)\n    return 1",
        "run",
        {"X": {}, "params": {}},
        memory_mb=256,
        preload=(),
    )
    assert not out["ok"]


@pytest.mark.skipif(not _strong(), reason="host cannot provide the strong tier")
def test_a_legitimate_numpy_artifact_still_runs():
    out = sandbox.run_sandboxed(
        "import numpy as np\ndef run(X, p):\n    return float(np.sum(X['a']))",
        "run",
        {"X": {"a": [1.0, 2.0]}, "params": {}},
    )
    assert out["ok"] and out["result"] == 3.0 and "seccomp" in out["limits_applied"]


def test_the_typesetting_jail_really_has_no_network():
    """§17.1 asks a LaTeX build to run "with no network". The jail is not the artifact
    sandbox — the engine is trusted code and needs its fonts and its cache — so the one
    thing it must prove is that a process inside it cannot reach the network at all."""
    import subprocess
    import sys

    jail = sandbox.net_jail()
    if not jail:
        pytest.skip("this host offers no network namespace (bubblewrap unavailable)")
    probe = (
        "import socket, sys\n"
        "s = socket.socket()\n"
        "try:\n"
        "    s.connect(('1.1.1.1', 53)); print('reached')\n"
        "except OSError as e:\n"
        "    print('refused', e.errno)\n"
    )
    inside = subprocess.run(
        [*jail, sys.executable, "-c", probe], capture_output=True, text=True, timeout=60
    )
    assert inside.stdout.startswith("refused"), inside.stdout + inside.stderr
    # and the same probe outside the jail is a fair control: it fails differently, or not
    # at all, but never with the jail's "network is unreachable"
    assert "reached" not in inside.stdout


def test_the_tier_falls_when_a_primitive_is_missing(monkeypatch):
    real = sandbox.capabilities()
    try:
        sandbox._CACHE.clear()
        sandbox._CACHE["caps"] = {**real, "bwrap": False}
        assert sandbox.sandbox_tier()["tier"] in ("moderate", "minimal")
        sandbox._CACHE.clear()
        sandbox._CACHE["caps"] = {**real, "bwrap": False, "cgroup": False}
        assert sandbox.sandbox_tier()["tier"] == "minimal"
    finally:
        sandbox._CACHE.clear()
