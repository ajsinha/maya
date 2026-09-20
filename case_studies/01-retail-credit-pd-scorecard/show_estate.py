"""
Step 7 — what the estate holds now, and what an auditor can read from it.

    .venv/bin/python case_studies/01-retail-credit-pd-scorecard/show_estate.py

Nothing is created here. This step only reads, which is the point: everything the
previous six steps did is discoverable afterwards by somebody who was not in the room —
the catalog, the hash-chained audit log, the warrant's chain of custody, and the lineage
graph from the panel down to the execution warrant.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, browse_hint, step_script  # noqa: E402
from study import EXTRA_USERS, LIVE, NS, PANEL, WARRANT, Cast, find_warrant  # noqa: E402

TITLE = "Case study 1, step 7 — the estate, read back"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("The catalog, as the feature manager sees it")
    for kind in ("feature", "featureset", "model"):
        rows = cast.mick.catalog.browse(type=kind)
        n.fact(f"{kind}s", f"{len(rows)}: " + ", ".join(r.get("name", "?") for r in rows))

    n.step("The audit log: append-only, each entry carrying the hash of the last")
    chain = cast.admin.admin.verify_audit()
    n.fact("entries", f"{chain['checked']:,}")
    n.fact("chain unbroken", chain["ok"])
    actions = cast.admin.admin.audit(limit=1000)
    kinds: dict[str, int] = {}
    for row in actions:
        kinds[row["action"]] = kinds.get(row["action"], 0) + 1
    n.fact("most frequent", ", ".join(f"{k}×{v}" for k, v in sorted(kinds.items())[:6]))

    n.step("The training warrant's chain of custody")
    warrant = find_warrant(cast.mgr, WARRANT)
    for event in warrant["custody"]:
        n.say(f"{event['event']} — {event.get('actor', '')}")

    n.step("Lineage: what fed what")
    graph = cast.mgr.access.lineage(f"maya://featureset/{NS}/{PANEL}@v1")
    n.fact("nodes", len(graph["nodes"]))
    n.fact("edges", len(graph["edges"]))
    for edge in graph["edges"]:
        label = f" ({edge['label']})" if edge.get("label") else ""
        n.say(f"{edge['source']}  --{edge['type']}{label}-->  {edge['target']}")

    n.step("And the live model")
    live = [row for row in cast.mgr.execution.list() if row["name"] == LIVE]
    for row in live:
        n.fact(row["name"], f"{row['state']}, {row.get('status', '')}")
    browse_hint(maya)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
