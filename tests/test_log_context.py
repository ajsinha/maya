"""
The two §20 logging requirements that were missing: every line carrying request
id, trace id, actor and object reference, and the level configurable per module
at runtime.

These are asserted on the emitted lines and on a running logger, not on the
existence of a helper — a formatter that can carry an actor is worth nothing
until the middleware and the job runner actually bind one.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json
import logging

import pytest

from maya.core.errors import PermissionDenied, ValidationFailed
from maya.observability import logs, tracing
from tests.conftest import World, build_platform


@pytest.fixture
def captured():
    """The JSON formatter's output, without touching the root logger's real handlers."""
    lines: list[str] = []

    class Sink(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(self.format(record))

    sink = Sink()
    sink.setFormatter(logs.JsonFormatter())
    logger = logging.getLogger("maya.test.logctx")
    logger.addHandler(sink)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        yield logger, lines
    finally:
        logger.removeHandler(sink)
        logger.setLevel(logging.NOTSET)
        logger.propagate = True


def test_a_line_carries_the_request_id_actor_object_and_trace(captured):
    logger, lines = captured
    with tracing.span("test"):
        with logs.bound(request_id="rq-1", actor="dana", object_ref="maya://feature/eq/prices"):
            logger.info("pinned")
    row = json.loads(lines[-1])
    assert row["request_id"] == "rq-1"
    assert row["actor"] == "dana"
    assert row["object_ref"] == "maya://feature/eq/prices"
    assert len(row["trace_id"]) == 32 and len(row["span_id"]) == 16
    assert row["message"] == "pinned" and row["logger"] == "maya.test.logctx"


def test_the_binding_is_restored_afterwards_so_lines_do_not_leak_context(captured):
    logger, lines = captured
    with logs.bound(actor="dana"):
        logger.info("mine")
    logger.info("nobody's")
    assert json.loads(lines[-2])["actor"] == "dana"
    assert "actor" not in json.loads(lines[-1])


def test_the_text_format_carries_the_same_context(captured):
    logger, _ = captured
    lines: list[str] = []

    class Sink(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(self.format(record))

    sink = Sink()
    sink.setFormatter(logs.TextFormatter())
    logger.addHandler(sink)
    try:
        with logs.bound(actor="mick", request_id="rq-2"):
            logger.warning("careful")
    finally:
        logger.removeHandler(sink)
    assert "actor=mick" in lines[-1] and "request_id=rq-2" in lines[-1]
    assert "careful" in lines[-1]


def test_only_the_declared_fields_are_carried(captured):
    """A bind is not a free-form log payload: §20 forbids logging data values, so a caller
    cannot smuggle a row into a line by binding it."""
    logger, lines = captured
    with logs.bound(actor="dana", close_price="123.45"):
        logger.info("x")
    row = json.loads(lines[-1])
    assert row["actor"] == "dana" and "close_price" not in row


def test_a_module_level_changes_at_runtime_and_can_be_put_back():
    resolution = logging.getLogger("maya.resolution")
    before = resolution.level
    try:
        logs.set_level("maya.resolution", "debug")
        assert resolution.level == logging.DEBUG
        assert logs.levels()["maya.resolution"] == "DEBUG"
        assert resolution.isEnabledFor(logging.DEBUG)
        child = logging.getLogger("maya.resolution.resolver")
        assert child.isEnabledFor(logging.DEBUG), "the override applies to everything under it"
        logs.set_level("maya.resolution", "inherit")
        assert "maya.resolution" not in logs.levels()
        assert resolution.level == logging.NOTSET
    finally:
        resolution.setLevel(before)


def test_an_unknown_level_is_refused_naming_what_is_accepted():
    with pytest.raises(ValidationFailed, match="not a log level"):
        logs.set_level("maya.resolution", "chatty")
    with pytest.raises(ValidationFailed, match="CRITICAL, ERROR, WARNING, INFO, DEBUG"):
        logs.set_level("maya", "trace")


def test_levels_reports_the_root_level_and_every_override():
    assert logs.levels()[""] in logs.LEVELS
    logs.set_level("maya.jobs", "ERROR")
    try:
        assert logs.levels() == {**logs.levels(), "maya.jobs": "ERROR"}
    finally:
        logs.set_level("maya.jobs", "inherit")


def test_setting_a_level_is_a_techops_action_and_is_audited():
    platform = build_platform()
    w = World(platform)
    try:
        with pytest.raises(PermissionDenied):
            platform.ops.set_log_level(w.dana, "maya.resolution", "DEBUG")
        with pytest.raises(PermissionDenied):
            platform.ops.log_levels(w.mona)
        out = platform.ops.set_log_level(w.tess, "maya.resolution", "DEBUG")
        assert out["levels"]["maya.resolution"] == "DEBUG"
        assert out["role"] == "primary" and out["pid"] > 0
        assert platform.ops.log_levels(w.admin)["levels"]["maya.resolution"] == "DEBUG"
        with platform.uow() as uow:
            row = uow.repo("audit_events").list(action="log_level.set", order_by=["-seq"], limit=1)
        assert row and row[0]["detail"] == {"module": "maya.resolution", "level": "DEBUG"}
    finally:
        logs.set_level("maya.resolution", "inherit")
        platform.shutdown()


def test_a_job_binds_its_owner_and_trace_onto_every_line_it_logs():
    """A job's logs are the only record of what it did; without the owner and the job
    reference on them, a failure in a fleet of workers is anonymous."""
    platform = build_platform()
    World(platform)
    seen: dict[str, str] = {}

    def handler(ctx, params):
        seen.update(logs.context())
        return {"ok": True}

    platform.jobs.register("test.logging", handler)
    try:
        with platform.uow("dana") as uow:
            job = platform.jobs.submit(uow, "test.logging", {}, owner="dana")
        assert platform.jobs.run_one("t") is True
        assert seen["actor"] == "dana"
        assert seen["object_ref"] == f"maya://job/{job['id']}"
        assert seen["request_id"] == job["trace_id"] and seen["channel"] == "worker"
        assert logs.context() == {}, "and it does not leak into the worker's next job"
    finally:
        platform.shutdown()


def test_a_unit_of_work_binds_its_actor():
    """The actor reaches a log line through the unit of work, not through the HTTP
    dependency: FastAPI resolves a sync dependency in a worker thread whose context copy is
    thrown away, so a bind there would be invisible to the code that logs. The unit of work
    knows the actor and runs in the same context as everything inside it."""
    platform = build_platform()
    World(platform)
    try:
        assert "actor" not in logs.context()
        with platform.uow("dana"):
            assert logs.context()["actor"] == "dana"
            with platform.uow("system"):
                assert logs.context()["actor"] == "system"
            assert logs.context()["actor"] == "dana", "the outer actor comes back"
        assert "actor" not in logs.context()
    finally:
        platform.shutdown()


def test_an_http_request_binds_its_request_id_and_the_path_it_is_about():
    """Asserted through the service the route calls, which is where a log line would be
    written."""
    platform = build_platform()
    World(platform)
    from starlette.testclient import TestClient

    from maya.api.app import create_api
    from maya.sdk import Client

    app = create_api(platform)
    seen: dict[str, str] = {}
    original = platform.ops.health

    def probe():
        seen.update(logs.context())
        return original()

    platform.ops.health = probe  # type: ignore[method-assign]
    try:
        token = Client(app=app).auth.login("admin", "maya-dev-admin")["token"]
        TestClient(app).get(
            "/api/v1/system/health",
            headers={"Authorization": f"Bearer {token}", "x-request-id": "rq-http"},
        )
        assert seen["request_id"] == "rq-http"
        assert seen["object_ref"] == "/api/v1/system/health"
        assert seen["channel"] == "api"
    finally:
        platform.ops.health = original  # type: ignore[method-assign]
        platform.shutdown()
