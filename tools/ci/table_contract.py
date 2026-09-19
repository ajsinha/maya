"""Gate 10 — every <table> comes from the one table macro (§16.7, SC-17).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import re
import sys

from _common import ROOT, report

TEMPLATES = ROOT / "maya" / "web" / "templates"
MACRO = TEMPLATES / "_macros" / "table.html"


def main() -> int:
    failures = []
    for path in sorted(TEMPLATES.rglob("*.html")) if TEMPLATES.exists() else []:
        if path == MACRO:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"<table\b", line, re.IGNORECASE):
                failures.append(f"{path.relative_to(ROOT)}:{i} raw <table>; use _macros/table.html")
    return report("table contract", failures)


if __name__ == "__main__":
    sys.exit(main())
