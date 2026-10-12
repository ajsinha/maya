"""
The examples gallery: every example valid, every one reachable, every one openable.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import pytest

from maya.services.catalog import blocking_errors, validate_feature_definition
from maya.web import examples
from maya.web.kernel_templates import TEMPLATES
from tests.test_web import env  # noqa: F401 - the web fixture, reused


@pytest.mark.parametrize("example", examples.FEATURES, ids=[e["slug"] for e in examples.FEATURES])
def test_every_feature_example_passes_mayas_own_validator(example):
    assert blocking_errors(validate_feature_definition(example["definition"])) == []
    assert example["title"] and example["summary"] and example["note"]


def test_the_gallery_shows_every_example_and_every_formula(env):  # noqa: F811
    from starlette.testclient import TestClient

    _, app, _, _ = env
    page = TestClient(app).get("/help/examples")
    assert page.status_code == 200
    for e in examples.FEATURES:
        assert f"/workbench/features/new?example={e['slug']}" in page.text
    for e in examples.OTHERS:
        assert f'id="other-{e["slug"]}"' in page.text
    for t in TEMPLATES:
        assert f"/models/kernel#template={t['key']}" in page.text


def test_a_feature_example_opens_in_the_designer_already_written():
    from maya.web.routes.workbench import _prefill

    d = _prefill({"example": "monthly-macro"})
    assert d["resolution"]["rules"]["unemployment_rate"] == "last_known_as_of(lag=30)"
    assert _prefill({"example": "no-such-example"}) == {}


def test_f1_opens_the_guide_for_the_page(env):  # noqa: F811
    from starlette.testclient import TestClient

    _, app, _, _ = env
    page = TestClient(app).get("/login").text
    assert 'data-help="/help/security"' in page
