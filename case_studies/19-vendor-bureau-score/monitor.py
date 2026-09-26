"""
Step 4 — live, under a drift covenant, for three months.

    .venv/bin/python case_studies/19-vendor-bureau-score/monitor.py

The execution warrant carries a population-stability covenant on utilisation, with its
baseline taken from the data the warrant was drawn on. Each month the scoring service bins
that month's utilisation on the baseline's edges and reports the histogram. MAYA computes
the index: under 0.10 is stable, 0.10 to 0.25 is worth watching, over 0.25 breaks the
covenant and suspends the warrant. The monitoring dashboard grades the warrant from the same
reports.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from maya_demo import browse_hint  # noqa: E402
from study import CONTACT, EXTRA_USERS, LIVE, NS, WARRANT, Cast, feed, find_warrant  # noqa: E402

TITLE = "Case study 19, step 4 — three months of drift"


def main(maya: Any, n: Narrator) -> None:
    import io

    import numpy as np
    import pandas as pd

    from maya.core.errors import MayaError

    cast = Cast(maya)
    n.step("Licensed to run, with a drift covenant on utilisation")
    warrant = find_warrant(cast.mgr, WARRANT)
    ew = cast.mgr.execution.create(
        NS,
        LIVE,
        training_warrant_id=warrant["id"],
        spec={
            "environments": ["prod"],
            "contact": CONTACT,
            "valid_days": 180,
            "covenants": [{"kind": "input_psi", "attr": "utilisation", "max": 0.25}],
        },
    )
    edges = next(c for c in ew["spec"]["covenants"] if c["kind"] == "input_psi")["bin_edges"]
    n.fact("baseline", f"{len(edges) - 1} bins from the warrant's data")
    cast.mgr.execution.transition(ew["id"], "submit")
    cast.lara.execution.transition(ew["id"], "approve")
    cast.mgr.execution.seal(ew["id"])

    n.step("Reporting three months of live scoring")
    live = pd.read_csv(io.BytesIO(feed("live_2026")))
    for month, frame in live.groupby("month"):
        counts, _ = np.histogram(frame["utilisation"].clip(edges[0], edges[-1]), bins=edges)
        out = cast.devi.execution.report(
            ew["id"],
            environment="prod",
            rows=len(frame),
            input_stats={
                "utilisation": {
                    "histogram": counts.tolist(),
                    "null_rate": 0.0,
                    "mean": float(frame["utilisation"].mean()),
                }
            },
        )
        psi = cast.mgr.monitoring.warrant(ew["id"], days=30)["series"]["inputs"]["utilisation"][-1][
            "psi"
        ]
        health = next(
            r for r in cast.mgr.monitoring.overview(days=30)["warrants"] if r["id"] == ew["id"]
        )["health"]
        n.fact(
            month,
            f"mean utilisation {frame['utilisation'].mean():.3f}, PSI {psi:.3f} → warrant {out['status']}, dashboard {health}",
        )

    n.step("What the service is told now, and what the dashboard says")
    try:
        cast.devi.execution.bundle(ew["id"], "prod")
    except MayaError as exc:
        n.refused("scoring applicants on a population the score was not built for", exc)
    row = next(r for r in cast.mgr.monitoring.overview(days=30)["warrants"] if r["id"] == ew["id"])
    n.fact("monitoring grade", row["health"])
    for signal in row["signals"]:
        n.say(f"{signal['level']}: {signal['what']} — {signal['why']}")
    browse_hint(maya)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
