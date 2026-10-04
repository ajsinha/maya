"""
Templates, the two-pass render, and the three output formats.

**Templates.** A template is a Jinja2 file producing Markdown, ``<name>.md.j2``. Its first
line may declare what it is::

    {# maya: kind=model_card; title=Model card (firm layout) #}

The library looks in ``documents.template_dir`` first and then at the built-ins, so a file
there named ``model_card.md.j2`` replaces the built-in model card, and any other file there
is a template of its own, offered for the kind it declares.

**What a template sees.** ``facts`` -- the snapshot of the model's record -- and:

* ``ai(key, instruction, words=150, profile=None)``: a section drafted by a language model
  from the facts. ``profile`` names a model profile; none means the default.
* ``table(rows, columns, headers=None)``: a Markdown table from a list of dicts.
* filters ``pct``, ``num``, ``yesno`` and ``dt``.

Missing facts render as empty rather than failing, so a template written for a model with a
challenger still renders for one without.

**Two passes.** The first renders the template with each ``ai()`` call leaving a marker and
recording its request; the requests are then drafted -- or, with drafting off, left marked
as not drafted -- and the second step puts each draft where its marker was, wrapped in
comments that name it. The label a reader sees on a drafted section ("drafted by …, not
reviewed" or "reviewed by …") is applied when the document is shown, from the document's
state, so approving it changes the label without changing the stored text.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

BUILT_IN_DIR = Path(__file__).resolve().parent / "templates"
HEADER = re.compile(r"^\{#\s*maya:\s*(?P<body>.*?)\s*#\}")
MARK = "\u2063AI:{}\u2063"
MARK_RE = re.compile("\u2063AI:([A-Za-z0-9_\\-]+)\u2063")
SECTION_RE = re.compile(r"<!--ai:(?P<key>[A-Za-z0-9_\-]+)-->\n?(?P<body>.*?)\n?<!--/ai-->", re.S)


@dataclass
class Template:
    name: str
    kind: str
    title: str
    origin: str  # "built-in", "custom", "custom (replaces the built-in)"
    path: Path
    sha256: str

    def as_row(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "title": self.title,
            "origin": self.origin,
            "sha256": self.sha256,
        }


@dataclass
class AiRequest:
    key: str
    instruction: str
    words: int = 150
    profile: str | None = None


@dataclass
class Rendered:
    markdown: str
    requests: list[AiRequest] = field(default_factory=list)


class Library:
    """The templates on offer: the firm's own first, then the built-ins."""

    def __init__(self, custom_dir: Path | None) -> None:
        self.custom = custom_dir if custom_dir and custom_dir.is_dir() else None

    def templates(self) -> list[Template]:
        found: dict[str, Template] = {}
        for folder, origin in ((BUILT_IN_DIR, "built-in"), (self.custom, "custom")):
            if folder is None:
                continue
            for path in sorted(folder.glob("*.md.j2")):
                name = path.name[: -len(".md.j2")]
                meta = _header(path.read_text(encoding="utf-8"))
                replaced = origin == "custom" and name in found
                found[name] = Template(
                    name,
                    meta.get("kind") or (found[name].kind if replaced else name),
                    meta.get("title") or name.replace("_", " ").capitalize(),
                    "custom (replaces the built-in)" if replaced else origin,
                    path,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
        return sorted(found.values(), key=lambda t: (t.kind, t.origin != "built-in", t.name))

    def get(self, name: str) -> Template:
        for t in self.templates():
            if t.name == name:
                return t
        from maya.core.errors import NotFound

        raise NotFound(f"No document template named '{name}'")

    def render(self, template: Template, facts: dict[str, Any]) -> Rendered:
        """The first pass: the template over the facts, ``ai()`` calls left as markers."""
        import jinja2
        from jinja2.sandbox import SandboxedEnvironment

        # The output is Markdown, not HTML, so HTML escaping here would corrupt it. Raw HTML is
        # neutralised where Markdown becomes HTML instead (to_html), so nothing a model's
        # description or a drafted section contains can reach a page as markup. Sandboxed: a
        # template is a file a firm places on the server, and it must not be a way to run code
        # there (no attribute walks to __class__, __globals__ and the like).
        env = SandboxedEnvironment(  # nosec B701
            loader=jinja2.FileSystemLoader([str(p) for p in (self.custom, BUILT_IN_DIR) if p]),
            undefined=jinja2.ChainableUndefined,
            autoescape=False,
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        requests: list[AiRequest] = []

        def ai(key: str, instruction: str, words: int = 150, profile: str | None = None) -> str:
            key = re.sub(r"[^A-Za-z0-9_\-]", "_", key)
            requests.append(AiRequest(key, instruction, int(words), profile))
            return MARK.format(key)

        env.globals.update(ai=ai, table=table)
        env.filters.update(pct=_pct, num=_num, yesno=_yesno, dt=_dt)
        source = template.path.read_text(encoding="utf-8")
        text = env.from_string(source).render(facts=facts)
        return Rendered(re.sub(r"\n{3,}", "\n\n", text).strip() + "\n", requests)


def fill(rendered: Rendered, drafts: dict[str, str]) -> str:
    """The second pass: each marker replaced by its draft, wrapped so it can be labelled."""

    def swap(m: re.Match[str]) -> str:
        return f"<!--ai:{m.group(1)}-->\n{drafts.get(m.group(1), '').strip()}\n<!--/ai-->"

    return MARK_RE.sub(swap, rendered.markdown)


def labelled(markdown: str, label: Callable[[str], str]) -> str:
    """The stored text with each drafted section introduced by its label, for showing."""

    def swap(m: re.Match[str]) -> str:
        return f"> *{label(m.group('key'))}*\n\n{m.group('body').strip()}\n"

    return SECTION_RE.sub(swap, markdown)


# -- helpers a template can use ------------------------------------------------------------
def table(rows: Any, columns: list[str], headers: list[str] | None = None) -> str:
    rows = list(rows or [])
    if not rows:
        return "*None recorded.*"
    head = headers or [c.replace("_", " ").capitalize() for c in columns]

    def cell(value: Any) -> str:
        if isinstance(value, float):
            value = _num(value)
        return str("" if value is None else value).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for row in rows:
        lines.append("| " + " | ".join(cell((row or {}).get(c)) for c in columns) + " |")
    return "\n".join(lines)


def _pct(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}%}"
    except (TypeError, ValueError):
        return "—"


def _num(value: Any, digits: int = 4) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—" if value in (None, "") else str(value)
    return (
        f"{v:.{digits}g}"
        if abs(v) < 1e-3 or abs(v) >= 1e6
        else f"{v:,.{digits}f}".rstrip("0").rstrip(".")
    )


def _yesno(value: Any) -> str:
    return "yes" if value else "no"


def _dt(value: Any) -> str:
    return str(value)[:10] if value else "—"


def _header(source: str) -> dict[str, str]:
    m = HEADER.match(source)
    if not m:
        return {}
    out = {}
    for part in m.group("body").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


# -- output formats -----------------------------------------------------------------------
def to_html(markdown_text: str, title: str) -> str:
    """A standalone HTML page. Display maths is a ``maya-math display`` block holding its TeX,
    which MAYA's own view typesets with KaTeX and a downloaded copy shows as source."""
    import markdown as md

    # Display maths is taken out before Markdown sees it: Markdown would read TeX's "\\" line
    # breaks and "\," spaces as escapes and eat the backslashes.
    maths: list[str] = []

    def hold(m: re.Match[str]) -> str:
        maths.append(m.group(1).strip())
        return f"\n\nMAYAMATH{len(maths) - 1}X\n\n"

    text = re.sub(r"\$\$(.+?)\$\$", hold, markdown_text, flags=re.S)
    # Every "<" becomes text before conversion: a description or a drafted section can say
    # anything, and none of it may reach the page as markup. Markdown's own syntax needs no "<".
    safe = text.replace("<", "&lt;")
    body = md.markdown(safe, extensions=["tables", "fenced_code", "sane_lists"])
    body = re.sub(
        r"(?:<p>)?MAYAMATH(\d+)X(?:</p>)?",
        lambda m: (
            f'<div class="maths maya-math display">{html.escape(maths[int(m.group(1))])}</div>'
        ),
        body,
    )
    return (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
        "<style>body{font:16px/1.6 Georgia,serif;max-width:52rem;margin:2rem auto;padding:0 1rem;color:#1a1a1a}"
        "h1,h2,h3{font-family:Helvetica,Arial,sans-serif;color:#6E1120}table{border-collapse:collapse;width:100%;"
        "font:14px/1.4 Helvetica,Arial,sans-serif}th,td{border-bottom:1px solid #ddd;padding:.35rem .5rem;text-align:left}"
        "blockquote{margin:1rem 0;padding:.4rem .9rem;border-left:4px solid #A51C30;background:#FBEEF0}"
        "code,.maths{font-family:Menlo,Consolas,monospace;font-size:.9em}.maths{background:#f4f1ec;padding:.5rem .8rem;"
        "border-radius:6px;overflow-x:auto}</style></head><body>" + body + "</body></html>"
    )


def to_latex(markdown_text: str, title: str) -> str:
    """The document as a LaTeX article, for the PDF (``maya.documents.latex``)."""
    from maya.documents.latex import to_latex as convert

    return convert(markdown_text, title)
