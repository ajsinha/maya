"""
Step 4 — the fix as version 2, reconciled again, and the finding closed by someone else.

    .venv/bin/python case_studies/09-basel-irb-capital/remediate.py

The owner writes version 2 and marks the finding remediated. MAYA's semantic diff shows the
change is the floor and cap and nothing more. A new warrant on the same pin reconciles to
the last digit -- and the finding is closed by the validator, because whoever made the fix
does not certify it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import (
    EXTRA_USERS,
    LEAKAGE_JUSTIFICATION,
    FORMULA_V2,
    MODEL,
    NS,
    PIN_REF,
    ROLES,
    WARRANT_V2,
    Cast,
    spec_document,
)  # noqa: E402

TITLE = "Case study 9, step 4 — version 2, and closing the finding"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import PermissionDenied

    cast = Cast(maya)
    ref = f"{NS}/{MODEL}"
    finding = next(f for f in cast.mona.governance.findings(ref, "active"))

    n.step("Version 2: the floor and the cap")
    cast.mona.models.new_draft(ref)
    cast.mona.models.update_draft(ref, formula=FORMULA_V2, roles=ROLES, spec_latex=spec_document(2))
    diff = cast.mona.models.diff(ref, 1, 2)
    for statement in diff["statements"]:
        n.say(statement.replace("\\left", "").replace("\\right", ""))
    n.fact("specification changed too", diff["spec_changed"])
    cast.mona.models.transition(ref, 2, "submit")
    cast.mgr.models.transition(ref, 2, "approve", rationale="fix for the maturity finding")
    cast.mona.governance.move_finding(finding["id"], "remediated", "v2 floors and caps M")

    n.step("Reconciling version 2 on the same pin")
    drawn = cast.devi.training.create(
        NS,
        WARRANT_V2,
        f"{ref}@v2",
        PIN_REF,
        spec={
            "target": "reference_k",
            "objective": "reconcile K with the reference calculator",
            "leakage_justification": LEAKAGE_JUSTIFICATION,
        },
    )
    scored = cast.devi.warrant(drawn["id"]).score_holdout()
    n.fact("RMSE of K", f"{scored['metrics']['rmse']:.2e}")
    cast.devi.training.transition(drawn["id"], "submit")
    cast.mgr.training.transition(drawn["id"], "approve")
    cast.mgr.training.seal(drawn["id"])
    n.fact("warrant", f"{WARRANT_V2} sealed")

    n.step("Closing the finding")
    try:
        cast.mona.governance.move_finding(finding["id"], "close", "fixed it myself")
    except PermissionDenied as exc:
        n.refused("the owner certifying her own fix", exc)
    closed = cast.lara.governance.move_finding(
        finding["id"], "close", f"v2 reconciles: RMSE {scored['metrics']['rmse']:.1e}"
    )
    n.fact("finding", f"{closed['state']} by {closed['closed_by']}")
    n.fact("history", " → ".join(h["action"] for h in closed["history"]))


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
