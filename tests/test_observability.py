"""
Observability (§20, §18.1), asserted on the artifacts rather than the intent:
the exposition text Prometheus would scrape, the trace id that comes back and
lands in the audit row and the job, the spans an OpenTelemetry exporter
receives, the events written with their audit entries, and webhook requests a
receiver can verify — plus retries, dead-lettering and the SSRF refusal.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import re

import httpx
import pytest

from maya.core.errors import ValidationFailed
from maya.observability import tracing
from maya.sdk import Client
from tests.conftest import World, approved_feature, build_platform, price_csv

TRACE = "4bf92f3577b34da6a3ce929d0e0e4736"


@pytest.fixture(scope="module")
def obs():
    platform = build_platform(["--observability.webhooks.allow_private=true"])
    w = World(platform)
    platform.access.create_namespace(w.admin, name="eq")
    from maya.api.app import create_api

    yield w, create_api(platform)
    platform.shutdown()


def _admin(app):
    return Client(app=app, token=Client(app=app).auth.login("admin", "maya-dev-admin")["token"])


def test_metrics_exposition_is_scrapeable(obs):
    w, app = obs
    _admin(app).features.list()
    from starlette.testclient import TestClient

    body = TestClient(app).get("/metrics").text
    assert re.search(
        r'^maya_http_requests_total\{method="GET",route="/api/v1/features",'
        r'status="200"\} [1-9]',
        body,
        re.M,
    )
    assert "# TYPE maya_http_request_duration_seconds histogram" in body
    assert re.search(r'^maya_jobs\{state="queued"\} \d', body, re.M)
    assert re.search(r'^maya_seam_backend\{backend="[a-z_]+",seam="lake"\} 1', body, re.M)
    label = r'[a-zA-Z_][a-zA-Z0-9_]*="(?:[^"\\]|\\.)*"'  # quoted values may hold braces
    sample = re.compile(
        rf"^[a-z_:][a-z0-9_:]*(\{{{label}(?:,{label})*\}})? -?[0-9.]+(?:e[+-]?[0-9]+)?$"
    )
    for line in body.splitlines():  # every sample line is well-formed
        if line and not line.startswith("#"):
            assert sample.match(line), line


def test_metrics_can_require_a_token(monkeypatch):
    monkeypatch.setenv("MAYA_TEST_METRICS_TOKEN", "s3cret")
    platform = build_platform(["--observability.metrics.token_env=MAYA_TEST_METRICS_TOKEN"])
    from maya.api.app import create_api
    from starlette.testclient import TestClient

    web = TestClient(create_api(platform))
    assert web.get("/metrics").status_code == 401
    assert web.get("/metrics", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    platform.shutdown()


def test_one_trace_from_request_to_audit_row_and_job(obs):
    w, app = obs
    ref = approved_feature(w, "traced", price_csv(3))
    from starlette.testclient import TestClient

    web = TestClient(app)
    token = Client(app=app).auth.login("mick", "Test-password-1")["token"]
    r = web.post(
        "/api/v1/features/eq/traced/pins",
        json={"version_no": 1, "pin_name": "t", "as_of": "2026-01-03"},
        headers={
            "Authorization": f"Bearer {token}",
            "traceparent": f"00-{TRACE}-00f067aa0ba902b7-01",
        },
    )
    assert r.status_code == 202
    assert r.headers["traceparent"].startswith(f"00-{TRACE}-")
    assert r.json()["job"]["trace_id"] == TRACE, "the job continues the request's trace"
    with w.p.uow() as uow:
        row = uow.repo("audit_events").list(action="pin.requested", order_by=["-seq"], limit=1)[0]
    assert row["request_id"] == TRACE
    del ref


def test_spans_are_exported_and_nested():
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    tracing.configure(None, exporter=exporter)
    try:
        parent = tracing.parse(f"00-{TRACE}-00f067aa0ba902b7-01")
        with tracing.span("outer", parent=parent) as outer:
            with tracing.span("inner") as inner:
                assert inner.trace_id == outer.trace_id == TRACE
        spans = {s.name: s for s in exporter.get_finished_spans()}
        assert spans["inner"].parent.span_id == spans["outer"].context.span_id
        assert f"{spans['outer'].context.trace_id:032x}" == TRACE
        assert tracing.status()["exporting"]
    finally:
        tracing.configure(None)
    assert not tracing.status()["exporting"] and "not exported" in tracing.status()["detail"]


class Receiver:
    def __init__(self, fail_first: int = 0) -> None:
        self.calls: list[httpx.Request] = []
        self.fail_first = fail_first

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if len(self.calls) <= self.fail_first:
            return httpx.Response(503)
        return httpx.Response(204)


def test_events_are_written_with_their_audit_entries_and_delivered_signed(obs):
    w, app = obs
    receiver = Receiver()
    w.p.webhooks.transport = httpx.MockTransport(receiver)
    hook = w.p.webhooks.create(
        w.admin,
        name="catalog",
        url="https://hooks.example.test/in",
        event_types=["feature_version.*", "pin.*"],
    )
    secret = hook["secret"]
    ref = approved_feature(w, "announced", price_csv(3))
    w.p.features.pin(w.mick, ref, version_no=1, pin_name="e", as_of=dt.date(2026, 1, 3))
    w.drain()
    types = [e["type"] for e in w.p.webhooks.events(w.admin)]
    assert "feature_version.in_review" in types and "feature_version.approved" in types
    assert "pin.sealed" in types
    w.p.webhooks.deliver_due()
    delivered = [json.loads(r.content) for r in receiver.calls]
    assert {"feature_version.approved", "pin.sealed"} <= {d["type"] for d in delivered}
    assert all(d["type"] != "feature.ingested" for d in delivered), "the filter holds"
    request = receiver.calls[0]
    stamp = request.headers["X-Maya-Timestamp"]
    expected = (
        "sha256="
        + hmac.new(
            secret.encode(), stamp.encode() + b"." + request.content, hashlib.sha256
        ).hexdigest()
    )
    assert hmac.compare_digest(request.headers["X-Maya-Signature"], expected)
    listed = w.p.webhooks.list(w.admin)
    assert all("secret_sealed" not in h and "secret" not in h for h in listed)


def test_failed_deliveries_retry_then_dead_letter(obs):
    w, _ = obs
    flaky = Receiver(fail_first=1)
    w.p.webhooks.transport = httpx.MockTransport(flaky)
    hook = w.p.webhooks.create(w.admin, name="flaky", url="https://flaky.example.test/")
    first = w.p.webhooks.ping(w.admin, hook["id"])
    assert first["state"] == "pending" and first["last_status"] == 503
    with w.p.uow() as uow:
        uow.repo("webhook_deliveries").update(
            first["id"], {"next_attempt_at": dt.datetime.now(dt.timezone.utc)}
        )
    w.p.webhooks.deliver_due()
    with w.p.uow() as uow:
        assert uow.repo("webhook_deliveries").require(first["id"])["state"] == "delivered"
    w.p.webhooks.transport = httpx.MockTransport(lambda r: httpx.Response(500))
    w.p.webhooks.max_attempts = 1
    dead = w.p.webhooks.ping(w.admin, hook["id"])
    assert dead["state"] == "dead" and dead["last_error"] == "HTTP 500"
    w.p.webhooks.max_attempts = 8


def test_webhooks_cannot_target_private_networks():
    platform = build_platform()  # allow_private is off
    w = World(platform)
    for url, why in (
        ("http://hooks.example.test/", "https"),
        ("https://localhost/", "private or local"),
        ("https://127.0.0.1:8600/", "private or local"),
    ):
        with pytest.raises(ValidationFailed, match=why):
            platform.webhooks.create(w.admin, name="x", url=url)
    platform.shutdown()


def test_admin_observability_pages_render(obs):
    import re as _re
    from starlette.testclient import TestClient
    from maya.server import build_app

    w, _ = obs
    web = TestClient(build_app(w.p))
    page = web.get("/login")
    csrf = _re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    web.post(
        "/login", data={"username": "admin2", "password": "Test-password-1", "csrf_token": csrf}
    )
    if web.get("/admin/webhooks", follow_redirects=False).status_code == 303:
        page = web.get("/account/password")
        csrf = _re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        web.post(
            "/account/password",
            data={
                "old_password": "Test-password-1",
                "new_password": "Changed-pass-33",
                "confirm_password": "Changed-pass-33",
                "csrf_token": csrf,
            },
        )
    for path, needle in (
        ("/admin/webhooks", "X-Maya-Signature"),
        ("/admin/events", "pin.sealed"),
        ("/admin/health", "Span export"),
    ):
        r = web.get(path)
        assert r.status_code == 200 and needle in r.text, path


def test_the_event_type_filter_is_a_prefix(obs):
    """``type`` selects by prefix, not substring; LIKE wildcards in it are literal."""
    w, _ = obs
    ref = approved_feature(w, "prefixed", price_csv(3))
    w.p.features.pin(w.mick, ref, version_no=1, pin_name="x", as_of=dt.date(2026, 1, 3))
    w.drain()
    pins = {e["type"] for e in w.p.webhooks.events(w.admin, type_prefix="pin.")}
    assert pins and all(t.startswith("pin.") for t in pins)
    assert not w.p.webhooks.events(w.admin, type_prefix="sealed")  # a substring, not a prefix
    assert not w.p.webhooks.events(w.admin, type_prefix="pin_")  # '_' is not a wildcard
    page = w.p.webhooks.events_page(w.admin, type_prefix="feature_version.", page_size=50)
    assert page["items"] and all(e["type"].startswith("feature_version.") for e in page["items"])
