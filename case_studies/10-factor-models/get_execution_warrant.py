"""
Step 6 — version 1 goes live, in dev and uat and nowhere else.

    .venv/bin/python case_studies/10-factor-models/get_execution_warrant.py

The environments list is the interesting field. Every other study in this library takes its
model to ``prod``. This one must not, and the reason is the leakage exception step 4
recorded: a model whose drivers are published a month after the returns they explain can
attribute and cannot forecast, so the only environments it is licensed for are the research
ones. The claim made in prose on the training warrant is enforced here in a field the SDK
checks on every call.

The step also shows the two-person rule as a refusal rather than as a convention: mgr
submits the warrant and then tries to approve it, and MAYA declines because he is the one
who submitted it. lara, a second model manager, approves.

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
    LIVE_V1,
    NS,
    WARRANT_V1,
    Cast,
    approved_parameters,
    find_warrant,
)

TITLE = "Case study 10, step 6 — live in research, refused in production"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError, NotApproved, PermissionDenied

    cast = Cast(maya)
    warrant = find_warrant(cast.mgr, WARRANT_V1)
    parameters = approved_parameters(warrant)

    n.step("Drawing the execution warrant from the sealed training warrant")
    ew = cast.mgr.execution.create(
        NS,
        LIVE_V1,
        training_warrant_id=warrant["id"],
        parameter_set_id=parameters["id"],
        spec={
            "environments": ["dev", "uat"],
            "contact": CONTACT,
            "covenants": [
                # No baseline: MAYA fixes it from this warrant's own training data, so
                # "the market has moved" means moved away from what alpha was measured in.
                {"kind": "input_psi", "attr": "mktExcess", "max": 0.25},
                {"kind": "output_range", "min": -0.5, "max": 0.5},
            ],
        },
    )
    n.fact("environments", ew["spec"]["environments"])
    n.fact("accountable", ew["spec"]["contact"])
    psi = next(c for c in ew["spec"]["covenants"] if c["kind"] == "input_psi")
    n.fact("PSI baseline", f"{len(psi['baseline'])} bins, fixed from the training data")
    n.fact("parameter set", f"{parameters['id'][:8]}… (exactly one, §9.2)")

    n.step("Whoever submits is not whoever approves")
    cast.mgr.execution.transition(ew["id"], "submit")
    try:
        cast.mgr.execution.transition(ew["id"], "approve")
    except (NotApproved, PermissionDenied) as exc:
        n.refused("mgr approving the warrant mgr submitted", exc)
    cast.lara.execution.transition(ew["id"], "approve")
    cast.mgr.execution.seal(ew["id"])
    live = cast.devi.execution.bundle(ew["id"], "uat")
    n.fact("bundle in uat", f"{live['status']}, {live['attestation']}")
    n.fact(
        "manifest", f"{len(cast.devi.execution.manifest_pdf(ew['id'])['data']) / 1000:.0f} kB PDF"
    )

    n.step("And in production, which this model is not licensed for")
    try:
        cast.devi.execution.bundle(ew["id"], "prod")
    except (PermissionDenied, MayaError) as exc:
        n.refused("running an attribution model in production", exc)
    n.say("A factor model whose inputs are published a month late cannot be used to")
    n.say("forecast, and the environment list is where that sentence stops being prose.")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
