"""
Step 5 — a warrant that fits nothing, and a constant that still needs a signature.

    .venv/bin/python case_studies/02-mortgage-cashflow/get_training_warrant.py

There is nothing to learn here: every quantity in a level-payment cashflow is
contractual. MAYA still requires a warrant and an approved parameter set, and that is the
right requirement — the servicing fee in production should be a figure somebody signed
for, taken from clause 7.2 of the servicing agreement, and a change to the agreement
should be a new parameter set and a new approval rather than an edit.

The warrant is then used for something a fitted model cannot do: the model's output is
scored blind against what the servicer actually remitted. The residual is not expected to
be zero, and its size is the accuracy statement.

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
    NS,
    PIN_REF,
    SERVICING_FEE,
    TARGET_JUSTIFICATION,
    WARRANT,
    Cast,
)

TITLE = "Case study 2, step 5 — a warrant with no fit, and blind reconciliation"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("Drawing the warrant: the benchmark is the target, the four tape columns the inputs")
    drawn = cast.devi.training.create(
        NS,
        WARRANT,
        MODEL_REF,
        PIN_REF,
        spec={
            "target": "remitted",
            "objective": "reconcile scheduled cash against the servicer's remittance",
            "metrics": ["rmse", "mae"],
            "leakage_justification": TARGET_JUSTIFICATION,
        },
    )
    n.fact("contract satisfied", drawn["contract_report"]["ok"])
    n.fact("leakage certificate", drawn["leakage_certificate"]["status"])
    warrant = cast.devi.warrant(drawn["id"])
    with warrant.data() as ds:
        checksum = ds.checksum
        n.fact("rows the warrant covers", f"{ds.table.num_rows:,}")
        n.fact("data checksum", f"{checksum[:16]}…")

    n.step("Registering the contractual constant as a parameter set")
    n.say("Nothing is fitted. The figure comes from the servicing agreement, and is quoted.")
    registered = warrant.upload_parameters(
        {"fee": SERVICING_FEE},
        data_checksum=checksum,
        metrics={"source": "servicing agreement clause 7.2, 25 basis points per annum"},
    )
    n.fact("fee", f"{SERVICING_FEE} ({SERVICING_FEE * 10_000:.0f} basis points a year)")
    n.fact("tied to the warrant's data", registered["verified_data"])
    cast.devi.training.parameter_transition(registered["id"], "submit")
    cast.mgr.training.parameter_transition(registered["id"], "approve")
    n.fact("parameter set", f"{registered['id'][:8]}… approved by mgr")

    n.step("Blind reconciliation against what the servicer actually remitted")
    scored = warrant.score_holdout(parameter_set_id=registered["id"])
    n.fact("loan-months scored", f"{scored['metrics']['rows']:,}")
    n.fact("RMSE per loan-month", f"{scored['metrics']['rmse']:,.2f}")
    n.fact("MAE per loan-month", f"{scored['metrics']['mae']:,.2f}")
    n.say(
        "The median loan reconciles to pennies; the RMSE is dominated by the small share "
        "of loan-months with a partial prepayment or a late payment, neither of which this "
        "model claims to predict. That is the Known Weaknesses section, measured."
    )

    n.step("Sealing it")
    cast.devi.training.transition(drawn["id"], "submit")
    cast.mgr.training.transition(drawn["id"], "approve")
    n.fact("sealed at", cast.mgr.training.seal(drawn["id"])["sealed_at"])


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
