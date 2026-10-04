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
