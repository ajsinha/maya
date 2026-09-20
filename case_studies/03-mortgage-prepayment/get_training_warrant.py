"""
Step 4 — the warrant, and the exception a forward-looking target needs.

    .venv/bin/python case_studies/03-mortgage-prepayment/get_training_warrant.py

Whether a loan paid off in a month is known a month later, when the remittance settles, so
every row of this panel breaks MAYA's leakage rule by construction. As in case study 1 the
answer is not to widen the rule but to state why this exception is sound — and here there
is a second thing worth stating, which the specification's Known Weaknesses section says
and the warrant's objective repeats: the incentive coefficient is identified only by the
rate cycle inside the fitting window.

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
    TARGET,
    TARGET_JUSTIFICATION,
    WARRANT,
    Cast,
)

TITLE = "Case study 3, step 4 — the warrant"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved

    cast = Cast(maya)
    n.step("Drawn without an explanation first")
    naive = cast.devi.training.create(
        NS, "smm_fit_naive", MODEL_REF, PIN_REF, spec={"target": TARGET}
    )
    certificate = naive["leakage_certificate"]
    n.fact("rows examined", f"{certificate['rows_examined']:,}")
    n.fact("violations", f"{certificate['violations']:,}")
    n.fact("status", certificate["status"])
    try:
        cast.devi.training.transition(naive["id"], "submit")
    except NotApproved as exc:
        n.refused("submitting a warrant whose leakage certificate was refused", exc)

    n.step("And again, with the exception written where a reviewer will read it")
    drawn = cast.devi.training.create(
        NS,
        WARRANT,
        MODEL_REF,
        PIN_REF,
        spec={
            "target": TARGET,
            "objective": (
                "monthly voluntary prepayment hazard for pool valuation; the incentive "
                "coefficient is identified only by the down-and-up rate cycle in this window"
            ),
            "metrics": ["rmse", "mae"],
            "seed": 3,
            "leakage_justification": TARGET_JUSTIFICATION,
        },
    )
    n.fact("status", drawn["leakage_certificate"]["status"])
    n.fact("contract satisfied", drawn["contract_report"]["ok"])
    n.fact("mapping", drawn["contract_report"]["mapping"])
    n.fact("split", drawn["spec"]["split"])
    n.fact("escrowed holdout", f"{drawn['holdout_rows'] or 0:,} rows")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
