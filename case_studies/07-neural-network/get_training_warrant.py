"""
Step 4 — a training warrant: the contract, the leakage certificate, and the seed.

    .venv/bin/python case_studies/07-neural-network/get_training_warrant.py

A training warrant is MAYA's record of one attempt to fit one model version to one pinned
data set: what data, what target, what split, what seed, who drew it. Every one of those
is exactly as strong for a black box as for a scorecard, and this step is where that
becomes visible — the contract is checked against the pin *before* anything is fitted, and
the seed the fit must use is written down before anybody runs it.

Drawn naively the leakage certificate refuses, and it refuses every row, which is correct:
the panel's knowledge time per row is the latest of its members', and the confirmed-fraud
label is known 45 days after the day it describes. The wrong response is to widen the rule.
The right one, and the one MAYA forces, is to write down why this exception is sound — and
for an unreadable model that written answer is the whole of the defence, because a leaked
driver could never be found afterwards by reading the coefficients.

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
    HYPERPARAMETERS,
    MODEL_REF,
    NAIVE_WARRANT,
    NS,
    PIN_REF,
    SEED,
    TARGET,
    TARGET_JUSTIFICATION,
    WARRANT,
    Cast,
)

TITLE = "Case study 7, step 4 — the warrant, the certificate, and the declared seed"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import ContractMismatch, NotApproved

    cast = Cast(maya)
    n.step("The input contract is checked against the pin before anything is fitted")
    try:
        cast.devi.training.create(
            NS, "fraud_mlp_wrong_target", MODEL_REF, PIN_REF, spec={"target": "fraud"}
        )
    except ContractMismatch as exc:
        n.refused("a warrant naming a target the panel does not carry", exc)
    n.say("An opaque model still declares its inputs, so this check is unchanged: MAYA knows")
    n.say("the six attributes the network needs and whether this pin exposes them.")

    n.step("Drawing one naively: target named, nothing said about it")
    naive = cast.devi.training.create(
        NS, NAIVE_WARRANT, MODEL_REF, PIN_REF, spec={"target": TARGET}
    )
    certificate = naive["leakage_certificate"]
    n.fact("rule", certificate["rule"])
    n.fact("rows examined", f"{certificate['rows_examined']:,}")
    n.fact("violating rows", f"{certificate['violations']:,}")
    n.fact("status", certificate["status"])
    try:
        cast.devi.training.transition(naive["id"], "submit")
    except NotApproved as exc:
        n.refused("submitting a warrant whose leakage certificate was refused", exc)

    n.step("Drawing it again, with the exception written down")
    drawn = cast.devi.training.create(
        NS,
        WARRANT,
        MODEL_REF,
        PIN_REF,
        spec={
            "target": TARGET,
            "objective": "rank card-days for a fixed-capacity fraud review queue",
            "metrics": ["auc"],
            "seed": SEED,
            "environment": {"python": "3.13", "libraries": ["numpy"]},
            "leakage_justification": TARGET_JUSTIFICATION,
        },
    )
    n.fact("status", drawn["leakage_certificate"]["status"])
    for exception in drawn["leakage_certificate"]["exceptions"]:
        n.say(f"exception: {exception['rule']} on {exception.get('rows', 0):,} row(s)")
        n.say(f"  because: {exception['justification']}")

    n.step("What the warrant fixes before the fit")
    report = drawn["contract_report"]
    n.fact("contract satisfied", report["ok"])
    n.fact("mapping MAYA resolved", report["mapping"])
    n.fact("split", drawn["spec"]["split"])
    n.fact("seed", f"{drawn['spec']['seed']} — the number the 209 weights come from")
    n.fact("stopping rule", HYPERPARAMETERS["stopping_rule"])
    n.fact(
        "holdout",
        f"{drawn['spec']['holdout']}, {drawn['holdout_rows'] or 0:,} rows, "
        f"hash {(drawn['holdout_hash'] or '')[:16]}…",
    )
    n.say("The holdout is escrowed and hashed exactly as in case study 1. Step 5 shows what")
    n.say("that turns out to be worth for a model MAYA cannot evaluate.")
    n.fact("warrant", f"{NS}/{WARRANT} ({drawn['state']})")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
