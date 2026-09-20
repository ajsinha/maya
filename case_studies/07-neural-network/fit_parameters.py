"""
Step 5 — the fit, the determinism claim, the challenger, and the refusal to score.

    .venv/bin/python case_studies/07-neural-network/fit_parameters.py

Four things happen here, and the last one is what the study is for.

**Determinism.** The network is fitted twice on the same rows with the seed the warrant
declares, and the 209 weights are compared value by value. Then it is fitted a third time
with a different seed, which is the honest half of the claim: the weights move a long way
and the performance does not, so "the weights" are one arbitrary member of a family and
only the seed pins which one.

**The challenger.** A logistic regression on the same six drivers and the same rows. The
gap between the two AUCs is the only honest justification for accepting a model nobody can
read, and it is uploaded with the parameters as the justification of record.

**The weights as a file.** A fit ends in whatever the trainer wrote. A pickle of the
weights is refused by MAYA's parameter reader — it would run code — and the ``.npz`` is
read into named values, with the file's own sha256 recorded beside them.

**The refusal.** ``score_holdout`` on a declared black box is refused by name: MAYA
evaluates a model's formula IR and this model has none (ADR-007). So the escrowed holdout —
5,328 rows, hashed on the warrant — cannot be scored by MAYA, and cannot be scored by the
desk either, because the desk never received those rows. Every number on this parameter set
is therefore *asserted by devi against a checksum*, which is a weaker claim than case study
1's blind score, and the README says exactly how much weaker.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import hashlib
import pickle
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import network  # noqa: E402
from maya_demo import Narrator, step_script  # noqa: E402
from study import (  # noqa: E402
    DRIVERS,
    EXTRA_USERS,
    NS,
    SEED,
    TARGET,
    WARRANT,
    Cast,
    Context,
    as_npz,
    auc,
    crafted_design,
    find_warrant,
    fit_logistic,
    logistic_design,
)

TITLE = "Case study 7, step 5 — the fit, the seed, the challenger, and the refusal"


def fit_once(frame: Any, seed: int) -> dict[str, Any]:
    """One fit of the network on one frame, entirely outside MAYA (ADR-007)."""
    return network.Model().fit(frame, frame[TARGET].astype(float).to_numpy(), Context(seed))


def identical(left: dict[str, Any], right: dict[str, Any]) -> tuple[bool, float]:
    """Whether two fits produced the same numbers, and how far apart they are."""
    same = all(np.array_equal(np.asarray(left[k]), np.asarray(right[k])) for k in left)
    worst = max(float(np.abs(np.asarray(left[k]) - np.asarray(right[k])).max()) for k in left)
    return same, worst


def scores(frame: Any, params: dict[str, Any]) -> np.ndarray:
    return np.asarray(network.Model().predict(frame, params, None), dtype=float)


def determinism(n: Narrator, train: Any, validation: Any) -> dict[str, Any]:
    """Fit twice with the declared seed, then once with another, and report all three."""
    n.step("Fitting, by mini-batch gradient descent, with the seed the warrant declares")
    started = time.perf_counter()
    first = fit_once(train, SEED)
    n.fact("fit", f"{time.perf_counter() - started:.1f}s, seed {SEED}, 209 values")
    n.fact(
        "AUC train / validation",
        f"{auc(train[TARGET].to_numpy(), scores(train, first)):.4f} / "
        f"{auc(validation[TARGET].to_numpy(), scores(validation, first)):.4f}",
    )

    n.step("The same rows, the same seed, a second time")
    second = fit_once(train, SEED)
    same, worst = identical(first, second)
    n.fact("every one of the 209 values identical", same)
    n.fact("largest difference", f"{worst:.2e}")

    n.step("The same rows, a different seed — the honest half of the claim")
    other = fit_once(train, SEED + 1)
    same_other, worst_other = identical(first, other)
    n.fact("identical", same_other)
    n.fact("largest difference in a weight", f"{worst_other:.3f}")
    n.fact(
        "AUC validation",
        f"{auc(validation[TARGET].to_numpy(), scores(validation, other)):.4f} "
        f"against {auc(validation[TARGET].to_numpy(), scores(validation, first)):.4f}",
    )
    n.say("The same function, near enough, out of very different weights. Reproducibility")
    n.say("here means the seed, the data and the code — never the numbers on their own.")
    return first


def challenger(n: Narrator, train: Any, validation: Any) -> float:
    """A logistic regression on the same rows: the model somebody can read."""
    n.step("What each driver says on its own")
    y = train[TARGET].astype(float).to_numpy()
    for name in DRIVERS:
        n.fact(f"AUC of {name} alone", f"{auc(y, train[name].astype(float).to_numpy()):.4f}")
    n.say("amount_ratio alone ranks card-days no better than a coin: fraud sits at both ends")
    n.say("of it — a cash-out is five times the card's usual largest, card testing a fifth of")
    n.say("it — and one coefficient cannot say 'either end'.")

    n.step("The challenger: a logistic regression on the same six drivers")
    beta = fit_logistic(logistic_design(train), y)
    got = auc(validation[TARGET].to_numpy(), logistic_design(validation) @ beta)
    n.fact("coefficients", dict(zip(("intercept", *DRIVERS), np.round(beta, 3).tolist())))
    n.fact("AUC train / validation", f"{auc(y, logistic_design(train) @ beta):.4f} / {got:.4f}")
    n.say("That gap against the network is the justification of record, and it is uploaded")
    n.say("with the parameters so a reviewer reads both numbers or neither.")

    n.step("And the challenger a fraud analyst would actually write")
    crafted = fit_logistic(crafted_design(train), y)
    with_terms = auc(validation[TARGET].to_numpy(), crafted_design(validation) @ crafted)
    n.fact("six drivers plus three conjunctions, AUC validation", f"{with_terms:.4f}")
    n.say("amount x foreign, night x velocity, and velocity over amount — the conjunctions")
    n.say("the fraud actually has. A readable model that is told them comes this close, so")
    n.say("what the network bought is finding them, not representing them. In a real book")
    n.say("nobody knows them, which is the argument; it is also the argument's whole extent.")
    return got


def carry_the_weights(n: Narrator, values: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """The fitted arrays as the file a trainer leaves behind, read back by MAYA's reader."""
    from maya.core import parameters
    from maya.core.errors import ValidationFailed

    n.step("Carrying 209 numbers: the file a fit actually leaves behind")
    archive = as_npz(values)
    digest = hashlib.sha256(archive).hexdigest()
    n.fact("fit.npz", f"{len(archive):,} bytes, sha256 {digest[:16]}…")
    try:
        parameters.read(pickle.dumps(values, protocol=5), "pickle")
    except ValidationFailed as exc:
        n.refused("the pickle every training script writes", exc)
    read = parameters.read(archive, "npz")
    n.fact("read from the npz", ", ".join(read))
    n.fact("numbers", sum(int(np.asarray(v).size) for v in read.values()))
    n.fact(
        "identical to the fitted arrays",
        all(np.array_equal(np.asarray(read[k]), np.asarray(values[k])) for k in values),
    )
    n.say("MAYA's own reader did that (maya.core.parameters, the codec its CLI runs before")
    n.say("it calls the SDK). The API takes named values, not files, so what reaches the")
    n.say("warrant is the decoded JSON and the file's sha256 in the notes.")
    return read, digest


def upload(n: Narrator, cast: Cast, warrant: Any, read: dict[str, Any], **kw: Any) -> Any:
    """Upload twice: once unable to prove its data, once able."""
    from maya.core.errors import NotApproved

    n.step("Uploading the fit quoting the wrong data checksum")
    untied = warrant.upload_parameters(read, data_checksum="0" * 64)
    n.fact("flag", untied["flag"])
    cast.devi.training.parameter_transition(untied["id"], "submit")
    try:
        cast.mgr.training.parameter_transition(untied["id"], "approve")
    except NotApproved as exc:
        n.refused("approving parameters that cannot prove which data produced them", exc)

    n.step("Uploading it quoting the right one, and approving that")
    tied = warrant.upload_parameters(read, **kw)
    n.fact("verified against a download MAYA issued", tied["verified_data"])
    n.fact("values hash", f"{tied['values_hash'][:16]}… over all 209 numbers")
    n.fact("parameter schema MAYA recorded", tied["param_schema"])
    n.say("Empty — and the IR names eight parameters. For a black box MAYA records no")
    n.say("schema and checks no bounds, which is a finding, not a design: see the README.")
    cast.devi.training.parameter_transition(tied["id"], "submit")
    cast.mgr.training.parameter_transition(tied["id"], "approve")
    n.fact("parameter set", f"{tied['id'][:8]}… approved by mgr")
    return tied


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import ValidationFailed

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
        n.fact("rows with a missing driver", int(frame[list(DRIVERS)].isna().any(axis=1).sum()))
        n.fact("data checksum", f"{checksum[:16]}…")
        train = frame[frame["_split"] == "train"]
        validation = frame[frame["_split"] == "validation"]
        n.fact(
            "train / validation",
            f"{len(train):,} rows with {int(train[TARGET].sum())} confirmed frauds, "
            f"{len(validation):,} with {int(validation[TARGET].sum())}",
        )
        fitted = determinism(n, train, validation)
        challenger_auc = challenger(n, train, validation)
        metrics = {
            "auc_train": round(auc(train[TARGET].to_numpy(), scores(train, fitted)), 4),
            "auc_validation": round(
                auc(validation[TARGET].to_numpy(), scores(validation, fitted)), 4
            ),
            "auc_validation_logistic_challenger": round(challenger_auc, 4),
            "rows_fitted": int(len(train)),
            "computed_by": "the desk, outside MAYA, on the rows this checksum names",
        }

    read, digest = carry_the_weights(n, fitted)
    tied = upload(
        n,
        cast,
        warrant,
        read,
        data_checksum=checksum,
        metrics=metrics,
        notes=f"fit.npz sha256 {digest}; seed {SEED}; AUCs asserted by devi, not computed by MAYA",
    )

    n.step("A parameter set with a whole layer missing")
    n.say("Seven of the eight arrays. The network would run and would compute nonsense.")
    try:
        warrant.upload_parameters({k: v for k, v in read.items() if k != "W2"})
        n.say("NOT REFUSED — an incomplete set of weights was accepted")
    except ValidationFailed as exc:
        n.refused("uploading weights with a whole layer missing", exc)
    n.say(
        "The mathematics is unavailable; the declaration of what parameters it takes is not, "
        "and that declaration is the only thing left to check the weights against. Writing "
        "this study is what found that: MAYA used to skip the check for anything without a "
        "formula body, which is every black box, so this upload was accepted."
    )

    n.step("Asking MAYA to score the escrowed holdout")
    try:
        warrant.score_holdout(parameter_set_id=tied["id"])
    except ValidationFailed as exc:
        n.refused("blind-scoring a declared black box", exc)
    n.fact("escrowed rows", f"{found['holdout_rows']:,}, hash {found['holdout_hash'][:16]}…")
    n.fact(
        "holdout attempts on the warrant", cast.devi.training.get(found["id"])["holdout_attempts"]
    )
    n.say("Nobody can score them. MAYA will not, because it evaluates formulas and there is")
    n.say("no formula; the desk cannot, because it was never given the rows. The escrow is")
    n.say("intact and useless, and every figure above is an assertion with a checksum.")

    n.step("Sealing the warrant: data, certificate, exception and parameters fixed together")
    cast.devi.training.transition(found["id"], "submit")
    cast.mgr.training.transition(found["id"], "approve")
    n.fact("sealed at", cast.mgr.training.seal(found["id"])["sealed_at"])


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
