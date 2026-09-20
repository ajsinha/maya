"""
Step 6 — live, with covenants about where a curve may be asked and what it may answer.

    .venv/bin/python case_studies/11-nelson-siegel-curve/get_execution_warrant.py

A curve is trustworthy between its first and last pillar. Nelson–Siegel will answer for any
maturity at all — it flattens smoothly towards $\\beta_0$ — so a fifty-year point comes back
looking exactly as authoritative as a ten-year point and is supported by nothing. The first
covenant is therefore about the region of the request:

* ``input_range`` on ``tau`` — the maturities the published curve actually covers.

The second is the backstop for the constraint step 5 could not express. A parameter set whose
$\\beta_0 + \\beta_1$ is negative produces negative yields at the front of the curve, and
while per-parameter bounds cannot refuse it, an output covenant notices the consequence:

* ``output_range`` on ``y`` — a zero yield between −50 and 2500 basis points.

That control fires after the parameters are already live, which is exactly the point worth
making about the difference between a bound and a covenant.

The warrant names the curve calibration, is submitted by one model manager and approved by
another. Then the actuarial system asks for a fifty-year discount factor.

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
    CONTACT,
    EXTRA_USERS,
    LIVE,
    MODEL,
    NS,
    WARRANT,
    Cast,
    evaluate_curve,
    find_warrant,
    parameter_set,
)

TITLE = "Case study 11, step 6 — live, and a request off the end of the curve"
CURVE_SET, DESK_SET = "ns-window-2606", "desk-fit-2606"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError, NotApproved

    cast = Cast(maya)
    warrant = find_warrant(cast.mgr, WARRANT)
    curve = parameter_set(warrant, CURVE_SET)

    n.step("Drawing the execution warrant on the curve calibration")
    ew = cast.mgr.execution.create(
        NS,
        LIVE,
        training_warrant_id=warrant["id"],
        parameter_set_id=curve["id"],
        spec={
            "environments": ["dev", "prod"],
            "contact": CONTACT,
            "covenants": [
                {"kind": "input_range", "attr": "tau", "min": 0.02, "max": 30.0},
                {"kind": "output_range", "min": -0.005, "max": 0.25},
            ],
        },
    )
    n.fact("parameter set", f"{CURVE_SET} ({curve['id'][:8]}…)")
    for covenant in ew["spec"]["covenants"]:
        n.fact(covenant["kind"], {k: v for k, v in covenant.items() if k != "kind"})
    n.say("The output covenant names no attribute: this model has one output, so MAYA filled")
    n.say("in 'y' rather than accepting a covenant that watches nothing and can never breach.")

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

    n.step("The calibration the reviewer sent back cannot be taken live either")
    desk = next(ps for ps in warrant["parameter_sets"] if ps["name"] == DESK_SET)
    sent_back = cast.mgr.execution.create(
        NS,
        f"{LIVE}_desk_fit",
        training_warrant_id=warrant["id"],
        parameter_set_id=desk["id"],
        spec={"environments": ["dev"], "contact": CONTACT},
    )
    try:
        cast.mgr.execution.transition(sent_back["id"], "submit")
    except NotApproved as exc:
        n.refused("licensing the factors the buggy implementation produced", exc)
    n.fact("its state", cast.mgr.execution.get(sent_back["id"])["status"])

    n.step("The actuarial system asks for a fifty-year discount factor")
    breach = cast.devi.execution.report(
        ew["id"],
        environment="prod",
        rows=8_400,
        input_stats={"tau": {"min": 0.0833, "max": 50.0}},
        output_stats={"y": {"min": 0.0181, "max": 0.0431}},
    )
    n.fact("warrant", breach["status"])
    for event in breach.get("breaches", []):
        n.say(f"  {event['detail']}")
    ir = cast.devi.models.get(f"{NS}/{MODEL}")["versions"][0]["formula_ir"]
    off_the_end = evaluate_curve(ir, np.array([30.0, 50.0]), curve["values"])
    n.fact(
        "what it would have answered",
        f"30Y {off_the_end[0] * 100:.3f}%, 50Y {off_the_end[1] * 100:.3f}%",
    )
    n.say("Perfectly plausible, inside the output covenant, and supported by nothing: the last")
    n.say("pillar is thirty years and the shape beyond it is an assumption rather than a fit.")
    n.say("Only a covenant about the request could see that, which is why it is there.")
    try:
        cast.devi.execution.bundle(ew["id"], "prod")
    except MayaError as exc:
        n.refused("discounting a maturity the curve was never built on", exc)

    n.step("Reinstated, with the reason on the record")
    cast.admin.execution.reinstate(
        ew["id"],
        reason="the fifty-year request came from a pension valuation run in error; the "
        "curve team will publish a 40Y and 50Y pillar before it is repeated",
    )
    n.fact("warrant", cast.devi.execution.get(ew["id"])["status"])
    n.fact("custody", ", ".join(e["event"] for e in cast.devi.execution.get(ew["id"])["custody"]))


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
