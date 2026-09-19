"""
A true Tectonic build, proved by what the PDF *says* (plan M6 exit criterion): a model
version's specification is rendered through the model service, and the PDF's text is
extracted with ``pdftotext`` — an extractor MAYA does not own — and asserted: the title,
every required section in order, the prose written into them, the input list pre-filled
from the IR, and the formula expanded from ``\\mayaformula{body}`` into mathematics,
with no draft watermark. Skipped where Tectonic or ``pdftotext`` is absent.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from maya.core.typeset import WATERMARK, detect
from maya.formula.specdoc import REQUIRED_SECTIONS, default_document

pytestmark = [
    pytest.mark.skipif(detect()["backend"] != "tectonic", reason="Tectonic is not installed"),
    pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext is not installed"),
]


def _text(pdf: bytes) -> str:
    out = subprocess.run(["pdftotext", "-layout", "-", "-"], input=pdf, capture_output=True,
                         check=True, timeout=60)
    return out.stdout.decode("utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def test_a_model_versions_pdf_says_what_its_specification_says(world):
    w = world
    w.p.access.create_namespace(w.admin, name="tex")
    w.p.models.create(w.mona, namespace="tex", name="basis_spread",
                      formula="spread = alpha * carry + beta * momentum",
                      roles={"alpha": "parameter", "beta": "parameter"})
    ir = w.p.models.get(w.mona, "tex/basis_spread")["versions"][0]["formula_ir"]
    doc = default_document("basis_spread", ir, author="Mona Designer")
    doc = doc.replace(r"\section{Purpose}" + "\n",
                      r"\section{Purpose}" + "\nEstimates the quarterly basis spread "
                      "from carry and momentum.\n")
    doc = doc.replace(r"\section{Known Weaknesses}" + "\n",
                      r"\section{Known Weaknesses}" + "\nUnstable when carry changes sign "
                      "inside a quarter.\n")
    w.p.models.update_draft(w.mona, "tex/basis_spread", spec_latex=doc)

    out = w.p.models.render_spec(w.mona, "tex/basis_spread", 1)
    assert out["draft_render"] is False and out["backend"] == "tectonic"
    pdf = w.p.models.spec_pdf(w.mona, "tex/basis_spread", 1)
    assert pdf.startswith(b"%PDF-")
    text = _text(pdf)
    flat = _flat(text)

    assert WATERMARK not in text and "DRAFT RENDER" not in text
    assert "basis_spread" in flat and "Mona Designer" in flat
    positions = [flat.find(s) for s in REQUIRED_SECTIONS]
    assert all(p >= 0 for p in positions), dict(zip(REQUIRED_SECTIONS, positions))
    assert positions == sorted(positions), "sections out of order"
    assert "Estimates the quarterly basis spread from carry and momentum." in flat
    assert "Unstable when carry changes sign inside a quarter." in flat
    # the input list is pre-filled from the IR's feature inputs
    formulation = flat[positions[2]:positions[3]]
    data_section = flat[positions[4]:positions[5]]
    assert "carry" in data_section and "momentum" in data_section
    # \mayaformula{body} became typeset mathematics, not its LaTeX source
    assert "mayaformula" not in flat and "\\" not in formulation
    assert "spread = α carry + β momentum" in formulation, formulation
