"""
The typesetting seam (§13.4.2, §13.4.3, §17.1) — Type A, *labelled*.

Preferred: Tectonic, a self-contained TeX engine, run in a temporary
directory with a timeout and ``--untrusted`` (no shell escape).

Fallback: MAYA's own structural renderer, written here in pure Python. It
produces a valid PDF that is faithful to the document's *structure* — title,
sections, paragraphs, lists, formulas shown as their LaTeX source — and is
watermarked ``DRAFT RENDER — NOT EVIDENCE`` on every page. Its metadata says
``draft_render: true`` and callers refuse it wherever a PDF is evidence: a
sealed model version, an execution manifest, an export bundle. The capability
degrades; the guarantee does not.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

WATERMARK = "DRAFT RENDER \u2014 NOT EVIDENCE"
PAGE_W, PAGE_H, MARGIN = 612, 792, 72
_BODY, _HEAD, _TITLE, _MONO = 10.5, 14, 18, 9.5


def detect() -> dict[str, str]:
    """Which backend renders PDFs on this host, and why."""
    exe = shutil.which("tectonic")
    if exe:
        return {"backend": "tectonic", "detail": f"Tectonic at {exe}"}
    return {"backend": "draft",
            "detail": "Tectonic not found on PATH: MAYA's structural draft renderer is used. "
                      "Draft PDFs are watermarked and refused wherever a PDF is evidence."}


def render_pdf(latex: str, *, timeout: int = 120, force_draft: bool = False) -> tuple[bytes, dict[str, Any]]:
    """Render LaTeX to PDF: ``(pdf_bytes, {"draft_render", "backend", "log"})``."""
    if not force_draft and detect()["backend"] == "tectonic":
        return _tectonic(latex, timeout)
    pdf = DraftRenderer().render(latex)
    return pdf, {"draft_render": True, "backend": "draft",
                 "log": "structural draft renderer (Tectonic unavailable)"}


FRAGMENT_PREAMBLE = ("\\documentclass[11pt]{article}\n\\usepackage{amsmath,amssymb}\n"
                     "\\begin{document}\n")


def as_document(latex: str) -> str:
    """A specification saved as a fragment (sections only) is wrapped in the standard
    preamble; the draft renderer always accepted fragments, and a true build must too."""
    if "\\documentclass" in latex:
        return latex
    return FRAGMENT_PREAMBLE + latex.rstrip() + "\n\\end{document}\n"


def _first_error(log: str) -> str:
    """The line a reviewer needs: Tectonic's first 'error:' or TeX's first '!' line."""
    for line in log.splitlines():
        s = line.strip()
        if s.startswith("error:") and "halted" not in s or s.startswith("!"):
            return s.removeprefix("error:").strip()[:300]
    return ""


def _tectonic(latex: str, timeout: int) -> tuple[bytes, dict[str, Any]]:
    latex = as_document(latex)
    exe = shutil.which("tectonic") or "tectonic"
    with tempfile.TemporaryDirectory(prefix="maya-tex-") as tmp:
        src = Path(tmp) / "doc.tex"
        src.write_text(latex, encoding="utf-8")
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [exe, "--untrusted", "--keep-logs", "--outdir", tmp, str(src)],
            cwd=tmp, capture_output=True, text=True, timeout=timeout, check=False,
        )
        log = (proc.stdout or "") + (proc.stderr or "")
        pdf_path = Path(tmp) / "doc.pdf"
        if proc.returncode != 0 or not pdf_path.exists():
            from maya.core.errors import ValidationFailed
            first = _first_error(log)
            raise ValidationFailed("LaTeX build failed" + (f": {first}" if first else ""),
                                   log=log[-4000:])
        return pdf_path.read_bytes(), {"draft_render": False, "backend": "tectonic", "log": log[-4000:]}


# ---------------------------------------------------------------- draft renderer

_DISPLAY = re.compile(r"\\\[(.*?)\\\]|\\begin\{(equation\*?|align\*?|aligned)\}(.*?)\\end\{\2\}", re.S)


def _clean_inline(text: str) -> str:
    text = re.sub(r"(?<!\\)%.*", "", text)
    text = re.sub(r"\\(textbf|textit|emph|texttt|mathrm|text)\{([^}]*)\}", r"\2", text)
    text = text.replace(r"\_", "_").replace(r"\%", "%").replace(r"\&", "&").replace("~", " ")
    text = re.sub(r"\\(maketitle|noindent|newpage|clearpage|centering)\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_blocks(latex: str) -> list[tuple[str, str]]:
    """``[(kind, text)]`` with kinds title, author, section, subsection, para, item, math."""
    blocks: list[tuple[str, str]] = []
    title = re.search(r"\\title\{([^}]*)\}", latex)
    author = re.search(r"\\author\{([^}]*)\}", latex)
    if title:
        blocks.append(("title", _clean_inline(title.group(1))))
    if author and author.group(1).strip():
        blocks.append(("author", _clean_inline(author.group(1))))
    body = latex.split(r"\begin{document}", 1)[-1].split(r"\end{document}", 1)[0]
    pos = 0
    for m in _DISPLAY.finditer(body):
        blocks += _text_blocks(body[pos:m.start()])
        blocks.append(("math", _clean_math(m.group(1) or m.group(3) or "")))
        pos = m.end()
    blocks += _text_blocks(body[pos:])
    return blocks


def _clean_math(tex: str) -> str:
    tex = re.sub(r"\\(mathit|mathrm|text)\{([^}]*)\}", r"\2", tex)
    tex = re.sub(r"\\(left|right)(?=[()|.\[\]])", "", tex)
    tex = tex.replace(r"\,", " ").replace("&=", "=").replace(r"\begin{aligned}", "").replace(r"\end{aligned}", "")
    return re.sub(r"\s+", " ", tex).strip()


def _text_blocks(chunk: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    chunk = re.sub(r"(?<!\\)%.*", "", chunk)
    chunk = re.sub(r"\\(begin|end)\{(itemize|enumerate|document|abstract)\}", "\n\n", chunk)
    parts = re.split(r"(\\(?:sub)?section\*?\{[^}]*\}|\\item\b)", chunk)
    for part in parts:
        head = re.match(r"\\(sub)?section\*?\{([^}]*)\}", part)
        if head:
            out.append(("subsection" if head.group(1) else "section", _clean_inline(head.group(2))))
        elif part.strip() == r"\item":
            out.append(("item", ""))
        else:
            for para in re.split(r"\n\s*\n", part):
                text = _clean_inline(para)
                if text:
                    if out and out[-1] == ("item", ""):
                        out[-1] = ("item", text)
                    else:
                        out.append(("para", text))
    return [b for b in out if b != ("item", "")]


def _wrap(text: str, size: float, width: float, mono: bool = False) -> list[str]:
    per_char = size * (0.6 if mono else 0.5)
    limit = max(10, int(width / per_char))
    lines, line = [], ""
    for word in text.split(" "):
        while len(word) > limit:
            if line:
                lines.append(line)
                line = ""
            lines.append(word[:limit])
            word = word[limit:]
        candidate = f"{line} {word}".strip()
        if len(candidate) > limit:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines or [""]


def _esc(text: str) -> str:
    raw = text.encode("cp1252", errors="replace").decode("latin-1")
    return raw.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class DraftRenderer:
    """Pure-Python structural PDF writer (PDF 1.4, uncompressed, standard fonts)."""

    def __init__(self) -> None:
        self.pages: list[list[str]] = []
        self.y = 0.0

    def _new_page(self) -> None:
        self.pages.append([])
        self.y = PAGE_H - MARGIN

    def _line(self, text: str, font: str, size: float, indent: float = 0, gap: float = 1.35) -> None:
        if self.y - size * gap < MARGIN:
            self._new_page()
        self.y -= size * gap
        self.pages[-1].append(f"BT /{font} {size} Tf {MARGIN + indent:.1f} {self.y:.1f} Td ({_esc(text)}) Tj ET")

    def _space(self, pts: float) -> None:
        self.y -= pts

    def render(self, latex: str) -> bytes:
        self._new_page()
        width = PAGE_W - 2 * MARGIN
        for kind, text in parse_blocks(latex):
            if kind == "title":
                for ln in _wrap(text, _TITLE, width):
                    self._line(ln, "F2", _TITLE)
                self._space(6)
            elif kind == "author":
                self._line(text, "F1", _BODY)
                self._space(8)
            elif kind in ("section", "subsection"):
                self._space(8)
                self._line(text, "F2", _HEAD if kind == "section" else 12)
                self._space(2)
            elif kind == "math":
                for ln in _wrap(text, _MONO, width - 36, mono=True):
                    self._line(ln, "F3", _MONO, indent=36)
                self._space(4)
            elif kind == "item":
                for i, ln in enumerate(_wrap(text, _BODY, width - 24)):
                    self._line(("- " if i == 0 else "  ") + ln, "F1", _BODY, indent=12)
            else:
                for ln in _wrap(text, _BODY, width):
                    self._line(ln, "F1", _BODY)
                self._space(4)
        return self._assemble()

    def _decorate(self, ops: list[str], number: int, total: int) -> str:
        mark = (f"q 0.82 g BT /F2 44 Tf 0.7071 0.7071 -0.7071 0.7071 110 170 Tm "
                f"({_esc(WATERMARK)}) Tj ET Q")
        foot = (f"BT /F1 8 Tf {MARGIN} 40 Td ({_esc(f'{WATERMARK} - MAYA structural renderer, not a LaTeX build - page {number} of {total}')}) Tj ET")
        return "\n".join([mark, *ops, foot])

    def _assemble(self) -> bytes:
        objs: list[bytes] = []
        fonts = {"F1": "Helvetica", "F2": "Helvetica-Bold", "F3": "Courier"}
        n_pages = len(self.pages)
        # 1 catalog, 2 pages, 3..5 fonts, then (page, content) pairs
        first = 6
        kids = " ".join(f"{first + 2 * i} 0 R" for i in range(n_pages))
        objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
        for name in ("F1", "F2", "F3"):
            objs.append(f"<< /Type /Font /Subtype /Type1 /BaseFont /{fonts[name]} "
                        f"/Encoding /WinAnsiEncoding >>".encode())
        res = "<< /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >>"
        for i, ops in enumerate(self.pages):
            content = self._decorate(ops, i + 1, n_pages).encode("latin-1")
            objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                        f"/Resources {res} /Contents {first + 2 * i + 1} 0 R >>".encode())
            objs.append(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n"
                        + content + b"\nendstream")
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for num, body in enumerate(objs, 1):
            offsets.append(len(out))
            out += f"{num} 0 obj\n".encode() + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R "
                f"/Info << /Producer (MAYA draft renderer) /Subject (draft_render) >> >>\n"
                f"startxref\n{xref}\n%%EOF\n").encode()
        return bytes(out)


_TJ = re.compile(rb"\(((?:\\.|[^\\)])*)\)\s*Tj")
_STREAM = re.compile(rb"stream\n(.*?)\nendstream", re.S)


def _unescape(raw: bytes) -> str:
    text = re.sub(rb"\\([\\()])", rb"\1", raw)
    return text.decode("cp1252", errors="replace")


def pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from an uncompressed PDF (enough for MAYA's own drafts).

    Pages are separated by form feeds so tests can assert per page.
    """
    pages = []
    for stream in _STREAM.findall(pdf_bytes):
        lines = [_unescape(m) for m in _TJ.findall(stream)]
        if lines:
            pages.append("\n".join(lines))
    return "\f".join(pages)
