"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Markdown rendering.

Server-side and vendored, like everything else the interface depends on. The
alternative — shipping a JavaScript renderer and parsing in the browser — would
mean the help system stops working exactly when someone has disabled scripts or
is reading through a restricted desktop, which in a bank is a real audience
rather than a hypothetical one.

Extensions are chosen for what technical documentation actually needs: tables,
fenced code with highlighting, definition lists, footnotes, and heading anchors
so a section can be linked to directly from a runbook.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import markdown

from core.log import get_logger

logger = get_logger(__name__)

EXTENSIONS = ["extra", "tables", "fenced_code", "codehilite", "toc",
              "sane_lists", "attr_list", "admonition", "footnotes"]
CONFIG: Dict[str, Dict[str, Any]] = {
    "codehilite": {"css_class": "highlight", "guess_lang": False},
    "toc": {"permalink": False, "toc_depth": "2-3"},
}


class MarkdownRenderer:
    """Renders markdown to HTML and reports the headings it found.

    A fresh Markdown instance per render: the library carries state between
    calls (the toc, footnote counters), and reusing one silently leaks a
    document's table of contents into the next one.
    """

    def render(self, text: str) -> Tuple[str, List[Dict[str, Any]]]:
        engine = markdown.Markdown(extensions=EXTENSIONS, extension_configs=CONFIG)
        html = engine.convert(text)
        return html, self._headings(getattr(engine, "toc_tokens", []))

    def _headings(self, tokens) -> List[Dict[str, Any]]:
        """Flatten the nested toc into a list a template can iterate."""
        out: List[Dict[str, Any]] = []
        for t in tokens:
            out.append({"id": t["id"], "name": t["name"], "level": t["level"]})
            out.extend(self._headings(t.get("children", [])))
        return out
