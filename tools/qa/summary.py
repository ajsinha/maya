"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Where the QA pass has got to, across every group at once.

    python -m tools.qa.summary

Reads the result files each runner writes and reports coverage against the
**published** case list, so the denominator is the same list a reader can
open rather than a count of whatever happened to be run.

Any case id in a result file that is not in `docs/QA/QA-CASES.md` is reported
separately. A pass over cases nobody published is not coverage of the case
list, and quietly folding the two together is how a run comes to claim a
percentage of something it is not measuring.
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import Dict, List

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASES = ROOT / "docs" / "QA" / "QA-CASES.md"
RESULTS = ROOT / "docs" / "QA" / "results"

#: Which published section each id prefix belongs to.
SECTIONS = [
    ("A–E  generated (operations, fields, ids, refusals, screens)",
     lambda cid: bool(re.match(r"QA-(?!GOV|FX|AM|PLT|DEL)", cid))),
    ("F    governance", lambda cid: cid.startswith("QA-GOV")),
    ("G    features and execution", lambda cid: cid.startswith("QA-FX")),
    ("H    assurance and monitoring", lambda cid: cid.startswith("QA-AM")),
    ("I    platform and interfaces", lambda cid: cid.startswith("QA-PLT")),
    ("J    deletion and storage", lambda cid: cid.startswith("QA-DEL")),
]


def published() -> List[str]:
    text = CASES.read_text(encoding="utf-8")
    return re.findall(r"^\|\s*(QA-[A-Z0-9-]+)\s*\|", text, re.M)


def executed() -> Dict[str, str]:
    """case id -> verdict, latest result wins."""
    out: Dict[str, str] = {}
    for path in sorted(RESULTS.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for row in payload.get("results", []):
            out[row["id"]] = row["verdict"]
    return out


def main() -> int:
    known, ran = set(published()), executed()
    rows = []
    for title, belongs in SECTIONS:
        in_list = {c for c in known if belongs(c)}
        done = {c: v for c, v in ran.items() if c in in_list}
        rows.append((title, len(in_list), len(done),
                     sum(1 for v in done.values() if v == "PASS"),
                     sum(1 for v in done.values() if v == "FAIL"),
                     sum(1 for v in done.values() if v == "BLOCKED"),
                     sum(1 for v in done.values() if v == "UNPROVEN")))
    width = max(len(r[0]) for r in rows)
    print(f"{'section'.ljust(width)}  {'cases':>6} {'run':>6} {'pass':>6} "
          f"{'fail':>5} {'block':>6} {'unprv':>6}")
    for title, total, run, ok, bad, blocked, unproven in rows:
        print(f"{title.ljust(width)}  {total:>6} {run:>6} {ok:>6} {bad:>5} "
              f"{blocked:>6} {unproven:>6}")
    total, run = len(known), len({c for c in ran if c in known})
    ok = sum(1 for c, v in ran.items() if c in known and v == "PASS")
    bad = sum(1 for c, v in ran.items() if c in known and v == "FAIL")
    blocked = sum(1 for c, v in ran.items() if c in known and v == "BLOCKED")
    unproven = sum(1 for c, v in ran.items() if c in known and v == "UNPROVEN")
    print(f"{'TOTAL'.ljust(width)}  {total:>6} {run:>6} {ok:>6} {bad:>5} "
          f"{blocked:>6} {unproven:>6}")
    print(f"\n{run} of {total} published cases executed "
          f"({100.0 * run / total:.0f}%), {total - run} not yet run")
    stray = sorted(c for c in ran if c not in known)
    if stray:
        print(f"{len(stray)} result(s) for ids not in the published list: "
              f"{stray[:6]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
