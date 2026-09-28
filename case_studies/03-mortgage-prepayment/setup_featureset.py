"""
Step 2 — one panel, joining loan-level and market-level data on the index they share.

    .venv/bin/python case_studies/03-mortgage-prepayment/setup_featureset.py

Six attributes from four features on two different indexes. MAYA broadcasts the
date-indexed members across the loans of each month; the step reads the pinned panel back
and shows that every loan in a month carries the same market rate, which is what makes
"the incentive" a well-defined quantity rather than a per-row copy that can drift.

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

TITLE = "Case study 3, step 2 — the panel, and a pin"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError

    cast = Cast(maya)
    n.step("Composing the panel from four features on two indexes")
    cast.devi.featuresets.create(NS, PANEL, PANEL_DEF, description=DESCRIPTIONS[PANEL])
    cast.devi.featuresets.transition(f"{NS}/{PANEL}", 1, "submit")
    cast.mick.featuresets.transition(f"{NS}/{PANEL}", 1, "approve")
    for member in PANEL_DEF["members"]:
        n.say(f"{member['attr']:<14} <- {member['ref'].split('/')[-1]}.{member['source_attr']}")

    n.step("Pinning it point-in-time")
    pinned = cast.mick.featuresets.pin(
        f"{NS}/{PANEL}", 1, PIN, str(AS_OF), cascade=True, as_of_known=KNOWN.isoformat()
    )
    maya.drain()
    job = cast.mick.jobs.get(pinned["job"]["id"])
    if job["state"] != "succeeded":
        raise MayaError(f"pinning {job['state']}: {job.get('error')}")
    n.fact("pin", PIN_REF)

    n.step("What the broadcast join produced")
    preview = cast.mick.featuresets.preview(PIN_REF)
    n.fact("rows", f"{preview['total_rows']:,}")
    n.fact("columns", ", ".join(preview["columns"]))
    first = preview["rows"][:3]
    for row in first:
        n.say(
            f"{str(row['date'])[:10]} {row['loan']}: wac={row['wac']:.4f} "
            f"mktRate={row['mktRate']:.4f} movingSeason={row['movingSeason']}"
        )
    same_month = {
        r["mktRate"] for r in preview["rows"] if str(r["date"])[:7] == str(first[0]["date"])[:7]
    }
    n.fact("distinct market rates within one month", len(same_month))


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
