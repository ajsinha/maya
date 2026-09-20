"""
Step 7 — version 2 of the same model, and everything a second version costs.

    .venv/bin/python case_studies/10-factor-models/add_second_version.py

This is the step the study exists for. Four published factors are added to the market
model. It is registered as **version 2 of the same model**, not as a new model, and MAYA
then makes every consequence of that explicit:

1. ``new_draft`` mints version 2 carrying version 1's document — and the moment the formula
   moves under it, MAYA marks the document for re-review and **refuses to submit the
   version** until somebody has written it again.
2. ``models.diff(ref, 1, 2)`` states what changed *in the mathematics*: four parameters
   added, four features added, and the output equation rewritten with the refs it now uses.
   A text diff of two Python files would have shown a longer line.
3. The **input contract grew by four attributes**, so ``capm_panel`` — which satisfied
   version 1 exactly — no longer satisfies the model. MAYA refuses the warrant and names
   the four missing attributes.
4. Version 2 gets its **own** training warrant, drawn on the same pin with the same split
   and the same seed, so it escrows the same holdout rows — the same content hash, printed
   for both. Version 1's approved parameter set is offered to it and **refused by name**.
5. Version 2's execution warrant is offered version 1's parameter set and refused: a
   parameter set belongs to a model version through the warrant that produced it.

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
    CONTACT,
    CONTRACT_CHECK_V1,
    DRIVERS_V2,
    EXTRA_USERS,
    FORMULA_V2,
    LIVE_V2,
    MODEL,
    MODEL_V1,
    MODEL_V2,
    NARROW,
    NARROW_REF,
    NS,
    PIN_REF,
    ROLES_V2,
    SEED,
    SPLIT,
    TARGET,
    TRADING_DAYS,
    TRUE,
    WARRANT_V1,
    WARRANT_V2,
    WEIGHTS_V2,
    Cast,
    approved_parameters,
    coefficient_table,
    design_matrix,
    find_warrant,
    fit_ols,
    r_squared,
    spec_v2,
    version,
)

TITLE = "Case study 10, step 7 — version 2, the semantic diff, and what version 1 cannot lend"
REF = f"{NS}/{MODEL}"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    mint_version_two(cast, n)
    show_the_diff(cast, n)
    the_contract_that_grew(cast, n)
    drawn, v1_warrant = version_twos_own_warrant(cast, n)
    fit_and_compare(cast, drawn, v1_warrant, n)


def mint_version_two(cast: Cast, n: Narrator) -> None:
    """A second version, and a document that no longer matches its own mathematics."""
    from maya.core.errors import NotApproved

    n.step("Minting version 2 of the same model, and changing the formula under it")
    cast.mona.models.new_draft(REF)
    draft = version(cast.mona, REF, 2)
    n.fact("version 2 state on creation", draft["state"])
    n.fact("inherited maturity", draft["maturity"])
    n.fact("inherited document", f"{len(draft['spec_latex'] or '')} characters of version 1's")
    cast.mona.models.update_draft(REF, formula=FORMULA_V2, roles=ROLES_V2)
    moved = version(cast.mona, REF, 2)
    for number in (1, 2):
        contract = version(cast.mona, REF, number)["input_contract"]
        n.fact(f"input contract, v{number}", ", ".join(c["name"] for c in contract))
    n.fact("document marked for re-review", (moved["spec_state"] or {}).get("needs_review"))
    n.fact("reason", (moved["spec_state"] or {}).get("review_reason"))

    n.step("Version 1's document cannot be version 2's")
    try:
        cast.mona.models.transition(REF, 2, "submit")
    except NotApproved as exc:
        n.refused("submitting version 2 on the document version 1 was approved with", exc)
    n.say("Nothing was deleted and nothing was hidden: the document is still there, and")
    n.say("MAYA's objection is that the mathematics moved after it was written. §8.5.")


def show_the_diff(cast: Cast, n: Narrator) -> None:
    """``models.diff`` — what changed in the *mathematics*, and then version 2's document."""
    n.step("What changed, as MAYA reads it — not as a text diff reads it")
    diff = cast.mgr.models.diff(REF, 1, 2)
    for statement in diff["statements"]:
        n.say(f"• {statement}")
    n.fact("code artifact changed", diff["artifact_changed"])
    n.fact("document changed", diff["spec_changed"])
    n.say("")
    n.say("Read the last statement again. The symbol 'beta' is in both versions, with the")
    n.say("same name, type and role, so no diff will report it as changed — and yet what")
    n.say("it means has changed completely: it is now the market exposure holding four")
    n.say("other exposures fixed. MAYA cannot say that for you. What it can say, and does,")
    n.say("is that the equation beta sits in now uses cma, hml, rmw and smb, which is the")
    n.say("fact from which a reviewer draws that conclusion. A line-by-line diff of two")
    n.say("Python files would have reported one line longer than before.")

    n.step("Writing version 2's own document, and getting it approved")
    cast.mona.models.update_draft(REF, spec_latex=spec_v2())
    cast.mona.models.transition(REF, 2, "submit")
    cast.mgr.models.transition(REF, 2, "approve")
    v2 = version(cast.mgr, REF, 2)
    n.fact("version 2", f"{v2['state']}, maturity {v2['maturity']}")
    n.fact("version 1", f"{version(cast.mgr, REF, 1)['state']} — still approved, still live")


def the_contract_that_grew(cast: Cast, n: Narrator) -> None:
    """One feature set, two versions, two answers — which is what a contract change means."""
    from maya.core.errors import ContractMismatch

    n.step("The narrow panel satisfied version 1 exactly")
    check = cast.devi.training.create(
        NS, CONTRACT_CHECK_V1, MODEL_V1, NARROW_REF, spec={"target": TARGET, "seed": SEED}
    )
    n.fact(f"{NARROW} against v1's contract", check["contract_report"]["ok"])
    n.fact("mapping", check["contract_report"]["mapping"])
    n.say("(a draft warrant, drawn to ask the question and never submitted — its own")
    n.say(" leakage certificate is refused for the reason step 4 explained)")

    n.step("And does not satisfy version 2's")
    try:
        cast.devi.training.create(
            NS, "ff5_on_capm_panel", MODEL_V2, NARROW_REF, spec={"target": TARGET, "seed": SEED}
        )
    except ContractMismatch as exc:
        n.refused("drawing version 2's warrant on the panel version 1 was happy with", exc)
    n.say("This is what an input contract changing between versions means in practice.")
    n.say("Every feature set, every pin and every consumer that satisfied version 1 has to")
    n.say("be re-checked against version 2, and MAYA does the checking at warrant time —")
    n.say("by name, before anything is fitted — rather than at three in the morning.")


def version_twos_own_warrant(cast: Cast, n: Narrator) -> tuple[dict[str, Any], dict[str, Any]]:
    """Its own warrant, on the same escrowed rows — and a parameter set it cannot borrow."""
    from maya.core.errors import ValidationFailed

    n.step("Version 2's own training warrant, on the same pin, split and seed")
    v1_warrant = find_warrant(cast.devi, WARRANT_V1)
    drawn = cast.devi.training.create(
        NS,
        WARRANT_V2,
        MODEL_V2,
        PIN_REF,
        spec={
            "target": TARGET,
            "objective": "attribute realised daily excess return to five published factors",
            "metrics": ["rmse", "mae"],
            "seed": SEED,
            "split": SPLIT,
            "leakage_justification": v1_warrant["spec"]["leakage_justification"],
        },
    )
    n.fact("leakage status", drawn["leakage_certificate"]["status"])
    n.fact("contract satisfied", drawn["contract_report"]["ok"])
    n.fact("holdout rows, v1", f"{v1_warrant['holdout_rows']:,}")
    n.fact("holdout rows, v2", f"{drawn['holdout_rows']:,}")
    n.fact("holdout hash, v1", f"{(v1_warrant['holdout_hash'] or '')[:24]}…")
    n.fact("holdout hash, v2", f"{(drawn['holdout_hash'] or '')[:24]}…")
    n.fact("the same escrowed rows", v1_warrant["holdout_hash"] == drawn["holdout_hash"])
    n.say("MAYA assigns splits by hashing (seed, index key), so the same pin with the same")
    n.say("seed escrows the same rows, and the two versions' holdout scores are comparable")
    n.say("by construction rather than by assurance.")

    n.step("Version 1's parameters are not version 2's")
    v1_parameters = approved_parameters(v1_warrant)
    n.fact("version 1's approved set", dict(v1_parameters["values"]))
    warrant = cast.devi.warrant(drawn["id"])
    try:
        warrant.upload_parameters(dict(v1_parameters["values"]), data_checksum="0" * 64)
    except ValidationFailed as exc:
        n.refused("uploading version 1's alpha and beta against version 2's warrant", exc)
    n.say("A parameter set is validated against the declared parameters of the model")
    n.say("version its warrant names. Two numbers where six are declared is not a")
    n.say("partially-fitted model; it is not a parameter set for this model at all.")
    return drawn, v1_warrant


def fit_and_compare(
    cast: Cast, drawn: dict[str, Any], v1_warrant: dict[str, Any], n: Narrator
) -> None:
    """The fit, and the two versions' holdout scores on the same escrowed rows."""
    n.step("Fitting version 2 on the same training rows")
    warrant = cast.devi.warrant(drawn["id"])
    with warrant.data() as ds:
        frame = ds.frame
        checksum = ds.checksum
        train = frame[frame["_split"] == "train"]
        validation = frame[frame["_split"] == "validation"]
        design = design_matrix(train, DRIVERS_V2)
        fit = fit_ols(design, train[TARGET].astype(float).to_numpy(), train["date"])
        values = dict(zip(WEIGHTS_V2, (round(float(b), 8) for b in fit["beta"])))
        r2_validation = r_squared(
            validation[TARGET].astype(float).to_numpy(),
            design_matrix(validation, DRIVERS_V2) @ fit["beta"],
        )
    n.fact("training rows / dates", f"{fit['n']:,} / {fit['clusters']}")
    for line in coefficient_table(WEIGHTS_V2, fit, TRUE):
        n.say(line)
    n.fact("R² train / validation", f"{fit['r2']:.4f} / {r2_validation:.4f}")
    alpha = float(fit["beta"][0])
    n.fact("alpha, annualised", f"{alpha * TRADING_DAYS:+.2%}")
    n.fact("t on alpha, classical", f"{alpha / float(fit['se'][0]):+.2f}")
    n.fact("t on alpha, clustered", f"{alpha / float(fit['se_clustered'][0]):+.2f}")
    n.say("Version 1 reported an annualised alpha of about fifteen per cent with a")
    n.say("clustered t above two. Version 2, on the same rows, reports an alpha that is")
    n.say("indistinguishable from zero — which is what the generating process actually")
    n.say("used. The classical and clustered standard errors have also converged, because")
    n.say("the common factor that separated them is now in the model instead of in the")
    n.say("residual.")

    n.step("Approving version 2's parameters, tied to the data MAYA issued")
    tied = warrant.upload_parameters(
        values,
        data_checksum=checksum,
        metrics={"r2_train": round(fit["r2"], 6), "r2_validation": round(r2_validation, 6)},
    )
    n.fact("verified against a download MAYA issued", tied["verified_data"])
    cast.devi.training.parameter_transition(tied["id"], "submit")
    cast.mgr.training.parameter_transition(tied["id"], "approve")

    n.step("Blind scoring, on the same escrowed rows version 1 was scored on")
    scored = warrant.score_holdout(parameter_set_id=tied["id"])
    # Version 1's two attempts, read back off its warrant: the fitted one carries a
    # parameter set reference, the zero benchmark was scored from loose values and does not.
    v1_scores = cast.devi.training.get(v1_warrant["id"])["holdout_scores"]
    v1_rmse = min(s["metrics"]["rmse"] for s in v1_scores if s["parameter_set_id"])
    naive_rmse = min(s["metrics"]["rmse"] for s in v1_scores if not s["parameter_set_id"])
    n.fact("holdout rows", f"{scored['metrics']['rows']:,}")
    n.fact("RMSE, predicting zero", f"{naive_rmse:.6f}")
    n.fact("RMSE, version 1", f"{v1_rmse:.6f}")
    n.fact("RMSE, version 2", f"{scored['metrics']['rmse']:.6f}")
    n.fact(
        "version 2 against version 1",
        f"{1.0 - scored['metrics']['rmse'] / v1_rmse:.2%} lower holdout RMSE",
    )
    n.fact(
        "version 2 against saying nothing",
        f"{1.0 - scored['metrics']['rmse'] / naive_rmse:.2%} lower holdout RMSE",
    )
    n.say("The extra factors are worth having, and the amount by which they are worth")
    n.say("having is smaller than the collapse in alpha suggests. Both numbers are the")
    n.say("finding; a study that reported only one of them would be advocacy.")

    take_version_two_live(cast, drawn, v1_warrant, tied["id"], n)


def take_version_two_live(
    cast: Cast,
    drawn: dict[str, Any],
    v1_warrant: dict[str, Any],
    parameter_set_id: str,
    n: Narrator,
) -> None:
    """Its own execution warrant, and the refusal when version 1's parameters are offered."""
    from maya.core.errors import ValidationFailed

    n.step("Sealing version 2's warrant, and taking it live in its own right")
    cast.devi.training.transition(drawn["id"], "submit")
    cast.mgr.training.transition(drawn["id"], "approve")
    cast.mgr.training.seal(drawn["id"])
    try:
        cast.mgr.execution.create(
            NS,
            LIVE_V2,
            training_warrant_id=drawn["id"],
            parameter_set_id=approved_parameters(v1_warrant)["id"],
            spec={"environments": ["dev", "uat"], "contact": CONTACT},
        )
    except ValidationFailed as exc:
        n.refused("running version 2 on the parameter set fitted under version 1's warrant", exc)
    ew = cast.mgr.execution.create(
        NS,
        LIVE_V2,
        training_warrant_id=drawn["id"],
        parameter_set_id=parameter_set_id,
        spec={
            "environments": ["dev", "uat"],
            "contact": CONTACT,
            "covenants": [
                {"kind": "input_psi", "attr": "mktExcess", "max": 0.25},
                {"kind": "output_range", "min": -0.5, "max": 0.5},
            ],
        },
    )
    cast.mgr.execution.transition(ew["id"], "submit")
    cast.lara.execution.transition(ew["id"], "approve")
    cast.mgr.execution.seal(ew["id"])
    n.fact("live", f"{NS}/{LIVE_V2} — {cast.devi.execution.bundle(ew['id'], 'uat')['status']}")
    n.fact("version 1's warrant", "still live, still serving; step 8 is about that")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
