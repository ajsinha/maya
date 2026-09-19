"""
The model specification document (§8.5, §17.1).

A firm-standard LaTeX template with required sections, completeness checks
that block submission, and the ``\\mayaformula`` / ``\\mayaref`` macros that
pull live content from the formula IR and the catalog so the document cannot
drift from the implementation.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import re
from typing import Any, Callable

REQUIRED_SECTIONS = (
    "Purpose", "Scope and Limitations", "Mathematical Formulation", "Assumptions",
    "Data and Features Used", "Calibration Methodology", "Validation Evidence",
    "Known Weaknesses", "Change Log",
)

TEMPLATE = r"""\documentclass[11pt]{article}
\usepackage{amsmath,amssymb}
\title{%(title)s}
\author{%(author)s}
\begin{document}
\maketitle

\section{Purpose}
%(purpose)s

\section{Scope and Limitations}

\section{Mathematical Formulation}
\mayaformula{body}

\section{Assumptions}

\section{Data and Features Used}
%(inputs)s

\section{Calibration Methodology}

\section{Validation Evidence}

\section{Known Weaknesses}

\section{Change Log}

\end{document}
"""

_SECTION = re.compile(r"\\section\*?\{([^}]*)\}")
_COMMENT = re.compile(r"(?<!\\)%.*$", re.MULTILINE)
_FORMULA = re.compile(r"\\mayaformula\{([^}]*)\}")
_REF = re.compile(r"\\mayaref\{([^}]*)\}")


def default_document(model_name: str, ir: dict[str, Any], author: str = "") -> str:
    """A new spec document from the firm template, pre-filled from the IR."""
    inputs = [i for i in ir.get("inputs", []) if i.get("role", "feature") == "feature"]
    items = "\n".join(
        rf"  \item \texttt{{{i['name'].replace('_', chr(92) + '_')}}} ({i.get('type', 'float64')})"
        + (f" — {i['desc']}" if i.get("desc") else "")
        for i in inputs
    )
    listing = "\\begin{itemize}\n" + items + "\n\\end{itemize}" if items else ""
    return TEMPLATE % {
        "title": model_name.replace("_", r"\_"), "author": author,
        "purpose": "", "inputs": listing,
    }


def _sections(latex: str) -> list[tuple[str, str]]:
    text = _COMMENT.sub("", latex)
    text = text.split(r"\end{document}")[0]
    marks = list(_SECTION.finditer(text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m.group(1).strip(), text[m.end():end]))
    return out


def outline(latex: str) -> list[dict[str, Any]]:
    """Every section with its line number, for the editor's outline pane."""
    lines = latex.splitlines()
    out = []
    for no, line in enumerate(lines, 1):
        m = _SECTION.search(line)
        if m:
            out.append({"section": m.group(1).strip(), "line": no,
                        "required": m.group(1).strip() in REQUIRED_SECTIONS})
    return out


def section_completeness(latex: str) -> list[dict[str, Any]]:
    """Each required section: present? empty? — the check that blocks submission."""
    found = {name: body for name, body in _sections(latex)}
    result = []
    for name in REQUIRED_SECTIONS:
        body = found.get(name)
        empty = body is None or not re.sub(r"\s+", "", body)
        result.append({"section": name, "present": body is not None, "empty": empty})
    return result


def is_complete(latex: str) -> bool:
    """True when every required section is present and non-empty."""
    return all(s["present"] and not s["empty"] for s in section_completeness(latex))


def expand_macros(latex: str, ir: dict[str, Any],
                  resolver: Callable[[str], str] | None = None) -> str:
    r"""Replace ``\mayaformula{body|let:NAME|full}`` and ``\mayaref{maya://...}``."""
    from maya.formula.latex import body_latex, let_latex, to_latex

    def formula(m: re.Match[str]) -> str:
        key = m.group(1).strip()
        if key in ("", "body"):
            tex = body_latex(ir)
        elif key == "full":
            tex = to_latex(ir)
        elif key.startswith("let:"):
            name = key[4:]
            if name not in (ir.get("lets") or {}):
                return rf"\textbf{{[unknown let '{name}']}}"
            tex = let_latex(ir, name)
        else:
            return rf"\textbf{{[unknown formula binding '{key}']}}"
        return "\\[" + tex + "\\]"

    def ref(m: re.Match[str]) -> str:
        uri = m.group(1).strip()
        if resolver is None:
            return rf"\texttt{{{uri}}}"
        return resolver(uri)

    return _REF.sub(ref, _FORMULA.sub(formula, latex))


def bound_formulas(latex: str) -> list[str]:
    r"""Every ``\mayaformula`` binding in the document (re-review trigger on IR change)."""
    return [m.group(1).strip() for m in _FORMULA.finditer(latex)]
