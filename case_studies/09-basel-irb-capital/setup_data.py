"""
Step 1 — the exposures feed becomes a governed feature, and the year-end panel is pinned.

    .venv/bin/python case_studies/09-basel-irb-capital/setup_data.py

The feed carries the regulator's reference capital beside the three inputs. It is the
benchmark the model will be reconciled against, so it goes into the panel as the target
and the model's input contract never names it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import AS_OF, EXTRA_USERS, FEATURE_DEF, FEED, NS, PANEL, PANEL_DEF, PIN, Cast, feed  # noqa: E402

TITLE = "Case study 9, step 1 — the exposures feed, governed and pinned"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("Defining the feed and loading four quarter-ends of exposures")
    cast.dana.features.create(NS, FEED, FEATURE_DEF)
    got = cast.dana.features.ingest(f"{NS}/{FEED}", feed(), fmt="csv", filename=f"{FEED}.csv")
    n.fact("rows ingested", f"{got['rows']:,}")
    cast.dana.features.transition(f"{NS}/{FEED}", 1, "submit")
    cast.mick.features.transition(
        f"{NS}/{FEED}", 1, "approve", rationale="ranges and nulls checked"
    )
    n.fact("feature", f"{FEED} v1 approved by mick")

    n.step("The panel: three inputs and the reference, pinned at the year end")
    cast.devi.featuresets.create(NS, PANEL, PANEL_DEF)
    cast.devi.featuresets.transition(f"{NS}/{PANEL}", 1, "submit")
    cast.mick.featuresets.transition(f"{NS}/{PANEL}", 1, "approve")
    cast.mick.featuresets.pin(f"{NS}/{PANEL}", 1, PIN, AS_OF.isoformat(), cascade=True)
    maya.drain()
    pin = next(
        p for p in cast.mick.featuresets.get(f"{NS}/{PANEL}")["pins"] if p["pin_name"] == PIN
    )
    n.fact(
        "pin", f"{pin['pin_name']}/{pin['as_of_date']}: {pin['row_count']:,} rows, {pin['state']}"
    )
    n.fact("content hash", f"{pin['content_hash'][:16]}…")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
