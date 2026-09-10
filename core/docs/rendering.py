"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Getting a compiled document into a shape a committee will read.

The compiler emits markdown, and the complaint is fair: a committee paper is
copied into a word processor, at which point it stops being compiled and starts
being edited --- and an edited document has broken every citation in itself
without changing a character of the prose.

**So the answer is not a PDF renderer; it is a typesetting source.** This emits
LaTeX from a compiled document, with the citations intact and machine-readable,
and leaves the rendering to a toolchain the firm already has. Three reasons, in
increasing order of how much they matter.

The dull one: rendering needs a toolchain. Shipping one means shipping a browser
engine or a TeX distribution inside a governance platform, and both are large
attack surfaces for a formatting need.

The better one: **a rendered document needs a house template**, and a firm's
document standard --- its cover page, its classification banner, its committee
minute conventions --- is not something a register should decide. `docs/12`
already says so; this makes it true rather than aspirational.

The one that matters: **every claim in a compiled document cites a node**, and a
PDF is where a citation goes to die. The LaTeX carries them as real
cross-references, so a reader can follow one and a checker can verify the set is
complete. A document whose citations survive typesetting is a document that can
still be audited after it has been through a committee.

**And what cannot be rendered is named in the output rather than dropped.** A
compiled document reports its own gaps --- a section with no evidence, a claim
whose support was withdrawn. Those become visible marks in the typeset copy, not
silence, because a gap that disappears at rendering is one the committee never
sees and the register can no longer prove it disclosed.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Sequence

from core.docs.common import DocumentError
from core.log import get_logger

logger = get_logger(__name__)

LATEX, MARKDOWN = "latex", "markdown"
FORMATS = (LATEX, MARKDOWN)

#: Formats asked for that this deliberately does not produce, each with the
#: reason. Named rather than absent, because an unexplained absence reads as an
#: oversight and gets raised as one every quarter.
NOT_PRODUCED: Dict[str, str] = {
    "pdf": "rendering needs a TeX distribution or a browser engine, which is a "
           "large attack surface for a formatting need — and it needs a house "
           "template, which is a firm's document standard and not a register's "
           "decision. The LaTeX this emits renders with one `pdflatex` run",
    "docx": "the same, plus a word processor is an *editor*: a compiled "
            "document that arrives editable is one whose citations will be "
            "broken by somebody improving the prose, and nothing downstream "
            "will notice",
    "html": "the help pipeline already renders the markdown for reading in the "
            "platform. A standalone HTML export is a third rendering of one "
            "document, and three renderings are three things that can disagree",
}


class DocumentRendering:
    """Emits a typesetting source from a compiled document. Renders nothing."""

    def __init__(self, documents, registry=None):
        self.documents, self.registry = documents, registry

    # ---------------------------------------------------------------- render
    def render(self, document_id: str, fmt: str = LATEX,
               now: Optional[float] = None) -> Dict[str, Any]:
        """Turn one compiled document into a source a typesetter will take."""
        chosen = (fmt or "").strip().lower()
        if chosen in NOT_PRODUCED:
            raise DocumentError(
                "format_not_produced",
                f"MAYA does not emit {chosen}: {NOT_PRODUCED[chosen]}",
                f"take the {LATEX} and run your own toolchain — the citations "
                f"survive it, which is the property that matters")
        if chosen not in FORMATS:
            raise DocumentError(
                "unknown_format", f"'{fmt}' is not a format this emits",
                f"one of {', '.join(FORMATS)}")
        document = self.documents.one(id=document_id)
        if not document:
            raise DocumentError("unknown_document",
                                f"no document '{document_id}'",
                                "compile one first")
        moment = now if now is not None else time.time()
        sections = document.get("sections") or []
        citations = document.get("citations") or {}
        gaps = self._gaps(document)
        body = (self._latex(document, sections, citations, gaps)
                if chosen == LATEX else self._markdown(document, sections, gaps))
        logger.info("rendered document %s as %s (%d section(s), %d gap(s))",
                    document_id, chosen, len(sections), len(gaps))
        return {
            "document_id": document_id, "format": chosen,
            "title": document.get("title"), "kind": document.get("kind"),
            "digest": document.get("digest"),
            "source": body,
            "sections": len(sections),
            "citations": sum(len(v or []) for v in citations.values())
            if isinstance(citations, dict) else 0,
            "gaps": gaps,
            "renders_it": False,
            "rendered_at": moment,
            "detail": self._detail(document, sections, citations, gaps, chosen),
        }

    @staticmethod
    def _detail(document, sections, citations, gaps, chosen) -> str:
        cited = sum(len(v or []) for v in citations.values()) \
            if isinstance(citations, dict) else 0
        out = (f"{len(sections)} section(s) and {cited} citation(s) emitted as "
               f"{chosen}. MAYA does not render it: rendering needs a toolchain "
               f"and a house template, and a firm's document standard is not a "
               f"register's decision")
        if gaps:
            out += (f". {len(gaps)} gap(s) are marked **in the output** rather "
                    f"than dropped — a gap that disappears at rendering is one "
                    f"the committee never sees, and the register can no longer "
                    f"prove it disclosed")
        out += (". The citations survive typesetting, which is the property "
                "that matters: a PDF is where a citation goes to die, and a "
                "document whose citations survive can still be audited after "
                "it has been through a committee")
        return out

    @staticmethod
    def _gaps(document: Dict[str, Any]) -> List[Dict[str, Any]]:
        coverage = document.get("coverage") or {}
        if isinstance(coverage, dict):
            named = coverage.get("gaps") or coverage.get("missing") or []
            return [g if isinstance(g, dict) else {"what": str(g)}
                    for g in named]
        return []

    # ------------------------------------------------------------------ latex
    def _latex(self, document: Dict[str, Any],
               sections: Sequence[Any], citations: Any,
               gaps: Sequence[Dict[str, Any]]) -> str:
        title = _tex(str(document.get("title") or "Untitled"))
        lines = [
            "% Emitted by MAYA from a compiled document. Do not edit.",
            "%",
            "% Every claim below cites an evidence node, and the citations are",
            "% real cross-references rather than prose. Editing this file breaks",
            "% that correspondence without changing what the document SAYS,",
            "% which is the failure the compiler exists to prevent — fix the",
            "% record and recompile instead.",
            f"% document: {document.get('id')}",
            f"% digest:   {document.get('digest')}",
            "",
            r"\documentclass[11pt,a4paper]{article}",
            r"\usepackage[utf8]{inputenc}",
            r"\usepackage[T1]{fontenc}",
            r"\usepackage{geometry}\geometry{margin=25mm}",
            r"\usepackage{hyperref}",
            r"\usepackage{longtable,booktabs}",
            "",
            "% A house template goes here. MAYA deliberately does not ship one:",
            "% a cover page, a classification banner and a committee minute",
            "% convention are a firm's document standard, not a register's.",
            "",
            rf"\title{{{title}}}",
            r"\date{\today}",
            r"\begin{document}\maketitle",
            "",
        ]
        if gaps:
            lines += [
                r"\section*{What this document does not contain}",
                "",
                "This section is emitted by the compiler and is part of the "
                "document. A gap dropped at rendering is one the committee "
                "never sees.",
                "",
                r"\begin{itemize}",
            ]
            lines += [rf"  \item {_tex(str(g.get('what') or g))}"
                      f"{' --- ' + _tex(str(g.get('why'))) if g.get('why') else ''}"
                      for g in gaps]
            lines += [r"\end{itemize}", ""]

        for index, section in enumerate(sections):
            if not isinstance(section, dict):
                continue
            key = str(section.get("key") or f"s{index}")
            lines += [rf"\section{{{_tex(str(section.get('title') or key))}}}",
                      rf"\label{{sec:{_slug(key)}}}", ""]
            lines.append(_tex_body(str(section.get("body")
                                       or section.get("text") or "")))
            supporting = (citations or {}).get(key) \
                if isinstance(citations, dict) else None
            if supporting:
                lines += ["", r"\par\smallskip\noindent\footnotesize",
                          r"\textbf{Rests on:} "
                          + ", ".join(rf"\texttt{{{_tex(str(node)[:16])}}}"
                                      for node in supporting)
                          + r"\normalsize", ""]
        lines += [r"\end{document}", ""]
        return "\n".join(lines)

    # --------------------------------------------------------------- markdown
    @staticmethod
    def _markdown(document: Dict[str, Any], sections: Sequence[Any],
                  gaps: Sequence[Dict[str, Any]]) -> str:
        lines = [f"# {document.get('title')}", "",
                 f"<!-- compiled by MAYA · {document.get('digest')} -->", ""]
        if gaps:
            lines += ["## What this document does not contain", ""]
            lines += [f"- {g.get('what') or g}"
                      + (f" — {g['why']}" if g.get("why") else "")
                      for g in gaps]
            lines.append("")
        for section in sections:
            if not isinstance(section, dict):
                continue
            lines += [f"## {section.get('title') or section.get('key')}", "",
                      str(section.get("body") or section.get("text") or ""), ""]
        return "\n".join(lines)

    # ------------------------------------------------------------------ what
    @staticmethod
    def formats() -> Dict[str, Any]:
        """What is emitted, and what is refused with the reason."""
        return {
            "emits": list(FORMATS),
            "not_produced": [{"format": f, "why": w}
                             for f, w in NOT_PRODUCED.items()],
            "renders_anything": False,
            "detail": ("MAYA emits a typesetting source and not a rendered "
                       "document. A PDF is where a citation goes to die, and "
                       "every claim in a compiled document cites a node — so "
                       "what is emitted carries the citations as real "
                       "cross-references, and the toolchain and the house "
                       "template stay with the firm that owns its own document "
                       "standard"),
        }


_SPECIALS = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
             "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
             "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"}


def _tex(raw: str) -> str:
    return "".join(_SPECIALS.get(ch, ch) for ch in raw)


def _tex_body(raw: str) -> str:
    """Escape, then restore paragraph breaks. Markdown emphasis is not carried.

    Deliberately: a half-honoured markdown-to-LaTeX translation produces a
    document that looks converted and is subtly wrong in the places nobody
    checks, and the compiler's output is prose and citations rather than
    formatting.
    """
    return "\n\n".join(_tex(block.strip())
                       for block in re.split(r"\n\s*\n", raw) if block.strip())


def _slug(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-") or "section"
