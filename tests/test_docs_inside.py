"""
The architecture and developer docs are held to the code they describe.

Three things are checked for every page under ``docs/architecture`` and ``docs/developer``:

* a code block that quotes source -- its first line is ``# path/to/file.py`` -- quotes it
  verbatim: every line of it is in that file (``# ...`` marks an elision);
* every Mermaid diagram has its current SVG, drawn by ``tools/docs/diagrams.py``, so Help never
  shows a stale or missing picture;
* Help serves every page, and every link and image on it lands somewhere that exists.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from maya.web import docs_render

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("architecture", "developer")
PAGES = sorted(p for g in GROUPS for p in (ROOT / "docs" / g).glob("*.md"))
FENCE = re.compile(r"```[a-z]*\n(.*?)```", re.S)
SOURCE = re.compile(
    r"^#\s+((?:maya|sdk|tools|tests|config|case_studies|maya_delta)/[\w./-]+\.\w+)\s*$"
)


def test_there_is_a_front_page_and_component_pages_in_each_group():
    for group in GROUPS:
        names = {p.stem for p in (ROOT / "docs" / group).glob("*.md")}
        assert "README" in names and len(names) >= 8, (group, sorted(names))


@pytest.mark.parametrize("page", PAGES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_quoted_source_is_verbatim(page):
    wrong = []
    for block in FENCE.findall(page.read_text(encoding="utf-8")):
        lines = block.splitlines()
        m = SOURCE.match(lines[0]) if lines else None
        if not m:
            continue
        source = ROOT / m.group(1)
        if not source.exists():
            wrong.append(f"{m.group(1)} does not exist")
            continue
        have = {ln.strip() for ln in source.read_text(encoding="utf-8").splitlines()}
        for ln in lines[1:]:
            s = ln.strip()
            if not s or s in ("# ...", "...", "…") or s.startswith("# ..."):
                continue
            if s not in have:
                wrong.append(f"{m.group(1)}: not in the file: {s[:90]}")
    assert wrong == [], f"{page.relative_to(ROOT)}:\n" + "\n".join(wrong)


def test_every_diagram_has_its_current_svg():
    missing = []
    for page in PAGES:
        for src in re.findall(r"```mermaid\n(.*?)```", page.read_text(encoding="utf-8"), re.S):
            svg = page.parent / "img" / "diagrams" / docs_render.diagram_name(src)
            if not svg.exists():
                missing.append(f"{page.relative_to(ROOT)}: {src.strip().splitlines()[0]}")
    assert missing == [], "run python tools/docs/diagrams.py:\n" + "\n".join(missing)


def test_help_serves_every_page_with_working_links_and_images(env):  # noqa: F811
    from starlette.testclient import TestClient

    _, app, _, _ = env
    anon = TestClient(app)
    seen: dict[str, str] = {}
    for page in PAGES:
        group = page.parent.name
        url = f"/help/docs/{group}" + ("" if page.stem == "README" else f"/{page.stem}")
        r = anon.get(url, follow_redirects=False)
        assert r.status_code == 200 and "Traceback" not in r.text, url
        seen[url] = r.text
    broken = []
    for url, text in seen.items():
        for target in set(re.findall(r'(?:href|src)="(/help/[^"#]*)', text)):
            if target in seen or target in ("/help", "/help/guides", "/help/case-studies"):
                continue
            status = anon.get(target, follow_redirects=False).status_code
            if status != 200:
                broken.append(f"{url} -> {target} ({status})")
    assert broken == [], "\n".join(sorted(broken))
    index = anon.get("/help").text
    assert 'href="/help/docs/architecture"' in index and 'href="/help/docs/developer"' in index
    subject = anon.get("/help/warrants").text
    assert 'href="/help/docs/architecture/warrants-and-custody"' in subject


def test_help_refuses_anything_outside_the_docs_images(env):  # noqa: F811
    from starlette.testclient import TestClient

    _, app, _, _ = env
    anon = TestClient(app)
    # a client normalises dot segments before sending, so these arrive as other paths, which
    # must not serve the file; the encoded forms reach the route itself, which refuses them
    for bad in ("../../../pyproject.toml", "screens/../../README.md"):
        r = anon.get(f"/help/docs/architecture/img/{bad}", follow_redirects=False)
        assert r.status_code in (303, 404) and "[project]" not in r.text, bad
    for bad in ("%2e%2e/%2e%2e/%2e%2e/pyproject.toml", "..%2f..%2f..%2fpyproject.toml"):
        r = anon.get(f"/help/docs/architecture/img/{bad}", follow_redirects=False)
        assert r.status_code == 404 and "[project]" not in r.text, bad
    assert docs_render.asset_path("architecture", "../../../pyproject.toml") is None
    assert anon.get("/help/docs/nowhere", follow_redirects=False).status_code == 303


from tests.test_web import env  # noqa: E402, F401 - the web fixture, reused
