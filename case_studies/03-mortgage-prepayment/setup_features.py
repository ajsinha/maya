"""
Step 1 — four feeds become four features, two of them not about loans at all.

    .venv/bin/python case_studies/03-mortgage-prepayment/setup_features.py

The loan tape and the payoff flag are indexed on (date, loan). The mortgage rate and the
moving-season flag are indexed on **date alone**, because neither is a property of any
loan: the survey publishes one number a month for the whole market. MAYA joins them onto
the loan panel on the index the two share, so the market rate is stored once and read
everywhere — rather than copied into 37,873 rows, where it can be wrong in one and right
in the next.

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
from study import DEFINITIONS, EXTRA_USERS, FEEDS, NEWLINE, NS, Cast, cpr, feed  # noqa: E402

TITLE = "Case study 3, step 1 — four feeds, on two different indexes"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("Reading the four feeds from data/")
    raw = {name: feed(name) for name in FEEDS}
    for name in FEEDS:
        body = raw[name]
        index = ", ".join(DEFINITIONS[name]["index"])
        n.fact(name, f"{body.count(NEWLINE) - 1:,} rows on ({index})")
    rate = pd.read_csv(io.BytesIO(raw["mortgage_rate"]))
    n.fact(
        "market rate over the window",
        f"{rate['mkt_rate'].min():.2%} to {rate['mkt_rate'].max():.2%}",
    )
    outcome = pd.read_csv(io.BytesIO(raw["prepaid"]))
    monthly = outcome["prepaid"].mean()
    n.fact("realised SMM", f"{monthly:.3%} a month")
    n.fact("realised CPR", f"{cpr(monthly):.1%} annualised")

    n.step("Defining each one, and approving it as somebody other than its author")
    for name in FEEDS:
        cast.dana.features.create(NS, name, DEFINITIONS[name])
        cast.dana.features.ingest(f"{NS}/{name}", raw[name], fmt="csv", filename=f"{name}.csv")
        cast.dana.features.transition(f"{NS}/{name}", 1, "submit")
        cast.mick.features.transition(f"{NS}/{name}", 1, "approve")
        n.say(f"{name}: v1 approved")
    n.say("The rate is 30 rows, and that is the point: one number a month, stored once.")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
