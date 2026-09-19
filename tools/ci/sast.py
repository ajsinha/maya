"""Gate 25a — static security analysis (bandit) over the product code (spec §22).

Every medium or high finding fails the gate unless it has been reviewed and marked
in place with ``# nosec <test id> - <why>``; low findings (asserts, subprocess use
and the like) are reported by ``bandit`` itself on demand, not gated.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json
import subprocess
import sys

from _common import ROOT, report

TARGETS = ["maya", "maya_delta", "run_maya_web.py"]


def main() -> int:
    r = subprocess.run(
        [sys.executable, "-m", "bandit", "-q", "-r", *TARGETS, "-ll", "-f", "json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    try:
        results = json.loads(r.stdout)["results"]
    except (ValueError, KeyError):
        return report(
            "static security analysis (bandit)",
            [(r.stderr or r.stdout).strip()[-500:] or "bandit did not run"],
        )
    return report(
        "static security analysis (bandit)",
        [
            f"{x['filename']}:{x['line_number']} {x['test_id']} ({x['issue_severity']}) "
            f"{x['issue_text']}"
            for x in results
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
