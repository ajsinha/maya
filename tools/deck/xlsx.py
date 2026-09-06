"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A minimal spreadsheet writer, so data can be embedded in a deck and opened.

PowerPoint embeds a foreign file in one of two ways. As an OLE *Package*, which
requires the payload to be wrapped in an OLE compound document — a binary
container the standard library cannot write, and which, handed raw bytes, gives
an icon that opens nothing. Or as a known type: an embedded workbook is a plain
``.xlsx``, and PowerPoint opens it on a double-click without any wrapper at all.

So this writes the workbook. It is about eighty lines because a valid ``.xlsx``
is a zip of five small XML parts, and writing them here keeps the deck free of a
dependency — the same reason every other asset in this platform is vendored.

Inline strings rather than a shared-string table: a table would be smaller for
repetitive data and is one more part to get wrong, and these sheets are hundreds
of rows rather than millions.
"""
from __future__ import annotations

import zipfile
from typing import Any, List, Sequence

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""


def _workbook(sheet_name: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{_escape(sheet_name)[:31]}" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>")


def _escape(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _column(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    name = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _numeric(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return True
    try:
        float(str(value))
    except (TypeError, ValueError):
        return False
    return str(value).strip() != ""


def _sheet(rows: Sequence[Sequence[Any]]) -> str:
    out: List[str] = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>"]
    for r, row in enumerate(rows, start=1):
        out.append(f'<row r="{r}">')
        for c, value in enumerate(row):
            ref = f"{_column(c)}{r}"
            if value is None or str(value) == "":
                continue                      # an empty cell is simply absent
            if _numeric(value):
                out.append(f'<c r="{ref}"><v>{_escape(value)}</v></c>')
            else:
                out.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">'
                           f"{_escape(value)}</t></is></c>")
        out.append("</row>")
    out += ["</sheetData>", "</worksheet>"]
    return "".join(out)


def write(path: str, rows: Sequence[Sequence[Any]],
          sheet_name: str = "Sheet1") -> str:
    """Write a workbook holding these rows. Returns the path."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("xl/workbook.xml", _workbook(sheet_name))
        z.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        z.writestr("xl/worksheets/sheet1.xml", _sheet(rows))
    return path


def from_csv(csv_path: str, xlsx_path: str, sheet_name: str = "Sheet1") -> str:
    """A workbook from a CSV, comment lines included as their own rows.

    The provenance header is kept rather than stripped: a file that says which
    series it is, from where and retrieved when is the only kind worth putting
    in front of somebody.
    """
    import csv as _csv
    rows: List[List[Any]] = []
    with open(csv_path, newline="") as fh:
        for line in fh:
            if line.startswith("#"):
                rows.append([line.rstrip("\n")])
            else:
                rows.extend(_csv.reader([line]))
    return write(xlsx_path, [r for r in rows if r], sheet_name)
