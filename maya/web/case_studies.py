"""
The case studies in Help: a card for each, and each study's README rendered as its page.

The READMEs are the source. The catalog -- number, title, domain, model type, what the study
is really about -- is read from the "Finished" table of ``case_studies/README.md``, so a
study appears in Help when it appears there and nowhere else has to be kept in step.

Rendering adds three things to the guide renderer's Markdown: mathematics (``$…$`` and
``$$…$$``) is kept away from Markdown, which would read its underscores as emphasis, and
typeset by KaTeX in the page; a link to another study opens that study's page; and a link
to a file in the study -- ``make_data.py``, a data file -- opens it in the repository.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2] / "case_studies"
REPO = "https://github.com/ajsinha/maya/blob/main/case_studies"
_ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*\[([^\]]+)\]\(([\w-]+)/\)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|", re.M
)
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def catalog() -> list[dict[str, str]]:
    """Every finished study, in the README's order, if the checkout carries them."""
    index = ROOT / "README.md"
    if not index.exists():
        return []
    text = index.read_text(encoding="utf-8")
    finished = text[text.find("### Finished") : text.find("### The catalogue")]
    out = []
    for num, title, folder, domain, model, about in _ROW.findall(finished):
        if (ROOT / folder / "README.md").exists():
            clean = re.sub(r"\*\*|`", "", about).strip()
            out.append(
                {
                    "num": num,
                    "title": title,
                    "slug": folder,
                    "domain": domain.strip(),
                    "model": re.sub(r"\*\*", "", model).strip(),
                    "about": clean if len(clean) < 260 else clean[:257].rsplit(" ", 1)[0] + "…",
                }
            )
    return sorted(out, key=lambda s: int(s["num"]))


def find(slug: str) -> dict[str, str] | None:
    return next((s for s in catalog() if s["slug"] == slug), None)


def _protect_maths(text: str) -> tuple[str, list[tuple[bool, str]]]:
    """Swap maths for placeholders outside code fences and code spans."""
    found: list[tuple[bool, str]] = []

    def keep(display: bool, tex: str) -> str:
        found.append((display, tex))
        return f"MAYAMATH{len(found) - 1}X"

    parts = re.split(r"(```.*?```)", text, flags=re.S)
    for i, part in enumerate(parts):
        if part.startswith("```"):
            continue
        spans = re.split(r"(`[^`\n]+`)", part)
        for j, span in enumerate(spans):
            if span.startswith("`"):
                continue
            span = re.sub(r"\$\$(.+?)\$\$", lambda m: keep(True, m.group(1)), span, flags=re.S)
            span = re.sub(r"(?<![\\$])\$([^$\n]+?)\$", lambda m: keep(False, m.group(1)), span)
            spans[j] = span
        parts[i] = "".join(spans)
    return "".join(parts), found


def _links(body: str, slug: str) -> str:
    def fix(m: re.Match[str]) -> str:
        href = m.group(1)
        if href.startswith(("http://", "https://", "#", "mailto:", "/")):
            return m.group(0)
        other = re.fullmatch(r"\.\./([\w-]+)/?", href)
        if other and (ROOT / other.group(1) / "README.md").exists():
            return f'href="/help/case-studies/{other.group(1)}"'
        target = (slug + "/" + href) if not href.startswith("../") else href[3:]
        return f'href="{REPO}/{target}" target="_blank" rel="noopener"'

    return re.sub(r'href="([^"]+)"', fix, body)


def render(slug: str) -> dict[str, Any]:
    """{"html", "toc", "title"} for a study's README; raises FileNotFoundError when absent."""
    import markdown

    from maya.web.guide_render import _CODE, _admonitions, _figure

    path = ROOT / slug / "README.md"
    mtime = path.stat().st_mtime
    hit = _CACHE.get(slug)
    if hit and hit[0] == mtime:
        return hit[1]
    source = path.read_text(encoding="utf-8")
    title = next((ln[2:].strip() for ln in source.splitlines() if ln.startswith("# ")), slug)
    text, maths = _protect_maths(source)
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "attr_list", "toc"],
        extension_configs={"toc": {"toc_depth": "2-3", "permalink": False}},
    )
    body = md.convert(text)
    body = _admonitions(_CODE.sub(_figure, body))
    body = body.replace(
        "<table>", '<div class="mt-scroll help-table-wrap"><table class="maya-table">'
    ).replace("</table>", "</table></div>")
    body = re.sub(r"<h1[^>]*>.*?</h1>", "", body, count=1, flags=re.S)
    for i, (display, tex) in enumerate(maths):
        tag = "div" if display else "span"
        cls = "maya-math display" if display else "maya-math"
        body = body.replace(
            f"MAYAMATH{i}X", f'<{tag} class="{cls}">{html.escape(tex.strip())}</{tag}>'
        )
    body = _links(body, slug)
    toc = [
        {
            "id": t["id"],
            "name": t["name"],
            "children": [{"id": c["id"], "name": c["name"]} for c in t.get("children", [])],
        }
        for t in md.toc_tokens
    ]
    out = {"html": body, "toc": toc, "title": title}
    _CACHE[slug] = (mtime, out)
    return out
