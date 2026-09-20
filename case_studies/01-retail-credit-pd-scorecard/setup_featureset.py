"""
Step 2 — the three features become one panel, pinned point-in-time.

    .venv/bin/python case_studies/01-retail-credit-pd-scorecard/setup_featureset.py

The bureau score is quarterly and delivered late, so it is carried **as-of** rather than
resampled: MAYA does not invent a monthly bureau score the bank never had. The panel is
then pinned — immutable, content-hashed, cascading down to the member features — and
that pin reference, not "the panel", is what everything downstream is drawn on.

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

TITLE = "Case study 1, step 2 — one panel, aligned as-of and pinned"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError

    cast = Cast(maya)
    n.step("Composing the panel: monthly drivers, a quarterly score carried as-of")
    cast.devi.featuresets.create(NS, PANEL, PANEL_DEF)
    cast.devi.featuresets.transition(f"{NS}/{PANEL}", 1, "submit")
    cast.mick.featuresets.transition(f"{NS}/{PANEL}", 1, "approve")
    n.fact("alignment", PANEL_DEF["alignment"])
    n.fact("members", ", ".join(m["attr"] for m in PANEL_DEF["members"]))

    n.step("Pinning it point-in-time, cascading to the features underneath")
    pinned = cast.mick.featuresets.pin(
        f"{NS}/{PANEL}", 1, PIN, str(AS_OF), cascade=True, as_of_known=KNOWN.isoformat()
    )
    maya.drain()  # a deployment's job workers would do this
    job = cast.mick.jobs.get(pinned["job"]["id"])
    if job["state"] != "succeeded":
        raise MayaError(f"pinning {job['state']}: {job.get('error')}")
    n.fact("as of (event time)", AS_OF)
    n.fact("as of known (knowledge time)", KNOWN.date())
    n.fact("pin", PIN_REF)

    n.step("What is in the pin, and what the alignment left empty")
    preview = cast.mick.featuresets.preview(PIN_REF)
    n.fact("rows", f"{preview['total_rows']:,}")
    n.fact("columns", ", ".join(preview["columns"]))
    n.say(
        "The earliest observation months have no bureau score: no file had been delivered "
        "yet, and MAYA leaves the gap as a gap rather than inventing a value. Step 5 says "
        "what that costs the fit."
    )


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
