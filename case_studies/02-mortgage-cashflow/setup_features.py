"""
Step 1 — the loan tape and the servicer's report become two governed features.

    .venv/bin/python case_studies/02-mortgage-cashflow/setup_features.py

The tape is what the model reads: balance, coupon, original term, age. The servicer's
report is what the model will be *measured against*: what was actually collected and
remitted that month. They arrive on different lags — two business days and a fortnight —
and each declares its own knowledge time, so MAYA knows when each became knowable.

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

TITLE = "Case study 2, step 1 — the loan tape and the servicer's report"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("Reading both files from data/")
    raw = {name: feed(name) for name in FEEDS}
    for name, body in raw.items():
        n.fact(name, f"{body.count(NEWLINE) - 1:,} rows, {len(body) / 1e6:.1f} MB")
    tape = pd.read_csv(io.BytesIO(raw["loan_tape"]))
    n.fact("loans", f"{tape['loan'].nunique():,} fixed-rate, 15 to 30 year")
    n.fact("balance outstanding", f"{tape.groupby('date')['balance'].sum().iloc[-1]:,.0f}")
    n.fact("coupon range", f"{tape['rate'].min():.2%} to {tape['rate'].max():.2%}")

    n.step("Defining each one, ingesting it, and having it approved by someone else")
    for name in FEEDS:
        cast.dana.features.create(NS, name, DEFINITIONS[name], description=DESCRIPTIONS[name])
        cast.dana.features.ingest(f"{NS}/{name}", raw[name], fmt="csv", filename=f"{name}.csv")
        cast.dana.features.transition(f"{NS}/{name}", 1, "submit")
        cast.mick.features.transition(f"{NS}/{name}", 1, "approve")
        got = cast.mick.features.get(f"{NS}/{name}")["versions"][0]
        n.fact(name, f"v1 {got['state']}, knowledge time from its kt column")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
