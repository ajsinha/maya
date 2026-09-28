"""
Step 3 — the two member models, each a model in its own right.

    .venv/bin/python case_studies/04-heloc-exposure/setup_members.py

A composite's members are not fragments. Each is a model with its own version, its own
input contract, its own specification document and its own approval, and each is registered
and approved here before the composite that uses them exists.

The two have **different functional forms**, and that is the argument for a router rather
than one model with an interaction term:

* in the draw period the quantity is a fraction of a known amount — it cannot be negative
  and cannot exceed one — so a logistic is the right shape and its bounds are a property of
  the problem;
* in repayment the line is closed and the balance amortises, so the twelve-month change is
  **negative**, which a logistic cannot produce at all.

Forcing both through one form would be wrong about at least one of them.

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
    DESCRIPTIONS,
    DRAW_FORMULA,
    DRAW_MODEL,
    DRAW_ROLES,
    DRAW_SECTIONS,
    EXTRA_USERS,
    NS,
    REPAY_FORMULA,
    REPAY_MODEL,
    REPAY_ROLES,
    REPAY_SECTIONS,
    Cast,
    document,
)

TITLE = "Case study 4, step 3 — two members, two shapes"

MEMBERS = (
    (DRAW_MODEL, DRAW_FORMULA, DRAW_ROLES, DRAW_SECTIONS, "Draw-period usage"),
    (REPAY_MODEL, REPAY_FORMULA, REPAY_ROLES, REPAY_SECTIONS, "Repayment-period usage"),
)


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    for name, formula, roles, sections, title in MEMBERS:
        n.step(f"{name}")
        for line in formula.strip().splitlines():
            n.say(line)
        cast.mona.models.create(
            NS, name, formula=formula, roles=roles, description=DESCRIPTIONS[name]
        )
        cast.mona.models.update_draft(f"{NS}/{name}", spec_latex=document(title, sections))
        cast.mona.models.transition(f"{NS}/{name}", 1, "submit")
        cast.mgr.models.transition(f"{NS}/{name}", 1, "approve")
        version = cast.mgr.models.get(f"{NS}/{name}")["versions"][0]
        n.fact("input contract", ", ".join(c["name"] for c in version["input_contract"]))
        n.fact(
            "parameters",
            ", ".join(
                c["name"] for c in version["formula_ir"]["inputs"] if c.get("role") == "parameter"
            ),
        )
        n.fact("state", f"v1 {version['state']}, maturity {version['maturity']}")

    n.step("Each is approved on its own merits, before anything composes them")
    n.say(
        "The repayment member's own document says why it is linear and not logistic, and "
        "says that being linear makes it unbounded — which is a weakness the composite's "
        "output-range covenant guards rather than fixes."
    )


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
