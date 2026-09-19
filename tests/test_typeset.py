"""The typesetting seam: the draft renderer is labelled, watermarked on every page, and says so."""
from __future__ import annotations

from maya.core.typeset import WATERMARK, detect, parse_blocks, pdf_text, render_pdf
from maya.formula.parse import parse_model
from maya.formula.specdoc import default_document, expand_macros


def _long_doc() -> str:
    ir = parse_model("price = S*a", roles={"a": "parameter"})
    doc = expand_macros(default_document("toy_model", ir), ir)
    filler = " ".join(["The limitation paragraph repeats to force pagination."] * 40)
    return doc.replace(r"\section{Scope and Limitations}", r"\section{Scope and Limitations}" + "\n"
                       + "\n\n".join([filler] * 6))


def test_draft_render_is_labelled_and_watermarked_on_every_page() -> None:
    pdf, meta = render_pdf(_long_doc(), force_draft=True)
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    assert meta["draft_render"] is True and meta["backend"] == "draft"
    pages = pdf_text(pdf).split("\f")
    assert len(pages) >= 2
    for page in pages:
        assert WATERMARK in page
    text = pdf_text(pdf)
    assert "Scope and Limitations" in text and "Change Log" in text and "toy_model" in text
    assert "price = S" in text  # the formula, rendered as its LaTeX source


def test_detect_reports_backend() -> None:
    info = detect()
    assert info["backend"] in ("tectonic", "draft") and info["detail"]


def test_parse_blocks_structure() -> None:
    blocks = parse_blocks(r"\title{T}\begin{document}\section{A} hello \[x^2\] \begin{itemize}\item one\end{itemize}\end{document}")
    kinds = [k for k, _ in blocks]
    assert kinds == ["title", "section", "para", "math", "item"]
