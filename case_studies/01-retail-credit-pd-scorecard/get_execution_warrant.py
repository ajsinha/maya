"""
Step 6 — into production, with the covenants that will take it back out.

    .venv/bin/python case_studies/01-retail-credit-pd-scorecard/get_execution_warrant.py

An execution warrant says where the model may run, who is accountable, and what would
make it stop. It is submitted by one model manager and approved by another, because the
person who submits is not the person who approves.

The PSI covenant is declared with no baseline, so MAYA takes the baseline from this
warrant's own training data and fixes it at creation: "drift" then means drift away from
the distribution the model was actually fitted on, not away from whatever last month
happened to look like. The step then reports a batch whose bureau score is 31% null, the
covenant breaks, and the warrant suspends itself and names the person to call.

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
    EXTRA_USERS,
    LIVE,
    NS,
    WARRANT,
    Cast,
    approved_parameters,
    find_warrant,
)

TITLE = "Case study 1, step 6 — the execution warrant, and a covenant breach"
CONTACT = "retail.credit.risk@example.com"


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
            "covenants": [
                {"kind": "input_null_rate", "attr": "bureau", "max": 0.05},
                # No baseline: MAYA takes it from this warrant's own training data and
                # fixes it at creation, so drift is measured against what was fitted.
                {"kind": "input_psi", "attr": "utilisation", "max": 0.25},
            ],
        },
    )
    n.fact("environments", ew["spec"]["environments"])
    n.fact("accountable", ew["spec"]["contact"])
    psi = next(c for c in ew["spec"]["covenants"] if c["kind"] == "input_psi")
    n.fact("PSI baseline", f"{len(psi['baseline'])} bins, fixed from the training data")

    n.step("Two people, because the submitter is not the approver")
    cast.mgr.execution.transition(ew["id"], "submit")
    cast.lara.execution.transition(ew["id"], "approve")
    cast.mgr.execution.seal(ew["id"])
    live = cast.devi.execution.bundle(ew["id"], "prod")
    n.fact("bundle", f"{live['status']}, {live['attestation']}")
    n.fact(
        "manifest", f"{len(cast.devi.execution.manifest_pdf(ew['id'])['data']) / 1000:.0f} kB PDF"
    )

    n.step("A production batch with a third of the bureau scores missing")
    breach = cast.devi.execution.report(
        ew["id"], environment="prod", rows=25_000, input_stats={"bureau": {"null_rate": 0.31}}
    )
    n.fact("warrant", breach["status"])
    try:
        cast.devi.execution.bundle(ew["id"], "prod")
    except MayaError as exc:
        n.refused("serving the model while it is suspended", exc)

    n.step("Reinstated, with the reason kept")
    cast.admin.execution.reinstate(
        ew["id"], "bureau file arrived late; the feed is confirmed restored"
    )
    n.fact("warrant", cast.devi.execution.bundle(ew["id"], "prod")["status"])
    custody = cast.mgr.execution.get(ew["id"])["custody"]
    n.fact("custody events", ", ".join(c["event"] for c in custody))


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
