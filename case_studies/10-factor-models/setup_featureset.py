"""
Step 2 — two panels: the wide one both versions are fitted on, and the narrow one that was
enough for version 1.

    .venv/bin/python case_studies/10-factor-models/setup_featureset.py

``factor_panel`` composes the equity tape with all five factor series on ``(date, stock)``.
MAYA broadcasts the date-indexed factor rows across the cross-section of each day, and the
step proves it: one distinct market factor value per date in the pinned panel, out of
thirty stocks.

``capm_panel`` carries only the two attributes version 1 declared it needed. Nothing is
fitted on it. It exists so that step 7 can put the same question to both versions of the
model and get two different answers, which is what an input contract changing actually
means.

The step also tries to pin the panel before it is approved, and MAYA refuses: a pin is a
claim about what data was used, and an unapproved definition has no business making one.

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
    AS_OF,
    EXTRA_USERS,
    KNOWN,
    NARROW,
    NARROW_DEF,
    NS,
    PANEL,
    PANEL_DEF,
    PIN,
    PIN_REF,
    Cast,
)

TITLE = "Case study 10, step 2 — one panel per contract, and one of them pinned"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError, NotApproved

    cast = Cast(maya)
    n.step("Composing the wide panel: the tape, and five factor series broadcast onto it")
    cast.devi.featuresets.create(NS, PANEL, PANEL_DEF)
    n.fact("index", ", ".join(PANEL_DEF["index"]))
    n.fact("attributes", ", ".join(m["attr"] for m in PANEL_DEF["members"]))
    n.say("Five of the six members come from a feature indexed on date alone.")

    n.step("A pin cannot be taken on a definition nobody has approved")
    try:
        cast.mick.featuresets.pin(f"{NS}/{PANEL}", 1, PIN, str(AS_OF))
    except (NotApproved, MayaError) as exc:
        n.refused("pinning an unapproved feature set version", exc)

    n.step("Approved, then pinned point-in-time, cascading to the features underneath")
    cast.devi.featuresets.transition(f"{NS}/{PANEL}", 1, "submit")
    cast.mick.featuresets.transition(f"{NS}/{PANEL}", 1, "approve")
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

    n.step("What is in the pin, and the proof that the factor rows were broadcast")
    preview = cast.mick.featuresets.preview(PIN_REF)
    n.fact("rows", f"{preview['total_rows']:,}")
    n.fact("columns", ", ".join(preview["columns"]))
    frame = preview["rows"]
    by_date = {}
    for row in frame:
        by_date.setdefault(str(row["date"]), set()).add(row["mktExcess"])
    n.fact(
        "distinct market factor values within one date",
        max(len(v) for v in by_date.values()),
    )
    n.say("One number a day, stored once, read by every stock of that day. A per-row copy")
    n.say("can be wrong in one row and right in the next; this cannot.")

    n.step("And the narrow panel: exactly what version 1's contract asked for")
    cast.devi.featuresets.create(NS, NARROW, NARROW_DEF)
    cast.devi.featuresets.transition(f"{NS}/{NARROW}", 1, "submit")
    cast.mick.featuresets.transition(f"{NS}/{NARROW}", 1, "approve")
    n.fact(f"{NARROW} attributes", ", ".join(m["attr"] for m in NARROW_DEF["members"]))
    n.say("Nothing is fitted on it. Step 7 asks both versions of the model whether it is")
    n.say("enough for them, and gets two different answers.")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
