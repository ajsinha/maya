"""
Step 6 — into production, with a covenant about where the surface is allowed to be used.

    .venv/bin/python case_studies/05-option-pricing/get_execution_warrant.py

A calibrated model is trustworthy exactly where it was calibrated. This surface knows
maturities from one month to one year and strikes within about 20 per cent of spot, because
that is what the chain quoted; a two-year request is priced by extrapolating a step function
off the edge of the data, confidently and wrongly. So the covenants are about the region:

* ``input_range`` on ``T`` — the maturities the calibration covered;
* ``input_psi`` on ``moneyness`` — with a baseline MAYA takes from this warrant's own
  quotes, so "drift" means away from the strikes the surface was marked on rather than away
  from whatever last week looked like.

The warrant names the surface parameter set, is submitted by one model manager and approved
by another, then a desk system reports a batch that asks for two-year options. The warrant
suspends itself and names who to call.

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
    parameter_set,
)

TITLE = "Case study 5, step 6 — live, and a request off the edge of the surface"
SURFACE_SET = "surface-2509"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError

    cast = Cast(maya)
    warrant = find_warrant(cast.mgr, WARRANT)
    surface = parameter_set(warrant, SURFACE_SET)

    n.step("Drawing the execution warrant on the surface calibration")
    ew = cast.mgr.execution.create(
        NS,
        LIVE,
        training_warrant_id=warrant["id"],
        parameter_set_id=surface["id"],
        spec={
            "environments": ["dev", "prod"],
            "contact": CONTACT,
            "covenants": [
                {"kind": "input_range", "attr": "T", "min": 0.02, "max": 1.05},
                {"kind": "input_psi", "attr": "moneyness", "max": 0.25},
            ],
        },
    )
    n.fact("parameter set", f"{SURFACE_SET} ({surface['id'][:8]}…)")
    for covenant in ew["spec"]["covenants"]:
        shown = {k: v for k, v in covenant.items() if k not in ("kind", "baseline", "bin_edges")}
        n.fact(covenant["kind"], shown)
    psi = next(c for c in ew["spec"]["covenants"] if c["kind"] == "input_psi")
    n.fact("PSI baseline", f"{len(psi['baseline'])} bins fixed from the warrant's own quotes")
    n.say("One execution warrant runs one parameter set: the flat calibration is approved")
    n.say("and never live, and another underlying's surface would be another warrant.")

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

    n.step("A desk system asks for two-year options")
    breach = cast.devi.execution.report(
        ew["id"],
        environment="prod",
        rows=1_240,
        input_stats={"T": {"min": 0.0833, "max": 2.5}, "moneyness": {"min": 0.82, "max": 1.19}},
    )
    n.fact("warrant", breach["status"])
    for event in breach.get("breaches", []):
        n.say(f"  {event['detail']}")
    try:
        cast.devi.execution.bundle(ew["id"], "prod")
    except MayaError as exc:
        n.refused("pricing a maturity the surface was never calibrated on", exc)

    n.step("Reinstated, with the reason on the record")
    cast.admin.execution.reinstate(
        ew["id"], reason="the two-year request came from a test harness; the feed is unchanged"
    )
    n.fact("warrant", cast.devi.execution.get(ew["id"])["status"])
    n.fact("custody", ", ".join(e["event"] for e in cast.devi.execution.get(ew["id"])["custody"]))


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
