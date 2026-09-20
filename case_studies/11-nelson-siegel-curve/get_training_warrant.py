"""
Step 5 — the calibration: least squares inside a search, and a parameter nobody can pin down.

    .venv/bin/python case_studies/11-nelson-siegel-curve/get_training_warrant.py

A warrant is drawn on the pinned curve with the published zero yield as the target. The
calibration is nested, because the curve is linear in the three factors given lambda and
non-linear in lambda alone:

    for each lambda on a log-spaced grid across the declared bounds
        evaluate the two loadings, solve the three factors exactly by least squares
        record the residual
    report the whole profile, not only its minimum

What the profile shows is worth more than the minimum it contains. And the same grid run one
day at a time — which is how the desk recalibrates — puts each day's best lambda somewhere
over a range of three to one, on data generated with one lambda throughout.

Four parameter sets go up against this one warrant, and MAYA scores every one of them blind:
the curve, a flat benchmark that is the same model with its shape switched off, the
coordinates the desk's buggy implementation would have produced, and a set that satisfies
every declared bound while implying a short rate of minus six per cent.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import (  # noqa: E402
    BOUNDS,
    EXTRA_USERS,
    FACTORS,
    LAMBDA_GRID,
    LEAKAGE_NOTE,
    MODEL,
    MODEL_REF,
    NS,
    PIN_REF,
    WARRANT,
    Cast,
    daily_fit,
    design,
    desk_design,
    evaluate_curve,
    lambda_profile,
    pooled_fit,
    rmse_bp,
)

TITLE = "Case study 11, step 5 — a grid search with least squares inside it"
CURVE_SET, LEVEL_SET = "ns-window-2606", "level-only-2606"
DESK_SET, ABSURD_SET = "desk-fit-2606", "short-rate-negative"


def factor_values(beta: np.ndarray, lam: float) -> dict[str, float]:
    return {**{name: float(beta[i]) for i, name in enumerate(FACTORS)}, "lambda": float(lam)}


def register(
    warrant: Any, cast: Cast, name: str, values: dict[str, float], checksum: str, **metrics: Any
) -> str:
    """Upload one calibration, submit it, and have a model manager approve it."""
    ps = warrant.upload_parameters(values, name=name, data_checksum=checksum, metrics=metrics)
    cast.devi.training.parameter_transition(ps["id"], "submit")
    cast.mgr.training.parameter_transition(ps["id"], "approve")
    return str(ps["id"])


def interpolated(frame: pd.DataFrame) -> np.ndarray:
    """Each row's yield read off a straight line between that day's *training* pillars.

    The benchmark a desk uses when it has no model: join the dots. It is not expressible as
    a MAYA model and this study says why — it needs the other rows of the same day, and a
    model sees one row at a time.
    """
    out = np.empty(len(frame))
    for _, day in frame.groupby("date", sort=False):
        source = day[day["_split"] == "train"].sort_values("tau")
        out[day.index] = np.interp(
            day["tau"].to_numpy(), source["tau"].to_numpy(), source["y"].to_numpy()
        )
    return out


def search(
    ir: dict[str, Any], train: pd.DataFrame, day: np.ndarray, days: int, n: Narrator
) -> float:
    """The grid search, and everything the profile says about how well lambda is known."""
    tau, y = train["tau"].to_numpy(), train["y"].to_numpy()
    profile, per_day = lambda_profile(ir, tau, y, day, days)
    best = int(profile.argmin())
    n.fact("grid", f"{len(LAMBDA_GRID)} log-spaced points over the declared {BOUNDS['lambda']}")
    n.say("  lambda     RMSE (bp, factors refitted each day)")
    for k in range(0, len(LAMBDA_GRID), 4):
        mark = "  <- minimum" if k == best else ""
        n.say(f"  {LAMBDA_GRID[k]:6.3f}     {profile[k]:6.3f}{mark}")
    n.fact("best lambda", f"{LAMBDA_GRID[best]:.4f} at {profile[best]:.3f} bp")
    near = LAMBDA_GRID[profile <= profile[best] + 0.1]
    within = LAMBDA_GRID[profile <= profile[best] + 0.5]
    n.fact("within 0.1 bp of the best", f"lambda {near.min():.3f} to {near.max():.3f}")
    n.fact("within 0.5 bp of the best", f"lambda {within.min():.3f} to {within.max():.3f}")
    n.fact(
        "each day's own best lambda",
        f"{per_day.min():.3f} to {per_day.max():.3f}, median {np.median(per_day):.3f}",
    )
    n.say("The objective is sharp in the sense that matters to an optimiser and flat in the")
    n.say("sense that matters to a person: doubling lambda costs a fraction of a basis point.")
    n.say("Read day by day it wanders over a factor of three, and the curve these yields came")
    n.say("from used a single lambda on every one of those days. So the number in the")
    n.say("approved parameter set is a convention: comparing it with another desk's, or")
    n.say("watching it move week to week, would be reading noise as information.")
    return float(LAMBDA_GRID[best])


def main(maya: Any, n: Narrator) -> None:  # noqa: PLR0915 - one narrated step per paragraph
    from maya.core.errors import ValidationFailed

    cast = Cast(maya)
    n.step("Drawing the warrant: the published zero yield is the target, the maturity is not")
    drawn = cast.devi.training.create(
        NS,
        WARRANT,
        MODEL_REF,
        PIN_REF,
        spec={
            "target": "y",
            "objective": "calibrate the Nelson-Siegel factors and lambda to the GBP OIS curve",
            "metrics": ["rmse", "mae"],
        },
    )
    n.fact("contract satisfied", drawn["contract_report"]["ok"])
    n.fact("mapping", drawn["contract_report"]["mapping"])
    n.fact("leakage certificate", drawn["leakage_certificate"]["status"])
    n.fact("rows examined", f"{drawn['leakage_certificate']['rows_examined']:,}")
    n.fact("violations", drawn["leakage_certificate"]["violations"])
    n.say(LEAKAGE_NOTE)

    n.step("Opening the data the warrant licenses")
    warrant = cast.devi.warrant(drawn["id"])
    with warrant.data() as ds:
        frame, checksum = ds.frame, ds.checksum
        n.fact("rows the warrant covers", f"{ds.table.num_rows:,}")
        n.fact("data checksum", f"{checksum[:16]}…")
    frame = frame.reset_index(drop=True)
    codes, dates = pd.factorize(frame["date"])
    days = len(dates)
    is_train = (frame["_split"] == "train").to_numpy()
    is_validation = (frame["_split"] == "validation").to_numpy()
    train = frame[is_train].reset_index(drop=True)
    validation = frame[is_validation].reset_index(drop=True)
    day_train, day_validation = codes[is_train], codes[is_validation]
    n.fact("train / validation", f"{len(train):,} / {len(validation):,} pillars")
    n.fact("escrowed holdout", f"{drawn['holdout_rows']:,} pillars MAYA keeps")
    n.fact("fewest training pillars on a day", int(np.bincount(day_train, minlength=days).min()))
    n.say("A pillar, not a day: the split hashes each (date, tenor) key, so the holdout is")
    n.say("scattered through the window rather than being the last few months of it, and")
    n.say("every day keeps enough pillars to fit three factors to.")

    n.step("Asking the model for the columns of the linear problem")
    ir = cast.devi.models.get(f"{NS}/{MODEL}")["versions"][0]["formula_ir"]
    tau = train["tau"].to_numpy()
    matrix = design(ir, tau, 1.30)
    check = evaluate_curve(ir, tau, factor_values(np.array([0.04, -0.02, -0.01]), 1.30))
    n.fact("design matrix", f"{matrix.shape[0]:,} x {matrix.shape[1]} from MAYA's own evaluation")
    n.fact(
        "superposition holds to",
        f"{np.abs(matrix @ np.array([0.04, -0.02, -0.01]) - check).max():.3g}",
    )
    n.say("The curve is linear in the three factors, so evaluating the approved tree with one")
    n.say("factor at 1 and the others at 0 *is* that factor's loading. The calibrator never")
    n.say("writes the loadings down, which is why it cannot drift from the specification.")

    n.step("The search over lambda, with least squares inside it")
    lam = search(ir, train, day_train, days, n)

    n.step("One curve for the whole window, and one curve a day")
    y_train = train["y"].to_numpy()
    x_train = design(ir, tau, lam)
    beta = pooled_fit(x_train, y_train)
    n.fact("window curve", ", ".join(f"{k}={v:+.5f}" for k, v in factor_values(beta, lam).items()))
    n.fact("implied long rate", f"{beta[0] * 100:.3f}%")
    n.fact("implied instantaneous rate", f"{(beta[0] + beta[1]) * 100:.3f}%")
    n.fact("in-sample RMSE", f"{rmse_bp(x_train @ beta - y_train):.2f} bp")
    daily = daily_fit(x_train, y_train, day_train, days)
    fitted_train = (x_train * daily[day_train]).sum(axis=1)
    n.fact("refitted each day instead", f"{rmse_bp(fitted_train - y_train):.2f} bp")
    n.fact(
        "how far the factors move",
        f"beta0 {daily[:, 0].min() * 100:.2f}% to {daily[:, 0].max() * 100:.2f}%, "
        f"beta1 {daily[:, 1].min() * 100:.2f}% to {daily[:, 1].max() * 100:.2f}%",
    )
    n.say(f"{days} days, {days} curves. A MAYA parameter set is one vector of numbers, so")
    n.say("the governed object is the first of those two lines and the desk runs the second.")

    n.step("What the alternatives score on the validation pillars")
    x_val = design(ir, validation["tau"].to_numpy(), lam)
    y_val = validation["y"].to_numpy()
    level = float(y_train.mean())
    joined = interpolated(frame)[is_validation]
    fitted_val = (x_val * daily[day_validation]).sum(axis=1)
    n.fact("Nelson-Siegel, one window curve", f"{rmse_bp(x_val @ beta - y_val):6.2f} bp")
    n.fact("flat curve at the mean yield", f"{rmse_bp(level - y_val):6.2f} bp")
    n.fact("straight lines between pillars", f"{rmse_bp(joined - y_val):6.2f} bp")
    n.fact("Nelson-Siegel refitted each day", f"{rmse_bp(fitted_val - y_val):6.2f} bp")
    n.say("Two of those four can be a parameter set of this model version, and the other two")
    n.say("cannot: joining the dots needs the other rows of the same day, and a curve a day")
    n.say("needs a parameter set a day. MAYA can only score what it can license.")

    n.step("A calibration MAYA will not accept")
    try:
        warrant.upload_parameters(
            {**factor_values(beta, 0.0), "beta0": -0.01},
            name="unconverged",
            data_checksum=checksum,
        )
    except ValidationFailed as exc:
        n.refused("registering a negative long rate and a decay of zero", exc)

    n.step("A calibration MAYA accepts, which is the finding")
    absurd = {"beta0": 0.0310, "beta1": -0.0980, "beta2": -0.0084, "lambda": lam}
    taken = warrant.upload_parameters(
        absurd,
        name=ABSURD_SET,
        data_checksum=checksum,
        metrics={"note": "every bound satisfied; beta0 + beta1 is -6.7%"},
    )
    absurd_id = taken["id"]
    n.fact("accepted", f"{ABSURD_SET}, {taken['state']}, verified_data={taken['verified_data']}")
    short = evaluate_curve(ir, np.array([0.02]), absurd)[0]
    n.fact("its yield at three weeks", f"{short * 100:.2f}%")
    n.fact("its long rate", f"{absurd['beta0'] * 100:.2f}%")
    n.say("beta0 is inside [0, 0.25] and beta1 is inside [-0.25, 0.25], so every bound on the")
    n.say("model holds. Their sum is the instantaneous short rate and it is -6.7%. That")
    n.say("constraint spans two parameters; MAYA's bounds are per parameter, so nothing in")
    n.say("the platform refuses this. The only thing between it and production is that a")
    n.say("person has to approve it — and the blind score below, after the fact.")

    n.step("What the desk's buggy implementation would have calibrated to")
    desk_x = desk_design(ir, tau, lam)
    desk_beta = pooled_fit(desk_x, y_train)
    desk_fitted = desk_x @ desk_beta
    n.fact(
        "its coordinates",
        ", ".join(f"{k}={v:+.5f}" for k, v in factor_values(desk_beta, lam).items()),
    )
    n.fact("its own in-sample RMSE", f"{rmse_bp(desk_fitted - y_train):.2f} bp")
    n.fact("difference from the correct fit", f"{rmse_bp(desk_fitted - x_train @ beta):.3g} bp")
    n.fact("predicted beta1", f"{lam * (beta[1] + beta[2]) - beta[2]:+.5f} — the same number")
    n.say("The bug rescales the loadings without leaving the space they span, so least squares")
    n.say("lands on exactly the same curve and reports exactly the same residual. Nothing")
    n.say("about the fit is worse. Only the numbers the desk would then write on the risk")
    n.say("report — its slope factor is lambda times too large — and what happens when MAYA")
    n.say("reprices those numbers through the specification instead of through the code.")

    n.step("Registering the calibrations against the warrant")
    n.say("The choice is made on validation, before the holdout is touched.")
    curve_id = register(
        warrant,
        cast,
        CURVE_SET,
        factor_values(beta, lam),
        checksum,
        method="grid over lambda, ordinary least squares in the factors at each point",
        pillars=len(train),
        train_rmse_bp=round(rmse_bp(x_train @ beta - y_train), 3),
        validation_rmse_bp=round(rmse_bp(x_val @ beta - y_val), 3),
        lambda_grid_points=len(LAMBDA_GRID),
    )
    level_id = register(
        warrant,
        cast,
        LEVEL_SET,
        factor_values(np.array([level, 0.0, 0.0]), lam),
        checksum,
        method="the same model with both shape factors set to zero: a flat curve at the mean",
        validation_rmse_bp=round(rmse_bp(level - y_val), 3),
    )
    desk_id = warrant.upload_parameters(
        factor_values(desk_beta, lam),
        name=DESK_SET,
        data_checksum=checksum,
        metrics={
            "method": "least squares against the desk's own implementation of the loadings",
            "train_rmse_bp": round(rmse_bp(desk_fitted - y_train), 3),
            "reported_by": "the desk, from its own code",
        },
    )["id"]
    cast.devi.training.parameter_transition(desk_id, "submit")
    n.fact("parameter sets", f"{CURVE_SET} and {LEVEL_SET} approved, {DESK_SET} in review")
    n.fact("tied to the warrant's data", "verified_data=True on all four")
    n.say("A flat curve is not a different model: it is this one with beta1 and beta2 at zero,")
    n.say("which §8.4 allows as another vintage of the same version. Note what that does to")
    n.say("lambda — it multiplies nothing, so it is unidentifiable in that parameter set:")
    flat_low = evaluate_curve(
        ir, np.array([0.5, 30.0]), {"beta0": level, "beta1": 0.0, "beta2": 0.0, "lambda": 0.3}
    )
    flat_high = evaluate_curve(
        ir, np.array([0.5, 30.0]), {"beta0": level, "beta1": 0.0, "beta2": 0.0, "lambda": 5.9}
    )
    n.fact(
        "flat curve at lambda 0.3 and 5.9", f"identical: {np.abs(flat_low - flat_high).max():.3g}"
    )

    n.step("Blind scoring: MAYA reprices the pillars it kept back")
    scores = {}
    for label, ps_id in (
        (CURVE_SET, curve_id),
        (LEVEL_SET, level_id),
        (DESK_SET, desk_id),
        (ABSURD_SET, absurd_id),
    ):
        got = warrant.score_holdout(parameter_set_id=ps_id)
        scores[label] = got["metrics"]
        n.fact(
            label,
            f"RMSE {got['metrics']['rmse'] * 1e4:8.2f} bp, MAE {got['metrics']['mae'] * 1e4:8.2f} bp"
            f" over {got['metrics']['rows']:,} pillars (attempt {got['attempt']})",
        )
    ratio = scores[LEVEL_SET]["rmse"] / scores[CURVE_SET]["rmse"]
    n.fact("flat / Nelson-Siegel", f"{ratio:.2f}x worse")
    n.say("Every attempt is counted on the warrant, so scoring the holdout until it flatters")
    n.say("you is visible. Four parameter sets, four attempts, and the third one is the point:")
    n.say("the desk's own report said its fit was as good as the model's, because it was. The")
    n.say("only number that disagrees is the one MAYA computed from the specification.")

    n.step("The reviewer answers the desk's calibration with that number")
    cast.mgr.training.parameter_transition(
        desk_id,
        "request_changes",
        rationale=(
            f"blind holdout {scores[DESK_SET]['rmse'] * 1e4:.0f} bp against "
            f"{scores[CURVE_SET]['rmse'] * 1e4:.0f} bp for the same fit reported in sample: "
            "these coordinates were produced by code that does not compute the specification"
        ),
    )
    sets = cast.mgr.training.get(drawn["id"])["parameter_sets"]
    n.fact(DESK_SET, next(ps["state"] for ps in sets if ps["name"] == DESK_SET))

    n.step("Sealing it")
    cast.devi.training.transition(drawn["id"], "submit")
    cast.mgr.training.transition(drawn["id"], "approve")
    n.fact("sealed at", cast.mgr.training.seal(drawn["id"])["sealed_at"])


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
