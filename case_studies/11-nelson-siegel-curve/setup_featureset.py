"""
Step 2 — one curve on one index, the build report broadcast onto it, pinned point-in-time.

    .venv/bin/python case_studies/11-nelson-siegel-curve/setup_featureset.py

The set's index is the published curve's: (date, tenor). The par quotes share that grain; the
build report is one row a day, so MAYA broadcasts it onto every pillar of that day rather
than making anybody write a join, and says so in its resolution plan.

The model's notation and the curve team's column names meet here. The set exposes ``tau``
and ``y`` — the maturity the model reads and the yield it is calibrated to — plus the ``par``
rate the pillar was built from and the ``buildResidual`` of that build, neither of which the
model may see.

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
    AS_OF,
    EXTRA_USERS,
    KNOWN,
    NS,
    PANEL,
    PANEL_DEF,
    PIN,
    PIN_REF,
    Cast,
)

TITLE = "Case study 11, step 2 — the curve, pinned point-in-time"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError

    cast = Cast(maya)
    n.step("Composing the curve")
    cast.devi.featuresets.create(NS, PANEL, PANEL_DEF, description=DESCRIPTIONS[PANEL])
    cast.devi.featuresets.transition(f"{NS}/{PANEL}", 1, "submit")
    cast.mick.featuresets.transition(f"{NS}/{PANEL}", 1, "approve")
    for member in PANEL_DEF["members"]:
        n.say(f"  {member['attr']:<14} <- {member['ref'].split('/')[-1]}.{member['source_attr']}")
    n.say("'y' is the calibration target and 'tau' is the only input the model will have.")

    n.step("Pinning it, cascading to the three features underneath")
    pinned = cast.mick.featuresets.pin(
        f"{NS}/{PANEL}", 1, PIN, str(AS_OF), cascade=True, as_of_known=KNOWN.isoformat()
    )
    maya.drain()
    job = cast.mick.jobs.get(pinned["job"]["id"])
    if job["state"] != "succeeded":
        raise MayaError(f"pinning {job['state']}: {job.get('error')}")
    n.fact("pin", PIN_REF)
    n.fact("known as of", KNOWN.isoformat())
    preview = cast.mick.featuresets.preview(PIN_REF)
    n.fact("rows", f"{preview['total_rows']:,}")
    n.fact("columns", ", ".join(preview["columns"]))

    n.step("How MAYA assembled it, in its own words")
    plan = cast.mick.featuresets.preview(f"maya://featureset/{NS}/{PANEL}@v1")["manifest"]["plan"]
    for line in plan:
        n.say(f"  {line}")
    n.say("The build report is one row a day and the curve is twenty-one rows a day, so the")
    n.say("coarser member is broadcast. Nobody wrote that join; the index declared it.")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
