"""
Render the Mermaid diagrams in the architecture and developer docs to SVG.

The diagrams are written once, as Mermaid blocks in the Markdown, which GitHub renders
itself. MAYA's help renders the same pages, and shows each diagram from the SVG this script
draws (mermaid.js in headless Chrome, as ``build_spec.py`` draws the specification's). Each
SVG is named by a hash of its source, so an unchanged diagram is never redrawn and a page can
never show a stale one; files no source names any more are removed.

    python tools/docs/diagrams.py            # render what is missing
    python tools/docs/diagrams.py --check    # exit 1 if any diagram has no current SVG

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GROUPS = ("architecture", "developer")
MERMAID = re.compile(r"```mermaid\n(.*?)```", re.S)
MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"


def diagram_name(source: str) -> str:
    """The SVG file a Mermaid source is drawn into (shared with MAYA's help renderer)."""
    return hashlib.sha256(source.strip().encode()).hexdigest()[:16] + ".svg"


def sources() -> dict[Path, list[str]]:
    """Each group's diagram directory, and every Mermaid source in that group's pages."""
    out: dict[Path, list[str]] = {}
    for group in GROUPS:
        folder = ROOT / "docs" / group
        found = []
        for page in sorted(folder.glob("*.md")):
            found += MERMAID.findall(page.read_text(encoding="utf-8"))
        out[folder / "img" / "diagrams"] = found
    return out


def render(missing: list[tuple[Path, str]]) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.set_content(
            f'<html><body><div id="d"></div><script src="{MERMAID_JS}"></script></body></html>'
        )
        page.wait_for_function("window.mermaid !== undefined")
        page.evaluate(
            "mermaid.initialize({startOnLoad: false, theme: 'neutral', securityLevel: 'strict',"
            " flowchart: {htmlLabels: false}})"
        )
        for path, src in missing:
            try:
                svg = page.evaluate(
                    "async s => (await mermaid.render('m' + Date.now(), s)).svg", src
                )
            except Exception as exc:  # noqa: BLE001 - name the diagram that does not parse
                first = src.strip().splitlines()[0]
                raise SystemExit(
                    f"{path.parent.parent.parent.name}: a diagram does not parse ({first!r}): {exc}"
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(svg, encoding="utf-8")
            print(f"  drew {path.relative_to(ROOT)}")
        browser.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    missing: list[tuple[Path, str]] = []
    for folder, found in sources().items():
        wanted = {diagram_name(s): s for s in found}
        missing += [(folder / n, s) for n, s in wanted.items() if not (folder / n).exists()]
        if not a.check and folder.exists():
            for stale in folder.glob("*.svg"):
                if stale.name not in wanted:
                    stale.unlink()
                    print(f"  removed {stale.relative_to(ROOT)}")
    if a.check:
        for path, _ in missing:
            print(f"no current SVG for a diagram: {path.relative_to(ROOT)}")
        return 1 if missing else 0
    if missing:
        render(missing)
    return 0


if __name__ == "__main__":
    sys.exit(main())
