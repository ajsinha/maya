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


needs_tectonic = __import__("pytest").mark.skipif(detect()["backend"] != "tectonic",
                                                  reason="Tectonic is not installed here")


@needs_tectonic
def test_a_true_build_is_a_real_pdf_without_the_draft_watermark() -> None:
    pdf, meta = render_pdf(_long_doc())
    assert meta == {**meta, "draft_render": False, "backend": "tectonic"}
    assert pdf.startswith(b"%PDF-") and WATERMARK.encode() not in pdf
    assert len(pdf) > 5000


@needs_tectonic
def test_broken_latex_fails_with_the_tex_log() -> None:
    import pytest

    from maya.core.errors import ValidationFailed
    with pytest.raises(ValidationFailed, match="LaTeX build failed") as info:
        render_pdf("\\documentclass{article}\\begin{document}\\undefinedmacro\\end{document}")
    assert "undefinedmacro" in info.value.context["log"] or "Undefined" in \
        info.value.context["log"]


@needs_tectonic
def test_approval_accepts_a_true_build_when_one_is_required() -> None:
    from tests.conftest import World, build_platform
    platform = build_platform(["--typeset.require_true_build=true"])
    try:
        w = World(platform)
        platform.access.create_namespace(w.admin, name="tx")
        platform.models.create(w.mona, namespace="tx", name="lin", formula="y = a*x",
                               roles={"a": "parameter"})
        out = platform.models.render_spec(w.mona, "tx/lin", 1)
        assert out["draft_render"] is False and out["backend"] == "tectonic"
        version = platform.models.get(w.mona, "tx/lin")["versions"][0]
        ok, why = platform.models.check_true_build(None, {"row": version})
        assert ok and why == "PDF is a true LaTeX build"
    finally:
        platform.shutdown()


@needs_tectonic
def test_a_fragment_is_wrapped_in_the_standard_preamble() -> None:
    from maya.core.typeset import as_document
    pdf, meta = render_pdf("\\section{Purpose}\nThe model prices $x^2$.")
    assert meta["draft_render"] is False and pdf.startswith(b"%PDF-")
    whole = "\\documentclass{article}\\begin{document}x\\end{document}"
    assert as_document(whole) == whole
