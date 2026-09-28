"""
Step 3 — the mean model, fitted on the past and scored on the last dates.

    .venv/bin/python case_studies/08-arima-garch/fit_mean.py

The warrant is drawn with ``shape: time_series``: the earliest dates train, the next
validate, and the last fifth of the calendar is the escrowed test. A random split of a
series trains on the future and tests on the past, which is the look-ahead a leakage
certificate exists to stop, arrived at by a different door.

The fit is ordinary least squares on the two lags. Before it is uploaded, a parameter set
that looks harmless one coefficient at a time is refused by the joint constraint.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
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
    MEAN_MODEL,
    MEAN_WARRANT,
    NS,
    PIN_REF,
    TARGET_JUSTIFICATION_MEAN,
    TRUE_AR,
    Cast,
    fit_ar2,
)

TITLE = "Case study 8, step 3 — the mean model, fitted on the past, scored on the last dates"
SPLIT = {"train": 0.7, "validation": 0.1, "test": 0.2}


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import ValidationFailed

    cast = Cast(maya)
    n.step("A time-ordered training warrant")
    drawn = cast.devi.training.create(
        NS,
        MEAN_WARRANT,
        f"{NS}/{MEAN_MODEL}@v1",
        PIN_REF,
        spec={
            "target": "ret",
            "seed": 8,
            "shape": "time_series",
            "split": SPLIT,
            "leakage_justification": TARGET_JUSTIFICATION_MEAN,
        },
    )
    n.fact("leakage certificate", drawn["leakage_certificate"]["status"])
    n.fact("escrowed holdout", f"{drawn['holdout_rows']:,} rows")
    warrant = cast.devi.warrant(drawn["id"])
    with warrant.data() as ds:
        frame = ds.frame
        checksum = ds.checksum
    train = frame[frame["_split"] == "train"].dropna(subset=["retLag1", "retLag2", "ret"])
    seen = frame["date"].astype(str)
    n.fact("dates downloaded", f"{seen.min()} to {seen.max()} (train and validation)")
    n.say("Every test date is later than every date the developer can see: the holdout is the")
    n.say("future of the training data, which is what a forecast is asked to predict.")

    n.step("Least squares on the two lags")
    beta, r2 = fit_ar2(
        train["retLag1"].to_numpy(float),
        train["retLag2"].to_numpy(float),
        train["ret"].to_numpy(float),
    )
    values = {"c": float(beta[0]), "phi1": float(beta[1]), "phi2": float(beta[2])}
    for k in ("c", "phi1", "phi2"):
        n.fact(k, f"{values[k]:+.5f}   (the process: {TRUE_AR[k]:+.5f})")
    n.fact("R squared", f"{r2:.4f}: daily returns are barely predictable, as they should be")

    n.step("A parameter set that is fine one coefficient at a time")
    explosive = {"c": values["c"], "phi1": 0.75, "phi2": 0.35}
    try:
        warrant.upload_parameters(explosive, data_checksum=checksum)
        raise SystemExit("MAYA accepted an explosive AR(2); the joint constraint did not bite")
    except ValidationFailed as exc:
        n.fact("phi1=0.75, phi2=0.35", "refused")
        n.say(f"  {exc.message[:220]}…")

    n.step("The fitted set: approved, scored blind on the last dates, sealed")
    ps = warrant.upload_parameters(values, data_checksum=checksum)
    cast.devi.training.parameter_transition(ps["id"], "submit")
    cast.mgr.training.parameter_transition(ps["id"], "approve")
    score = warrant.score_holdout(parameter_set_id=ps["id"])
    scale = float(train["ret"].std())
    n.fact("holdout RMSE", f"{score['metrics']['rmse']:.5f} on {score['metrics']['rows']:,} rows")
    n.fact("return volatility", f"{scale:.5f}: the forecast error is almost all of it")
    cast.devi.training.transition(drawn["id"], "submit")
    cast.mgr.training.transition(drawn["id"], "approve")
    cast.mgr.training.seal(drawn["id"])
    n.fact("warrant", "sealed")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
