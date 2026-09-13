"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Every QA failure, recorded rather than repaired.

    python -m tools.qa.findings            # the register
    python -m tools.qa.findings --plan     # grouped into fixable batches

The pass now runs to the end before anything is fixed. Fixing as you go has
one real cost and it is not effort: a defect repaired the moment it is found
never joins the group it belongs to, so eleven instances of one mistake get
eleven separate repairs and nobody ever writes down the mistake. Four blank
stated grounds were found in four subsystems on four different days of this
pass before the pattern was named.

So failures accumulate here, and the plan groups them by **what is actually
wrong**, not by which endpoint noticed.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
from typing import Dict, List

ROOT = pathlib.Path(__file__).resolve().parents[2]
RESULTS = ROOT / "docs" / "QA" / "results"

#: How a failure is grouped. First match wins, so the specific patterns come
#: before the general ones.
#: How a failure is grouped, matched against the EVIDENCE only.
#:
#: Not against the title or the "why", which is prose written to explain the
#: case to a reader — "the entity is what a row is keyed on" matched the
#: family about reading a wrong *key*, and a plan that groups by a word in an
#: explanation groups nothing.
FAMILIES = [
    ("a stated ground accepted blank",
     r"accepted blank|was accepted, and|with no (name|owner|entity|"
     r"description|reason|title)"),
    ("a value outside its range accepted",
     r"negative \w+ was accepted|unknown \w+ was accepted|"
     r"out of range|not a shape|unknown dtype"),
    ("an unknown identifier answered 500",
     r"-> 500|answered 500|Internal Server Error"),
    ("an unhandled exception reached the caller",
     r"KeyError|TypeError|AttributeError|IndexError|raised \w+Error"),
    ("a control that exists and nothing calls",
     r"unknown_permission|no caller|never called|unreachable"),
    ("a warning to a human and success to the script",
     r"exited 0|exit code|DIGEST DIFFERS"),
    ("an answer that changes when nothing changed",
     r"digests? (differ|changed)|two renderings|grew because"),
    ("a count read off a key nothing publishes",
     r"reports? 0|always 0|reported zero|reads a key"),
    ("not callable by a generic driver — needs a hand-written case",
     r"not callable by a generic driver|streams without ending"),
    ("the platform is right and the case was wrong",
     r"a considered refusal|known.: ?false|correct refusal"),
]


def failures() -> List[Dict]:
    out: List[Dict] = []
    for path in sorted(RESULTS.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for row in payload.get("results", []):
            if row.get("verdict") in ("FAIL", "BLOCKED"):
                out.append({**row, "source": path.name})
    return out


def family_of(row: Dict) -> str:
    text = row.get("evidence", "")
    for name, pattern in FAMILIES:
        if re.search(pattern, text, re.I):
            return name
    return "not yet classified"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan", action="store_true",
                    help="group into batches instead of listing")
    args = ap.parse_args(argv)
    found = failures()
    if not found:
        print("no open QA failures recorded")
        return 0
    if not args.plan:
        for row in found:
            print(f"{row['verdict']:8s} {row['id']}  {row.get('title', '')}")
            print(f"         {row.get('evidence', '')[:150]}")
        print(f"\n{len(found)} open")
        return 0
    grouped: Dict[str, List[Dict]] = collections.defaultdict(list)
    for row in found:
        grouped[family_of(row)].append(row)
    for name, rows in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        print(f"\n## {name}  ({len(rows)} case(s))")
        for row in rows:
            print(f"   {row['id']}  {row.get('title', '')[:70]}")
    print(f"\n{len(found)} open across {len(grouped)} group(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
