"""
The architecture and developer docs (``docs/architecture``, ``docs/developer``), shown in Help.

They are written once, as Markdown in the repository, for whoever reads them on GitHub or in
an editor; Help renders the same files so a person inside MAYA reads the same words. Three
things change on the way:

* each Mermaid block becomes the SVG ``tools/docs/diagrams.py`` drew from it (named by a hash
  of its source, so a page can never show a stale diagram);
* links between these pages stay inside Help (``/help/docs/<group>/<page>``), links to the
  user references in ``maya/web/guides`` go to the Help subject that carries them, and images
  are served from the docs folders;
* a link to any other repository file keeps its text and loses its target, since Help cannot
  serve source files.

An installed package has no ``docs/`` folder; then these pages are simply not offered.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

GROUPS = {
    "architecture": "How MAYA fits together",
    "developer": "Developer guide",
}
_MERMAID = re.compile(r"```mermaid\n(.*?)```", re.S)
_HREF = re.compile(r'(href|src)="([^"#:]*?)(#[^"]*)?"')
_CACHE: dict[Path, tuple[float, dict[str, Any]]] = {}


REPO = Path(__file__).resolve().parents[2]  # the checkout; an installed package has no docs/


def docs_root() -> Path:
    return REPO / "docs"


def available() -> bool:
    return all((docs_root() / g / "README.md").exists() for g in GROUPS)


def diagram_name(source: str) -> str:
    """Must match tools/docs/diagrams.py, which draws the file this names."""
    return hashlib.sha256(source.strip().encode()).hexdigest()[:16] + ".svg"


def page_path(group: str, page: str) -> Path | None:
    if group not in GROUPS or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", page):
        return None
    path = docs_root() / group / f"{page}.md"
    return path if path.exists() else None


def asset_path(group: str, rel: str) -> Path | None:
    """An image under a group's img/ folder, and nothing else."""
    if group not in GROUPS:
        return None
    base = (docs_root() / group / "img").resolve()
    path = (base / rel).resolve()
    if not path.is_relative_to(base) or path.suffix.lower() not in (".png", ".svg", ".jpg"):
        return None
    return path if path.exists() else None


def pages(group: str) -> list[dict[str, str]]:
    """The group's pages in reading order: the README first, then in the order the README
    links to them, then any it does not link; each titled by its first heading."""
    folder = docs_root() / group
    readme = (
        (folder / "README.md").read_text(encoding="utf-8")
        if (folder / "README.md").exists()
        else ""
    )
    # the front page's index table, when it has one, is the reading order
    index = re.search(
        r"^## [^\n]*(?:index|guides)[^\n]*\n(.*?)(?=^## |\Z)", readme, re.M | re.S | re.I
    )
    linked = list(
        dict.fromkeys(re.findall(r"\]\(([a-z0-9-]+)\.md", index.group(1) if index else readme))
    )
    rank = {name: i for i, name in enumerate(linked)}
    out = []
    for path in sorted(
        folder.glob("*.md"),
        key=lambda p: (p.stem != "README", rank.get(p.stem, len(rank)), p.stem),
    ):
        first = next(
            (ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.startswith("# ")), ""
        )
        out.append({"page": path.stem, "title": first[2:].strip() or path.stem})
    return out


def _target(source: Path, href: str) -> str | None:
    """Where a relative link in a docs page goes inside Help, or None to drop it."""
    from maya.web.help_catalog import GUIDE_HOME, GUIDES

    target = (source.parent / href).resolve()
    root = docs_root().resolve()
    for group in GROUPS:
        folder = (root / group).resolve()
        if target.is_relative_to(folder):
            rel = target.relative_to(folder)
            if target.suffix == ".md":
                return f"/help/docs/{group}" + ("" if rel.stem == "README" else f"/{rel.stem}")
            return f"/help/docs/{group}/{rel.as_posix()}"
    static = (REPO / "maya" / "web" / "static").resolve()
    if target.is_relative_to(static):  # the screenshots Help serves itself
        return "/static/" + target.relative_to(static).as_posix()
    guides = (REPO / "maya" / "web" / "guides").resolve()
    if target.suffix == ".md" and target.parent == guides:
        if target.stem in GUIDE_HOME:
            return f"/help/{GUIDE_HOME[target.stem]}"
        if any(g["slug"] == target.stem for g in GUIDES):
            return f"/help/guides/{target.stem}"
    return None


def _rewrite(source: Path, html: str) -> str:
    def link(m: re.Match[str]) -> str:
        attr, href, frag = m.group(1), m.group(2), m.group(3) or ""
        if not href or href.startswith("/"):
            return m.group(0)
        to = _target(source, href)
        return f'{attr}="{to}{frag}"' if to else 'data-unlinked="1"'

    html = _HREF.sub(link, html)
    # a link Help cannot follow keeps its text
    return re.sub(r'<a data-unlinked="1"[^>]*>(.*?)</a>', r"\1", html, flags=re.S)


def render(group: str, page: str) -> dict[str, Any]:
    """{"html", "toc", "title"} for one docs page; raises FileNotFoundError when absent."""
    import markdown

    from maya.web import guide_render as gr

    path = page_path(group, page)
    if path is None:
        raise FileNotFoundError(f"{group}/{page}")
    mtime = path.stat().st_mtime
    hit = _CACHE.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    text = path.read_text(encoding="utf-8")
    text = _MERMAID.sub(lambda m: f"\n![Diagram](img/diagrams/{diagram_name(m.group(1))})\n", text)
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "admonition", "attr_list", "toc"],
        extension_configs={"toc": {"toc_depth": "2-3", "permalink": False}},
    )
    body = md.convert(text)
    body = gr._CODE.sub(gr._figure, body)
    body = gr._admonitions(body)
    body = body.replace(
        "<table>", '<div class="mt-scroll help-table-wrap"><table class="maya-table">'
    ).replace("</table>", "</table></div>")
    # a diagram opens full size in a new tab: the larger ones are dense at page width
    body = re.sub(
        r'<img alt="Diagram" src="([^"]+)"\s*/?>',
        r'<a href="\1" target="_blank" rel="noopener" title="Open the diagram full size">'
        r'<img class="help-diagram" alt="Diagram" src="\1"></a>',
        body,
    )
    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
    title = re.sub(r"<[^>]+>", "", title_m.group(1)) if title_m else page
    body = re.sub(r"<h1[^>]*>.*?</h1>", "", body, count=1, flags=re.S)
    body = gr.captioned(_rewrite(path, body))
    toc = [
        {
            "id": t["id"],
            "name": t["name"],
            "children": [{"id": c["id"], "name": c["name"]} for c in t.get("children", [])],
        }
        for t in md.toc_tokens
    ]
    out = {"html": body, "toc": toc, "title": title}
    _CACHE[path] = (mtime, out)
    return out
