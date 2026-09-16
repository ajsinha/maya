"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Reconcile `qa/ACTION-PLAN.md` against the newest section runs.

    python -m qa.regression_suite.reconcile

The plan is the fix backlog and the section results are the truth. They drift in
both directions and each direction hides something different:

  a finding that now PASSES and still has a row  — work already done, re-read
    as outstanding, and a batch that looks larger than it is
  a finding that FAILS and has no row            — work that will never be
    scheduled, because the plan is what gets worked through

The second is the one that bites. It is how `QA-GOV-4608` survived batch B
being written up as closed: the batch was summarised from what had been fixed
rather than from what was still failing, and nothing compared the two.

**Verdicts are only taken from FULL-SECTION runs.** A single-case result file
is written by `--only QA-X-123` and is exactly the shape that has been wrong
before: a case can pass alone and fail beside its neighbours (a shared
register, a chain another case broke) or fail alone and pass in a section
(a fixture the section's earlier cases set up). So this reads
`scenarios-qa_<section>.json` and ignores the rest.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Dict, List, Set, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLAN = ROOT / "qa" / "ACTION-PLAN.md"
RESULTS = ROOT / "qa" / "results"

#: The five sections, and the only result files read. `scenarios-qa_am.json` is
#: a full-section run; `scenarios-qa_am_646.json` is one case.
SECTIONS: Tuple[str, ...] = ("am", "fx", "gov", "plt", "del")


def failing() -> Tuple[Set[str], List[str]]:
    """Every id failing in the newest full-section runs, and what is missing."""
    out: Set[str] = set()
    absent: List[str] = []
    for section in SECTIONS:
        path = RESULTS / f"scenarios-qa_{section}.json"
        if not path.is_file():
            absent.append(f"qa_{section}")
            continue
        for row in json.loads(path.read_text(encoding="utf-8")).get("results", []):
            if row.get("verdict") == "FAIL":
                out.add(row["id"])
    return out, absent


def counts() -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    for section in SECTIONS:
        path = RESULTS / f"scenarios-qa_{section}.json"
        if not path.is_file():
            continue
        rows = json.loads(path.read_text(encoding="utf-8")).get("results", [])
        tally = {"pass": 0, "fail": 0, "blocked": 0}
        for row in rows:
            tally[str(row.get("verdict", "")).lower()] = \
                tally.get(str(row.get("verdict", "")).lower(), 0) + 1
        out[f"QA-{section.upper()}"] = tally
    return out


def planned() -> Set[str]:
    """Every id the plan still carries a row for."""
    return set(re.findall(r"^\| `(QA-[A-Z]+-\d+)` \|",
                          PLAN.read_text(encoding="utf-8"), re.M))


def main(argv=None) -> int:
    del argv
    open_now, absent = failing()
    rows = planned()
    stale = sorted(rows - open_now)
    unassigned = sorted(open_now - rows)

    for section, tally in counts().items():
        print(f"  {section:8} {tally['pass']:4} pass  {tally['fail']:3} fail  "
              f"{tally['blocked']:3} blocked")
    print(f"\n{len(open_now)} finding(s) failing; {len(rows)} row(s) in the plan")

    if absent:
        print(f"\nNO FULL-SECTION RUN for {', '.join(absent)} — this report is "
              f"about the sections that HAVE one, and says nothing about the "
              f"rest. Run `python -m qa.regression_suite.scenario_run --only "
              f"QA-{absent[0].split('_')[1].upper()}` first.")
    if stale:
        print(f"\nSTALE — a row in the plan that no longer fails ({len(stale)}). "
              f"Fixed, and the plan still asks for it:")
        for case_id in stale:
            print(f"    {case_id}")
    if unassigned:
        print(f"\nUNASSIGNED — failing with no row in the plan ({len(unassigned)}). "
              f"This is work that will never be scheduled:")
        for case_id in unassigned:
            print(f"    {case_id}")
    if not stale and not unassigned and not absent:
        print("\nthe plan and the newest section runs agree")
    return 1 if (unassigned or absent) else 0


if __name__ == "__main__":                       # pragma: no cover
    sys.exit(main())
