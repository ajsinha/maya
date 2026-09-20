"""
Step 4 — version 1's training warrant, and a leakage certificate with no easy answer.

    .venv/bin/python case_studies/10-factor-models/get_training_warrant.py

Case study 1's leakage exception was the comfortable kind: the *target* was a
forward-looking outcome, every driver was known at the observation date, and the written
exception could honestly say "the exception covers the target column alone".

This one is not comfortable. The drivers themselves — the published factor returns — are
knowable up to thirty-four days after the day whose returns they explain, because a factor
library is rebuilt from the cross-section after the month has closed. Every row of the
panel violates MAYA's rule, and it violates it *on the inputs*.

There is exactly one honest defence, and the warrant has to carry it in writing: this is
an attribution model and never a forecast. It decomposes a return that has already
happened. The moment somebody uses it to predict one, the exception becomes a lie — which
is why the claim is made twice, here and in the execution warrant that refuses to run the
model in production at all.

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
    EXTRA_USERS,
    LEAKAGE_JUSTIFICATION,
    MODEL_V1,
    NAIVE_WARRANT,
    NS,
    PIN_REF,
    SEED,
    SPLIT,
    TARGET,
    WARRANT_V1,
    Cast,
)

TITLE = "Case study 10, step 4 — the warrant, and a leakage exception on the drivers"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved

    cast = Cast(maya)
    n.step("Drawing one naively: target named, nothing said about the publication lag")
    naive = cast.devi.training.create(
        NS, NAIVE_WARRANT, MODEL_V1, PIN_REF, spec={"target": TARGET, "seed": SEED}
    )
    certificate = naive["leakage_certificate"]
    n.fact("rule", certificate["rule"])
    n.fact("rows examined", f"{certificate['rows_examined']:,}")
    n.fact("violating rows", f"{certificate['violations']:,}")
    n.fact("status", certificate["status"])
    if certificate["examples"]:
        first = certificate["examples"][0]
        n.fact(
            "first example",
            f"{first['date']} {first['stock']}, knowable {first['_knowledge_time']}",
        )
    try:
        cast.devi.training.transition(naive["id"], "submit")
    except NotApproved as exc:
        n.refused("submitting a warrant whose leakage certificate was refused", exc)

    n.step("Drawing it again, with the exception written down and signed for")
    drawn = cast.devi.training.create(
        NS,
        WARRANT_V1,
        MODEL_V1,
        PIN_REF,
        spec={
            "target": TARGET,
            "objective": "attribute realised daily excess return to the market factor",
            "metrics": ["rmse", "mae"],
            "seed": SEED,
            "split": SPLIT,
            "leakage_justification": LEAKAGE_JUSTIFICATION,
        },
    )
    n.fact("status", drawn["leakage_certificate"]["status"])
    for exception in drawn["leakage_certificate"]["exceptions"]:
        n.say(f"exception: {exception['rule']} on {exception.get('rows', 0):,} row(s)")
        n.say(f"  because: {exception['justification']}")

    n.step("The contract, checked before anybody fits anything")
    report = drawn["contract_report"]
    n.fact("contract satisfied", report["ok"])
    n.fact("mapping MAYA resolved", report["mapping"])
    n.fact("split", drawn["spec"]["split"])
    n.fact("seed", drawn["spec"]["seed"])
    n.fact("holdout rows escrowed", f"{drawn['holdout_rows'] or 0:,}")
    n.fact("holdout content hash", f"{(drawn['holdout_hash'] or '')[:24]}…")
    n.say("Remember that hash. Version 2's warrant in step 7 reports the same one, which")
    n.say("is what makes the comparison between the two versions a measurement.")
    n.fact("warrant", f"{NS}/{WARRANT_V1} ({drawn['state']})")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
