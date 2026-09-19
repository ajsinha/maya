"""
The worker-only process (§15.1 "background jobs on worker processes", §24.1's
worker pods), started the one supported way: ``python run_maya_web.py --worker``.

This is a process test, not a unit test, because the claim being made is about a
process: that a second operating-system process, with no HTTP server and no
schema of its own, drains work an already-running MAYA queued. Asserting that a
thread inside the test interpreter ran the job would prove nothing about the
deployment shape the specification asks for.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PG = os.environ.get("MAYA_TEST_PG_URL")


def _platform(home: Path):
    """A primary platform over ``home``, with no workers of its own: whatever drains the
    queue in these tests is the separate process, never this one."""
    import sys as _sys

    _sys.argv = ["pytest", "--jobs.workers=0"]
    os.environ["MAYA_HOME"] = str(home)
    from maya.config import load_settings
    from maya.services.platform import Platform

    settings = load_settings(ROOT / "config" / "application.yaml", fresh=True)
    return Platform.build(settings, start_workers=False)


def _launch_worker(home: Path) -> subprocess.Popen:
    env = dict(os.environ, MAYA_HOME=str(home))
    env.pop("MAYA_CONFIG_FILE", None)
    return subprocess.Popen(
        # -u: the banner is a print() to a pipe, which Python would otherwise hold in a
        # block buffer until the process exits — and this test reads it while it runs
        [sys.executable, "-u", "run_maya_web.py", "--worker", "--logging.level=WARNING"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _wait_for(platform, job_id: str, proc: subprocess.Popen, seconds: float = 120.0) -> str:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate()
            pytest.fail(f"the worker exited {proc.returncode}: {(out + err).decode()[-3000:]}")
        with platform.uow() as uow:
            state = uow.repo("jobs").require(job_id)["state"]
        if state not in ("queued", "running"):
            return state
        time.sleep(0.4)
    return "timed out"


@pytest.fixture(scope="module")
def estate(tmp_path_factory):
    if PG:
        pytest.skip("the worker test drives one MAYA_HOME; it runs on the SQLite default")
    home = tmp_path_factory.mktemp("maya-worker")
    platform = _platform(home)
    yield home, platform
    platform.shutdown()


def test_a_worker_process_drains_work_the_web_process_queued(estate):
    """The whole point: a job submitted where no worker thread exists is finished by a
    separate process that serves no requests."""
    home, platform = estate
    assert platform.jobs.n_workers == 0, "nothing in this process can run the job"
    with platform.uow("admin") as uow:
        job = platform.jobs.submit(uow, "integrity.verify", {"by": "test"}, owner="admin")
    proc = _launch_worker(home)
    try:
        state = _wait_for(platform, job["id"], proc)
        assert state == "succeeded", state
        with platform.uow() as uow:
            row = uow.repo("jobs").require(job["id"])
        assert row["worker"] and row["worker"] != "inline", "a worker in another process claimed it"
        assert str(os.getpid()) not in str(row["worker"]), "and it was not this process"
        with platform.uow() as uow:
            verified = uow.repo("audit_events").list(action="integrity.verified", limit=5)
        assert verified, "the job really ran: it left its audit entry"
    finally:
        proc.terminate()
        proc.wait(30)


def test_the_worker_binds_no_port_and_says_which_role_it_is(estate):
    import select

    home, _ = estate
    proc = _launch_worker(home)
    try:
        deadline = time.time() + 90
        banner = b""
        while time.time() < deadline and b"No port is bound" not in banner:
            if not select.select([proc.stdout], [], [], 1.0)[0]:
                if proc.poll() is not None:
                    break
                continue
            chunk = os.read(proc.stdout.fileno(), 4096)
            if not chunk:
                break
            banner += chunk
        text = banner.decode(errors="replace")
        assert "Role          worker" in text, text[-2000:]
        assert "No port is bound" in text
        assert "Serving on http" not in text
    finally:
        proc.terminate()
        proc.wait(30)


def test_a_worker_neither_seeds_nor_reaps(estate):
    """A worker joins an estate the primary prepared. Reaping from a second process would
    requeue jobs the first is halfway through, so a worker must not do it."""
    home, platform = estate
    from maya.config import load_settings
    from maya.services.platform import Platform

    sys.argv = ["pytest"]
    os.environ["MAYA_HOME"] = str(home)
    with platform.uow("admin") as uow:
        running = platform.jobs.submit(
            uow, "integrity.verify", {"pretend": "running"}, owner="admin"
        )
    with platform.uow() as uow:
        uow.repo("jobs").update(running["id"], {"state": "running", "worker": "elsewhere-w0"})
    worker = Platform.build(
        load_settings(ROOT / "config" / "application.yaml", fresh=True),
        role="worker",
        start_workers=False,
    )
    try:
        assert worker.role == "worker" and worker.primary is False
        with worker.uow() as uow:
            assert uow.repo("jobs").require(running["id"])["state"] == "running"
        assert worker.ops.health()["process"]["role"] == "worker"
        assert worker.ops.health()["jobs"]["workers"] == worker.jobs.n_workers
    finally:
        with platform.uow() as uow:
            uow.repo("jobs").update(running["id"], {"state": "cancelled"})
        worker.shutdown()
