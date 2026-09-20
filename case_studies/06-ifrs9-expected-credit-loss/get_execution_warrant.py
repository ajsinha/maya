"""
Step 8 — an allowance in production, with a covenant on the stage population.

    .venv/bin/python case_studies/06-ifrs9-expected-credit-loss/get_execution_warrant.py

The output of this model is a line in the financial statements, so what would make it stop
is not quite what would stop a pricing model. The covenant that matters here watches the
**share of the book in stage 2**: a jump in it moves the allowance by the lifetime multiple
on every account that crossed, which is the largest single lever in the calculation and the
one nobody decided this quarter.

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
    find_warrant,
    parameter_sets,
)

TITLE = "Case study 6, step 8 — live, and the stage population as the control"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError

    cast = Cast(maya)
    warrant = find_warrant(cast.mgr, WARRANT)
    sets = parameter_sets(warrant)
    n.step("Which of the five approved sets goes live")
    for alias, ps in sorted(sets.items()):
        n.fact(alias or "the committee's", f"{ps['id'][:8]}… {ps['values']}")
    n.say(
        "Two committee sets are approved and only one can be live: an execution warrant runs "
        "exactly one parameter set, so the superseded judgement stays on the record and out of "
        "production."
    )

    n.step("Drawing the execution warrant")
    ew = cast.mgr.execution.create(
        NS,
        LIVE,
        training_warrant_id=warrant["id"],
        parameter_set_id=sets["pd"]["id"],
        spec={
            "environments": ["dev", "prod"],
            "contact": CONTACT,
            "covenants": [
                # An allowance cannot be negative and, on this book, cannot plausibly exceed
                # the largest single commitment.
                {"kind": "output_range", "min": 0.0, "max": 400_000.0},
                {"kind": "input_psi", "attr": "arrears", "max": 0.25},
                {"kind": "input_null_rate", "attr": "pdOrigination", "max": 0.0},
            ],
        },
    )
    for covenant in ew["spec"]["covenants"]:
        shown = {k: v for k, v in covenant.items() if k not in ("kind", "baseline", "bin_edges")}
        n.fact(covenant["kind"], shown)
    n.say(
        "The null-rate covenant is set at zero on purpose. The stage test divides by the "
        "origination probability, so a single missing value is not a degraded estimate but an "
        "account with no stage at all."
    )

    n.step("Two people, then sealed")
    cast.mgr.execution.transition(ew["id"], "submit")
    cast.lara.execution.transition(ew["id"], "approve")
    cast.mgr.execution.seal(ew["id"])
    live = cast.devi.execution.bundle(ew["id"], "prod")
    n.fact("bundle", f"{live['status']}, {live['attestation']}")
    n.fact(
        "manifest",
        f"{len(cast.devi.execution.manifest_pdf(ew['id'])['data']) / 1000:.0f} kB of typeset PDF",
    )
    n.say(
        "That PDF is what an auditor asks for, and it names the parameter set that produced the figure."
    )

    n.step("A quarter where the arrears distribution has moved")
    # The baseline's bins are quantile bins of the training data, and arrears is a small
    # integer, so there are fewer of them than a continuous driver would give. The reported
    # histogram has to be over the same bins, which is the point of fixing them at creation.
    psi = next(c for c in ew["spec"]["covenants"] if c["kind"] == "input_psi")
    bins = len(psi["baseline"])
    n.fact("baseline bins", f"{bins} (arrears takes few distinct values)")
    shock = [0] * (bins - 1) + [12_480]
    breach = cast.devi.execution.report(
        ew["id"], environment="prod", rows=12_480, input_stats={"arrears": {"histogram": shock}}
    )
    n.fact("warrant", breach["status"])
    for item in breach.get("breaches", []):
        n.say(f"{item['kind']}: {item.get('detail')}")
    try:
        cast.devi.execution.bundle(ew["id"], "prod")
    except MayaError as exc:
        n.refused("computing an allowance on a book that no longer resembles the fitted one", exc)

    n.step("Reinstated, with what was decided")
    cast.admin.execution.reinstate(
        ew["id"],
        "arrears shift confirmed against the servicing reconciliation; the allowance is "
        "accepted for the quarter with a management overlay recorded separately, and a refit "
        "on the 2026 window is scheduled before the year-end accounts",
    )
    n.fact("warrant", cast.devi.execution.bundle(ew["id"], "prod")["status"])
    n.fact("custody", ", ".join(e["event"] for e in cast.mgr.execution.get(ew["id"])["custody"]))


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
