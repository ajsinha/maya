"""Gate 10 — every <table> comes from the one table macro (§16.7, SC-17).

Server-paged tables are held to the same contract: every table a web route pages
from the server (``first_page(..., "<name>")``) is registered in
``maya.web.routes.tables.TABLES``, and every registered table's row macro exists in
``templates/_rows.html`` — so page one and every later page render the same row.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import re
import sys

from _common import ROOT, report

TEMPLATES = ROOT / "maya" / "web" / "templates"
MACRO = TEMPLATES / "_macros" / "table.html"
ROWS = TEMPLATES / "_rows.html"
ROUTES = ROOT / "maya" / "web" / "routes"


def server_mode_failures() -> list[str]:
    from maya.web.routes.tables import TABLES
    failures = []
    macros = set(re.findall(r"{%-?\s*macro\s+(\w+)\(", ROWS.read_text(encoding="utf-8"))) \
        if ROWS.exists() else set()
    for name, table in TABLES.items():
        if table.row not in macros:
            failures.append(f"server table '{name}' renders rows with '{table.row}', which "
                            "templates/_rows.html does not define")
    for path in sorted(ROUTES.glob("*.py")):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for name in re.findall(r"first_page\([^)]*?\"(\w+)\"", line):
                if name not in TABLES:
                    failures.append(f"{path.relative_to(ROOT)}:{i} pages table '{name}', which "
                                    "maya/web/routes/tables.py does not register")
    return failures


def main() -> int:
    failures = []
    for path in sorted(TEMPLATES.rglob("*.html")) if TEMPLATES.exists() else []:
        if path == MACRO:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"<table\b", line, re.IGNORECASE):
                failures.append(f"{path.relative_to(ROOT)}:{i} raw <table>; use _macros/table.html")
    failures += server_mode_failures()
    return report("table contract", failures)


if __name__ == "__main__":
    sys.exit(main())
