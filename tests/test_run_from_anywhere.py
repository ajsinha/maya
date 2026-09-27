"""
Scripts run from wherever an IDE starts them, beside whatever else shares the estate.

PyCharm runs a case study from the study's own folder, often with the web server running on
the same MAYA home. Two things broke there: a relative default path was read against the
working directory, and ``drain()`` returned while a job the server's worker had claimed was
still running, so the study read a pin that did not exist yet.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import threading
import time

import pytest

from maya.testing.kit import Maya
from tests.conftest import build_platform


@pytest.fixture(scope="module")
def platform():
    p = build_platform()
    yield p
    p.shutdown()


def test_the_tiering_questionnaire_is_found_from_any_working_directory(
    platform, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    assert platform.governance.questionnaire()["questions"]


def _running_job(platform, started: dt.datetime) -> str:
    with platform.uow() as uow:
        return uow.repo("jobs").add(
            {
                "job_type": "elsewhere",
                "owner": "admin",
                "state": "running",
                "params": {},
                "params_hash": "0" * 64,
                "trace_id": "0" * 32,
                "started_at": started,
            }
        )["id"]


def test_drain_waits_for_a_job_another_process_claimed(platform, tmp_path):
    maya = Maya(platform, tmp_path, "anywhere", {})
    job_id = _running_job(platform, dt.datetime.now(dt.timezone.utc))

    def finish_elsewhere() -> None:
        time.sleep(0.6)
        with platform.uow() as uow:
            uow.repo("jobs").update(job_id, {"state": "succeeded"})

    threading.Thread(target=finish_elsewhere).start()
    began = time.monotonic()
    maya.drain(wait_seconds=20)
    assert time.monotonic() - began >= 0.5


def test_drain_does_not_wait_for_a_job_a_dead_process_left_running(platform, tmp_path):
    maya = Maya(platform, tmp_path, "anywhere2", {})
    stale = _running_job(platform, dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1))
    began = time.monotonic()
    maya.drain(wait_seconds=20)
    assert time.monotonic() - began < 5
    with platform.uow() as uow:
        uow.repo("jobs").update(stale, {"state": "failed"})
