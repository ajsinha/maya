"""
Step 8 — the estate, read back, with the composite's members visible in it.

    .venv/bin/python case_studies/04-heloc-exposure/show_estate.py

Nothing is created here. It reads the catalog, the composite's members and their maturities,
the two approved parameter sets and which member each belongs to, the holdout attempts, the
lineage, and the audit chain.

The lineage is the interesting read in this study: the composite sits above two member models
and below one warrant, so the graph shows both directions of a structure that a list of names
cannot.

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
    DRAW_MODEL,
    EXTRA_USERS,
    LIVE,
    NS,
    REPAY_MODEL,
    WARRANT,
    Cast,
    find_warrant,
)

TITLE = "Case study 4, step 8 — the estate, read back"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("The catalog")
    for kind in ("feature", "featureset", "model"):
        rows = cast.mick.catalog.browse(type=kind)
        n.fact(f"{kind}s", f"{len(rows)}: " + ", ".join(sorted(r.get("name", "?") for r in rows)))

    n.step("The composite, and the members it is capped by")
    composite = cast.mgr.models.get(f"{NS}/{COMPOSITE}")
    version = composite["versions"][0]
    n.fact("kind", composite["kind"])
    n.fact("maturity", version["maturity"])
    n.fact("contract", ", ".join(c["name"] for c in version["input_contract"]))
    for c in version["input_contract"]:
        n.say(f"{c['name']:<12} needed by {', '.join(c['needed_by'])}")
    for name in (DRAW_MODEL, REPAY_MODEL):
        member = cast.mgr.models.get(f"{NS}/{name}")["versions"][0]
        n.fact(name, f"v{member['version_no']} {member['state']}, maturity {member['maturity']}")

    n.step("The warrant: one warrant, two parameter sets, one per member")
    warrant = find_warrant(cast.mgr, WARRANT)
    for ps in warrant["parameter_sets"]:
        n.fact(
            f"{ps.get('member_alias') or '(composite)'}",
            f"{ps['id'][:8]}… {ps['state']}, verified_data={ps['verified_data']}",
        )
    for score in warrant.get("holdout_scores", []):
        n.fact(
            f"holdout attempt {score['attempt_no']}",
            f"RMSE {score['metrics']['rmse']:,.0f} over {score['metrics']['rows']:,} rows",
        )
    n.say("Both attempts are on the record, including the one that scored the benchmark.")

    n.step("Lineage around the composite")
    graph = cast.mgr.access.lineage(f"maya://model/{NS}/{COMPOSITE}@v1")
    n.fact("nodes", len(graph["nodes"]))
    for edge in graph["edges"]:
        label = f" ({edge['label']})" if edge.get("label") else ""
        n.say(f"{edge['source']}  --{edge['type']}{label}-->  {edge['target']}")

    n.step("The live warrant and the audit chain")
    for row in cast.mgr.execution.list():
        if row["name"] == LIVE:
            n.fact(row["name"], f"{row['state']}, {row.get('status', '')}")
    chain = cast.admin.admin.verify_audit()
    n.fact("audit entries", f"{chain['checked']:,}, unbroken={chain['ok']}")
    browse_hint(maya)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
