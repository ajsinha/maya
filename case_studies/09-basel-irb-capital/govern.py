"""
Step 5 — materiality, a periodic review, the live licence, and the SR 11-7 inventory.

    .venv/bin/python case_studies/09-basel-irb-capital/govern.py

A regulatory capital model is as material as models get: the owner declares its use and the
exposure it sits over, answers the firm's questionnaire, and MAYA puts it in tier 1 with a
yearly review. The validator records the first review. The model is licensed to run, a
quarter's run is reported, and the model inventory is exported in the SR 11-7 layout a
supervisor asks for.

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
from study import CONTACT, EXTRA_USERS, LIVE, MODEL, NS, WARRANT_V2, Cast, feed, find_warrant  # noqa: E402

TITLE = "Case study 9, step 5 — tier, review, live use, inventory"


def main(maya: Any, n: Narrator) -> None:
    import csv
    import io

    import pandas as pd

    cast = Cast(maya)
    ref = f"{NS}/{MODEL}"
    book = pd.read_csv(io.BytesIO(feed()))
    exposure = float(book[book["date"] == book["date"].max()]["ead"].sum())

    n.step("Materiality: declared use, exposure, and the firm's questionnaire")
    questions = {
        q["id"]: max(q["answers"], key=q["answers"].get)
        for q in cast.mona.governance.profile(ref)["questionnaire"]
    }
    questions["customer_impact"] = "indirectly"
    profile = cast.mona.governance.set_profile(
        ref, use="regulatory", exposure=exposure, answers=questions
    )
    n.fact("exposure declared", f"{exposure / 1e9:.2f} bn")
    n.fact(
        "tier",
        f"{profile['tier']} (derived {profile['derived_tier']}), review every {profile['review_days']} days",
    )

    n.step("The first periodic review, by the validator")
    reviewed = cast.lara.governance.record_review(
        ref, "satisfactory", "Reconciliation clean after the v2 fix; limitations stated."
    )
    n.fact("next review due", reviewed["next_review_due"])

    n.step("Licensed to run, and a quarter's run reported")
    warrant = find_warrant(cast.mgr, WARRANT_V2)
    ew = cast.mgr.execution.create(
        NS,
        LIVE,
        training_warrant_id=warrant["id"],
        spec={
            "environments": ["prod"],
            "contact": CONTACT,
            "valid_days": 120,
            "covenants": [{"kind": "output_range", "min": 0.0, "max": 1.0}],
        },
    )
    cast.mgr.execution.transition(ew["id"], "submit")
    cast.lara.execution.transition(ew["id"], "approve")
    cast.mgr.execution.seal(ew["id"])
    run = cast.devi.execution.report(
        ew["id"],
        environment="prod",
        rows=300,
        output_stats={"k": {"min": 0.0, "max": 0.31, "mean": 0.07}},
    )
    n.fact("warrant after the run", run["status"])

    n.step("The model inventory, in the SR 11-7 layout")
    out = cast.mgr.governance.inventory(format="csv", framework="sr11-7")
    rows = list(csv.reader(io.StringIO(out["data"].decode())))
    header, row = rows[2], next(r for r in rows[3:] if r and r[0] == f"maya://model/{ref}")
    for label in (
        "Risk rating",
        "Status",
        "Last validation / review",
        "Open findings",
        "Deployments (live warrants)",
        "Monitoring status",
    ):
        n.fact(label, row[header.index(label)] or "—")
    browse_hint(maya)


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
