"""
Step 5 — fitting a rare event, and saying what the holdout figure means.

    .venv/bin/python case_studies/03-mortgage-prepayment/fit_parameters.py

Prepayment is about two per cent a month, so this is a fit on a rare event and the
intercept carries most of the base rate. Because the book is synthetic the generating
coefficients are known, and the step prints the fit beside them — which is the clearest
possible statement of what a fit on this much data can and cannot recover.

The blind holdout returns a root Brier score. On a two-per-cent event, predicting zero
everywhere scores about 0.133, so that number is quoted beside the model's: a calibration
figure with nothing to compare it against is not evidence.

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
    DRIVERS,
    EXTRA_USERS,
    NS,
    TARGET,
    TRUE,
    WARRANT,
    WEIGHTS,
    Cast,
    auc,
    cpr,
    design_matrix,
    find_warrant,
    fit_logistic,
)

TITLE = "Case study 3, step 5 — the fit, and what the holdout number means"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    found = find_warrant(cast.devi, WARRANT)
    warrant = cast.devi.warrant(found["id"])

    n.step("Opening the warrant's data")
    with warrant.data() as ds:
        frame = ds.frame
        checksum = ds.checksum
        n.fact("rows handed over", f"{len(frame):,}")
        n.fact("partitions", ", ".join(sorted(frame["_split"].unique())))
        n.fact("target among the inputs", ds.target in ds.X.columns)
        complete = frame.dropna(subset=[*DRIVERS, TARGET])
        if len(complete) != len(frame):
            n.fact("incomplete rows excluded", f"{len(frame) - len(complete):,}")
        train = complete[complete["_split"] == "train"]
        validation = complete[complete["_split"] == "validation"]
        n.fact("events in training", f"{int(train[TARGET].sum()):,} of {len(train):,}")

        n.step("Fitting, and comparing against the process that generated the book")
        design = design_matrix(train)
        beta = fit_logistic(design, train[TARGET].astype(float).to_numpy())
        values = dict(zip(WEIGHTS, (round(float(b), 6) for b in beta)))
        vdesign = design_matrix(validation)
        metrics = {
            "auc_train": round(auc(train[TARGET].to_numpy(), design @ beta), 4),
            "auc_validation": round(auc(validation[TARGET].to_numpy(), vdesign @ beta), 4),
        }
        base_rate = float(train[TARGET].mean())
    for name in WEIGHTS:
        n.fact(name, f"fitted {values[name]:+.3f}   generated {TRUE[name]:+.3f}")
    n.fact("AUC train / validation", f"{metrics['auc_train']} / {metrics['auc_validation']}")
    n.fact("base rate in training", f"{base_rate:.3%} a month, CPR {cpr(base_rate):.1%}")

    approve_and_score(cast, found, warrant, values, checksum, metrics, base_rate, n)


def approve_and_score(
    cast: Cast,
    found: dict[str, Any],
    warrant: Any,
    values: dict[str, float],
    checksum: str,
    metrics: dict[str, float],
    base_rate: float,
    n: Narrator,
) -> None:
    """The parameter set, the blind score, and the seal."""
    from maya.core.errors import NotApproved

    n.step("Uploading the fit, tied to the rows it came from")
    untied = warrant.upload_parameters(values, data_checksum="0" * 64)
    n.fact("a set with the wrong checksum", untied["flag"])
    cast.devi.training.parameter_transition(untied["id"], "submit")
    try:
        cast.mgr.training.parameter_transition(untied["id"], "approve")
    except NotApproved as exc:
        n.refused("approving parameters that cannot prove their data", exc)
    tied = warrant.upload_parameters(values, data_checksum=checksum, metrics=metrics)
    cast.devi.training.parameter_transition(tied["id"], "submit")
    cast.mgr.training.parameter_transition(tied["id"], "approve")
    n.fact("parameter set", f"{tied['id'][:8]}… approved, verified_data={tied['verified_data']}")

    n.step("Blind scoring, against something to compare it with")
    scored = warrant.score_holdout(parameter_set_id=tied["id"])
    rmse = scored["metrics"]["rmse"]
    null_model = float(np.sqrt(base_rate * (1 - base_rate) ** 2 + (1 - base_rate) * base_rate**2))
    n.fact("holdout rows", f"{scored['metrics']['rows']:,}")
    n.fact("root Brier, this model", f"{rmse:.4f}")
    n.fact("root Brier, predicting the base rate", f"{null_model:.4f}")
    n.fact("improvement", f"{(1 - (rmse / null_model) ** 2):.1%} of the Brier score")

    n.step("Sealing it")
    cast.devi.training.transition(found["id"], "submit")
    cast.mgr.training.transition(found["id"], "approve")
    n.fact("sealed at", cast.mgr.training.seal(found["id"])["sealed_at"])


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
