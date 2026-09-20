"""
Step 9 — what the estate holds now, with two versions of one model in it.

    .venv/bin/python case_studies/10-factor-models/show_estate.py

Nothing is created here. This step only reads, which is the point: somebody who was not in
the room can find both versions, see which is current and which is superseded and by what,
read the diff between them, compare the two parameter sets and the two holdout scores, and
walk the lineage from a 504-row factor feed to two live warrants.

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
    MODEL,
    NS,
    WARRANT_V1,
    WARRANT_V2,
    Cast,
    find_warrant,
)

TITLE = "Case study 10, step 9 — the estate, read back"
REF = f"{NS}/{MODEL}"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("The catalog")
    for kind in ("feature", "featureset", "model"):
        rows = cast.mick.catalog.browse(type=kind)
        n.fact(f"{kind}s", f"{len(rows)}: " + ", ".join(r.get("name", "?") for r in rows))

    n.step("One model, two versions, and which is which")
    for v in sorted(cast.mgr.models.get(REF)["versions"], key=lambda r: r["version_no"]):
        n.fact(
            f"v{v['version_no']}",
            f"{v['state']}, maturity {v['maturity']}, "
            f"{len(v['input_contract'])} feature(s) in the contract"
            + (f", successor {v['successor_ref']}" if v.get("successor_ref") else ""),
        )

    n.step("The diff a reviewer would be shown")
    diff = cast.mgr.models.diff(REF, 1, 2)
    for statement in diff["statements"]:
        n.say(f"• {statement}")

    n.step("The two fits, side by side, on the same escrowed rows")
    for name in (WARRANT_V1, WARRANT_V2):
        warrant = find_warrant(cast.mgr, name)
        approved = [p for p in warrant["parameter_sets"] if p["state"] == "approved"]
        n.fact(
            name,
            f"model v{warrant['model']['version_no']}, "
            f"{len(warrant['parameter_sets'])} parameter set(s), "
            f"{warrant['holdout_attempts']} holdout attempt(s), "
            f"holdout {(warrant['holdout_hash'] or '')[:12]}…",
        )
        for row in approved:
            n.say("  " + ", ".join(f"{k}={v:+.5f}" for k, v in sorted(row["values"].items())))
        for score in warrant["holdout_scores"]:
            tag = "fitted" if score["parameter_set_id"] else "zero benchmark"
            n.say(f"  attempt {score['attempt_no']} ({tag}): RMSE {score['metrics']['rmse']:.6f}")

    n.step("Lineage from the 504-row factor feed")
    graph = cast.mgr.access.lineage(f"maya://feature/{NS}/factor_daily@v1")
    n.fact("nodes", len(graph["nodes"]))
    n.fact("edges", len(graph["edges"]))
    for edge in graph["edges"]:
        label = f" ({edge['label']})" if edge.get("label") else ""
        n.say(f"{edge['source']}  --{edge['type']}{label}-->  {edge['target']}")

    n.step("The audit log: append-only, each entry carrying the hash of the last")
    chain = cast.admin.admin.verify_audit()
    n.fact("entries", f"{chain['checked']:,}")
    n.fact("chain unbroken", chain["ok"])

    n.step("And what is live")
    for row in cast.mgr.execution.list():
        ew = cast.mgr.execution.get(row["id"])
        n.fact(
            row["name"],
            f"{row['state']}/{ew['status']}, model v{ew['manifest']['model']['version_no']}, "
            f"environments {ew['spec']['environments']}",
        )
    browse_hint(maya)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
