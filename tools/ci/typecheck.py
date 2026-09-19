"""Gate 2 — ``mypy --strict`` on maya/services (plan §7), configured in pyproject.toml.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import subprocess
import sys

from _common import ROOT, report

TARGETS = ["maya/services"]


def main() -> int:
    r = subprocess.run(
        [sys.executable, "-m", "mypy", *TARGETS], cwd=ROOT, capture_output=True, text=True
    )
    problems = [line for line in r.stdout.splitlines() if ": error:" in line]
    if r.returncode and not problems:
        problems = [(r.stderr or r.stdout).strip()[-500:]]
    return report("types (mypy --strict, maya/services)", problems)


if __name__ == "__main__":
    sys.exit(main())
