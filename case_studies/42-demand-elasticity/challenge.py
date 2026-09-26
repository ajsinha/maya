"""
Step 3 — champion against challenger, row by row, and a decision someone else takes.

    .venv/bin/python case_studies/42-demand-elasticity/challenge.py

Two RMSEs side by side are not a comparison: the difference could be luck. MAYA scores both
parameter sets on the shared holdout, keeps the per-row errors to itself, and reports the
difference with a paired bootstrap interval. The verdict is "challenger better" only if the
whole interval lies below zero. A warrant drawn on a different holdout is refused rather
than compared. The challenger's developer is refused the decision; the manager who takes it
records why, and the champion's live use is untouched until someone acts on it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from maya_demo import browse_hint  # noqa: E402
from study import (
    LEAKAGE_JUSTIFICATION,
    CHALLENGER,
    CHALLENGER_WARRANT,
    CHAMPION_WARRANT,
    EXTRA_USERS,
    NS,
    OTHER_WARRANT,
    PIN_REF,
    Cast,
    approved_parameters,
    find_warrant,
)  # noqa: E402

TITLE = "Case study 42, step 3 — the challenge, and the decision"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import PermissionDenied, ValidationFailed

    cast = Cast(maya)
    champ = find_warrant(cast.mgr, CHAMPION_WARRANT)
    chall = find_warrant(cast.mgr, CHALLENGER_WARRANT)

    n.step("A warrant on a different holdout is not a fair comparison")
    other = cast.dev2.training.create(
        NS,
        OTHER_WARRANT,
        f"{NS}/{CHALLENGER}@v1",
        PIN_REF,
        spec={"target": "demand", "seed": 7, "leakage_justification": LEAKAGE_JUSTIFICATION},
    )
    try:
        cast.dev2.challenges.create(champ["id"], other["id"])
    except ValidationFailed as exc:
        n.refused("comparing models scored on different rows", exc)

    n.step("The challenge: both scored on the same rows, compared row by row")
    c = cast.dev2.challenges.create(
        champ["id"],
        chall["id"],
        metric="rmse",
        champion_parameter_set_id=approved_parameters(champ)["id"],
        challenger_parameter_set_id=approved_parameters(chall)["id"],
    )
    r = c["result"]
    n.fact("champion RMSE", f"{r['champion']:.4f}")
    n.fact("challenger RMSE", f"{r['challenger']:.4f}")
    n.fact("difference", f"{r['difference']:+.4f}")
    n.fact(
        "95% interval",
        f"[{r['interval'][0]:+.4f}, {r['interval'][1]:+.4f}] ({r['bootstrap']['draws']} paired draws)",
    )
    n.fact("rows the challenger wins", f"{r['challenger_wins']:.0%} of {r['rows']}")
    n.fact("verdict", r["verdict"].replace("_", " "))

    n.step("The decision")
    try:
        cast.dev2.challenges.decide(c["id"], "promote", "mine is better")
    except PermissionDenied as exc:
        n.refused("the challenger's developer deciding for it", exc)
    done = cast.lara.challenges.decide(
        c["id"], "promote", "the whole interval is below zero; elasticity is the right form"
    )
    n.fact("decision", f"{done['state']} by {done['decided_by']}")
    n.say("Recorded, not enacted: the champion's execution warrants keep running until the")
    n.say("challenger's is drawn and the champion's retired, as a change of its own.")
    browse_hint(maya)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
