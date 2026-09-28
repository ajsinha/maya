"""
Step 1 — the tape and the realised exposure become two governed features.

    .venv/bin/python case_studies/04-heloc-exposure/setup_features.py

A home equity line of credit is a commitment, so the tape carries two amounts that matter
and are easy to confuse: the **commitment**, which the bank has promised, and the **drawn**
balance, which it has actually lent. The gap between them is the thing this study forecasts.

The second feed is the drawn balance twelve months later — the target, and unknowable until
those twelve months have passed.

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
from study import DESCRIPTIONS, DEFINITIONS, EXTRA_USERS, FEEDS, NEWLINE, NS, Cast, feed  # noqa: E402

TITLE = "Case study 4, step 1 — the tape, and the exposure a year later"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("Reading both feeds from data/")
    raw = {name: feed(name) for name in FEEDS}
    for name, body in raw.items():
        n.fact(name, f"{body.count(NEWLINE) - 1:,} rows, {len(body) / 1e6:.2f} MB")
    tape = pd.read_csv(io.BytesIO(raw["heloc_month"]))
    n.fact("accounts", f"{tape['account'].nunique():,}")
    n.fact("committed", f"{tape.groupby('date')['commitment'].sum().iloc[-1]:,.0f}")
    n.fact("drawn", f"{tape.groupby('date')['drawn'].sum().iloc[-1]:,.0f}")
    n.fact("mean utilisation", f"{(tape['drawn'] / tape['commitment']).mean():.1%}")
    n.fact(
        "regime split",
        f"{int(tape['in_draw'].sum()):,} in the draw period, "
        f"{int((1 - tape['in_draw']).sum()):,} in repayment",
    )
    n.say("The undrawn line is what the bank is exposed to and has not yet lent.")

    n.step("Defining each one, and approving it as somebody other than its author")
    for name in FEEDS:
        cast.dana.features.create(NS, name, DEFINITIONS[name], description=DESCRIPTIONS[name])
        cast.dana.features.ingest(f"{NS}/{name}", raw[name], fmt="csv", filename=f"{name}.csv")
        cast.dana.features.transition(f"{NS}/{name}", 1, "submit")
        cast.mick.features.transition(f"{NS}/{name}", 1, "approve")
        n.fact(name, f"v1 {cast.mick.features.get(f'{NS}/{name}')['versions'][0]['state']}")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
