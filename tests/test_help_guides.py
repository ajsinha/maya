"""
Full-reference guides and tutorials: every declared guide has its Markdown,
every Markdown file is declared, each renders signed out, and each topic's
companion link resolves.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import re

import pytest

from maya.web.guide_render import GUIDES_DIR, render
from maya.web.help_catalog import COMPANIONS, GUIDES, all_topics
from tests.test_web import env  # noqa: F401 - the web fixture, reused


def test_guides_and_markdown_files_agree():
    declared = {g["slug"] for g in GUIDES}
    on_disk = {p.stem for p in GUIDES_DIR.glob("*.md")}
    assert declared == on_disk, (sorted(declared - on_disk), sorted(on_disk - declared))
    assert set(COMPANIONS) <= {t["slug"] for t in all_topics()}
    assert set(COMPANIONS.values()) <= declared


@pytest.mark.parametrize("slug", [g["slug"] for g in GUIDES])
def test_each_guide_renders_with_contents_and_no_script(slug):
    doc = render(slug)
    assert doc["toc"], f"{slug} has no ## sections"
    assert "<script" not in doc["html"].lower()
    assert len(re.findall(r"<table\b", doc["html"])) == \
        len(re.findall(r'<table class="maya-table"', doc["html"]))


def test_guides_are_served_to_anyone(env):  # noqa: F811 - the imported fixture
    from starlette.testclient import TestClient
    _, app, _, _ = env
    anon = TestClient(app)
    assert "Tutorials and full references" in anon.get("/help/guides").text
    for g in GUIDES:
        r = anon.get(f"/help/guides/{g['slug']}")
        assert r.status_code == 200 and g["title"] in r.text, g["slug"]
    assert anon.get("/help/guides/nope", follow_redirects=False).status_code == 303
    page = anon.get("/help/features").text
    assert "Full reference:" in page and "/help/guides/features-reference" in page

