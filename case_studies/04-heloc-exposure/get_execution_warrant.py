"""
Step 7 — live, with the covenant the repayment member's own document asked for.

    .venv/bin/python case_studies/04-heloc-exposure/get_execution_warrant.py

The repayment member is linear, and its specification says so plainly: being linear makes it
unbounded, so far outside the fitted range of equity it will return a fraction below minus
one, which is arithmetically impossible. The document also says what stops that reaching a
balance sheet — an output-range covenant on the composite — and calls it a guard rather than
a fix.

This step declares that covenant and then trips it, which is the point: a weakness written
into a document is a sentence, and a weakness written into a covenant is a control.

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
    member_parameters,
)

TITLE = "Case study 4, step 7 — live, and an exposure that cannot be right"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError

    cast = Cast(maya)
    warrant = find_warrant(cast.mgr, WARRANT)
    members = member_parameters(warrant)
    n.step("Which parameter set goes live, per member")
    for alias, ps in sorted(members.items()):
        n.fact(alias or "(composite)", f"{ps['id'][:8]}… {ps['state']}")

    n.step("Drawing the execution warrant")
    ew = cast.mgr.execution.create(
        NS,
        LIVE,
        training_warrant_id=warrant["id"],
        parameter_set_id=members["draw"]["id"],
        spec={
            "environments": ["dev", "prod"],
            "contact": CONTACT,
            "covenants": [
                # The guard the repayment member's document asks for by name.
                # No attr: the composite declares one output, so MAYA fills in which one
                # this watches. A covenant that named nothing would be compared against
                # nothing and could never breach.
                {"kind": "output_range", "min": 0.0, "max": 2_000_000.0},
                {"kind": "input_psi", "attr": "cltv", "max": 0.25},
                {"kind": "input_null_rate", "attr": "commitment", "max": 0.001},
            ],
        },
    )
    for covenant in ew["spec"]["covenants"]:
        shown = {k: v for k, v in covenant.items() if k not in ("kind", "baseline", "bin_edges")}
        n.fact(covenant["kind"], shown)

    n.step("Two people, then sealed")
    cast.mgr.execution.transition(ew["id"], "submit")
    cast.lara.execution.transition(ew["id"], "approve")
    cast.mgr.execution.seal(ew["id"])
    live = cast.devi.execution.bundle(ew["id"], "prod")
    n.fact("bundle", f"{live['status']}, {live['attestation']}")

    n.step("A batch that produced a negative exposure")
    n.say("Which is not a small exposure. It is a number that cannot be an exposure at all.")
    breach = cast.devi.execution.report(
        ew["id"],
        environment="prod",
        rows=10_320,
        output_stats={"ead": {"min": -41_250.0, "max": 188_400.0, "mean": 74_100.0}},
    )
    n.fact("warrant", breach["status"])
    for item in breach.get("breaches", []):
        n.say(f"{item['kind']}: {item.get('detail')}")
    try:
        cast.devi.execution.bundle(ew["id"], "prod")
    except MayaError as exc:
        n.refused("serving a model that has produced an impossible exposure", exc)

    n.step("Reinstated, with what was done about it")
    cast.admin.execution.reinstate(
        ew["id"],
        "traced to 41 accounts whose combined loan-to-value exceeds the repayment member's "
        "fitted range; the calling system now floors the fraction at zero and the member is "
        "scheduled for a bounded reformulation in the next version",
    )
    n.fact("warrant", cast.devi.execution.bundle(ew["id"], "prod")["status"])
    n.fact("custody", ", ".join(e["event"] for e in cast.mgr.execution.get(ew["id"])["custody"]))


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
