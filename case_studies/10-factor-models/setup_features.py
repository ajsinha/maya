"""
Step 1 — two delivered feeds become two governed features, on two different indexes.

    .venv/bin/python case_studies/10-factor-models/setup_features.py

The equity tape is indexed on ``(date, stock)``. The factor library is indexed on **date
alone**, because a factor return is a property of the market and not of any stock: one
number a day for the whole cross-section, stored once, joined on the index the two share.

The two knowledge-time lags could hardly be further apart, and the whole study turns on
the second one. A close is known the evening of the same day. A factor library assembles a
month's returns after the month has closed and publishes them on the fourth of the next
month — so the drivers of this model are known up to thirty-four days after the returns
they explain. This step measures that lag from the delivered file rather than asserting it.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
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
from study import DEFINITIONS, EXTRA_USERS, FEEDS, NS, Cast, feed  # noqa: E402

TITLE = "Case study 10, step 1 — two feeds, two indexes, two very different lags"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved, PermissionDenied

    cast = Cast(maya)
    n.step("Reading the two feeds from data/, as they were delivered")
    raw = {name: feed(name) for name in FEEDS}
    for name, body in raw.items():
        n.fact(name, f"{body.count(b'\n') - 1:,} rows, {len(body) / 1e6:.2f} MB")

    n.step("The lag each feed carries, measured from the files themselves")
    for name in FEEDS:
        frame = pd.read_csv(io.BytesIO(raw[name]))
        lag = (pd.to_datetime(frame["kt"]).dt.tz_convert(None) - pd.to_datetime(frame["date"])).dt
        hours = lag.total_seconds() / 3600.0
        span = (
            f"{hours.min():.0f} to {hours.max():.0f} hours"
            if hours.max() < 48
            else f"{hours.min() / 24:.1f} to {hours.max() / 24:.1f} days"
        )
        n.fact(f"{name} known after", span)
    equity = pd.read_csv(io.BytesIO(raw["equity_daily"]))
    factors = pd.read_csv(io.BytesIO(raw["factor_daily"]))
    n.fact("stocks × days", f"{equity['stock'].nunique()} × {equity['date'].nunique()}")
    n.fact(
        "realised premia, annualised",
        ", ".join(
            f"{c} {factors[c].mean() * 252:+.2%}" for c in ("mkt_rf", "smb", "hml", "rmw", "cma")
        ),
    )
    n.say("Size and value both earned money over this window. Version 1 cannot see either,")
    n.say("and step 5 shows where the return it cannot see ends up instead.")

    n.step("Defining each feed, and putting its rows into MAYA's lake")
    for name in FEEDS:
        cast.dana.features.create(NS, name, DEFINITIONS[name])
        cast.dana.features.ingest(f"{NS}/{name}", raw[name], fmt="csv", filename=f"{name}.csv")
        cast.dana.features.transition(f"{NS}/{name}", 1, "submit")
        index = ", ".join(DEFINITIONS[name]["index"])
        n.say(f"{name}: indexed on ({index}), defined and submitted by dana")

    n.step("Four eyes, which is a property of the capability matrix and not a convention")
    try:
        cast.dana.features.transition(f"{NS}/{FEEDS[0]}", 1, "approve")
    except (PermissionDenied, NotApproved) as exc:
        n.refused("dana approving her own feature", exc)
    for name in FEEDS:
        cast.mick.features.transition(f"{NS}/{name}", 1, "approve")
        got = cast.mick.features.get(f"{NS}/{name}")
        n.fact(name, f"v1 {got['versions'][0]['state']} (by mick)")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
