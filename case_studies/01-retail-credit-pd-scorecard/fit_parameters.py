"""
Step 5 — fit on the training partition, and tie the fit to the rows it came from.

    .venv/bin/python case_studies/01-retail-credit-pd-scorecard/fit_parameters.py

``warrant.data()`` hands over the training and validation partitions and nothing else;
the test partition is escrowed. The fit is iteratively reweighted least squares in a
dozen lines of numpy, because this study is about the governance around a fit and not
about the optimiser.

Then the part that answers "which data produced these numbers": the same coefficients
are uploaded twice, once quoting the wrong data checksum and once the right one. The
first is flagged ``unverified_data`` and cannot be approved. Finally MAYA scores the
escrowed holdout itself — metrics out, rows never — and counts the attempt.

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
    DRIVERS,
    EXTRA_USERS,
    NS,
    TARGET,
    WARRANT,
    WEIGHTS,
    Cast,
    auc,
    design_matrix,
    find_warrant,
    fit_logistic,
)

TITLE = "Case study 1, step 5 — the fit, and the checksum that ties it to its data"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved

    cast = Cast(maya)
    found = find_warrant(cast.devi, WARRANT)
    warrant = cast.devi.warrant(found["id"])

    n.step("Opening the warrant's data: training and validation, and no more")
    with warrant.data() as ds:
        frame = ds.frame
        checksum = ds.checksum
        n.fact("rows handed over", f"{len(frame):,}")
        n.fact("partitions present", ", ".join(sorted(frame["_split"].unique())))
        n.fact("target among the inputs", ds.target in ds.X.columns)
        n.fact("data checksum", f"{checksum[:16]}…")

        # The bureau file is quarterly and delivered late, so the earliest observation
        # months have no bureau score to carry forward yet. MAYA left that gap visible
        # rather than inventing a value, which puts the decision here, in the open.
        complete = frame.dropna(subset=[*DRIVERS, TARGET])
        n.fact(
            "rows with no bureau score yet",
            f"{len(frame) - len(complete):,} of {len(frame):,}, excluded from the fit",
        )
        train = complete[complete["_split"] == "train"]
        validation = complete[complete["_split"] == "validation"]

        n.step("Fitting, by iteratively reweighted least squares")
        design = design_matrix(train)
        beta = fit_logistic(design, train[TARGET].astype(float).to_numpy())
        values = dict(zip(WEIGHTS, (round(float(b), 6) for b in beta)))
        metrics = {
            "auc_train": round(auc(train[TARGET].to_numpy(), design @ beta), 4),
            "auc_validation": round(
                auc(validation[TARGET].to_numpy(), design_matrix(validation) @ beta), 4
            ),
        }
    for name, value in values.items():
        n.fact(name, f"{value:+.4f}")
    n.fact("AUC train / validation", f"{metrics['auc_train']} / {metrics['auc_validation']}")

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
    n.fact("parameter set", f"{tied['id'][:8]}… approved by mgr")

    n.step("Blind scoring against the escrowed holdout: metrics out, rows never")
    scored = warrant.score_holdout(parameter_set_id=tied["id"])
    n.fact("holdout rows", f"{scored['metrics']['rows']:,}")
    n.fact("RMSE (= root Brier score)", f"{scored['metrics']['rmse']:.4f}")
    n.fact("MAE", f"{scored['metrics']['mae']:.4f}")
    n.fact("attempt", f"{scored['attempt']} (every attempt is counted on the warrant)")

    n.step("Sealing the warrant: data, certificate, exception and parameters fixed together")
    cast.devi.training.transition(found["id"], "submit")
    cast.mgr.training.transition(found["id"], "approve")
    n.fact("sealed at", cast.mgr.training.seal(found["id"])["sealed_at"])


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
