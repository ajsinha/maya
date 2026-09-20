"""
Step 9 — the estate, read back as an auditor would.

    .venv/bin/python case_studies/06-ifrs9-expected-credit-loss/show_estate.py

Nothing is created. The question this step answers is the one a reviewer of the accounts
actually asks: *which numbers produced the allowance in the statements, who approved each of
them, and what did they know when they did?*

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, browse_hint, step_script  # noqa: E402
from study import (  # noqa: E402
    COMPOSITE,
    EXTRA_USERS,
    LIVE,
    NS,
    WARRANT,
    Cast,
    find_warrant,
)

TITLE = "Case study 6, step 9 — the estate, read back"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("The catalog")
    for kind in ("feature", "featureset", "model"):
        rows = cast.mick.catalog.browse(type=kind)
        n.fact(f"{kind}s", f"{len(rows)}: " + ", ".join(sorted(r.get("name", "?") for r in rows)))

    n.step("The composite's contract, and who needs each input")
    version = cast.mgr.models.get(f"{NS}/{COMPOSITE}")["versions"][0]
    for c in version["input_contract"]:
        n.say(f"{c['name']:<15} {c['role']:<10} needed by {', '.join(c['needed_by'])}")
    n.fact("maturity", version["maturity"])

    n.step("Every number behind the allowance, and what was said about it")
    warrant = find_warrant(cast.mgr, WARRANT)
    for ps in warrant["parameter_sets"]:
        alias = ps.get("member_alias") or "the committee's"
        n.fact(f"{alias} · {ps['state']}", ps["values"])
        if ps.get("notes"):
            n.say(f"  notes: {ps['notes'][:300]}")
        if ps.get("unverified_justification"):
            n.say(f"  approved because: {ps['unverified_justification'][:200]}")
    for score in warrant.get("holdout_scores", []):
        n.fact(
            f"holdout attempt {score['attempt_no']}",
            f"RMSE {score['metrics']['rmse']:,.0f} over {score['metrics']['rows']:,} rows",
        )

    n.step("The chain of custody, and the audit log")
    n.fact("custody", ", ".join(e["event"] for e in warrant["custody"]))
    chain = cast.admin.admin.verify_audit()
    n.fact("audit entries", f"{chain['checked']:,}, unbroken={chain['ok']}")
    graph = cast.mgr.access.lineage(f"maya://model/{NS}/{COMPOSITE}@v1")
    n.fact("lineage", f"{len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
    for row in cast.mgr.execution.list():
        if row["name"] == LIVE:
            n.fact(row["name"], f"{row['state']}, {row.get('status', '')}")
    browse_hint(maya)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
