"""
Step 5 — calibration: the volatility nobody can observe, and what it is worth.

    .venv/bin/python case_studies/05-option-pricing/get_training_warrant.py

A warrant is drawn on the pinned chain with the quoted mid as the target, and the desk
calibrates the surface on the training partition — not by fitting outcomes, but by choosing
the volatility that best reprices quotes the market has already published. Two calibrations
are uploaded against the same warrant, as §8.4 allows:

* **flat** — the single best volatility in all nine buckets, which is what Black–Scholes
  assumes and what a desk would use if the smile were not there;
* **surface** — one volatility per bucket.

The decision between them is taken on the validation partition. MAYA then scores each one
blind against the escrowed holdout, and the gap between the two numbers is this study's
result: a single volatility cannot price this market, and here is how badly.

On the way, MAYA refuses a calibration that wandered outside the bounds declared on the
model, which is the only thing standing between an unconverged optimiser and production.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import (  # noqa: E402
    BANDS,
    EXTRA_USERS,
    LEAKAGE_NOTE,
    MATURITIES,
    MODEL,
    MODEL_REF,
    NS,
    PIN_REF,
    SIGMAS,
    VOL_BOUNDS,
    WARRANT,
    Cast,
    bucket_masks,
    calibrate,
    columns,
    flat,
    price,
)

TITLE = "Case study 5, step 5 — calibrating a volatility that is not observable"
FLAT_SET, SURFACE_SET = "flat-vol-2509", "surface-2509"


def residual(ir: dict[str, Any], frame: Any, vols: dict[str, float]) -> np.ndarray:
    return price(ir, columns(frame), vols) - frame["mid"].astype(float).to_numpy()


def rmse(ir: dict[str, Any], frame: Any, vols: dict[str, float]) -> float:
    return float(np.sqrt(np.nanmean(residual(ir, frame, vols) ** 2)))


def table(rows: dict[int, str], cell: Any) -> None:
    """A three by three of the model's own buckets, printed as the surface it is."""
    print(f"    {'':<26}" + "".join(f"{band:>18}" for band in BANDS.values()))
    for i, label in rows.items():
        print(f"    {label:<26}" + "".join(f"{cell(i, j):>18}" for j in BANDS))


def register(
    warrant: Any, cast: Cast, name: str, vols: dict[str, float], checksum: str, **metrics: Any
) -> str:
    """Upload one calibration, submit it, and have a model manager approve it."""
    ps = warrant.upload_parameters(vols, name=name, data_checksum=checksum, metrics=metrics)
    cast.devi.training.parameter_transition(ps["id"], "submit")
    cast.mgr.training.parameter_transition(ps["id"], "approve")
    return str(ps["id"])


def main(maya: Any, n: Narrator) -> None:  # noqa: PLR0915 - one narrated step per paragraph
    from maya.core.errors import ValidationFailed

    cast = Cast(maya)
    n.step("Drawing the warrant: the quoted mid is the target, the five market inputs are not")
    drawn = cast.devi.training.create(
        NS,
        WARRANT,
        MODEL_REF,
        PIN_REF,
        spec={
            "target": "mid",
            "objective": "calibrate the nine-bucket volatility surface to the ACME chain",
            "metrics": ["rmse", "mae"],
        },
    )
    n.fact("contract satisfied", drawn["contract_report"]["ok"])
    n.fact("mapping", drawn["contract_report"]["mapping"])
    n.fact("leakage certificate", drawn["leakage_certificate"]["status"])
    n.fact("rows examined", f"{drawn['leakage_certificate']['rows_examined']:,}")
    n.fact("violations", drawn["leakage_certificate"]["violations"])
    n.say(LEAKAGE_NOTE)

    n.step("Opening the data: the quotes the desk may calibrate on")
    warrant = cast.devi.warrant(drawn["id"])
    with warrant.data() as ds:
        frame, checksum = ds.frame, ds.checksum
        n.fact("rows the warrant covers", f"{ds.table.num_rows:,}")
        n.fact("target among the inputs", ds.target in list(ds.X.columns))
        n.fact("data checksum", f"{checksum[:16]}…")
    train = frame[frame["_split"] == "train"].reset_index(drop=True)
    validation = frame[frame["_split"] == "validation"].reset_index(drop=True)
    n.fact("train / validation", f"{len(train):,} / {len(validation):,} quotes")
    n.fact("escrowed holdout", f"{drawn['holdout_rows']:,} quotes MAYA keeps")

    n.step("Asking the model which bucket each quote belongs to")
    ir = cast.devi.models.get(f"{NS}/{MODEL}")["versions"][0]["formula_ir"]
    cols = columns(train)
    masks = bucket_masks(ir, cols)
    claimed = sum(int(m.sum()) for m in masks.values())
    n.fact("quotes claimed by exactly one bucket", f"{claimed:,} of {len(train):,}")
    n.say("The band edges live in the expression tree, so the calibrator perturbs each")
    n.say("volatility and sees which prices move rather than re-reading the boundaries.")

    n.step("The single best volatility for the whole chain")
    mid = train["mid"].astype(float).to_numpy()
    whole = np.ones(len(train), dtype=bool)
    one = calibrate(ir, cols, mid, whole)
    n.fact("flat volatility", f"{one['sigma']:.4f} over {one['quotes']:,} quotes")
    n.fact("in-sample RMSE", f"{one['rmse']:.4f} per contract")

    n.step("And one volatility per bucket, which is what the market is actually quoting")
    surface = {name: calibrate(ir, cols, mid, masks[name]) for name in SIGMAS}
    table(
        MATURITIES,
        lambda i, j: (
            f"{surface[f'sigma{i}{j}']['sigma']:.4f} ({surface[f'sigma{i}{j}']['quotes']})"
        ),
    )
    vols = {name: surface[name]["sigma"] for name in SIGMAS}
    worst = max(SIGMAS, key=lambda name: surface[name]["rmse"])
    best = min(SIGMAS, key=lambda name: surface[name]["rmse"])
    n.fact("worst bucket in-sample", f"{worst} at RMSE {surface[worst]['rmse']:.4f}")
    n.fact("best bucket in-sample", f"{best} at RMSE {surface[best]['rmse']:.4f}")
    n.say("Read each row left to right: the market charges more volatility for low strikes")
    n.say("than for high ones, and each column top to bottom: more for longer maturities.")
    n.say("One number cannot be all of those at once.")

    n.step("What the one number costs, bucket by bucket")
    n.say("Mean error in pence per contract on the validation quotes, flat / nine buckets.")
    n.say("A positive number is the model paying more than the market.")
    seen = bucket_masks(ir, columns(validation))
    errors = {
        label: residual(ir, validation, vol)
        for label, vol in (("flat", flat(one["sigma"])), ("nine", vols))
    }
    table(
        MATURITIES,
        lambda i, j: (
            "%+.1f / %+.1f"
            % tuple(100.0 * float(np.nanmean(e[seen[f"sigma{i}{j}"]])) for e in errors.values())
        ),
    )
    n.say("The one volatility is not merely less accurate: it is wrong in a pattern. It")
    n.say("underpays the long-dated low-strike wing — the most expensive contracts on the")
    n.say("sheet — while overpaying most of the short-dated book, because it is trying to")
    n.say("be the average of a surface that has a shape. Where it looks harmless, at 1M")
    n.say("low strikes, that is because those calls are nearly all intrinsic: no vega, no")
    n.say("volatility error. The nine buckets are inside seven pence everywhere.")

    n.step("A calibration that wandered outside the bounds on the model")
    absurd = {**vols, "sigma13": -0.15, "sigma33": 8.0}
    try:
        warrant.upload_parameters(absurd, name="unconverged", data_checksum=checksum)
    except ValidationFailed as exc:
        n.refused(f"registering a volatility outside {VOL_BOUNDS}", exc)

    n.step("Registering both calibrations against the same warrant")
    n.say("The choice between them is made on validation, before the holdout is touched.")
    flat_validation = rmse(ir, validation, flat(one["sigma"]))
    surface_validation = rmse(ir, validation, vols)
    n.fact("validation RMSE, flat", f"{flat_validation:.4f}")
    n.fact("validation RMSE, surface", f"{surface_validation:.4f}")
    flat_id = register(
        warrant,
        cast,
        FLAT_SET,
        flat(one["sigma"]),
        checksum,
        method="least squares in price on the training partition, one volatility everywhere",
        quotes=one["quotes"],
        train_rmse=round(one["rmse"], 6),
        validation_rmse=round(flat_validation, 6),
    )
    surface_id = register(
        warrant,
        cast,
        SURFACE_SET,
        vols,
        checksum,
        method="least squares in price on the training partition, per bucket",
        quotes={name: surface[name]["quotes"] for name in SIGMAS},
        train_rmse={name: round(surface[name]["rmse"], 6) for name in SIGMAS},
        validation_rmse=round(surface_validation, 6),
    )
    n.fact("parameter sets", f"{FLAT_SET} and {SURFACE_SET}, both approved by mgr")
    n.fact("tied to the warrant's data", "verified_data=True on both")

    n.step("Blind scoring: MAYA reprices the quotes it kept back")
    scores = {}
    for label, ps_id in ((FLAT_SET, flat_id), (SURFACE_SET, surface_id)):
        got = warrant.score_holdout(parameter_set_id=ps_id)
        scores[label] = got["metrics"]
        n.fact(
            label,
            f"RMSE {got['metrics']['rmse']:.4f}, MAE {got['metrics']['mae']:.4f} "
            f"over {got['metrics']['rows']:,} quotes (attempt {got['attempt']})",
        )
    ratio = scores[FLAT_SET]["rmse"] / scores[SURFACE_SET]["rmse"]
    n.fact("flat / surface", f"{ratio:.2f}x worse")
    n.say("Every attempt is counted on the warrant, so scoring the holdout until it")
    n.say("flatters you is visible. Two parameter sets, two attempts.")

    n.step("Sealing it")
    cast.devi.training.transition(drawn["id"], "submit")
    cast.mgr.training.transition(drawn["id"], "approve")
    n.fact("sealed at", cast.mgr.training.seal(drawn["id"])["sealed_at"])


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
