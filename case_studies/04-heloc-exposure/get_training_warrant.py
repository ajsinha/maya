"""
Step 5 — one warrant, one pinned feature set, two members to fit.

    .venv/bin/python case_studies/04-heloc-exposure/get_training_warrant.py

§8.7's promise is that a composite "trains and executes under **one** warrant against
**one** feature set". This is that warrant. Its contract check covers the union MAYA
computed in step 4, its leakage certificate covers the same forward-looking target as the
other studies, and the data it hands over contains both regimes — because the router
chooses per row, and a developer fitting only the rows they remembered would be fitting a
different model.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import (  # noqa: E402
    COMPOSITE_REF,
    EXTRA_USERS,
    NS,
    PIN_REF,
    TARGET,
    TARGET_JUSTIFICATION,
    WARRANT,
    Cast,
    realised_fraction,
)

TITLE = "Case study 4, step 5 — one warrant over a composite"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("Drawing it against the composite and the pinned panel")
    drawn = cast.devi.training.create(
        NS,
        WARRANT,
        COMPOSITE_REF,
        PIN_REF,
        spec={
            "target": TARGET,
            "objective": (
                "twelve-month exposure at default on committed home equity lines, for "
                "capital, the exposure input to expected credit loss, and liquidity planning"
            ),
            "metrics": ["rmse", "mae"],
            "seed": 17,
            "leakage_justification": TARGET_JUSTIFICATION,
        },
    )
    report = drawn["contract_report"]
    n.fact("contract satisfied", report["ok"])
    n.fact("mapping MAYA resolved", report["mapping"])
    n.fact("leakage certificate", drawn["leakage_certificate"]["status"])
    n.fact("escrowed holdout", f"{drawn['holdout_rows'] or 0:,} rows")

    n.step("What the warrant hands over, and how the two regimes divide it")
    warrant = cast.devi.warrant(drawn["id"])
    with warrant.data() as ds:
        frame = ds.frame
        n.fact("rows", f"{len(frame):,}")
        n.fact("partitions", ", ".join(sorted(frame["_split"].unique())))
        usable = realised_fraction(frame)
        dropped = len(frame) - len(usable)
        n.fact(
            "rows where the draw fraction is defined",
            f"{len(usable):,} of {len(frame):,}"
            + (f"; {dropped:,} dropped for having almost no undrawn line" if dropped else ""),
        )
        for regime, label in ((1, "draw period"), (0, "repayment")):
            rows = usable[usable["inDraw"] == regime]
            n.fact(
                f"{label}",
                f"{len(rows):,} rows, mean realised fraction {rows['fraction'].mean():+.3f}",
            )
    n.say(
        "One is positive and one is negative. That is the whole reason the composite routes "
        "between two members instead of adding an interaction term to one."
    )
    n.fact("seeds", "one per member, derived from the warrant's seed (§9.5)")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
