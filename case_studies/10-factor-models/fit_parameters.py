"""
Step 5 — fit version 1, and find out where the return it cannot see went.

    .venv/bin/python case_studies/10-factor-models/fit_parameters.py

Ordinary least squares by the normal equations, on the training partition only. Two
coefficients. What makes the step worth watching is not the fit but three things around it:

* **Two standard errors per coefficient.** The classical one, and one clustered by date.
  Thirty stocks share one day's factor realisation, so the residuals of a day are not
  independent, and the gap between the two numbers is a measurement of how much common
  variation the model has left in its residual. For version 1 the gap is large. In step 7,
  for version 2, it very nearly closes — which is the cleanest diagnostic in the study.
* **The checksum.** The same coefficients are uploaded twice, once quoting the wrong data
  checksum and once the right one. The first is flagged ``unverified_data`` and cannot be
  approved.
* **A benchmark, scored blind by MAYA.** A root mean squared error of 0.0145 on daily
  returns means nothing on its own, so MAYA is asked to score the escrowed holdout twice:
  once with the fitted coefficients, and once with alpha and beta both set to zero, which
  is a model that predicts no excess return for anybody. Both attempts are counted on the
  warrant.

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
    DRIVERS_V1,
    EXTRA_USERS,
    NS,
    TARGET,
    TRADING_DAYS,
    TRUE,
    WARRANT_V1,
    WEIGHTS_V1,
    Cast,
    coefficient_table,
    design_matrix,
    find_warrant,
    fit_ols,
    r_squared,
)

TITLE = "Case study 10, step 5 — version 1's fit, and an alpha that is not skill"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    found = find_warrant(cast.devi, WARRANT_V1)
    warrant = cast.devi.warrant(found["id"])

    n.step("Opening the warrant's data: training and validation, and no more")
    with warrant.data() as ds:
        frame = ds.frame
        checksum = ds.checksum
        n.fact("rows handed over", f"{len(frame):,}")
        n.fact("partitions present", ", ".join(sorted(frame["_split"].unique())))
        n.fact("target among the inputs", ds.target in ds.X.columns)
        n.fact("data checksum", f"{checksum[:16]}…")
        train = frame[frame["_split"] == "train"]
        validation = frame[frame["_split"] == "validation"]

        n.step("Fitting by ordinary least squares, on the training partition only")
        design = design_matrix(train, DRIVERS_V1)
        fit = fit_ols(design, train[TARGET].astype(float).to_numpy(), train["date"])
        values = dict(zip(WEIGHTS_V1, (round(float(b), 8) for b in fit["beta"])))
        r2_validation = r_squared(
            validation[TARGET].astype(float).to_numpy(),
            design_matrix(validation, DRIVERS_V1) @ fit["beta"],
        )
    n.fact("training rows / dates", f"{fit['n']:,} / {fit['clusters']}")
    for line in coefficient_table(WEIGHTS_V1, fit, TRUE):
        n.say(line)
    n.fact("R² train / validation", f"{fit['r2']:.4f} / {r2_validation:.4f}")
    n.fact("residual sd (daily)", f"{fit['resid_sd']:.6f}")

    alpha = float(fit["beta"][0])
    n.step("What alpha is, on a universe whose tilt the model cannot see")
    n.fact("alpha, daily", f"{alpha:+.6f}")
    n.fact("alpha, annualised at 252 days", f"{alpha * TRADING_DAYS:+.2%}")
    n.fact("t on alpha, classical", f"{alpha / float(fit['se'][0]):+.2f}")
    n.fact("t on alpha, clustered by date", f"{alpha / float(fit['se_clustered'][0]):+.2f}")
    n.say("The process that generated these returns gave every stock an alpha of exactly")
    n.say("zero. This alpha is the size and value premium the model has no term for, and")
    n.say("the clustered t is the honest one: the residual still holds a common factor,")
    n.say("which is precisely what a date-clustered standard error is sensitive to.")
    n.fact(
        "beta bias against the generating value",
        f"{float(fit['beta'][1]) - TRUE['beta']:+.4f} (an omitted factor moves the slope too)",
    )

    metrics = {
        "r2_train": round(fit["r2"], 6),
        "r2_validation": round(r2_validation, 6),
        "alpha_t_clustered": round(alpha / float(fit["se_clustered"][0]), 4),
    }
    approve_and_score(cast, found, warrant, values, checksum, metrics, n)


def approve_and_score(
    cast: Cast,
    found: dict[str, Any],
    warrant: Any,
    values: dict[str, float],
    checksum: str,
    metrics: dict[str, float],
    n: Narrator,
) -> None:
    """The three controls around the fit: the checksum, blind scoring, and the seal."""
    from maya.core.errors import NotApproved

    n.step("Uploading the fit quoting the wrong data checksum")
    untied = warrant.upload_parameters(values, data_checksum="0" * 64)
    n.fact("flag", untied["flag"])
    cast.devi.training.parameter_transition(untied["id"], "submit")
    try:
        cast.mgr.training.parameter_transition(untied["id"], "approve")
    except NotApproved as exc:
        n.refused("approving parameters that cannot prove which data produced them", exc)

    n.step("Uploading it quoting the right one, and approving that")
    tied = warrant.upload_parameters(values, data_checksum=checksum, metrics=metrics)
    n.fact("verified against a download MAYA issued", tied["verified_data"])
    cast.devi.training.parameter_transition(tied["id"], "submit")
    cast.mgr.training.parameter_transition(tied["id"], "approve")
    n.fact("parameter set", f"{tied['id'][:8]}… approved by mgr, bound to {NS}/… v1")

    n.step("Blind scoring against the escrowed holdout, and against a model that says nothing")
    scored = warrant.score_holdout(parameter_set_id=tied["id"])
    n.fact("holdout rows", f"{scored['metrics']['rows']:,}")
    n.fact("RMSE, version 1", f"{scored['metrics']['rmse']:.6f}")
    n.fact("MAE, version 1", f"{scored['metrics']['mae']:.6f}")
    naive = warrant.score_holdout(values={"alpha": 0.0, "beta": 0.0})
    n.fact("RMSE, predicting zero for everybody", f"{naive['metrics']['rmse']:.6f}")
    n.fact("MAE, predicting zero for everybody", f"{naive['metrics']['mae']:.6f}")
    improvement = 1.0 - scored["metrics"]["rmse"] / naive["metrics"]["rmse"]
    n.fact("reduction in holdout RMSE", f"{improvement:.1%}")
    n.fact("holdout attempts counted on the warrant", naive["attempt"])
    n.say("MAYA evaluated the expression tree against rows the developer has never seen,")
    n.say("for both candidate parameter sets, and returned metrics only.")

    n.step("Sealing: data, certificate, exception and parameters fixed together")
    cast.devi.training.transition(found["id"], "submit")
    cast.mgr.training.transition(found["id"], "approve")
    n.fact("sealed at", cast.mgr.training.seal(found["id"])["sealed_at"])


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
