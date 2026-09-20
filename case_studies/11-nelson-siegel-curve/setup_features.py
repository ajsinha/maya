"""
Step 1 — the screens, the published curve, and the build report become three features.

    .venv/bin/python case_studies/11-nelson-siegel-curve/setup_features.py

Three feeds on two grains and two lags. The par quotes print at 16:15, the curve the desk
actually consumes is published at 18:40 — after somebody bootstrapped it — and the report of
that build arrives with it, one row a day.

The third feed is worth watching. ``curve_build`` carries the number of instruments the
bootstrap used, the largest residual it left, and the name of the method. That is the
construction report of a piece of mathematics with no specification, no parameter set and no
approved version anywhere in MAYA, and the only control the platform can put on it is a
range check on a number the team reports about itself. Keep it in mind for step 7.

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
from study import (  # noqa: E402
    DEFINITIONS,
    EXTRA_USERS,
    FEEDS,
    NEWLINE,
    NS,
    Cast,
    feed,
)

TITLE = "Case study 11, step 1 — the quotes, the published curve, and the build report"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import MayaError

    cast = Cast(maya)
    n.step("Reading the three files from data/")
    raw = {name: feed(name) for name in FEEDS}
    for name, body in raw.items():
        n.fact(name, f"{body.count(NEWLINE) - 1:,} rows, {len(body) / 1e6:.2f} MB")
    curve = pd.read_csv(io.BytesIO(raw["zero_yields"]))
    build = pd.read_csv(io.BytesIO(raw["curve_build"]))
    n.fact(
        "business days",
        f"{curve['date'].nunique():,}, {curve['date'].min()} to {curve['date'].max()}",
    )
    n.fact(
        "pillars",
        f"{curve['tenor'].nunique()}, tau {curve['tau'].min():.4f} to {curve['tau'].max():g}",
    )
    n.fact(
        "zero yields",
        f"{curve['zeroYield'].min() * 100:.4f}% to {curve['zeroYield'].max() * 100:.4f}%",
    )
    n.fact("the build's own residual", f"max {build['maxResidualBp'].max():.2f} bp over the window")
    n.fact("its method", build["method"].iloc[0])

    n.step("Defining each feed, ingesting it, and submitting it")
    for name in FEEDS:
        cast.dana.features.create(NS, name, DEFINITIONS[name])
        cast.dana.features.ingest(f"{NS}/{name}", raw[name], fmt="csv", filename=f"{name}.csv")
        cast.dana.features.transition(f"{NS}/{name}", 1, "submit")
        index = ", ".join(DEFINITIONS[name]["index"])
        checks = len(DEFINITIONS[name]["quality"])
        n.say(f"{name}: on ({index}), {checks} quality checks, submitted by dana")

    n.step("Four eyes, which is a property of the capability matrix and not a convention")
    try:
        cast.dana.features.transition(f"{NS}/{FEEDS[1]}", 1, "approve")
    except MayaError as exc:
        n.refused("the designer of the curve feed approving it herself", exc)
    for name in FEEDS:
        cast.mick.features.transition(f"{NS}/{name}", 1, "approve")
        got = cast.mick.features.get(f"{NS}/{name}")["versions"][0]
        n.fact(name, f"v1 {got['state']}, approved by mick")
    n.say("Three feeds, two grains, two lags, one declaration each. Step 2 puts them on")
    n.say("one index and pins them.")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
