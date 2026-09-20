"""
Step 6 — into production, watched from the outside.

    .venv/bin/python case_studies/07-neural-network/get_execution_warrant.py

For a scorecard, covenants are one control among several: a reviewer can also read the
coefficients and say whether they still make sense. For a network nobody can read they are
**the** control: what §29.10 says of a *bought* black box, that "the covenants of §29.5
become the primary control because they are the only one available", is just as true of one
built in-house. So they are chosen with more care here:

* ``input_psi`` on ``amount_ratio`` — the driver the two fraud patterns live at the ends
  of. If the population of that ratio moves, every conjunction the network learned is being
  asked about a different book. The baseline is taken from this warrant's own training data
  and fixed at creation, so drift means drift from what was fitted.
* ``input_null_rate`` on ``tenure_months`` — the fragile feed. The profile file is monthly
  and carried as-of; if it fails to arrive the column goes null, and a network handed nulls
  does not complain, it just scores.
* ``output_range`` on ``fraud_score`` — a logistic output is a probability, so anything
  outside [0, 1] means the code running in production is not the code that was approved.
  It is a weak check, and it is the only end-to-end one available: there is no formula to
  re-evaluate and MAYA will not run the artifact.

The drift is not invented. The batch's histogram is computed from the warrant's own rows,
binned on the covenant's own edges, and the second batch is those rows with every ratio
inflated — an acquirer-mix change, the commonest way this feed moves. The PSI in the
suspension message is MAYA's own arithmetic.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import network  # noqa: E402
from maya_demo import Narrator, step_script  # noqa: E402
from study import (  # noqa: E402
    CONTACT,
    EXTRA_USERS,
    LIVE,
    NS,
    WARRANT,
    Cast,
    approved_parameters,
    find_warrant,
)

TITLE = "Case study 7, step 6 — the execution warrant, and drift it can still see"
COVENANTS = [
    {"kind": "input_psi", "attr": "amount_ratio", "max": 0.25},
    {"kind": "input_null_rate", "attr": "tenure_months", "max": 0.02},
    {"kind": "output_range", "attr": "fraud_score", "min": 0.0, "max": 1.0},
]


def batch(frame: Any, values: dict[str, Any], edges: list[float], inflate: float) -> dict[str, Any]:
    """One reported batch: the histogram MAYA will compare, and the scores it produced."""
    rows = frame.copy()
    rows["amount_ratio"] = rows["amount_ratio"].astype(float) * inflate
    counts, _ = np.histogram(rows["amount_ratio"].to_numpy(), bins=edges)
    scores = np.asarray(network.Model().predict(rows, values, None), dtype=float)
    return {
        "rows": int(len(rows)),
        "input_stats": {
            "amount_ratio": {"histogram": counts.tolist(), "null_rate": 0.0},
            "tenure_months": {"null_rate": 0.0},
        },
        "output_stats": {"fraud_score": {"min": float(scores.min()), "max": float(scores.max())}},
    }


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError

    cast = Cast(maya)
    warrant = find_warrant(cast.mgr, WARRANT)
    parameters = approved_parameters(warrant)

    n.step("Drawing the execution warrant from the sealed training warrant")
    ew = cast.mgr.execution.create(
        NS,
        LIVE,
        training_warrant_id=warrant["id"],
        parameter_set_id=parameters["id"],
        spec={
            "environments": ["dev", "prod"],
            "contact": CONTACT,
            "limits": {"max_rows_per_day": 200_000},
            "covenants": COVENANTS,
        },
    )
    n.fact("environments", ew["spec"]["environments"])
    n.fact("accountable", ew["spec"]["contact"])
    n.fact("parameter set it runs", f"{parameters['id'][:8]}… ({parameters['state']})")
    psi = next(c for c in ew["spec"]["covenants"] if c["kind"] == "input_psi")
    n.fact("PSI baseline", f"{len(psi['baseline'])} bins, fixed from this warrant's own data")
    n.fact("bin edges", [round(float(e), 3) for e in psi["bin_edges"]])
    n.say("The model declares parameters, so MAYA would not let this warrant name none: the")
    n.say("weights are the model here, and an unapproved set is an unapproved model.")

    n.step("Two people, because the submitter is not the approver")
    cast.mgr.execution.transition(ew["id"], "submit")
    cast.lara.execution.transition(ew["id"], "approve")
    cast.mgr.execution.seal(ew["id"])
    live = cast.devi.execution.bundle(ew["id"], "prod")
    n.fact("bundle", f"{live['status']}, {live['attestation']}")
    n.fact(
        "manifest", f"{len(cast.devi.execution.manifest_pdf(ew['id'])['data']) / 1000:.0f} kB PDF"
    )

    n.step("A batch of the book it was fitted on")
    with cast.devi.warrant(warrant["id"]).data() as ds:
        frame = ds.frame
    healthy = batch(frame, parameters["values"], psi["bin_edges"], 1.0)
    reported = cast.devi.execution.report(ew["id"], environment="prod", **healthy)
    n.fact("rows reported", f"{healthy['rows']:,}")
    n.fact("score range", [round(v, 4) for v in healthy["output_stats"]["fraud_score"].values()])
    n.fact("warrant", reported["status"])

    n.step("The same book with every amount ratio inflated: an acquirer-mix change")
    drifted = batch(frame, parameters["values"], psi["bin_edges"], 1.8)
    breach = cast.devi.execution.report(ew["id"], environment="prod", **drifted)
    n.fact("warrant", breach["status"])
    for broken in breach["breaches"]:
        n.say(f"breach: {broken['detail']}")
    try:
        cast.devi.execution.bundle(ew["id"], "prod")
    except MayaError as exc:
        n.refused("serving the model while it is suspended", exc)
    n.say("Nobody read a weight to find that. The inputs moved, and the model whose inputs")
    n.say("moved was taken out of service by the platform, which is the only kind of")
    n.say("monitoring an unreadable model admits.")

    n.step("Reinstated, with the reason kept")
    cast.admin.execution.reinstate(
        ew["id"],
        "acquirer mix confirmed changed by the payments team; the network is being refitted "
        "under a new warrant and runs in shadow until then",
    )
    n.fact("warrant", cast.devi.execution.bundle(ew["id"], "prod")["status"])
    custody = cast.mgr.execution.get(ew["id"])["custody"]
    n.fact("custody events", ", ".join(c["event"] for c in custody))


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
