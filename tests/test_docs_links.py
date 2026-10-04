"""
Every relative link in the repository's Markdown resolves.

The documents in ``docs/`` are grouped in folders (getting-started, reference, design,
operations, quality, publications), and moving one breaks every link into or out of it
unless each is rewritten. This test catches the one that was not: README files, the docs,
the runbooks, the decision records, the in-product guides and the case studies.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".venv", "node_modules", ".git", "data", "build", "dist", "__pycache__", ".claude"}
LINK = re.compile(r"\]\(([^)\s#]+)(?:#[^)\s]*)?(?:\s+\"[^\"]*\")?\)")


def _markdown() -> list[Path]:
    return sorted(p for p in ROOT.rglob("*.md") if not SKIP & set(p.relative_to(ROOT).parts))


def test_every_relative_markdown_link_resolves():
    broken, checked = [], 0
    for page in _markdown():
        text = re.sub(
            r"```.*?```", "", page.read_text(encoding="utf-8", errors="ignore"), flags=re.S
        )
        for target in LINK.findall(text):
            if re.match(r"^[a-z]+:|^/", target) or not re.search(r"[./]", target):
                continue  # a URL, a site path, or notation such as ](F) in mathematics
            checked += 1
            if not (page.parent / target).resolve().exists():
                broken.append(f"{page.relative_to(ROOT)} -> {target}")
    assert checked > 200, checked
    assert broken == [], "\n".join(broken)


def test_the_docs_folder_is_grouped():
    loose = sorted(
        p.name
        for p in (ROOT / "docs").iterdir()
        if p.is_file() and p.name not in {"README.md", "CHANGELOG.md"}
    )
    assert loose == [], f"put these in a group folder under docs/: {loose}"
    groups = {p.name for p in (ROOT / "docs").iterdir() if p.is_dir()}
    assert groups == {
        "getting-started",
        "architecture",
        "developer",
        "reference",
        "design",
        "operations",
        "quality",
        "publications",
    }
