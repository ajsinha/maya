"""
docs/reference/API_GUIDE.md is executed, not just read.

A real MAYA is started on a socket with an empty estate; every ``python`` block of the guide
runs in order in one namespace, as a reader following it would, and every ``bash`` block
runs with ``set -euo pipefail`` against the same server. An example that stops working
fails the build, which is the only way a guide full of examples stays true. The appendix is
checked against the OpenAPI document, so a new endpoint cannot ship without a line here.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "reference" / "API_GUIDE.md"
BLOCK = re.compile(r"^```(python|bash)\n(.*?)^```", re.S | re.M)


def blocks() -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for m in BLOCK.finditer(GUIDE.read_text(encoding="utf-8"))]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    home = tmp_path_factory.mktemp("api-guide")
    port = _free_port()
    env = dict(os.environ, MAYA_HOME=str(home), PYTHONPATH=str(ROOT))
    proc = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "run_maya_web.py"),
            f"--server.port={port}",
            "--jobs.workers=1",
            f"--storage.root={home}",
            f"--lake.root={home}/lake",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    import httpx

    deadline = time.monotonic() + 90
    while True:
        try:
            if httpx.get(url + "/readyz", timeout=1).status_code == 200:
                break
        except Exception:  # noqa: BLE001 - not up yet
            pass
        if proc.poll() is not None or time.monotonic() > deadline:
            proc.kill()
            raise AssertionError(proc.stdout.read().decode() if proc.stdout else "no output")
        time.sleep(0.25)
    yield url
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_every_example_in_the_api_guide_runs(server, monkeypatch):
    if not (shutil.which("curl") and shutil.which("jq")):
        pytest.skip("the guide's shell examples need curl and jq")
    monkeypatch.setenv("MAYA_URL", server)
    namespace: dict = {"__name__": "api_guide"}
    for i, (lang, code) in enumerate(blocks(), start=1):
        if lang == "python":
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                try:
                    exec(compile(code, f"API_GUIDE.md block {i}", "exec"), namespace)  # noqa: S102
                except Exception as exc:  # noqa: BLE001 - reported with the block
                    raise AssertionError(f"python block {i} failed: {exc}\n{code}") from exc
        else:
            r = subprocess.run(
                ["bash", "-c", "set -euo pipefail\n" + code],
                env=dict(os.environ, MAYA_URL=server),
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert r.returncode == 0, f"bash block {i} failed:\n{code}\n{r.stdout}\n{r.stderr}"
            if "Authorization" in code:  # an authenticated example must not get a problem back
                assert '"type": "' not in r.stdout, f"bash block {i} got an error:\n{r.stdout}"
    # what the walkthrough says it achieves, it achieved
    assert namespace["score"]["metrics"]["rmse"] < 1e-9
    assert namespace["bundle"]["status"] == "live"
    assert namespace["bad"]["status"] == "suspended"
    assert namespace["profile"]["tier"] == 2


def test_the_appendix_lists_every_endpoint():
    sys.path.insert(0, str(ROOT / "tools" / "ci"))
    try:
        from _common import api_app
    finally:
        sys.path.remove(str(ROOT / "tools" / "ci"))
    text = GUIDE.read_text(encoding="utf-8")
    listed = set(re.findall(r"^\| `([A-Z]+)` \| `([^`]+)` \|", text, re.M))
    served = {
        (method.upper(), path.removeprefix("/api/v1"))
        for path, ops in api_app().openapi()["paths"].items()
        for method in ops
    }
    assert served - listed == set(), f"endpoints missing from the guide: {sorted(served - listed)}"
    assert listed - served == set(), (
        f"the guide lists endpoints that do not exist: {sorted(listed - served)}"
    )
