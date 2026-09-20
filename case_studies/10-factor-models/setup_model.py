"""
Step 3 — version 1: the simple linear regression, registered as mathematics.

    .venv/bin/python case_studies/10-factor-models/setup_model.py

Two parameters. One feature. It is the smallest model in this library, and it gets the
same treatment as the nine-parameter volatility surface in case study 5 and the
four-driver scorecard in case study 1: a parsed expression tree, an input contract MAYA
derives rather than believes, a nine-section specification document it refuses to proceed
without, and a maturity.

That is the argument this step exists to make. MAYA's ceremony is not proportional to the
model's complexity, because the *consequences* are not either. A one-slope regression on
the wrong panel, or with an alpha nobody challenged, reaches the investment committee's
report exactly as fast as a hard one would.

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
    FORMULA_V1,
    MODEL,
    NS,
    ROLES_V1,
    Cast,
    spec_v1,
    version,
)

TITLE = "Case study 10, step 3 — version 1, and the ceremony a two-parameter model earns"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved

    cast = Cast(maya)
    n.step("Registering the market model as a formula")
    cast.mona.models.create(NS, MODEL, formula=FORMULA_V1, roles=ROLES_V1)
    v1 = version(cast.mona, f"{NS}/{MODEL}", 1)
    n.fact("formula", FORMULA_V1.strip())
    n.fact("input contract", ", ".join(c["name"] for c in v1["input_contract"]))
    n.fact(
        "parameters to be fitted",
        ", ".join(c["name"] for c in v1["formula_ir"]["inputs"] if c.get("role") == "parameter"),
    )
    n.fact("maturity on creation", v1["maturity"])
    n.say("The contract is what MAYA found in the tree, not what anyone promised it.")

    n.step("A model version cannot be submitted with an empty specification")
    try:
        cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    except NotApproved as exc:
        n.refused("submitting version 1 before its document is written", exc)

    n.step("Writing the nine sections §8.3 requires, then submitting for review")
    cast.mona.models.update_draft(f"{NS}/{MODEL}", spec_latex=spec_v1())
    filled = version(cast.mona, f"{NS}/{MODEL}", 1)
    n.fact(
        "sections present",
        f"{sum(1 for s in filled['completeness'] if s['present'] and not s['empty'])}"
        f" of {len(filled['completeness'])}",
    )
    cast.mona.models.transition(f"{NS}/{MODEL}", 1, "submit")
    cast.mgr.models.transition(f"{NS}/{MODEL}", 1, "approve")
    approved = version(cast.mgr, f"{NS}/{MODEL}", 1)
    n.fact("state", approved["state"])
    n.fact("maturity after approval", approved["maturity"])
    n.fact("definition hash", f"{(approved['definition_hash'] or '')[:16]}…")

    n.step("The mathematics, as MAYA renders it from the tree")
    for line in (approved["latex"] or "").splitlines():
        n.say(line)
    n.say("")
    n.say("Two coefficients, one of which — alpha — is the one an investment committee")
    n.say("will read as skill. Step 5 reports it with a standard error, twice over.")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
