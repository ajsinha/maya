"""
Step 6 — two fits, and a warrant that will not seal until both are done.

    .venv/bin/python case_studies/04-heloc-exposure/fit_parameters.py

Each member is fitted on its own regime's rows, and each gets its **own parameter set**,
tagged with the member alias it belongs to. The two are fitted independently — the
composite declares `mode: parallel`, because neither consumes the other's output.

The step then does the thing that makes composite governance worth having: it tries to seal
the warrant with only the draw member fitted, and MAYA refuses. A composite that went to
production with one member fitted and the other left at whatever it happened to have would
be the single easiest way to ship a wrong number, and it would be invisible.

Finally MAYA scores the **composite** blind against the realised exposure, in currency, with
the naive forecast — that exposure does not change — quoted beside it.

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
    DRAW_WEIGHTS,
    EXTRA_USERS,
    NS,
    REPAY_WEIGHTS,
    WARRANT,
    Cast,
    draw_design,
    find_warrant,
    fit_least_squares,
    fit_logistic_fraction,
    realised_fraction,
    repay_design,
)

TITLE = "Case study 4, step 6 — a fit per member, and a seal that waits for both"


def fits(warrant: Any, n: Narrator) -> tuple[dict[str, dict[str, float]], str, dict[str, Any]]:
    """Fit each member on its own regime's rows, and report against the generating process."""
    with warrant.data() as ds:
        checksum = ds.checksum
        usable = realised_fraction(ds.frame)
        train = usable[usable["_split"] == "train"]
        draw_rows = train[train["inDraw"] == 1]
        repay_rows = train[train["inDraw"] == 0]
        draw_beta = fit_logistic_fraction(
            draw_design(draw_rows), np.clip(draw_rows["fraction"].to_numpy(), 0.0, 1.0)
        )
        repay_beta = fit_least_squares(repay_design(repay_rows), repay_rows["fraction"].to_numpy())
        sizes = {"draw": len(draw_rows), "repay": len(repay_rows)}
    values = {
        "draw": dict(zip(DRAW_WEIGHTS, (round(float(b), 6) for b in draw_beta))),
        "repay": dict(zip(REPAY_WEIGHTS, (round(float(b), 6) for b in repay_beta))),
    }
    n.fact("rows per member", sizes)
    for alias, weights in (("draw", DRAW_WEIGHTS), ("repay", REPAY_WEIGHTS)):
        for name in weights:
            n.fact(f"{alias}.{name}", f"{values[alias][name]:+.4f}")
    # These are deliberately *not* compared with the coefficients in make_data.py. The book
    # is generated month by month and these members are twelve-month reduced forms, so the
    # two sets of numbers are in different units and comparing them would be a category
    # error. What can be checked is that the signs are what the model's own document commits
    # to, and that each member reproduces its regime's mean.
    n.say("The signs the specification commits to:")
    n.say(
        f"  more equity, more drawing: dEq {values['draw']['dEq']:+.3f}; "
        f"more room, more drawing: dRoom {values['draw']['dRoom']:+.3f}; "
        f"dearer money, less drawing: dRate {values['draw']['dRate']:+.3f}"
    )
    return values, checksum, sizes


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved, ValidationFailed

    cast = Cast(maya)
    found = find_warrant(cast.devi, WARRANT)
    warrant = cast.devi.warrant(found["id"])

    n.step("Fitting each member on its own regime's rows")
    values, checksum, _ = fits(warrant, n)

    n.step("Uploading the draw member's parameters, tagged with the alias they belong to")
    draw_set = cast.devi.training.upload_parameters(
        found["id"], values["draw"], data_checksum=checksum, member_alias="draw"
    )
    n.fact("member_alias", draw_set["member_alias"])
    n.fact("verified against a MAYA download", draw_set["verified_data"])
    cast.devi.training.parameter_transition(draw_set["id"], "submit")
    cast.mgr.training.parameter_transition(draw_set["id"], "approve")

    n.step("Trying to seal with one member fitted and the other untouched")
    cast.devi.training.transition(found["id"], "submit")
    cast.mgr.training.transition(found["id"], "approve")
    try:
        cast.mgr.training.seal(found["id"])
        n.say("NOT REFUSED — a composite sealed with an unfitted member")
    except (NotApproved, ValidationFailed) as exc:
        n.refused("sealing a composite whose repayment member has no parameters", exc)

    n.step("Fitting the repayment member too, then sealing")
    repay_set = cast.devi.training.upload_parameters(
        found["id"], values["repay"], data_checksum=checksum, member_alias="repay"
    )
    cast.devi.training.parameter_transition(repay_set["id"], "submit")
    cast.mgr.training.parameter_transition(repay_set["id"], "approve")
    n.fact("sealed at", cast.mgr.training.seal(found["id"])["sealed_at"])

    n.step("Blind scoring the composite against realised exposure, in currency")
    flat = {f"{alias}.{k}": v for alias, vs in values.items() for k, v in vs.items()}
    scored = cast.devi.training.score_holdout(found["id"], values=flat)
    n.fact("holdout rows", f"{scored['metrics']['rows']:,}")
    n.fact("RMSE", f"{scored['metrics']['rmse']:,.0f}")
    n.fact("MAE", f"{scored['metrics']['mae']:,.0f}")

    n.step("And the benchmark, scored by MAYA on the same escrowed rows")
    n.say(
        "The forecast worth beating is 'exposure does not change'. Rather than compute that "
        "on rows the developer can see, the warrant is scored again with parameters that make "
        "both members return a zero draw fraction, so the prediction is exactly today's drawn "
        "balance - through the same code path, on the same escrowed rows. It costs a holdout "
        "attempt, and MAYA counts it."
    )
    naive = {**dict.fromkeys(flat, 0.0), "draw.d0": -50.0}
    baseline = cast.devi.training.score_holdout(found["id"], values=naive)
    n.fact("RMSE, exposure does not change", f"{baseline['metrics']['rmse']:,.0f}")
    n.fact("MAE, exposure does not change", f"{baseline['metrics']['mae']:,.0f}")
    better = 1.0 - (scored["metrics"]["rmse"] / baseline["metrics"]["rmse"]) ** 2
    n.fact("improvement", f"{better:.1%} of the mean squared error")
    n.fact("holdout attempts counted", baseline["attempt"])


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
