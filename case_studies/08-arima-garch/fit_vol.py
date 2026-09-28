"""
Step 4 — the volatility model: a likelihood fit, a boundary refused, a blind score.

    .venv/bin/python case_studies/08-arima-garch/fit_vol.py

GARCH is fitted by maximum likelihood on the training dates, one parameter set pooled over
the three indices, each recursed on its own. A persistence of one or more is refused by the
model's stationarity constraint even though alpha and beta each sit inside [0, 1].

The escrowed holdout is the last fifth of the calendar, in date order, which is the only
order a recursion can run in. MAYA scores it blind: it runs the validated artifact in the
sandbox on rows the developer never saw.

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
    NS,
    PIN_REF,
    TARGET_JUSTIFICATION_VOL,
    TRUE_GARCH,
    VOL_MODEL,
    VOL_WARRANT,
    Cast,
    constant_variance_loglik,
    fit_garch,
)

TITLE = "Case study 8, step 4 — the volatility model, fitted, refused at the boundary, scored blind"
SPLIT = {"train": 0.7, "validation": 0.1, "test": 0.2}


def main(maya: Any, n: Narrator) -> None:
    import math

    from maya.core.errors import ValidationFailed

    cast = Cast(maya)
    n.step("A time-ordered warrant whose target is the squared return")
    drawn = cast.devi.training.create(
        NS,
        VOL_WARRANT,
        f"{NS}/{VOL_MODEL}@v1",
        PIN_REF,
        spec={
            "target": "retSq",
            "seed": 8,
            "shape": "time_series",
            "split": SPLIT,
            "leakage_justification": TARGET_JUSTIFICATION_VOL,
        },
    )
    n.fact("leakage certificate", drawn["leakage_certificate"]["status"])
    n.fact("escrowed holdout", f"{drawn['holdout_rows']:,} rows, the last dates")
    warrant = cast.devi.warrant(drawn["id"])
    with warrant.data() as ds:
        frame = ds.frame
        checksum = ds.checksum
    train = frame[frame["_split"] == "train"]
    shocks = [
        (g["ret"] - g["ret"].mean()).to_numpy(float) for _, g in train.groupby("index", sort=True)
    ]
    n.fact("training days", f"{len(train):,} rows over {len(shocks)} indices")

    n.step("Maximum likelihood, pooled over the indices")
    values, loglik = fit_garch(shocks)
    for k in ("omega", "alpha", "beta"):
        fmt = "{:.3e}" if k == "omega" else "{:.4f}"
        n.fact(k, f"{fmt.format(values[k])}   (the process: {fmt.format(TRUE_GARCH[k])})")
    persistence = values["alpha"] + values["beta"]
    n.fact(
        "persistence alpha+beta",
        f"{persistence:.4f}; a shock halves in {math.log(0.5) / math.log(persistence):.0f} days",
    )
    lr = 2 * (loglik - constant_variance_loglik(shocks))
    n.fact(
        "against one constant variance",
        f"likelihood-ratio statistic {lr:,.0f} on 2 degrees of freedom",
    )

    n.step("A persistence of one, fine one coefficient at a time")
    boundary = {"omega": values["omega"], "alpha": 0.15, "beta": 0.90}
    try:
        warrant.upload_parameters(boundary, data_checksum=checksum)
        raise SystemExit(
            "MAYA accepted alpha + beta = 1.05; the stationarity constraint did not bite"
        )
    except ValidationFailed as exc:
        n.fact("alpha=0.15, beta=0.90", "refused")
        n.say(f"  {exc.message[:220]}…")

    n.step("The fitted set: approved, scored blind in the sandbox, sealed")
    ps = warrant.upload_parameters(values, data_checksum=checksum)
    cast.devi.training.parameter_transition(ps["id"], "submit")
    cast.mgr.training.parameter_transition(ps["id"], "approve")
    score = warrant.score_holdout(parameter_set_id=ps["id"])
    m = score["metrics"]
    n.fact("scored in", score.get("scored_in") or m.get("scored_in") or "sandbox")
    n.fact("holdout RMSE of the variance", f"{m['rmse']:.3e} on {m['rows']:,} rows")
    n.say("The error is measured against the squared return, a one-observation estimate of the")
    n.say("day's variance, so it is large by nature. What matters is that it was measured at all:")
    n.say("MAYA cannot read this model, and it still ran it on data nobody had seen.")
    cast.devi.training.transition(drawn["id"], "submit")
    cast.mgr.training.transition(drawn["id"], "approve")
    cast.mgr.training.seal(drawn["id"])
    n.fact("warrant", "sealed")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
