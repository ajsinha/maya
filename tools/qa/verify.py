#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Assemble the QA case list, and check that the number means something.

Three thousand cases is a pile until somebody can answer *what is not in it*.
This assembles the generated backbone and the hand-written sections into one
document and then verifies the two claims the list makes:

  * **every operation** in `openapi.lock.json` is named by at least one case;
  * **every refusal code** mapped in `routes/base.py` is provoked by one.

Both are derived from the same artefacts the generator read, so the check is
not "did the generator run" — it is "does the assembled document, including
everything written by hand and everything edited since, still cover the system
as it is *now*". A case list that stops covering the system the moment somebody
adds a route is the failure this guards.

It also refuses **duplicate IDs**, because four authors wrote in parallel and an
ID that means two things is an ID nobody can report a result against.

    python -m tools.qa.verify              # assemble and check
    python -m tools.qa.verify --check      # check only, write nothing
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASES = ROOT / "docs" / "QA" / "cases"
ASSEMBLED = ROOT / "docs" / "QA" / "QA-CASES.md"


def _generated() -> str:
    from tools.qa.enumerate import build, render
    return render(build())


def _sections() -> list:
    return sorted(CASES.glob("*.md")) if CASES.is_dir() else []


def _rows(text: str) -> list:
    return re.findall(r"^\|\s*(QA-[A-Z0-9-]+)\s*\|(.*)$", text, re.M)


def assemble() -> str:
    parts = [_generated()]
    for path in _sections():
        parts.append(f"\n\n<!-- {path.name} -->\n"
                     + path.read_text(encoding="utf-8").rstrip() + "\n")
    return "".join(parts)


def check(document: str) -> list:
    """Every complaint, or an empty list."""
    problems = []
    rows = _rows(document)

    seen = collections.Counter(case_id for case_id, _rest in rows)
    duplicates = sorted(i for i, n in seen.items() if n > 1)
    if duplicates:
        problems.append(
            f"{len(duplicates)} duplicate case id(s) — an id that means two "
            f"things is one nobody can report a result against: "
            f"{duplicates[:8]}")

    body = document
    lock = json.loads((ROOT / "openapi.lock.json").read_text(encoding="utf-8"))
    uncovered = []
    for path, item in lock["paths"].items():
        for method in item:
            if method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            if f"{method.upper()} {path}" not in body and \
                    f"`{method.upper()} {path}`" not in body:
                uncovered.append(f"{method.upper()} {path}")
    if uncovered:
        problems.append(
            f"{len(uncovered)} operation(s) named by no case: "
            f"{uncovered[:8]}")

    mapped = set(re.findall(
        r'"([a-z][a-z0-9_]+)"\s*:\s*\d{3}',
        (ROOT / "routes" / "base.py").read_text(encoding="utf-8")))
    missing = sorted(c for c in mapped if f"`{c}`" not in body)
    if missing:
        problems.append(
            f"{len(missing)} refusal code(s) provoked by no case — a refusal "
            f"the platform maps and no case reaches is a control nobody has "
            f"tried: {missing[:8]}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tools.qa.verify")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    document = assemble()
    rows = _rows(document)
    problems = check(document)

    print(f"assembled {len(rows)} cases from the generator and "
          f"{len(_sections())} hand-written section(s)")
    for problem in problems:
        print(f"  ! {problem}")
    if not problems:
        print("  coverage: every operation and every refusal code is named "
              "by at least one case")
    if not args.check:
        ASSEMBLED.write_text(document, encoding="utf-8")
        print(f"wrote {ASSEMBLED.relative_to(ROOT)}")
    return 1 if problems else 0


if __name__ == "__main__":                       # pragma: no cover
    sys.exit(main())
