"""
Step 5 — one warrant for three fits and two judgements.

    .venv/bin/python case_studies/06-ifrs9-expected-credit-loss/get_training_warrant.py

The warrant covers the whole composite: three members to fit, and the combiner's two
parameters to have approved. Its target is the money actually lost over the following
twelve months, which is why its leakage certificate needs the same written exception the
other studies' do.

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
)

TITLE = "Case study 6, step 5 — one warrant over the whole allowance"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved

    cast = Cast(maya)
    n.step("Drawn without an explanation first")
    naive = cast.devi.training.create(
        NS, "ecl_fit_naive", COMPOSITE_REF, PIN_REF, spec={"target": TARGET}
    )
    certificate = naive["leakage_certificate"]
    n.fact("rows examined", f"{certificate['rows_examined']:,}")
    n.fact("violations", f"{certificate['violations']:,}")
    try:
        cast.devi.training.transition(naive["id"], "submit")
    except NotApproved as exc:
        n.refused("submitting a warrant whose leakage certificate was refused", exc)

    n.step("And again, with the exception written down")
    drawn = cast.devi.training.create(
        NS,
        WARRANT,
        COMPOSITE_REF,
        PIN_REF,
        spec={
            "target": TARGET,
            "objective": (
                "the IFRS 9 expected credit loss allowance on the secured revolving book, "
                "stages 1 and 2, for the 2025 interim accounts"
            ),
            "metrics": ["rmse", "mae"],
            "seed": 23,
            "leakage_justification": TARGET_JUSTIFICATION,
        },
    )
    n.fact("certificate", drawn["leakage_certificate"]["status"])
    report = drawn["contract_report"]
    n.fact("contract satisfied", report["ok"])
    n.fact("mapping", report["mapping"])
    n.fact("escrowed holdout", f"{drawn['holdout_rows'] or 0:,} rows")
    n.say(
        "Note what the contract check mapped and what it did not: the two combiner "
        "parameters are inputs of the composite but they are parameters, so the feature set "
        "is not asked to supply them. Somebody has to approve them instead."
    )

    n.step("What the warrant hands over")
    warrant = cast.devi.warrant(drawn["id"])
    with warrant.data() as ds:
        frame = ds.frame
        n.fact("rows", f"{len(frame):,}")
        n.fact("partitions", ", ".join(sorted(frame["_split"].unique())))
        train = frame[frame["_split"] == "train"]
        n.fact("defaults in training", f"{int(train['defaulted12'].sum()):,} of {len(train):,}")
        n.fact(
            "loss in training",
            f"{train['realisedLoss12'].sum():,.0f} over {int((train['realisedLoss12'] > 0).sum()):,} rows",
        )


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
