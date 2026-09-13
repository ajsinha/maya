"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section D: every mapped refusal code, and whether anything can actually emit it.

    python -m tools.qa.refusals --out docs/QA/results/D.json

## Why this is not part of the runner

`tools/qa/run.py` calls endpoints. Provoking `segregation_of_duties` means
building two principals, an approval, and a conflict between them; provoking
`composite_spanned_a_revocation` means revoking a grant *while* a chain is
resolving. There are 591 codes and no generic driver constructs 591 different
states, so a runner that tried would report a long list of BLOCKED and teach
nobody anything.

## The method, stated plainly because it is weaker than calling

A code passes here when **both** are true:

1. **It has a raise site.** Found by walking `core/` and `routes/` for a string
   literal in first-argument position of an `*Error(...)` call — the same walk
   `tests/test_refusal_discipline.py` uses, and the reason refusal codes are
   never built with f-strings in this codebase.
2. **Something provokes it.** The test suite runs with every refusal class
   instrumented, and each code that is actually constructed during the run is
   recorded. This is evidence that the state which raises it is reachable, from
   a body of tests that assert on the consequence.

A code with a raise site and no provocation is not a defect and is not reported
as one. It is reported as **UNPROVEN** — the platform maps it, the source can
raise it, and nothing in the suite reaches the state. That is a real gap in
coverage and a candidate for a hand-written case, and calling it a pass would
be the exact failure this whole exercise exists to avoid.
"""
from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import subprocess
import sys
from typing import Dict, List, Set, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CODE_SHAPE = re.compile(r"[a-z][a-z0-9_]{2,}")

#: Where the instrumented run writes the codes it saw.
SEEN = ROOT / "docs" / "QA" / "results" / ".codes-seen.txt"


def mapped() -> Dict[str, int]:
    from tools.qa.enumerate import refusal_codes
    return refusal_codes()


def _scanned() -> List[pathlib.Path]:
    """Every Python file a refusal could be raised from.

    The root modules are included because `run_maya_web.py` raises
    `csrf_token_invalid` and nothing else does. Scanning only the packages
    reported the CSRF refusal as existing in a status table and in no code
    path — which is exactly the finding this check exists to make, and would
    have been entirely an artefact of where it looked.
    """
    out = list(sorted(ROOT.glob("*.py")))
    for folder in ("core", "routes", "db", "sdk", "tools"):
        base = ROOT / folder
        if base.is_dir():
            out.extend(sorted(base.rglob("*.py")))
    return out


def raise_sites() -> Dict[str, List[str]]:
    """Every code this codebase can emit, and where from.

    **Three shapes, because knowing only one reports the other two as absent** —
    and absent is the answer that looks like a finding. A first version of this
    knew only the first shape and reported nine perfectly emittable refusals as
    raised nowhere.
    """
    found: Dict[str, List[str]] = {}

    # 1. `SomeError("code", detail, remediation)` — the ordinary shape, and the
    #    reason refusal codes in this codebase are never built with f-strings.
    for path in _scanned():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"),
                             filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = (getattr(node.func, "id", "")
                    or getattr(node.func, "attr", ""))
            if not name.endswith("Error"):
                continue
            first = node.args[0]
            if (isinstance(first, ast.Constant)
                    and isinstance(first.value, str)
                    and CODE_SHAPE.fullmatch(first.value)):
                found.setdefault(first.value, []).append(
                    f"{path.relative_to(ROOT)}:{node.lineno}")

    for path in _scanned():
        text = path.read_text(encoding="utf-8")
        # 2. A route answering with `HTTPException(detail={"error": "code"})`
        #    rather than raising a typed error.
        for match in re.finditer(r'"error"\s*:\s*"([a-z][a-z0-9_]{2,})"', text):
            line = text.count("\n", 0, match.start()) + 1
            found.setdefault(match.group(1), []).append(
                f"{path.relative_to(ROOT)}:{line} (HTTPException detail)")
        # 3. The class-to-code table in `routes/base.py`, where the code exists
        #    only as a dict value. Not anchored to the line start: the first
        #    entry shares its line with `table = {`, and anchoring reported
        #    `registry_refused` as raised nowhere.
        for match in re.finditer(
                r'(?:[A-Za-z_]+Error|[A-Za-z_]*Rejected)\s*:\s*'
                r'"([a-z][a-z0-9_]{2,})"', text):
            line = text.count("\n", 0, match.start()) + 1
            found.setdefault(match.group(1), []).append(
                f"{path.relative_to(ROOT)}:{line} (class-to-code table)")
    return found


def provoked(rerun: bool) -> Set[str]:
    """Codes actually constructed while the test suite runs."""
    if rerun or not SEEN.is_file():
        SEEN.parent.mkdir(parents=True, exist_ok=True)
        SEEN.write_text("", encoding="utf-8")
        print("running the suite with every refusal class instrumented "
              "(this takes a few minutes) ...", flush=True)
        subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly",
             "-p", "tools.qa.codeprobe", "tests/"],
            cwd=ROOT, capture_output=True, text=True)
    if not SEEN.is_file():
        return set()
    return {line.strip() for line in SEEN.read_text(encoding="utf-8").splitlines()
            if line.strip()}


def assess(rerun: bool = False) -> Tuple[List[dict], dict]:
    codes, sites, seen = mapped(), raise_sites(), provoked(rerun)
    rows, counter = [], {"PASS": 0, "UNPROVEN": 0, "FAIL": 0}
    for index, (code, status) in enumerate(sorted(codes.items()), start=1):
        where = sites.get(code, [])
        if not where:
            verdict, evidence = "FAIL", (
                "mapped to a status and raised nowhere — a control that "
                "exists in a status table and in no code path")
        elif code in seen:
            verdict, evidence = "PASS", (
                f"raised at {where[0]}"
                + (f" (+{len(where) - 1} more)" if len(where) > 1 else "")
                + "; provoked by the suite")
        else:
            verdict, evidence = "UNPROVEN", (
                f"raised at {where[0]}; the suite never reaches the state that "
                f"raises it, so nothing here shows it can fire")
        counter[verdict] += 1
        rows.append({"id": f"QA-REFUSAL-{index:03d}", "section": "D",
                     "area": "refusal", "title": f"`{code}` can be provoked",
                     "expect": f"refused ({status})", "status": status,
                     "verdict": verdict, "evidence": evidence,
                     "method": "raise-site + instrumented suite"})
    return rows, {"total": len(rows), **counter}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/QA/results/D.json")
    ap.add_argument("--rerun", action="store_true",
                    help="re-run the instrumented suite rather than reusing "
                         "the codes recorded last time")
    args = ap.parse_args(argv)
    rows, summary = assess(args.rerun)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "results": rows}, indent=1),
                   encoding="utf-8")
    print(f"{summary['total']} refusal codes — {summary['PASS']} provoked, "
          f"{summary['UNPROVEN']} unproven, {summary['FAIL']} raised nowhere")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
