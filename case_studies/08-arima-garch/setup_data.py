"""
Step 1 — the daily feed, its lags declared, pinned as it stood.

    .venv/bin/python case_studies/08-arima-garch/setup_data.py

The lag structure of an AR(2) usually lives in a line of pandas inside a fitting script,
where a reviewer has to read code to learn that the model looks two days back, and where a
``shift`` over the whole frame quietly lends one index's history to the next. Here the lags
are transforms on the governed feature, grouped by index, and the panel is pinned as it was
known on 15 July 2025.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import (  # noqa: E402
    AS_OF,
    DEFINITIONS,
    EXTRA_USERS,
    KNOWN,
    NS,
    PANEL,
    PANEL_DEF,
    PIN,
    Cast,
    feed,
)

TITLE = "Case study 8, step 1 — the daily feed, its lags declared, pinned as it stood"
FEED = "index_daily"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError

    cast = Cast(maya)
    raw = feed(FEED)
    frame = pd.read_csv(io.BytesIO(raw))
    n.step("The feed as delivered: three indices, one close a day")
    n.fact(
        "rows",
        f"{len(frame):,} ({frame['index'].nunique()} indices × {frame['date'].nunique():,} days)",
    )
    n.fact("dates", f"{frame['date'].min()} to {frame['date'].max()}")

    n.step("A governed feature whose lags are part of its definition")
    definition = DEFINITIONS[FEED]
    cast.dana.features.create(NS, FEED, definition)
    cast.dana.features.ingest(f"{NS}/{FEED}", raw, fmt="csv", filename=f"{FEED}.csv")
    cast.dana.features.transition(f"{NS}/{FEED}", 1, "submit")
    cast.mick.features.transition(f"{NS}/{FEED}", 1, "approve")
    for step in definition["transform"]:
        n.say(f"  transform: {step}")
    n.say("A lag is grouped by everything after the first index column, so AZX's yesterday")
    n.say("is never BQI's. A reviewer sees 'lag 1, lag 2' in the definition, not in a script.")

    n.step("The panel, pinned point-in-time")
    cast.devi.featuresets.create(NS, PANEL, PANEL_DEF)
    cast.devi.featuresets.transition(f"{NS}/{PANEL}", 1, "submit")
    cast.mick.featuresets.transition(f"{NS}/{PANEL}", 1, "approve")
    pinned = cast.mick.featuresets.pin(
        f"{NS}/{PANEL}", 1, PIN, str(AS_OF), cascade=True, as_of_known=KNOWN.isoformat()
    )
    maya.drain()
    job = cast.mick.jobs.get(pinned["job"]["id"])
    if job["state"] != "succeeded":
        raise MayaError(f"pinning {job['state']}: {job.get('error')}")
    pin = cast.mick.featuresets.get(f"{NS}/{PANEL}")["pins"][0]
    n.fact("members", ", ".join(m["attr"] for m in PANEL_DEF["members"]))
    n.fact("pin", f"{pin['row_count']:,} rows as of {AS_OF}, known by {KNOWN.date()}")
    n.fact("content hash", pin["content_hash"][:16] + "…")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
