"""
Step 2 — each model fitted under its own warrant, on the same escrowed holdout.

    .venv/bin/python case_studies/42-demand-elasticity/fit_both.py

The two warrants are drawn on the same pin with the same split and seed, so their holdouts
are the same rows: MAYA records a holdout hash on each, and the two hashes are equal. That
is what will make them comparable. Devi fits the champion; a second developer fits the
challenger. Each fit is tied to its data by checksum, approved, and scored blind.

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
    LEAKAGE_JUSTIFICATION,
    CHALLENGER,
    CHALLENGER_WARRANT,
    CHAMPION,
    CHAMPION_WARRANT,
    EXTRA_USERS,
    NS,
    PIN_REF,
    SEED,
    Cast,
)  # noqa: E402

TITLE = "Case study 42, step 2 — two fits, one holdout"


def _fit(frame: Any, model: str) -> dict[str, float]:
    import numpy as np

    train = frame[frame["_split"] == "train"]
    x, y = train["price"].to_numpy(float), train["demand"].to_numpy(float)
    if model == CHAMPION:
        b, a = np.polyfit(x, y, 1)
        return {"a": round(float(a), 6), "b": round(float(b), 6)}
    beta, alpha = np.polyfit(np.log(x), np.log(y), 1)
    return {"alpha": round(float(alpha), 6), "beta": round(float(beta), 6)}


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    for model, warrant_name, dev in (
        (CHAMPION, CHAMPION_WARRANT, cast.devi),
        (CHALLENGER, CHALLENGER_WARRANT, cast.dev2),
    ):
        n.step(f"{model}: warrant, fit, approval, blind score")
        drawn = dev.training.create(
            NS,
            warrant_name,
            f"{NS}/{model}@v1",
            PIN_REF,
            spec={"target": "demand", "seed": SEED, "leakage_justification": LEAKAGE_JUSTIFICATION},
        )
        warrant = dev.warrant(drawn["id"])
        with warrant.data() as ds:
            values = _fit(ds.frame, model)
            checksum = ds.checksum
        ps = warrant.upload_parameters(values, data_checksum=checksum)
        dev.training.parameter_transition(ps["id"], "submit")
        cast.mgr.training.parameter_transition(ps["id"], "approve")
        score = warrant.score_holdout(parameter_set_id=ps["id"])
        n.fact("parameters", ", ".join(f"{k} = {v:+.4f}" for k, v in values.items()))
        n.fact("holdout hash", f"{drawn['holdout_hash'][:16]}…")
        n.fact("blind RMSE", f"{score['metrics']['rmse']:.4f} on {score['metrics']['rows']} rows")
        dev.training.transition(drawn["id"], "submit")
        cast.mgr.training.transition(drawn["id"], "approve")
        cast.mgr.training.seal(drawn["id"])


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
