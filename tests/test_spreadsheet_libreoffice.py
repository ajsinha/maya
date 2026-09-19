"""
The spreadsheet lift judged by a real spreadsheet engine (§29.9).

tests/test_spreadsheet.py writes the workbooks' cached results itself. Here the
same workbooks are recalculated by LibreOffice Calc, headless, and every lift must
agree, cell by cell, with the results LibreOffice cached: the arithmetic and
precedence rules, the functions, IF/AND/OR/NOT, the normal distribution, the
lookups (exact, approximate, a miss) and a multi-sheet loan model with names.

Skipped where LibreOffice is not installed.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

openpyxl = pytest.importorskip("openpyxl")

from maya.formula.xlsx import lift_workbook  # noqa: E402
from tests.test_spreadsheet import FEES, LOAN, LOAN_NAMES, SEMANTICS, X, book  # noqa: E402

SOFFICE = shutil.which("soffice") or shutil.which("libreoffice")
pytestmark = pytest.mark.skipif(SOFFICE is None, reason="LibreOffice is not installed")

LOOKUP_TABLE = {"A1": 1, "B1": 100, "A2": 2, "B2": 200, "C1": 5, "D1": 7, "C2": 6, "D2": 8}
LOOKUPS = ["=VLOOKUP(2, A1:B2, 2, FALSE)", "=HLOOKUP(5, C1:D2, 2, 0)",
           "=VLOOKUP(3, A1:B2, 2, FALSE)", "=VLOOKUP(1.5, A1:B2, 2)", "=VLOOKUP(9, A1:B2, 2)"]


def _column(n: int) -> str:
    return f"Z{n + 1}"


def _as_excel_writes(formula: str) -> str:
    """Functions newer than Excel 2007 are stored with the _xlfn. prefix; a file without it
    is not what Excel writes, and LibreOffice (rightly) answers #NAME?."""
    import re
    return re.sub(r"(?<![\w.])(NORM\.S\.DIST|NORM\.DIST)\(", r"_xlfn.\1(", formula)


@pytest.fixture(scope="module")
def recalculated(tmp_path_factory):
    """Each workbook, as LibreOffice saves it after calculating every formula."""
    src, out = tmp_path_factory.mktemp("in"), tmp_path_factory.mktemp("out")
    profile = tmp_path_factory.mktemp("lo-profile")
    books = {
        "semantics": book({**X, **{_column(i): _as_excel_writes(f)
                                   for i, (f, _) in enumerate(SEMANTICS)}}),
        "lookups": book({**LOOKUP_TABLE, **{_column(i): f for i, f in enumerate(LOOKUPS)}}),
        "loan": book(LOAN, {"Fees": FEES}, LOAN_NAMES),
    }
    for name, data in books.items():
        (src / f"{name}.xlsx").write_bytes(data)
    subprocess.run([SOFFICE, f"-env:UserInstallation={profile.as_uri()}", "--headless",
                    "--calc", "--convert-to", "xlsx", "--outdir", str(out),
                    *[str(src / f"{n}.xlsx") for n in books]],
                   check=True, capture_output=True, timeout=300)
    return {n: (out / f"{n}.xlsx").read_bytes() for n in books}


def _agrees(data: bytes, output: str) -> dict:
    check = lift_workbook(data, output=output)["lifted_from"]["workbook"]["check"]
    assert check["status"] == "agreed", check
    return check


@pytest.mark.parametrize("index", range(len(SEMANTICS)),
                         ids=[f for f, _ in SEMANTICS])
def test_each_construct_agrees_with_libreoffice(recalculated, index):
    _agrees(recalculated["semantics"], _column(index))


@pytest.mark.parametrize("index", range(len(LOOKUPS)), ids=LOOKUPS)
def test_lookups_agree_with_libreoffice_including_a_miss(recalculated, index):
    _agrees(recalculated["lookups"], _column(index))


def test_the_loan_model_agrees_with_libreoffice_cell_by_cell(recalculated):
    check = _agrees(recalculated["loan"], "B7")
    assert check["checked"] == check["formula_cells"] == 4
