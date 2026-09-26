"""
Step 3 — reconciling version 1 against the regulator's reference, and the finding.

    .venv/bin/python case_studies/09-basel-irb-capital/reconcile_v1.py

A model with nothing to fit is proved by reconciliation. The warrant makes the reference
the target; MAYA evaluates the approved formula on the escrowed holdout and compares, blind.
The difference is not rounding. On the training rows the desk *can* see, the misses sit
exactly where the regulation floors and caps the maturity -- so the validator raises a
finding against version 1, and it gets an owner and a due date.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import (
    EXTRA_USERS,
    LEAKAGE_JUSTIFICATION,
    FORMULA_V1,
    MODEL,
    NS,
    PIN_REF,
    ROLES,
    WARRANT_V1,
    Cast,
)  # noqa: E402

TITLE = "Case study 9, step 3 — reconciliation, and a finding"


def main(maya: Any, n: Narrator) -> None:
    import numpy as np

    from maya.formula.evaluate import evaluate
    from maya.formula.parse import parse_model

    cast = Cast(maya)
    n.step("Drawing the warrant: the reference capital is the target")
    drawn = cast.devi.training.create(
        NS,
        WARRANT_V1,
        f"{NS}/{MODEL}@v1",
        PIN_REF,
        spec={
            "target": "reference_k",
            "objective": "reconcile K with the reference calculator",
            "leakage_justification": LEAKAGE_JUSTIFICATION,
        },
    )
    n.fact("contract", "satisfied" if drawn["contract_report"]["ok"] else drawn["contract_report"])
    n.fact("leakage certificate", drawn["leakage_certificate"]["status"])

    n.step("Blind reconciliation on the escrowed holdout")
    scored = cast.devi.warrant(drawn["id"]).score_holdout()
    n.fact("obligors scored", scored["metrics"]["rows"])
    n.fact("RMSE of K", f"{scored['metrics']['rmse']:.5f}")
    n.fact("MAE of K", f"{scored['metrics']['mae']:.5f}")

    n.step("Where the misses are, on the training rows the desk can see")
    with cast.devi.warrant(drawn["id"]).data() as ds:
        frame = ds.frame
    ir = parse_model(FORMULA_V1, roles=ROLES)
    k = evaluate(ir, {c: frame[c].to_numpy(float) for c in ("pd", "lgd", "M")}, {})["k"]
    miss = np.abs(k - frame["reference_k"].to_numpy(float))
    inside = frame["M"].between(1, 5).to_numpy()
    n.fact("largest miss, maturity inside 1–5y", f"{miss[inside].max():.2e}")
    n.fact("largest miss, maturity outside", f"{miss[~inside].max():.4f} of EAD")
    n.say("Inside the band the formula agrees to the last digit; outside it, it does not.")

    n.step("The validator raises a finding against version 1")
    finding = cast.lara.governance.raise_finding(
        f"{NS}/{MODEL}",
        "Effective maturity not floored at 1 year or capped at 5 (CRE31.46)",
        "high",
        version_no=1,
        source="validation",
        detail=f"Reconciliation RMSE {scored['metrics']['rmse']:.5f}; every miss is outside 1-5 years.",
    )
    n.fact("finding", f"{finding['severity']}, owner {finding['owner']}, due {finding['due_date']}")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
