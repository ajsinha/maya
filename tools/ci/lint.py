"""Gate 1 — ruff over the code, the tools and the tests (plan §7): the lint rules, and
the formatting, so a diff is only ever about what changed.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import subprocess
import sys

from _common import ROOT, report

PATHS = ["maya", "maya_delta", "tools", "tests", "run_maya_web.py"]


def main() -> int:
    r = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--output-format", "concise", *PATHS],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    problems = (
        [
            line
            for line in r.stdout.splitlines()
            if ":" in line and " " in line and not line.startswith("Found")
        ]
        if r.returncode
        else []
    )
    if r.returncode and not problems:
        problems = [(r.stderr or r.stdout).strip()[-500:]]
    f = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", "--output-format", "concise", *PATHS],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    problems += [
        line.split(":", 1)[0] + " is not formatted (run `ruff format`)"
        for line in f.stdout.splitlines()
        if "unformatted:" in line
    ]
    if f.returncode and not any("not formatted" in p for p in problems):
        problems.append((f.stderr or f.stdout).strip()[-500:])
    return report("lint (ruff)", problems)


if __name__ == "__main__":
    sys.exit(main())
