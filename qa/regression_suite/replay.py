"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Published cases whose own steps can be executed.

    python -m qa.regression_suite.replay --out qa/results/replayed.json

Of the 1,715 hand-written case rows, **294 name a method and a path** in their
Steps column. That number was measured before this was built, because the
attractive version of this idea — "parse the case list and run all of it" —
buys 17% and not 100%, and knowing which before writing a parser is the
difference between a tool and a disappointment.

## What an execution here is worth, and what it is not

The Steps column is written for a person: *"register a baselined model; POST
/models/{name}/amend"*. This runs the calls it names and cannot perform the
prose. So a case whose setup is a sentence will reach its final call in the
wrong state, and the answer will be about the wrong thing.

That is why a mismatch here is **never** reported as a defect. Three verdicts:

`PASS`       the platform did what the case predicted
`NEEDS-CASE` it did something else — which usually means the setup was prose,
             and always means a person should write this one by hand
`CRASHED`    a 500, which is a defect whatever the setup was

Only the first counts as coverage, and only the last is a finding. The middle
one is a worklist.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CASES = ROOT / "qa" / "QA-CASES.md"
CALL = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[A-Za-z0-9{}/_.:-]+)")
REFUSAL = re.compile(r"refused\s*\(`?([a-z_]+)", re.I)
ACCEPTED = re.compile(r"\*\*accepted", re.I)
AVOID = ("/admin/shutdown", "/admin/restart", "/api/v1/logs/stream",
         "/logout", "/login")


def rows() -> List[Tuple[str, str, str]]:
    """`(id, expectation, steps)` for every published case."""
    text = CASES.read_text(encoding="utf-8")
    out = []
    for match in re.finditer(
            r"^\|\s*(QA-[A-Z0-9-]+)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|",
            text, re.M):
        out.append((match.group(1).strip(), match.group(4), match.group(5)))
    return out


def normalise(path: str, known: set) -> Optional[str]:
    """The published path as the application actually spells it.

    Cases are written the way people say them — `/models`, not
    `/api/v1/models` — so a literal match finds almost nothing.
    """
    path = path.rstrip(".,;")
    for candidate in (path, f"/api/v1{path}"):
        if candidate in known:
            return candidate
    # A parameterised path: match by shape, since the case writes `{name}`
    # and the specification may write `{name:path}`.
    shape = re.sub(r"\{[^}]*\}", "{}", path)
    for candidate in known:
        if re.sub(r"\{[^}]*\}", "{}", candidate) in (shape, f"/api/v1{shape}"):
            return candidate
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="qa/results/replayed.json")
    args = ap.parse_args(argv)

    from qa.regression_suite.harness import live_client
    from qa.regression_suite.shapes import body_for, document

    started = time.time()
    results: List[Dict[str, Any]] = []
    with live_client() as (_ui, api, _observer):
        spec = document(api)
        known = set(spec.get("paths", {}))
        for case_id, expectation, steps in rows():
            # HAND-WRITTEN sections only.
            #
            # `rows()` reads the whole published list, and re-driving the
            # generated sections here would overwrite their proper results
            # with a weaker method's verdict — turning 1,507 real passes into
            # NEEDS-CASE in the summary. A replay must never be able to
            # downgrade a case that was executed properly.
            if not re.match(r"QA-(GOV|FX|AM|PLT|DEL)-", case_id):
                continue
            calls = CALL.findall(steps)
            if not calls:
                continue
            wanted = REFUSAL.search(expectation)
            expects_ok = bool(ACCEPTED.search(expectation)) and not wanted
            answer = None
            reached = None
            for method, raw in calls:
                path = normalise(raw, known)
                if path is None or any(path.startswith(a) for a in AVOID):
                    continue
                filled = re.sub(r"\{[^}]*\}", "qa-replay", path)
                body = body_for(method, path, api)
                answer = api.request(method, filled,
                                     json=body if method != "GET" else None)
                reached = f"{method} {filled}"
            if answer is None:
                continue
            try:
                got = (answer.json() or {}).get("error", "")
            except Exception:
                got = ""
            # 501 carrying a coded body is the platform saying *this
            # deployment has no time stamp authority / no identity provider*,
            # with a detail and a remediation. That is the boundary discipline
            # working, and four of the first twelve "crashes" were exactly
            # that.
            considered_501 = answer.status_code == 501 and '"error"' in answer.text
            if answer.status_code >= 500 and not considered_501:
                verdict = "CRASHED"
            elif wanted and got == wanted.group(1):
                verdict = "PASS"
            elif expects_ok and answer.status_code < 400:
                verdict = "PASS"
            else:
                verdict = "NEEDS-CASE"
            results.append({
                "id": case_id, "verdict": verdict, "reached": reached,
                "expected": (wanted.group(1) if wanted
                             else "accepted" if expects_ok else "?"),
                "got": got or answer.status_code,
                "evidence": f"{reached} -> {answer.status_code} "
                            f"{answer.text[:120]}"})

    counts: Dict[str, int] = {}
    for row in results:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": counts,
                               "seconds": round(time.time() - started, 1),
                               "results": results}, indent=1),
                   encoding="utf-8")
    print(f"{len(results)} published cases driven from their own steps — "
          f"{counts}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
