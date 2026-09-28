"""
Step 3 — the hazard as mathematics, with the scalings declared in it.

    .venv/bin/python case_studies/03-mortgage-prepayment/setup_model.py

Two scalings are part of the model rather than of the fitting script: the incentive in
percentage points and the seasoning in years. That is not tidiness. It makes a coefficient
readable — "per percentage point of incentive", "per year on book" — it stops the design
matrix mixing 0.02 against 180, and it means any second implementation reads the same
statement instead of choosing its own units.

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
    EXTRA_USERS,
    FORMULA,
    MATERIALITY,
    MATERIALITY_WHY,
    MODEL,
    NS,
    ROLES,
    Cast,
    specification,
)

TITLE = "Case study 3, step 3 — the hazard, and its document"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved

    cast = Cast(maya)
    n.step("Registering it")
    for line in FORMULA.strip().splitlines():
        n.say(line)
    cast.mona.models.create(
        NS, MODEL, formula=FORMULA, roles=ROLES, description=DESCRIPTIONS[MODEL]
    )
    version = cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]
    n.fact("input contract", ", ".join(c["name"] for c in version["input_contract"]))
    n.fact(
        "parameters to fit",
        ", ".join(
            c["name"] for c in version["formula_ir"]["inputs"] if c.get("role") == "parameter"
        ),
    )

    n.step("The document is the gate, not decoration")
    try:
        cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    except NotApproved as exc:
        n.refused("submitting before the specification is complete", exc)
    cast.mona.models.update_draft(f"{NS}/{MODEL}", spec_latex=specification())

    n.step("Declaring what this model calls a material shift")
    n.say(MATERIALITY_WHY)
    cast.mona.models.update_draft(f"{NS}/{MODEL}", shadow_materiality=MATERIALITY)
    n.fact(
        "shadow_materiality",
        cast.mona.models.get(f"{NS}/{MODEL}")["versions"][0]["shadow_materiality"],
    )
    n.say(
        "Without it a replay measures against the platform default, which for a probability "
        "reports every rounding difference as material — and a reviewer soon learns to "
        "ignore the report. Step 7 shows the threshold being used."
    )

    n.step("Submitting, and approving")
    cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    cast.mgr.models.transition(f"{NS}/{MODEL}", 1, "approve")
    approved = cast.mgr.models.get(f"{NS}/{MODEL}")["versions"][0]
    n.fact("model", f"{NS}/{MODEL} v1, {approved['state']}")

    n.step("The mathematics, as MAYA renders it")
    for line in (approved["latex"] or "").splitlines():
        n.say(line)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
