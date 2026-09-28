"""
Step 1 — two feeds with two clocks, and the panel pinned at the year end.

    .venv/bin/python case_studies/19-vendor-bureau-score/setup_data.py

The bureau attributes are known the evening they are pulled; the outcome is known a year
later. Keeping them as two feeds with their own knowledge times is what lets MAYA certify
that the score never saw the outcome.

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
    APPLICATIONS_DEF,
    AS_OF,
    EXTRA_USERS,
    NS,
    OUTCOMES_DEF,
    PANEL,
    PANEL_DEF,
    PIN,
    Cast,
    feed,
)  # noqa: E402

TITLE = "Case study 19, step 1 — two feeds, two clocks, one pin"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("The bureau attributes and the outcomes, as two governed features")
    for name, definition in (("applications", APPLICATIONS_DEF), ("outcomes", OUTCOMES_DEF)):
        cast.dana.features.create(NS, name, definition, description=DESCRIPTIONS[name])
        got = cast.dana.features.ingest(
            f"{NS}/{name}", feed(name), fmt="csv", filename=f"{name}.csv"
        )
        cast.dana.features.transition(f"{NS}/{name}", 1, "submit")
        cast.mick.features.transition(f"{NS}/{name}", 1, "approve")
        n.fact(name, f"{got['rows']:,} rows, approved")

    n.step("The panel, pinned at the year end")
    cast.devi.featuresets.create(NS, PANEL, PANEL_DEF, description=DESCRIPTIONS[PANEL])
    cast.devi.featuresets.transition(f"{NS}/{PANEL}", 1, "submit")
    cast.mick.featuresets.transition(f"{NS}/{PANEL}", 1, "approve")
    cast.mick.featuresets.pin(f"{NS}/{PANEL}", 1, PIN, AS_OF.isoformat(), cascade=True)
    maya.drain()
    pin = next(
        p for p in cast.mick.featuresets.get(f"{NS}/{PANEL}")["pins"] if p["pin_name"] == PIN
    )
    n.fact("pin", f"{pin['row_count']:,} rows, {pin['state']}, hash {pin['content_hash'][:16]}…")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
