"""
The Markdown subset document templates use, as a LaTeX article, for the PDF.

Headings, paragraphs, bullet and numbered lists, pipe tables, quotes, rules, inline code,
bold and italic, and display maths (``$$ ... $$``), which passes through as maths -- so a
model's formula prints as a formula. Anything else is escaped and printed as text rather
than guessed at.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re

SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
HEADINGS = {1: "section*", 2: "section*", 3: "subsection*", 4: "subsubsection*"}


def escape(text: str) -> str:
    return "".join(SPECIALS.get(c, c) for c in text)


def inline(text: str) -> str:
    """Escape a run of prose, then turn Markdown's inline marks into LaTeX."""
    out = []
    for part in re.split(r"(`[^`]+`)", text):
        if len(part) > 1 and part.startswith("`") and part.endswith("`"):
            out.append(r"\texttt{" + escape(part[1:-1]) + "}")
            continue
        s = escape(part)
        s = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", s)
        s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\\emph{\1}", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", s)
        out.append(s)
    return "".join(out)


class _Writer:
    def __init__(self, lines: list[str]) -> None:
        self.lines, self.i = lines, 0
        self.out: list[str] = []
        self.open_list: str | None = None

    def close_list(self) -> None:
        if self.open_list:
            self.out.append(r"\end{%s}" % self.open_list)
            self.open_list = None

    def item(self, env: str, text: str) -> None:
        if self.open_list != env:
            self.close_list()
            self.out.append(r"\begin{%s}" % env)
            self.open_list = env
        self.out.append(r"\item " + inline(text))

    def maths(self) -> None:
        block = [self.lines[self.i].strip()[2:]]
        while not block[-1].rstrip().endswith("$$") and self.i + 1 < len(self.lines):
            self.i += 1
            block.append(self.lines[self.i])
        self.out.append(r"\[" + "\n".join(block).rstrip()[:-2].strip() + r"\]")

    def is_table(self) -> bool:
        nxt = self.lines[self.i + 1].strip() if self.i + 1 < len(self.lines) else ""
        return self.lines[self.i].strip().startswith("|") and bool(re.match(r"^\|?\s*:?-{2,}", nxt))

    def table(self) -> None:
        rows = []
        while self.i < len(self.lines) and self.lines[self.i].strip().startswith("|"):
            rows.append([c.strip() for c in self.lines[self.i].strip().strip("|").split("|")])
            self.i += 1
        self.i -= 1
        head, cols = rows[0], len(rows[0])
        width = f"{0.95 / cols:.3f}"
        self.out.append(r"\begin{longtable}{" + ("p{" + width + r"\linewidth}") * cols + "}")
        self.out.append(" & ".join(r"\textbf{" + inline(h) + "}" for h in head) + r" \\ \hline")
        for r in rows[2:]:
            self.out.append(" & ".join(inline(c) for c in (r + [""] * cols)[:cols]) + r" \\")
        self.out.append(r"\end{longtable}")

    def line(self) -> None:
        s = self.lines[self.i].strip()
        bullet = re.match(r"^[-*]\s+(.*)", s)
        number = re.match(r"^\d+\.\s+(.*)", s)
        if bullet:
            self.item("itemize", bullet.group(1))
            return
        if number:
            self.item("enumerate", number.group(1))
            return
        self.close_list()
        heading = re.match(r"^(#{1,4})\s+(.*)", s)
        if s.startswith("$$"):
            self.maths()
        elif heading:
            self.out.append(
                "\\%s{%s}" % (HEADINGS[len(heading.group(1))], inline(heading.group(2)))
            )
        elif self.is_table():
            self.table()
        elif s.startswith(">"):
            self.out.append(r"\begin{quote}" + inline(s.lstrip("> ").strip()) + r"\end{quote}")
        elif s in ("---", "***"):
            self.out.append(r"\noindent\rule{\linewidth}{0.4pt}")
        else:
            self.out.append(inline(s) if s else "")

    def run(self) -> list[str]:
        while self.i < len(self.lines):
            self.line()
            self.i += 1
        self.close_list()
        return self.out


def to_latex(markdown_text: str, title: str) -> str:
    text = re.sub(r"<!--.*?-->", "", markdown_text, flags=re.S)
    body = _Writer(text.splitlines()).run()
    return (
        "\\documentclass[11pt]{article}\n\\usepackage[margin=2.2cm]{geometry}\n"
        "\\usepackage{amsmath,longtable}\n"
        f"\\title{{{inline(title)}}}\n\\begin{{document}}\n"  # the template's own heading is the title
        + "\n".join(body)
        + "\n\\end{document}\n"
    )
