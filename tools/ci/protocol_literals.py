"""Gate 21 — no literal Delta protocol version numbers in test assertions (plan §7).

A test that asserts ``min_reader_version == 3`` breaks the day the protocol moves,
for no reason about MAYA. Tests compare against the constants maya_delta declares.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re
import sys

from _common import ROOT, report

PATTERN = re.compile(
    r"(min_?reader_?version|min_?writer_?version|minReaderVersion|"
    r"minWriterVersion|reader_features|writer_features|protocol_version)"
    r"\W{0,6}\s*(==|!=|<=|>=|<|>|in)\s*[\[(]?\s*\d",
    re.I,
)


def main() -> int:
    problems = []
    for base in ("tests", "maya_delta"):
        for path in sorted((ROOT / base).rglob("test*.py")):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "assert" in line and PATTERN.search(line):
                    problems.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
    return report("no literal Delta protocol versions in tests", problems)


if __name__ == "__main__":
    sys.exit(main())
