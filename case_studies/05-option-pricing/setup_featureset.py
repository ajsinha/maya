"""
Step 2 — one chain on one index, broadcast across three grains, pinned point-in-time.

    .venv/bin/python case_studies/05-option-pricing/setup_featureset.py

The set's index is the quote's: (date, underlying, tenor, contract). The spot and the
dividend forecast are per (date, underlying) and the curve is per (date, tenor), so MAYA
broadcasts each of them onto the chain — the resolution plan says so in words. The model's
notation and the vendors' column names meet here: the set exposes S, K, T, r, q, the quoted
mid it will be calibrated to, and the moneyness a covenant will later watch.

The set is filtered to one underlying, because a volatility surface belongs to one
underlying. The other three names stay in the features.

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
    PILLAR,
    PILLAR_DEF,
    PILLAR_REF,
    PIN,
    PIN_REF,
    Cast,
)

TITLE = "Case study 5, step 2 — the chain, pinned point-in-time"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError

    cast = Cast(maya)
    n.step("Composing the chain")
    cast.devi.featuresets.create(NS, PANEL, PANEL_DEF, description=DESCRIPTIONS[PANEL])
    cast.devi.featuresets.transition(f"{NS}/{PANEL}", 1, "submit")
    cast.mick.featuresets.transition(f"{NS}/{PANEL}", 1, "approve")
    for member in PANEL_DEF["members"]:
        n.say(f"  {member['attr']:<10} <- {member['ref'].split('/')[-1]}.{member['source_attr']}")
    n.say("'mid' and 'moneyness' are members of the chain and not inputs of the model")

    n.step("Pinning it, cascading to the four features underneath")
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

    n.step("The 1Y pillar, as set algebra over the same chain")
    n.say("Not a second definition to keep in step: the same one, with one filter replaced.")
    cast.devi.featuresets.create(NS, PILLAR, PILLAR_DEF, description=DESCRIPTIONS[PILLAR])
    cast.devi.featuresets.transition(f"{NS}/{PILLAR}", 1, "submit")
    cast.mick.featuresets.transition(f"{NS}/{PILLAR}", 1, "approve")
    pillar = cast.mick.featuresets.preview(PILLAR_REF)
    n.fact("1Y pillar", f"{pillar['total_rows']:,} of {preview['total_rows']:,} quotes")
    n.say("Step 4 uses it as a test domain, and it is the point of the whole study's §5.")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
