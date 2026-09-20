"""
Step 6 — three fits, two judgements, and a seal that waits for all five numbers.

    .venv/bin/python case_studies/06-ifrs9-expected-credit-loss/fit_parameters.py

Each member is fitted on what it estimates, and on the rows where that quantity exists:
the probability member on every row, the loss-given-default member on the accounts that
actually defaulted, and the conversion factor on the realised exposure of those same
accounts. The combiner's two parameters are not fitted at all — they are the impairment
committee's judgements, registered with their provenance so that the figure in the accounts
is a figure somebody signed for.

Then MAYA scores the allowance blind against realised loss, and the step is careful about
what that number can mean: realised loss is zero on nine rows in ten, so a per-account error
is dominated by the variance of a Bernoulli outcome. The portfolio total is the test that
matters for an expectation, and both are reported.

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
    COMMITTEE,
    COMMITTEE_WHY,
    EAD_WEIGHTS,
    EXTRA_USERS,
    LGD_WEIGHTS,
    NS,
    PD_WEIGHTS,
    TRUE_CCF,
    TRUE_LGD,
    TRUE_PD,
    WARRANT,
    Cast,
    auc,
    find_warrant,
    fit_logistic,
    lgd_design,
    pd_design,
)

TITLE = "Case study 6, step 6 — three fits, two judgements"


def fits(warrant: Any, n: Narrator) -> tuple[dict[str, dict[str, float]], str, dict[str, Any]]:
    with warrant.data() as ds:
        checksum = ds.checksum
        frame = ds.frame
        train = frame[frame["_split"] == "train"]
        defaulted = train[train["defaulted12"] == 1]

        pd_beta = fit_logistic(pd_design(train), train["defaulted12"].astype(float).to_numpy())
        lgd_beta = fit_logistic(
            lgd_design(defaulted), defaulted["lossRate"].astype(float).to_numpy()
        )
        # The conversion factor: the realised loss divided by the loss rate is the exposure at
        # default, so the factor is the share of the undrawn limit that implies. Least squares
        # through the origin on (exposure - drawn) against (limit - drawn).
        drawn = defaulted["drawn"].astype(float).to_numpy()
        undrawn = defaulted["commitment"].astype(float).to_numpy() - drawn
        rate = np.clip(defaulted["lossRate"].astype(float).to_numpy(), 1e-6, None)
        implied = defaulted["realisedLoss12"].astype(float).to_numpy() / rate
        usable = undrawn > 1.0
        ccf = float(
            np.clip(
                np.sum((implied - drawn)[usable] * undrawn[usable]) / np.sum(undrawn[usable] ** 2),
                0.0,
                1.0,
            )
        )
        metrics = {
            "pd_auc_train": round(
                auc(train["defaulted12"].to_numpy(), pd_design(train) @ pd_beta), 4
            ),
            "lgd_rows": int(len(defaulted)),
        }
        validation = frame[frame["_split"] == "validation"]
        metrics["pd_auc_validation"] = round(
            auc(validation["defaulted12"].to_numpy(), pd_design(validation) @ pd_beta), 4
        )
    values = {
        "pd": dict(zip(PD_WEIGHTS, (round(float(b), 6) for b in pd_beta))),
        "lgd": dict(zip(LGD_WEIGHTS, (round(float(b), 6) for b in lgd_beta))),
        "ead": dict(zip(EAD_WEIGHTS, (round(ccf, 6),))),
    }
    for alias, truth in (("pd", TRUE_PD), ("lgd", TRUE_LGD), ("ead", {"ccf": TRUE_CCF})):
        for name, fitted in values[alias].items():
            n.fact(f"{alias}.{name}", f"fitted {fitted:+.3f}   generated {truth[name]:+.3f}")
    n.fact(
        "PD AUC train / validation", f"{metrics['pd_auc_train']} / {metrics['pd_auc_validation']}"
    )
    n.fact("defaults the LGD member was fitted on", f"{metrics['lgd_rows']:,}")
    return values, checksum, metrics


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved, ValidationFailed

    cast = Cast(maya)
    found = find_warrant(cast.devi, WARRANT)
    warrant = cast.devi.warrant(found["id"])

    n.step("Fitting the three members, each on the rows where its quantity exists")
    values, checksum, _ = fits(warrant, n)

    n.step("A parameter set per member, tagged with the alias it belongs to")
    for alias, vals in values.items():
        ps = cast.devi.training.upload_parameters(
            found["id"], vals, data_checksum=checksum, member_alias=alias
        )
        cast.devi.training.parameter_transition(ps["id"], "submit")
        cast.mgr.training.parameter_transition(ps["id"], "approve")
        n.fact(alias, f"{ps['id'][:8]}… approved, verified_data={ps['verified_data']}")

    n.step("Trying to seal with the members fitted and the committee's numbers missing")
    cast.devi.training.transition(found["id"], "submit")
    cast.mgr.training.transition(found["id"], "approve")
    try:
        cast.mgr.training.seal(found["id"])
        n.say("NOT REFUSED — the allowance sealed with no approved threshold or multiple")
    except (NotApproved, ValidationFailed) as exc:
        n.refused("sealing an allowance whose stage threshold nobody approved", exc)

    n.step("The committee's two numbers, registered with their provenance")
    n.say(COMMITTEE_WHY)
    try:
        cast.devi.training.upload_parameters(found["id"], {"sicrThreshold": 3.0})
        n.say("NOT REFUSED — half the committee's decision was accepted")
    except ValidationFailed as exc:
        n.refused("registering the threshold and forgetting the multiple", exc)
    # No data checksum, deliberately. A judgement is not a fit: it was not derived from the
    # rows MAYA handed over, and quoting their checksum would claim it was.
    judgement = cast.devi.training.upload_parameters(found["id"], COMMITTEE, notes=COMMITTEE_WHY)
    n.fact("tied to a MAYA download", judgement["verified_data"])
    n.fact("flag", judgement["flag"])
    cast.devi.training.parameter_transition(judgement["id"], "submit")
    try:
        cast.mgr.training.parameter_transition(judgement["id"], "approve")
        n.say("NOT REFUSED — an untied parameter set was approved in silence")
    except NotApproved as exc:
        n.refused("approving a judgement with nothing said about where it came from", exc)
    cast.mgr.training.parameter_transition(
        judgement["id"],
        "approve",
        justification=(
            "Not fitted: these are the impairment committee's judgements, minuted on "
            "2025-12-11, and there is no MAYA download they could be tied to. " + COMMITTEE_WHY
        ),
    )
    n.fact(
        "committee set",
        f"{judgement['id'][:8]}… approved, member_alias={judgement['member_alias']}",
    )
    n.say(
        "The warrant is not sealed yet: step 7 is the evidence that decides whether it should be."
    )

    n.step("Blind scoring the allowance against realised loss")
    flat = {f"{alias}.{k}": v for alias, vs in values.items() for k, v in vs.items()}
    scored = cast.devi.training.score_holdout(found["id"], values={**flat, **COMMITTEE})
    n.fact("escrowed rows", f"{scored['metrics']['rows']:,}")
    n.fact("RMSE per account", f"{scored['metrics']['rmse']:,.0f}")
    n.fact("MAE per account", f"{scored['metrics']['mae']:,.0f}")
    n.say(
        "Read those two carefully. Realised loss is zero on more than nine rows in ten and "
        "large on the rest, so a per-account error is mostly the variance of a Bernoulli "
        "outcome and not the quality of the expectation. §7 of the README does the portfolio "
        "arithmetic, which is the test an expected-loss model can actually fail."
    )


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
