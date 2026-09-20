"""
Step 4 — a training warrant, and the refusal that matters most.

    .venv/bin/python case_studies/01-retail-credit-pd-scorecard/get_training_warrant.py

A training warrant is MAYA's record of one attempt to fit one model version to one
pinned data set: what data, what target, what split, what seed, who drew it. Drawing one
produces two pieces of evidence at once — the contract report, and the leakage
certificate.

Drawn naively the certificate *refuses*, and it refuses every row, which is correct: the
panel's knowledge time per row is the latest of its members', and the twelve-month
default flag is known a year after the month it describes. The warrant cannot even be
submitted. The wrong response is to widen the rule; the right one, and the one MAYA
forces, is to write down why this exception is sound.

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
    MODEL_REF,
    NAIVE_WARRANT,
    NS,
    PIN_REF,
    TARGET,
    TARGET_JUSTIFICATION,
    WARRANT,
    Cast,
)

TITLE = "Case study 1, step 4 — the warrant, and the leakage certificate"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved

    cast = Cast(maya)
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
            "objective": "twelve-month PD for IFRS 9 stage allocation",
            "metrics": ["rmse", "mae"],
            "seed": 11,
            "leakage_justification": TARGET_JUSTIFICATION,
        },
    )
    n.fact("status", drawn["leakage_certificate"]["status"])
    for exception in drawn["leakage_certificate"]["exceptions"]:
        n.say(f"exception: {exception['rule']} on {exception.get('rows', 0):,} row(s)")
        n.say(f"  because: {exception['justification']}")

    n.step("And the contract, checked before anyone fits anything")
    report = drawn["contract_report"]
    n.fact("contract satisfied", report["ok"])
    n.fact("mapping MAYA resolved", report["mapping"])
    n.fact("split", drawn["spec"]["split"])
    n.fact("holdout", f"{drawn['spec']['holdout']}, {drawn['holdout_rows'] or 0:,} rows escrowed")
    n.fact("warrant", f"{NS}/{WARRANT} ({drawn['state']})")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
