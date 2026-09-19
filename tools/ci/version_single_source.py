"""Gate 8 — the version string lives in maya/core/version.py and nowhere else.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re
import sys

from _common import ROOT, python_files, report


def main() -> int:
    from maya.core.version import VERSION

    pattern = re.compile(r"""["']""" + re.escape(VERSION) + r"""["']""")
    authority = ROOT / "maya" / "core" / "version.py"
    allowed = {authority, ROOT / "maya" / "sdk" / "transport.py"}  # SDK versions independently
    failures = [
        f"{p.relative_to(ROOT)} hard-codes the version string"
        for p in python_files()
        if p not in allowed and pattern.search(p.read_text())
    ]
    return report("version single source", failures)


if __name__ == "__main__":
    sys.exit(main())
