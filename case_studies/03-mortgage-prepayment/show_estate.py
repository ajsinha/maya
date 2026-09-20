"""
Step 8 — the estate, read back, including the proposal that has not landed.

    .venv/bin/python case_studies/03-mortgage-prepayment/show_estate.py

Nothing is created here. It reads the catalog, the fitted coefficients against the ones
that generated the book, the audit chain, the lineage from the market rate — which is the
interesting root in this study, because one 30-row feature feeds every loan's forecast —
and the workspace still sitting open with its replay attached.

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
    EXTRA_USERS,
    LIVE,
    NS,
    TRUE,
    WARRANT,
    WORKSPACE,
    Cast,
    approved_parameters,
    find_warrant,
    find_workspace,
)

TITLE = "Case study 3, step 8 — the estate, read back"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("The catalog")
    for kind in ("feature", "featureset", "model"):
        rows = cast.mick.catalog.browse(type=kind)
        n.fact(f"{kind}s", f"{len(rows)}: " + ", ".join(r.get("name", "?") for r in rows))

    n.step("The approved coefficients, against the process that generated the book")
    warrant = find_warrant(cast.mgr, WARRANT)
    parameters = approved_parameters(warrant)
    for name, generated in TRUE.items():
        n.fact(name, f"approved {parameters['values'][name]:+.3f}   generated {generated:+.3f}")
    n.fact("reported metrics", parameters.get("metrics"))
    n.fact("verified against a MAYA download", parameters["verified_data"])

    n.step("Lineage from the market rate: 30 rows that reach every forecast")
    graph = cast.mgr.access.lineage(f"maya://feature/{NS}/mortgage_rate@v1")
    n.fact("nodes", len(graph["nodes"]))
    for edge in graph["edges"]:
        label = f" ({edge['label']})" if edge.get("label") else ""
        n.say(f"{edge['source']}  --{edge['type']}{label}-->  {edge['target']}")

    n.step("The live warrant, and the proposal that has not landed")
    for row in cast.mgr.execution.list():
        if row["name"] == LIVE:
            n.fact(row["name"], f"{row['state']}, {row.get('status', '')}")
    workspace = find_workspace(cast.devi, WORKSPACE)
    if workspace:
        replay = workspace.get("replay") or {}
        n.fact("workspace", f"{workspace['name']} ({workspace['state']})")
        n.fact("its replay", replay.get("summary", "not run"))

    n.step("The audit chain")
    chain = cast.admin.admin.verify_audit()
    n.fact("entries", f"{chain['checked']:,}, unbroken={chain['ok']}")
    browse_hint(maya)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
