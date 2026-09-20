"""
Step 8 — what the estate holds, and what the calibration looks like from outside.

    .venv/bin/python case_studies/11-nelson-siegel-curve/show_estate.py

Nothing is created here. It reads back what the previous seven steps built: the catalog, the
model version's artifact report with the domain *and the parameter values* its conformance was
gathered at, every calibration with its blind score in basis points, the audit chain and the
lineage around the pinned curve.

The point of reading it back is that somebody who was not in the room can find out which
curve was live, what it was calibrated to, how badly the alternatives scored, and — for the
one that was sent back — why.

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
    PANEL,
    PARAMS,
    WARRANT,
    Cast,
    find_warrant,
)

TITLE = "Case study 11, step 8 — the estate, read back"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("The catalog")
    for kind in ("feature", "featureset", "model"):
        rows = cast.mick.catalog.browse(type=kind)
        n.fact(f"{kind}s", f"{len(rows)}: " + ", ".join(r.get("name", "?") for r in rows))

    n.step("What the model version carries about its own code")
    version = cast.mgr.models.get(f"{NS}/{MODEL}")["versions"][0]
    report = version["artifact_report"] or {}
    conformance = report.get("conformance") or {}
    n.fact("artifact hash", f"{(version['artifact_hash'] or '')[:16]}…")
    n.fact("ladder", f"passed={report.get('passed')}, deterministic={report.get('deterministic')}")
    n.fact("conformance", f"{conformance.get('agreed')} of {conformance.get('total')} agreed")
    n.fact("on the domain", conformance.get("domain"))
    n.fact(
        "at the parameter values",
        ", ".join(f"{k}={v:.4g}" for k, v in sorted((conformance.get("params") or {}).items())),
    )
    n.fact("run by", f"{conformance.get('run_by')} at {conformance.get('run_at', '')[:19]}")

    n.step("The warrant, its four calibrations and what each one scored blind")
    warrant = find_warrant(cast.mgr, WARRANT)
    n.fact("drawn on", warrant["featureset_ref"])
    n.fact("leakage certificate", warrant["leakage_certificate"]["status"])
    for ps in warrant.get("parameter_sets", []):
        shown = ", ".join(f"{k}={float(ps['values'][k]):+.5f}" for k in PARAMS)
        n.fact(ps["name"], f"{ps['state']}, verified_data={ps['verified_data']}")
        n.say(f"  {shown}")
    for score in warrant.get("holdout_scores", []):
        n.fact(
            f"holdout attempt {score['attempt_no']}",
            f"RMSE {score['metrics']['rmse'] * 1e4:8.2f} bp over "
            f"{score['metrics']['rows']:,} pillars",
        )
    n.fact("custody", ", ".join(e["event"] for e in warrant["custody"]))

    n.step("The execution warrants")
    for row in cast.mgr.execution.list():
        ew = cast.mgr.execution.get(row["id"])
        covenants = ", ".join(c["kind"] for c in ew["spec"]["covenants"]) or "none"
        n.fact(ew["name"], f"{ew['status']}, covenants: {covenants}")

    n.step("The audit chain, and the lineage")
    chain = cast.admin.admin.verify_audit()
    n.fact("audit entries", f"{chain['checked']:,}, unbroken={chain['ok']}")
    graph = cast.mgr.access.lineage(f"maya://featureset/{NS}/{PANEL}@v1")
    n.fact("lineage", f"{len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
    browse_hint(maya)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
