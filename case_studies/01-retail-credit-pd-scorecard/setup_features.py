"""
Step 1 — the three delivered feeds become three governed features.

    .venv/bin/python case_studies/01-retail-credit-pd-scorecard/setup_features.py

Each feed is defined (index, types, where knowledge time comes from, what must be true
of the values), ingested into MAYA's Delta lake, submitted by its designer and approved
by somebody else. The study tries the "somebody else" part the wrong way round on
purpose, and MAYA refuses: a feature designer's ceiling on features does not include
approval, and no grant can raise it.

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
from study import DESCRIPTIONS, DEFINITIONS, EXTRA_USERS, FEEDS, NS, Cast, feed  # noqa: E402

TITLE = "Case study 1, step 1 — three feeds become three features"


def main(maya: Any, n: Narrator) -> None:
    from maya.core.errors import NotApproved, PermissionDenied

    cast = Cast(maya)
    n.step("Reading the three feeds from data/, as they were delivered")
    raw = {name: feed(name) for name in FEEDS}
    for name, body in raw.items():
        n.fact(name, f"{body.count(b'\n') - 1:,} rows, {len(body) / 1e6:.1f} MB")
    outcome = pd.read_csv(io.BytesIO(raw["default_outcome"]))
    n.fact("default rate in the book", f"{outcome['default_12m'].mean():.2%}")

    n.step("Defining each one, and putting its rows into the lake")
    for name in FEEDS:
        cast.dana.features.create(NS, name, DEFINITIONS[name], description=DESCRIPTIONS[name])
        cast.dana.features.ingest(f"{NS}/{name}", raw[name], fmt="csv", filename=f"{name}.csv")
        cast.dana.features.transition(f"{NS}/{name}", 1, "submit")
        n.say(f"{name}: defined and submitted by dana, and now in MAYA's lake")

    n.step("Four eyes, which is a property of the capability matrix and not a convention")
    try:
        cast.dana.features.transition(f"{NS}/{FEEDS[0]}", 1, "approve")
    except (PermissionDenied, NotApproved) as exc:
        n.refused("dana approving her own feature", exc)
    for name in FEEDS:
        cast.mick.features.transition(f"{NS}/{name}", 1, "approve")
    n.fact("approved by mick", ", ".join(FEEDS))
    for name in FEEDS:
        got = cast.mick.features.get(f"{NS}/{name}")
        n.say(f"{name}: v1 {got['versions'][0]['state']}")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
