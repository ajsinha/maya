"""Gate 3 — no non-UI source file over 1,500 non-comment lines (§22.1, SC-6).

1,500 fails; 1,200 needs a note; 800 warns. Templates, CSS and JS are UI and exempt.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys

from _common import code_lines, python_files, report, ROOT

HARD, NOTE, WARN = 1500, 1200, 800


def main() -> int:
    failures = []
    for path in python_files():
        n = code_lines(path)
        rel = path.relative_to(ROOT)
        if n > HARD:
            failures.append(f"{rel}: {n} code lines (limit {HARD})")
        elif n > NOTE:
            print(f"note {rel}: {n} code lines — explain in the pull request why it is not split")
        elif n > WARN:
            print(f"warn {rel}: {n} code lines")
    return report("file size ≤ 1,500 code lines", failures)


if __name__ == "__main__":
    sys.exit(main())
