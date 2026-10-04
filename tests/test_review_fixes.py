"""
Defects found while documenting how MAYA fits together, each pinned by a test.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from maya.core.errors import ClientTooOld, NotApproved


def test_a_retired_execution_warrant_is_not_live_even_when_sealed():
    from maya.services.execution import ExecutionService
    from maya.services.warrants import WarrantService

    now = dt.datetime.now(dt.timezone.utc)
    ew = {"state": "retired", "sealed_at": now, "valid_to": now + dt.timedelta(days=30)}
    assert ExecutionService.status(ew) == "retired"
    assert ExecutionService.status({**ew, "state": "approved"}) == "live"
    assert WarrantService.status({"state": "withdrawn", "sealed_at": now}) == "withdrawn"
    service = ExecutionService.__new__(ExecutionService)
    with pytest.raises(NotApproved, match="retired"):
        service.check({**ew, "spec": {"environments": ["prod"], "contact": "x"}}, "prod")


def test_a_document_template_cannot_reach_python_internals(tmp_path):
    from jinja2.exceptions import SecurityError

    from maya.documents.render import Library

    (tmp_path / "model_card.md.j2").write_text(
        "{# maya: kind=model_card; title=Evil #}\n{{ ''.__class__.__mro__[1].__subclasses__() }}\n",
        encoding="utf-8",
    )
    lib = Library(tmp_path)
    with pytest.raises(SecurityError):
        lib.render(lib.get("model_card"), {})


def test_cloning_a_handle_made_from_a_full_reference_keeps_its_namespace():
    from maya.sdk.handles import FeatureHandle

    made = {}

    def create(namespace, name, definition):
        made.update(namespace=namespace, name=name, definition=definition)
        return {"name": name}

    client = SimpleNamespace(features=SimpleNamespace(create=create))
    handle = FeatureHandle.of(
        client, {"latest_version": 3}, ref="maya://feature/eq/prices@v3", kind="feature"
    )
    handle.clone("prices_adj")
    assert made["namespace"] == "eq"
    assert made["definition"]["extends"]["parent"] == "eq/prices@v3"


def test_an_sdk_too_old_for_the_server_gets_a_typed_problem(monkeypatch):
    from starlette.testclient import TestClient

    from maya.api import app as app_module
    from tests.conftest import build_platform

    p = build_platform()
    try:
        client = TestClient(app_module.create_api(p))
        r = client.get("/api/v1/auth/me", headers={"X-Maya-Client": "python/0.0.1"})
        assert r.status_code == 426
        assert r.headers["content-type"].startswith("application/problem+json")
        assert r.json()["type"] == "client_too_old" and "maya-sdk" in r.json()["detail"]
    finally:
        p.shutdown()
    from maya.sdk._shared.errors import ERRORS_BY_CODE

    assert ERRORS_BY_CODE["client_too_old"] is ClientTooOld


def test_the_cold_pin_age_is_a_declared_setting():
    from maya.config import schema

    assert schema.find("retention.cold_after_days").default == "180"


def test_a_webhook_is_sent_to_the_address_that_was_vetted_and_rebinding_is_refused(monkeypatch):
    """Resolve once, vet, connect there: a DNS answer that turns private between the check and
    the connection must not reach the private address."""
    import socket

    import httpx

    from tests.conftest import World, build_platform

    answers = {"hooks.example.com": "93.184.216.34"}

    def fake_getaddrinfo(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (answers[host], 0))]

    monkeypatch.setattr("maya.services.webhooks.socket.getaddrinfo", fake_getaddrinfo)
    seen = []

    def receiver(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    p = build_platform()  # private targets refused
    try:
        w = World(p)
        p.webhooks.transport = httpx.MockTransport(receiver)
        hook = p.webhooks.create(w.admin, name="pinned", url="https://hooks.example.com/in")
        p.webhooks.ping(w.admin, hook["id"])
        assert seen, "the ping was not sent"
        sent = seen[-1]
        assert sent.url.host == "93.184.216.34"  # the vetted address, not a second lookup
        assert sent.headers["host"] == "hooks.example.com"
        assert sent.extensions["sni_hostname"] == "hooks.example.com"  # TLS checks the name
        answers["hooks.example.com"] = "10.0.0.5"  # rebinding: the name now points inside
        before = len(seen)
        out = p.webhooks.ping(w.admin, hook["id"])
        assert len(seen) == before, "a request reached the rebinding address"
        assert out["state"] != "delivered" and "private" in (out.get("last_error") or "")
    finally:
        p.shutdown()


def test_a_page_and_its_in_process_calls_take_one_slot_and_one_rate_token():
    """A web page calls the SDK in process through the same application. With room for one
    request in flight and a burst of two, a dashboard that makes several inner calls must
    still render: its calls are part of it, not competitors for its slot."""
    import re

    from starlette.testclient import TestClient

    from maya.server import build_app
    from tests.conftest import build_platform

    p = build_platform(["--api.limits.max_concurrent=1", "--api.limits.burst=3"])
    try:
        web = TestClient(build_app(p))
        page = web.get("/login")
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        web.post(
            "/login",
            data={"username": "admin", "password": "maya-dev-admin", "csrf_token": token},
            follow_redirects=False,
        )
        home = web.get("/")  # the dashboard: queue, features, models, health, jobs...
        assert home.status_code == 200, home.text[:300]
        assert "overloaded" not in home.text and "rate_limited" not in home.text
    finally:
        p.shutdown()


def test_the_concurrency_limit_still_holds_for_separate_requests():
    import asyncio

    from maya.api.limits import NESTING, Shed

    started = asyncio.Event()
    release = asyncio.Event()
    sent: list[int] = []

    async def app(scope, receive, send):
        started.set()
        await release.wait()

    shed = Shed(app, max_concurrent=1, timeout=0)

    async def send(message):
        if message["type"] == "http.response.start":
            sent.append(message["status"])

    async def main():
        first = asyncio.create_task(shed({"type": "http"}, None, send))
        await started.wait()
        assert NESTING.get() == 0  # the admitting task's context, not this one's
        await shed({"type": "http"}, None, send)  # a separate request: refused
        release.set()
        await first

    asyncio.run(main())
    assert sent == [503]


def test_the_lineage_of_a_bare_object_is_drawn_through_its_versions(journey):  # noqa: F811
    """Lineage is recorded between versions and pins; asking about the object itself used to
    find nothing. It is now joined to each of its versions and pins that has lineage."""
    w = journey
    root = "maya://model/quant/linear"
    with w.p.uow("test") as uow:  # as a training warrant records it: between versions
        uow.repo("lineage_edges").link(
            "maya://featureset/quant/panel@v1", root + "@v1", "trained_on", "test"
        )
    g = w.p.ops.lineage(root, depth=3, p=w.devi)
    ids = {n["id"] for n in g["nodes"]}
    assert root in ids and len(ids) > 1, ids
    joins = [e for e in g["edges"] if e["type"] == "version_of" and e["target"] == root]
    assert joins and all(e["source"].startswith(root + "@") for e in joins)
    assert any(e["type"] == "trained_on" for e in g["edges"])
    # a version or pin as root is walked exactly as before
    one = w.p.ops.lineage(root + "@v1", depth=1, p=w.devi)
    assert not any(e["type"] == "version_of" for e in one["edges"])


from tests.test_warrants import journey  # noqa: E402, F401 - the fixture, reused
