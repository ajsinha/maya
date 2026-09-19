"""
Several web processes (``server.workers`` above 1), started exactly as in
production: ``python run_maya_web.py --server.workers=2``. Requests are served by
more than one process, and a job submitted through a web process runs in the
launching process — the only one with job workers.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from maya.sdk import Client
from tests.conftest import price_csv

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(os.environ, MAYA_HOME=str(tmp_path_factory.mktemp("maya-web-processes")))
    env.pop("MAYA_CONFIG_FILE", None)
    proc = subprocess.Popen([sys.executable, "run_maya_web.py", "--server.workers=2",
                             f"--server.port={port}", "--logging.level=WARNING"],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 90
    while True:
        if proc.poll() is not None:
            pytest.fail(proc.stderr.read().decode()[-3000:])
        try:
            if httpx.get(base + "/login", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        if time.time() > deadline:
            proc.kill()
            pytest.fail("the server did not come up")
        time.sleep(0.3)
    token = Client(base).auth.login("admin", "maya-dev-admin")["token"]
    yield base, token
    proc.terminate()
    proc.wait(30)


def test_requests_are_served_by_more_than_one_web_process(server):
    base, token = server
    seen = {}
    for _ in range(40):                      # a fresh connection each time
        h = Client(base, token=token).admin.health()
        seen[h["process"]["pid"]] = h["process"]["role"]
        if len(seen) > 1:
            break
    assert len(seen) > 1 and set(seen.values()) == {"web"}
    assert Client(base, token=token).admin.health()["jobs"]["workers"] == 0


def test_a_job_submitted_through_a_web_process_runs_in_the_launcher(server):
    base, token = server
    Client(base, token=token).admin.create_user("desi", password="Test-password-1",
                                                roles=["feature_designer"])
    sdk = Client(base, token=Client(base).auth.login("desi", "Test-password-1")["token"])
    ref = sdk.features.quick(price_csv(5), name="multi")["ref"]    # scratch: pins directly
    job = sdk.features.pin(ref, version_no=1, pin_name="p", as_of="2026-01-05")["job"]
    deadline = time.time() + 60
    while (state := sdk.jobs.get(job["id"])["state"]) in ("queued", "running"):
        assert time.time() < deadline, "the job was never picked up"
        time.sleep(0.3)
    assert state == "succeeded"
    assert any(p["state"] == "sealed" for p in sdk.features.get(ref)["pins"])
