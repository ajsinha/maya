"""
Step 6 — into production, with a covenant about the tape rather than the model.

    .venv/bin/python case_studies/02-mortgage-cashflow/get_execution_warrant.py

A scheduled cashflow model is exactly as right as the tape it reads. So the covenant that
matters is not about the model's behaviour at all: it is about whether the tape arrived.
The step declares a staleness covenant of forty days and an output range, takes the model
live, then reports a batch computed on a tape seventy-five days old. The warrant suspends
itself and names the person to call.

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

TITLE = "Case study 2, step 6 — live, and a tape that did not arrive"


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
                {"kind": "staleness_days", "attr": "balance", "max": 40},
                {"kind": "output_range", "min": 0.0, "max": 20_000.0},
            ],
        },
    )
    for covenant in ew["spec"]["covenants"]:
        n.fact(covenant["kind"], {k: v for k, v in covenant.items() if k != "kind"})

    n.step("Submitted by one model manager, approved by another")
    cast.mgr.execution.transition(ew["id"], "submit")
    cast.lara.execution.transition(ew["id"], "approve")
    cast.mgr.execution.seal(ew["id"])
    live = cast.devi.execution.bundle(ew["id"], "prod")
    n.fact("bundle", f"{live['status']}, {live['attestation']}")
    n.fact(
        "manifest",
        f"{len(cast.devi.execution.manifest_pdf(ew['id'])['data']) / 1000:.0f} kB of typeset PDF",
    )

    n.step("A batch computed on a tape seventy-five days old")
    breach = cast.devi.execution.report(
        ew["id"], environment="prod", rows=29_400, input_stats={"balance": {"age_days": 75}}
    )
    n.fact("warrant", breach["status"])
    try:
        cast.devi.execution.bundle(ew["id"], "prod")
    except MayaError as exc:
        n.refused("running the model on a tape nobody refreshed", exc)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
