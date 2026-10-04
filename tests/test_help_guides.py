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
from maya.web.help_catalog import GUIDE_HOME, GUIDES, LEGACY, SUBJECTS, all_parts
from tests.test_web import env  # noqa: F401 - the web fixture, reused

TEMPLATES = GUIDES_DIR.parent / "templates"


def test_every_guide_and_part_is_declared_once_and_exists():
    """One source of truth: every Markdown file is a library guide or a subject's reference,
    every part template is in exactly one subject, and nothing is declared without a file."""
    library = {g["slug"] for g in GUIDES}
    references = {s["guide"] for s in SUBJECTS.values() if s["guide"]}
    on_disk = {p.stem for p in GUIDES_DIR.glob("*.md")}
    assert not library & references
    assert library | references == on_disk, (
        sorted((library | references) - on_disk),
        sorted(on_disk - library - references),
    )
    parts = all_parts()
    assert len(parts) == len(set(parts)), "a part is in two subjects"
    templates = {p.stem for p in (TEMPLATES / "help" / "parts").glob("*.html")}
    assert set(parts) == templates, (sorted(set(parts) - templates), sorted(templates - set(parts)))
    for target in LEGACY.values():
        assert target.split("#")[0].removeprefix("/help/") in SUBJECTS, target


@pytest.mark.parametrize("slug", sorted({p.stem for p in GUIDES_DIR.glob("*.md")}))
def test_each_guide_renders_with_contents_and_no_script(slug):
    doc = render(slug)
    assert doc["toc"], f"{slug} has no ## sections"
    assert "<script" not in doc["html"].lower()
    assert len(re.findall(r"<table\b", doc["html"])) == len(
        re.findall(r'<table class="maya-table"', doc["html"])
    )


def test_subjects_library_and_old_addresses_are_served_to_anyone(env):  # noqa: F811
    from starlette.testclient import TestClient

    _, app, _, _ = env
    anon = TestClient(app)
    assert "Tutorials and catalogues" in anon.get("/help/guides").text
    for g in GUIDES:
        r = anon.get(f"/help/guides/{g['slug']}")
        assert r.status_code == 200 and g["title"] in r.text, g["slug"]
    assert anon.get("/help/guides/nope", follow_redirects=False).status_code == 303
    # a reference that became part of a subject opens on the subject's page
    for guide, home in GUIDE_HOME.items():
        r = anon.get(f"/help/guides/{guide}", follow_redirects=False)
        assert r.status_code == 301 and r.headers["location"] == f"/help/{home}", guide
    # every old topic address lands where its content went
    for old, target in LEGACY.items():
        r = anon.get(f"/help/{old}", follow_redirects=False)
        assert r.status_code == 301 and r.headers["location"] == target, old
    page = anon.get("/help/warrants").text
    for anchor in (
        'id="training-warrants"',
        'id="execution-warrants"',
        'id="bundles"',
        'id="reference"',
    ):
        assert anchor in page
    assert "Full reference" in page


def test_the_index_shows_one_card_per_subject(env):  # noqa: F811
    from starlette.testclient import TestClient

    _, app, _, _ = env
    index = TestClient(app).get("/help").text
    cards = re.findall(r'class="card help-card h-100" href="/help/([a-z0-9-]+)"', index)
    assert sorted(cards) == sorted(SUBJECTS), "one card per subject, and no other subject cards"
    assert len(cards) <= 22


def test_every_case_study_has_a_card_and_a_page_rendered_from_its_readme(env):  # noqa: F811
    from pathlib import Path

    from starlette.testclient import TestClient

    from maya.web.case_studies import catalog

    _, app, _, _ = env
    anon = TestClient(app)
    studies = catalog()
    runnable = sorted(p.parent.name for p in Path("case_studies").glob("[0-9]*/run.py"))
    assert sorted(s["slug"] for s in studies) == runnable, "every runnable study has a card"
    listing = anon.get("/help/case-studies").text
    assert "Case studies" in anon.get("/help").text
    for s in studies:
        assert f'href="/help/case-studies/{s["slug"]}"' in listing
        assert "*" not in s["about"] and "`" not in s["about"], (
            f"raw markdown on {s['slug']}'s card"
        )
        page = anon.get(f"/help/case-studies/{s['slug']}")
        assert page.status_code == 200 and s["title"].split(":")[0] in page.text, s["slug"]
        assert "MAYAMATH" not in page.text and "$$" not in page.text
    basel = anon.get("/help/case-studies/09-basel-irb-capital").text
    assert 'class="maya-math display"' in basel and "maths.js" in basel
    assert anon.get("/help/case-studies/nope", follow_redirects=False).status_code == 303


def test_every_help_link_lands_on_a_page_and_an_anchor_that_exist(env):  # noqa: F811
    """Links between help pages, and from the app's hint boxes into help, resolve: the page
    is served, and the #anchor is an id on it."""
    from starlette.testclient import TestClient

    _, app, client, _ = env
    anon = TestClient(app)
    pages = {f"/help/{s}": anon.get(f"/help/{s}").text for s in SUBJECTS}
    pages |= {
        f"/help/guides/{g['slug']}": anon.get(f"/help/guides/{g['slug']}").text for g in GUIDES
    }
    ids = {path: set(re.findall(r'\bid="([^"]+)"', text)) for path, text in pages.items()}
    sources = dict(pages)
    for path in ("/models/kernel", "/models/new", "/workbench/features/new", "/help"):
        sources[path] = client.get(path).text
    broken = []
    for where, text in sources.items():
        for href in re.findall(r'href="(/help/[^"]*)"', text):
            target, _, anchor = href.partition("#")
            if target in ("/help", "/help/guides", "/help/case-studies") or target.startswith(
                ("/help/case-studies/", "/help/docs/")  # docs pages: tests/test_docs_inside.py
            ):
                continue
            if target not in ids:
                broken.append(f"{where} -> {href} (no such page)")
            elif anchor and anchor not in ids[target]:
                broken.append(f"{where} -> {href} (no such anchor)")
    checked = sum(len(re.findall(r'href="/help/[^"]*#', t)) for t in sources.values())
    assert checked > 15, checked  # the check saw the anchored links it exists for
    assert broken == [], "\n".join(sorted(set(broken)))
