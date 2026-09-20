"""
Step 6 — live, with a covenant on the thing that actually breaks.

    .venv/bin/python case_studies/03-mortgage-prepayment/get_execution_warrant.py

A prepayment model's failure mode is not a bad coefficient. It is a rate environment that
no longer resembles the one the model was fitted in: the coefficient on incentive was
identified by one down-and-up cycle, and a book sitting two points further in the money
than anything in that window is being extrapolated, not predicted.

So the covenant that matters is a population-shift test on the incentive's own inputs, with
the baseline taken from this warrant's own training data.

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
    EXTRA_USERS,
    LIVE,
    NS,
    WARRANT,
    Cast,
    approved_parameters,
    find_warrant,
)

TITLE = "Case study 3, step 6 — live, and a rate environment that moved"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError

    cast = Cast(maya)
    warrant = find_warrant(cast.mgr, WARRANT)
    parameters = approved_parameters(warrant)

    n.step("Drawing the execution warrant")
    ew = cast.mgr.execution.create(
        NS,
        LIVE,
        training_warrant_id=warrant["id"],
        parameter_set_id=parameters["id"],
        spec={
            "environments": ["dev", "prod"],
            "contact": CONTACT,
            "covenants": [
                # The baseline is taken from this warrant's own training data, so "shifted"
                # means shifted away from what the coefficients were estimated on.
                {"kind": "input_psi", "attr": "mktRate", "max": 0.25},
                {"kind": "input_psi", "attr": "wac", "max": 0.25},
                {"kind": "output_range", "min": 0.0, "max": 0.5},
            ],
        },
    )
    for covenant in ew["spec"]["covenants"]:
        shown = {k: v for k, v in covenant.items() if k not in ("kind", "baseline", "bin_edges")}
        bins = f", baseline of {len(covenant['baseline'])} bins" if covenant.get("baseline") else ""
        n.fact(covenant["kind"], f"{shown}{bins}")

    n.step("Approved by a second model manager, then sealed")
    cast.mgr.execution.transition(ew["id"], "submit")
    cast.lara.execution.transition(ew["id"], "approve")
    cast.mgr.execution.seal(ew["id"])
    live = cast.devi.execution.bundle(ew["id"], "prod")
    n.fact("bundle", f"{live['status']}, {live['attestation']}")

    n.step("A month where the market rate has moved out of the fitted range")
    # A PSI covenant compares a histogram against the baseline's fixed bins. Reporting one
    # with every loan in the lowest bin is what a rate shock looks like to a covenant: the
    # whole book has moved into a corner of the distribution the model was fitted on.
    shock = [31_000] + [0] * 9
    moved = cast.devi.execution.report(
        ew["id"],
        environment="prod",
        rows=31_000,
        input_stats={"mktRate": {"histogram": shock}},
    )
    n.fact("warrant", moved["status"])
    for breach in moved.get("breaches", []):
        n.say(f"{breach['kind']} on '{breach.get('attr')}': {breach.get('detail')}")
    try:
        cast.devi.execution.bundle(ew["id"], "prod")
    except MayaError as exc:
        n.refused("serving a prepayment forecast in a rate environment it never saw", exc)

    n.step("Reinstated only with a reason that becomes part of the record")
    cast.admin.execution.reinstate(
        ew["id"],
        "refinancing wave confirmed; forecast accepted as a lower bound pending a refit on "
        "the 2026 window, and the ALM committee has been told",
    )
    n.fact("warrant", cast.devi.execution.bundle(ew["id"], "prod")["status"])
    n.fact("custody", ", ".join(e["event"] for e in cast.mgr.execution.get(ew["id"])["custody"]))


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
