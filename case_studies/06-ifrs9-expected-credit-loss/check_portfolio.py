"""
Step 7 — the test an expected-loss model can actually fail.

    .venv/bin/python case_studies/06-ifrs9-expected-credit-loss/check_portfolio.py

MAYA's blind holdout gives a per-account error, and step 6 was careful about what that can
mean: realised loss is zero on more than nine accounts in ten and large on the rest, so the
error is dominated by the variance of a Bernoulli outcome rather than by the quality of the
expectation. **No expected-loss model can have a small per-account error, and a model that
did would be predicting which accounts default, not what the allowance should be.**

The test that matters is whether the *sum* of the allowance matches the *sum* of the loss.
This step does that arithmetic on the rows the developer can see, and then asks MAYA for two
more blind figures on the rows nobody can see: the model's, and the one you get by holding no
allowance at all. The second is the number the allowance has to beat to be worth computing.

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
    CHOSEN_THRESHOLD,
    COMBINER_WEIGHTS,
    EXTRA_USERS,
    NS,
    WARRANT,
    Cast,
    find_warrant,
    lgd_design,
    parameter_sets,
    pd_design,
)

TITLE = "Case study 6, step 7 — the portfolio test"


def allowance(frame: Any, values: dict[str, float]) -> np.ndarray:
    """The composite's own arithmetic, in numpy, so the portfolio view can be computed here.

    It is the same expression MAYA holds — the study's own copy of it, used only for the
    portfolio arithmetic on rows the developer is allowed to see. The blind figures below come
    from MAYA evaluating its own tree, not from this."""
    pd12 = 1.0 / (
        1.0
        + np.exp(
            -(pd_design(frame) @ np.array([values[k] for k in ("p0", "pArr", "pUtil", "pLtv")]))
        )
    )
    lgd = 1.0 / (1.0 + np.exp(-(lgd_design(frame) @ np.array([values["l0"], values["lCov"]]))))
    drawn = frame["drawn"].astype(float).to_numpy()
    ead = drawn + values["ccf"] * (frame["commitment"].astype(float).to_numpy() - drawn)
    sicr = pd12 / frame["pdOrigination"].astype(float).to_numpy()
    horizon = np.where(sicr > values["sicrThreshold"], values["lifetimeFactor"], 1.0)
    return horizon * pd12 * lgd * ead


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    found = find_warrant(cast.devi, WARRANT)
    sets = parameter_sets(found)
    values: dict[str, float] = {}
    for alias, ps in sets.items():
        for name, value in ps["values"].items():
            values[name.split(".", 1)[-1] if alias else name] = float(value)

    n.step("The approved numbers, all five of them")
    for alias in ("pd", "lgd", "ead"):
        n.fact(alias, sets[alias]["values"])
    n.fact("the committee's", sets[""]["values"])
    n.say(f"and {', '.join(COMBINER_WEIGHTS)} belong to the combination, not to any member.")

    n.step("The portfolio arithmetic, on the rows the developer can see")
    warrant = cast.devi.warrant(found["id"])
    with warrant.data() as ds:
        frame = ds.frame
        ecl = allowance(frame, values)
        realised = frame["realisedLoss12"].astype(float).to_numpy()
        stage2 = (
            1.0
            / (
                1.0
                + np.exp(
                    -(
                        pd_design(frame)
                        @ np.array([values[k] for k in ("p0", "pArr", "pUtil", "pLtv")])
                    )
                )
            )
            / frame["pdOrigination"].astype(float).to_numpy()
            > values["sicrThreshold"]
        )
    n.fact("accounts", f"{len(frame):,}")
    n.fact("allowance the model implies", f"{ecl.sum():,.0f}")
    n.fact("loss actually realised", f"{realised.sum():,.0f}")
    n.fact("coverage", f"{ecl.sum() / realised.sum():.2f}× the realised loss")
    n.fact("accounts in stage 2", f"{int(stage2.sum()):,} ({stage2.mean():.1%})")
    n.fact("share of the allowance from stage 2", f"{ecl[stage2].sum() / ecl.sum():.1%}")
    n.say(
        "A ratio near one is what an unbiased expectation looks like in aggregate. Further "
        "from one in either direction is the number an auditor asks about, and it is a "
        "question about the *level* of the allowance, which the per-account error cannot see."
    )

    grid_evidence(cast, found, warrant, values, sets, n)


def grid_evidence(
    cast: Cast,
    found: dict[str, Any],
    warrant: Any,
    values: dict[str, float],
    sets: dict[str, dict[str, Any]],
    n: Narrator,
) -> None:
    """The consequence of each threshold the committee could have chosen, then its revision."""
    n.step("What the threshold is doing, across the range the committee could have chosen")
    with warrant.data() as ds:
        grid_frame = ds.frame
        realised_total = float(grid_frame["realisedLoss12"].astype(float).sum())
        rows = []
        for threshold in (1.5, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0, 40.0):
            trial = {**values, "sicrThreshold": threshold}
            total = float(allowance(grid_frame, trial).sum())
            in_stage2 = float(
                (
                    1.0
                    / (
                        1.0
                        + np.exp(
                            -(
                                pd_design(grid_frame)
                                @ np.array([values[k] for k in ("p0", "pArr", "pUtil", "pLtv")])
                            )
                        )
                    )
                    / grid_frame["pdOrigination"].astype(float).to_numpy()
                    > threshold
                ).mean()
            )
            rows.append((threshold, in_stage2, total / realised_total))
    for threshold, in_stage2, coverage in rows:
        n.say(
            f"  threshold {threshold:>5.1f}   stage 2 {in_stage2:>6.1%}   coverage {coverage:>5.2f}×"
        )
    nearest = min(rows, key=lambda r: abs(r[2] - 1.0))
    n.fact(
        "the threshold that flatters the total most",
        f"{nearest[0]}, coverage {nearest[2]:.2f}×, stage 2 {nearest[1]:.1%}",
    )
    n.say(
        "And the study is not going to choose it. Picking the threshold that makes the total "
        "come out right is fitting a judgement to an outcome, and the threshold's whole purpose "
        "is to express a view about credit risk rather than to calibrate a number. Worse, the "
        "grid says it would not work: even at a fortieth-fold increase in default probability — "
        "a threshold nobody would defend — the allowance is still 31% above the loss realised "
        "on the same accounts. The threshold explains part of the gap and not the rest of it."
    )

    n.step("What the committee actually decided, and what it recorded as unfinished")
    chosen = next(r for r in rows if r[0] == CHOSEN_THRESHOLD)
    n.say(
        f"Threshold {chosen[0]}: a {chosen[0]:.0f}-fold increase in the probability of default "
        f"since origination is a defensible reading of 'significant' for this book, and it puts "
        f"{chosen[1]:.1%} of accounts in stage 2, which is a stage-2 population the committee "
        f"can explain. It was not chosen to make the total come out right, and it does not: "
        f"coverage is still {chosen[2]:.2f}×."
    )
    revised = {"sicrThreshold": chosen[0], "lifetimeFactor": values["lifetimeFactor"]}
    second = cast.devi.training.upload_parameters(
        found["id"],
        revised,
        notes=(
            f"Threshold revised from 3.0 to {chosen[0]}. At 3.0 the model placed "
            f"{rows[2][1]:.0%} of the book in stage 2 and implied an allowance {rows[2][2]:.2f} "
            f"times the loss realised on the same accounts; at {chosen[0]} it is "
            f"{chosen[2]:.2f} times with {chosen[1]:.0%} in stage 2. The lifetime multiple is "
            "unchanged: this evidence says nothing about it. OPEN FINDING: the residual "
            f"over-provision of {chosen[2] - 1:.0%} is not explained by the threshold — the grid "
            "shows it persists at any threshold — and is to be investigated in the members. Two "
            "candidates are named in their own documents: the loss-given-default member measures "
            "collateral coverage on the balance drawn today rather than on the exposure at "
            "default, and the conversion factor is a single figure for the whole book. Neither "
            "is fixed in this version and the allowance is not to be taken as unbiased."
        ),
    )
    cast.devi.training.parameter_transition(second["id"], "submit")
    cast.mgr.training.parameter_transition(
        second["id"],
        "approve",
        justification=(
            "Not fitted: a revised committee judgement, minuted on the evidence in this "
            "warrant's portfolio review, carrying an open finding about the residual "
            "over-provision. There is no MAYA download it could be tied to."
        ),
    )
    n.fact("revised set", f"{second['id'][:8]}… approved")
    n.say(
        "The first set stays on the warrant. A superseded judgement is part of the record, and "
        "so is the finding that came with the replacement: MAYA has not fixed this model. It "
        "has turned a disagreement about the level of the allowance into a number, attached it "
        "to the warrant, and made the next step somebody's job."
    )

    n.step("And two blind figures, on the rows nobody can see")
    flat = {
        **{
            f"{alias}.{k.split('.', 1)[-1]}": v
            for alias in ("pd", "lgd", "ead")
            for k, v in sets[alias]["values"].items()
        },
        **revised,
    }
    model = cast.devi.training.score_holdout(found["id"], values=flat)
    # No allowance at all: drive the probability of default to zero and the product follows.
    nothing = {**flat, "pd.p0": -60.0, "pd.pArr": 0.0, "pd.pUtil": 0.0, "pd.pLtv": 0.0}
    none_at_all = cast.devi.training.score_holdout(found["id"], values=nothing)
    n.fact("escrowed rows", f"{model['metrics']['rows']:,}")
    n.fact("RMSE, the model", f"{model['metrics']['rmse']:,.0f}")
    n.fact("RMSE, no allowance at all", f"{none_at_all['metrics']['rmse']:,.0f}")
    better = 1.0 - (model["metrics"]["rmse"] / none_at_all["metrics"]["rmse"]) ** 2
    n.fact("improvement", f"{better:.1%} of the mean squared error")
    n.fact("holdout attempts counted", none_at_all["attempt"])
    n.say(
        "The second figure is the root mean square of the realised loss itself. An "
        "expected-loss model should not beat it by much and may not beat it at all: it cannot "
        "say which account will default, only how much to set aside across all of them, and "
        "the per-account error of a correct expectation on a rare event is close to the error "
        "of predicting nothing. §7 of the README works through why, and why the portfolio "
        "coverage above is the figure to argue about."
    )

    n.step("Now the warrant can be sealed")
    n.fact("sealed at", cast.mgr.training.seal(found["id"])["sealed_at"])
    n.fact(
        "parameter sets on it",
        len(cast.mgr.training.get(found["id"])["parameter_sets"]),
    )
    n.say("Three members, two committee decisions, one of them superseded, all on the record.")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
