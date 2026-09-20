"""
Step 2 — one panel for three members and one combiner.

    .venv/bin/python case_studies/06-ifrs9-expected-credit-loss/setup_featureset.py

Eight attributes: what the three members read, what the combiner reads, and the three
outcome columns the fits and the blind score need. One panel and one pin, because a
composite trains under one warrant against one feature set.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import AS_OF, EXTRA_USERS, KNOWN, NS, PANEL, PANEL_DEF, PIN, PIN_REF, Cast  # noqa: E402

TITLE = "Case study 6, step 2 — the panel, pinned"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError

    cast = Cast(maya)
    n.step("Composing the panel")
    cast.devi.featuresets.create(NS, PANEL, PANEL_DEF)
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


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
