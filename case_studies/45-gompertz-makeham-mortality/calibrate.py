"""
Step 2 — calibrating a law that is non-linear in two of its four parameters.

    .venv/bin/python case_studies/45-gompertz-makeham-mortality/calibrate.py

For fixed gamma and lambda the law is linear in A and B, so the fit is a grid over the two
and ordinary least squares inside it -- a dozen lines of numpy, because the study is about
the governance of a calibration, not the optimiser. The fit is tied to the warrant's data by
checksum, approved, and scored blind on the escrowed holdout.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import EXTRA_USERS, LEAKAGE_JUSTIFICATION, MODEL, NS, PIN_REF, WARRANT, Cast  # noqa: E402

TITLE = "Case study 45, step 2 — the calibration"


def fit(frame: Any) -> dict[str, float]:
    import numpy as np

    age, t, rate = (frame[c].to_numpy(float) for c in ("age", "t", "rate"))
    best = None
    for gamma in np.arange(0.080, 0.130, 0.0005):
        for lam in np.arange(0.0, 0.035, 0.0005):
            design = np.column_stack([np.exp(-lam * t), np.exp(gamma * age - lam * t)])
            coef, *_ = np.linalg.lstsq(design, rate, rcond=None)
            err = float(np.sum((design @ coef - rate) ** 2))
            if best is None or err < best[0]:
                best = (err, coef, gamma, lam)
    _, (a, b), gamma, lam = best
    return {
        "A": float(a),
        "B": float(b),
        "gamma": round(float(gamma), 4),
        "lambda": round(float(lam), 4),
    }


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("The calibration warrant: observed death rates are the target")
    drawn = cast.devi.training.create(
        NS,
        WARRANT,
        f"{NS}/{MODEL}@v1",
        PIN_REF,
        spec={"target": "rate", "seed": 45, "leakage_justification": LEAKAGE_JUSTIFICATION},
    )
    warrant = cast.devi.warrant(drawn["id"])
    with warrant.data() as ds:
        train = ds.frame[ds.frame["_split"] == "train"]
        values = fit(train)
        checksum = ds.checksum
    n.fact("training cells", f"{len(train):,}")
    n.fact("A (Makeham, age-independent)", f"{values['A']:.6f}")
    n.fact("B", f"{values['B']:.3e}")
    n.fact(
        "gamma (Gompertz slope)",
        f"{values['gamma']:.4f}: mortality doubles every {0.6931 / values['gamma']:.1f} years of age",
    )
    n.fact(
        "lambda (improvement)",
        f"{values['lambda']:.4f}: {values['lambda']:.1%} lower each calendar year",
    )

    n.step("Approved, scored blind, sealed")
    ps = warrant.upload_parameters(values, data_checksum=checksum)
    cast.devi.training.parameter_transition(ps["id"], "submit")
    cast.mgr.training.parameter_transition(ps["id"], "approve")
    score = warrant.score_holdout(parameter_set_id=ps["id"])
    n.fact(
        "blind RMSE of the death rate",
        f"{score['metrics']['rmse']:.5f} on {score['metrics']['rows']} cells",
    )
    cast.devi.training.transition(drawn["id"], "submit")
    cast.mgr.training.transition(drawn["id"], "approve")
    cast.mgr.training.seal(drawn["id"])


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
