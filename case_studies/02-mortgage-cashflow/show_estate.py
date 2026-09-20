"""
Step 7 — what the estate holds, and what the reconciliation looks like from outside.

    .venv/bin/python case_studies/02-mortgage-cashflow/show_estate.py

Nothing is created here. It reads back what the previous six steps built: the catalog, the
model version's artifact report including the conformance result recorded against the
artifact hash it tested, the audit chain, and the lineage.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, browse_hint, step_script  # noqa: E402
from study import EXTRA_USERS, MODEL, NS, PANEL, WARRANT, Cast, find_warrant  # noqa: E402

TITLE = "Case study 2, step 7 — the estate, read back"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("The catalog")
    for kind in ("feature", "featureset", "model"):
        rows = cast.mick.catalog.browse(type=kind)
        n.fact(f"{kind}s", f"{len(rows)}: " + ", ".join(r.get("name", "?") for r in rows))

    n.step("What the model version carries about its own code")
    version = cast.mgr.models.get(f"{NS}/{MODEL}")["versions"][0]
    report = version["artifact_report"] or {}
    n.fact("artifact hash", f"{(version['artifact_hash'] or '')[:16]}…")
    n.fact("ladder", f"passed={report.get('passed')}, deterministic={report.get('deterministic')}")
    conformance = report.get("conformance") or {}
    n.fact("conformance", f"{conformance.get('agreed')} of {conformance.get('total')} agreed")
    n.fact("tested against", f"{(conformance.get('artifact_hash') or '')[:16]}…")
    n.fact("run by", f"{conformance.get('run_by')} at {conformance.get('run_at', '')[:19]}")
    n.say("Recorded against the hash it tested, so changing the code invalidates it.")

    n.step("The warrant, and what it reconciled to")
    warrant = find_warrant(cast.mgr, WARRANT)
    for score in warrant.get("holdout_scores", []):
        n.fact(
            f"attempt {score['attempt_no']}",
            f"RMSE {score['metrics']['rmse']:,.2f}, MAE {score['metrics']['mae']:,.2f} "
            f"over {score['metrics']['rows']:,} loan-months",
        )
    n.fact("custody", ", ".join(e["event"] for e in warrant["custody"]))

    n.step("The audit chain, and the lineage")
    chain = cast.admin.admin.verify_audit()
    n.fact("audit entries", f"{chain['checked']:,}, unbroken={chain['ok']}")
    graph = cast.mgr.access.lineage(f"maya://featureset/{NS}/{PANEL}@v1")
    n.fact("lineage", f"{len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
    browse_hint(maya)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
