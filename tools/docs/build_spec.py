"""
Render the specification (docs/MAYA_Requirements_and_Design.md) to .docx and .pdf.

The Markdown is the authority; these are renderings of it, rebuilt by this script
whenever the Markdown changes so they never fall behind. Mermaid diagrams are drawn
locally in headless Chrome (only the mermaid library is fetched, from its CDN; the
specification itself never leaves the machine) and embedded as PNG images.

Needs: pandoc 3 (``--pandoc``, or on PATH), Tectonic for the PDF, and Playwright
with an installed Chrome.

    python tools/docs/build_spec.py [--pandoc /path/to/pandoc] [--only docx|pdf]

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "MAYA_Requirements_and_Design.md"
MERMAID = re.compile(r"```mermaid\n(.*?)```", re.S)
MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"


def render_diagrams(sources: list[str], out: Path) -> list[Path]:
    """Each Mermaid source as a PNG, drawn by mermaid.js in headless Chrome."""
    from playwright.sync_api import sync_playwright
    paths = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(device_scale_factor=2)
        page.set_content(f'<html><body style="background:white"><div id="d"></div>'
                         f'<script src="{MERMAID_JS}"></script></body></html>')
        page.wait_for_function("window.mermaid !== undefined")
        page.evaluate("mermaid.initialize({startOnLoad: false, theme: 'neutral'})")
        for i, src in enumerate(sources, start=1):
            svg = page.evaluate("async s => (await mermaid.render('m' + Date.now(), s)).svg",
                                src)
            page.evaluate("s => document.getElementById('d').innerHTML = s", svg)
            path = out / f"diagram-{i}.png"
            page.locator("#d svg").screenshot(path=str(path))
            paths.append(path)
        browser.close()
    return paths


def with_images(text: str, images: list[Path]) -> str:
    it = iter(images)
    return MERMAID.sub(lambda m: f"![]({next(it).name})\n", text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pandoc", default=shutil.which("pandoc"))
    ap.add_argument("--only", choices=("docx", "pdf"))
    a = ap.parse_args()
    if not a.pandoc:
        sys.exit("pandoc not found: pass --pandoc (e.g. from the pypandoc_binary package)")
    text = SPEC.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        images = render_diagrams(MERMAID.findall(text), work)
        source = work / "spec.md"
        source.write_text(with_images(text, images), encoding="utf-8")
        common = [a.pandoc, str(source), "--from", "markdown-yaml_metadata_block", "--resource-path", str(work),
                  "--toc", "--toc-depth=2", "--metadata",
                  "title=MAYA — System Requirements & Design Specification"]
        if a.only in (None, "docx"):
            out = SPEC.with_suffix(".docx")
            subprocess.run([*common, "-o", str(out)], check=True)
            print(f"wrote {out.relative_to(ROOT)}")
        if a.only in (None, "pdf"):
            engine = shutil.which("tectonic") or str(Path.home() / ".local/bin/tectonic")
            out = SPEC.with_suffix(".pdf")
            subprocess.run([*common, "--pdf-engine", engine,
                            "-V", "mainfont=DejaVu Serif", "-V", "sansfont=DejaVu Sans",
                            "-V", "monofont=DejaVu Sans Mono", "-V", "fontsize=10pt",
                            "-V", "geometry:margin=2cm", "-V", "colorlinks=true",
                            "-o", str(out)], check=True)
            print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
