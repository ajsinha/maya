"""
Step 1 — the sales feed, the panel pinned, and both models approved.

    .venv/bin/python case_studies/42-demand-elasticity/setup.py

The champion is the model the pricing team runs today: demand as a straight line in price.
The challenger says demand responds to price by a constant percentage -- a power law, whose
exponent is the elasticity economists quote. Both are registered as mathematics and approved
on their documents; neither is better yet, because nothing has been measured.

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
    DESCRIPTIONS,
    AS_OF,
    EXTRA_USERS,
    FEATURE_DEF,
    FEED,
    MODELS,
    NS,
    PANEL,
    PANEL_DEF,
    PIN,
    Cast,
    feed,
    spec_document,
)  # noqa: E402

TITLE = "Case study 42, step 1 — the feed, the pin, and two models"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("Two years of weekly sales, governed and pinned")
    cast.dana.features.create(NS, FEED, FEATURE_DEF, description=DESCRIPTIONS[FEED])
    got = cast.dana.features.ingest(f"{NS}/{FEED}", feed(), fmt="csv", filename=f"{FEED}.csv")
    cast.dana.features.transition(f"{NS}/{FEED}", 1, "submit")
    cast.mick.features.transition(f"{NS}/{FEED}", 1, "approve")
    cast.devi.featuresets.create(NS, PANEL, PANEL_DEF, description=DESCRIPTIONS[PANEL])
    cast.devi.featuresets.transition(f"{NS}/{PANEL}", 1, "submit")
    cast.mick.featuresets.transition(f"{NS}/{PANEL}", 1, "approve")
    cast.mick.featuresets.pin(f"{NS}/{PANEL}", 1, PIN, AS_OF.isoformat(), cascade=True)
    maya.drain()
    n.fact("rows ingested", f"{got['rows']:,}")

    n.step("The champion and the challenger, as mathematics")
    for name, m in MODELS.items():
        cast.mona.models.create(
            NS, name, formula=m["formula"], roles=m["roles"], description=m["description"]
        )
        cast.mona.models.update_draft(f"{NS}/{name}", spec_latex=spec_document(name))
        cast.mona.models.transition(f"{NS}/{name}", 1, "submit")
        cast.mgr.models.transition(f"{NS}/{name}", 1, "approve")
        n.fact(name, f"{m['formula']}  — approved")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
