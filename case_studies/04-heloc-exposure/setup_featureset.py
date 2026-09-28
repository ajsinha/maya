"""
Step 2 — one panel carrying both regimes and the realised exposure.

    .venv/bin/python case_studies/04-heloc-exposure/setup_featureset.py

Seven attributes, including the regime flag the composite's router reads and the realised
exposure it will be scored against. Both regimes live in one panel and one pin: the router
selects per row, so splitting the data into two feature sets would make the composite
impossible to train under one warrant, which is the thing §8.7 promises.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import DESCRIPTIONS, AS_OF, EXTRA_USERS, KNOWN, NS, PANEL, PANEL_DEF, PIN, PIN_REF, Cast  # noqa: E402

TITLE = "Case study 4, step 2 — one panel, both regimes"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError

    cast = Cast(maya)
    n.step("Composing the panel")
    cast.devi.featuresets.create(NS, PANEL, PANEL_DEF, description=DESCRIPTIONS[PANEL])
    cast.devi.featuresets.transition(f"{NS}/{PANEL}", 1, "submit")
    cast.mick.featuresets.transition(f"{NS}/{PANEL}", 1, "approve")
    n.fact("attributes", ", ".join(m["attr"] for m in PANEL_DEF["members"]))

    n.step("Pinning it point-in-time")
    pinned = cast.mick.featuresets.pin(
        f"{NS}/{PANEL}", 1, PIN, str(AS_OF), cascade=True, as_of_known=KNOWN.isoformat()
    )
    maya.drain()
    job = cast.mick.jobs.get(pinned["job"]["id"])
    if job["state"] != "succeeded":
        raise MayaError(f"pinning {job['state']}: {job.get('error')}")
    preview = cast.mick.featuresets.preview(PIN_REF)
    n.fact("pin", PIN_REF)
    n.fact("rows", f"{preview['total_rows']:,}")
    n.fact("columns", ", ".join(preview["columns"]))


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
