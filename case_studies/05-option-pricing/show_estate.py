"""
Step 7 — what the estate holds, and what the calibration looks like from outside.

    .venv/bin/python case_studies/05-option-pricing/show_estate.py

Nothing is created here. It reads back what the previous six steps built: the catalog, the
model version's artifact report including the conformance result and the domain it was
gathered on, both calibrations with their blind holdout scores, the audit chain, and the
lineage around the pinned chain.

The point of reading it back is that a person who was not in the room can find out which
volatility was live, what it was calibrated to, and how badly the alternative scored.

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
    SIGMAS,
    WARRANT,
    Cast,
    find_warrant,
)

TITLE = "Case study 5, step 7 — the estate, read back"


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
    n.fact("tested against", f"{(conformance.get('artifact_hash') or '')[:16]}…")
    n.fact("run by", f"{conformance.get('run_by')} at {conformance.get('run_at', '')[:19]}")

    n.step("The warrant, its two calibrations and what each scored")
    warrant = find_warrant(cast.mgr, WARRANT)
    n.fact("drawn on", warrant["featureset_ref"])
    n.fact("leakage certificate", warrant["leakage_certificate"]["status"])
    for ps in warrant.get("parameter_sets", []):
        vols = ps["values"]
        spread = f"{min(vols[s] for s in SIGMAS):.4f}..{max(vols[s] for s in SIGMAS):.4f}"
        n.fact(ps["name"], f"{ps['state']}, verified_data={ps['verified_data']}, sigma {spread}")
    for score in warrant.get("holdout_scores", []):
        n.fact(
            f"holdout attempt {score['attempt_no']}",
            f"RMSE {score['metrics']['rmse']:.4f}, MAE {score['metrics']['mae']:.4f} "
            f"over {score['metrics']['rows']:,} quotes",
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
