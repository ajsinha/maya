"""
Step 1 — four market data feeds become four governed features.

    .venv/bin/python case_studies/05-option-pricing/setup_features.py

A European call needs the spot, the strike, the rate, the dividend yield and the time to
expiry, and on a real desk those arrive from four systems on four different grains: the
option chain per (date, underlying, tenor, contract), the spot and the dividend forecast per
(date, underlying), the curve per (date, tenor). Each declares its own knowledge time — the
evening the quote printed, the morning the forecast was published — so MAYA knows when each
became knowable without anybody promising it did.

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
    UNDERLYING,
    Cast,
    feed,
)

TITLE = "Case study 5, step 1 — the chain, the spot, the dividends and the curve"


def main(maya: Any, n: Narrator) -> None:
    cast = Cast(maya)
    n.step("Reading the four files from data/")
    raw = {name: feed(name) for name in FEEDS}
    for name, body in raw.items():
        n.fact(name, f"{body.count(NEWLINE) - 1:,} rows, {len(body) / 1e6:.2f} MB")
    chain = pd.read_csv(io.BytesIO(raw["option_quotes"]))
    acme = chain[chain["underlying"] == UNDERLYING]
    n.fact("underlyings", ", ".join(sorted(chain["underlying"].unique())))
    n.fact("tenors", ", ".join(sorted(chain["tenor"].unique(), key=len)))
    n.fact(f"{UNDERLYING} quotes", f"{len(acme):,} over {acme['date'].nunique()} business days")
    n.fact(
        "strikes",
        f"{acme['strike'].nunique()} on the ladder, {acme['strike'].min():g} to {acme['strike'].max():g}",
    )
    n.fact("moneyness", f"{acme['moneyness'].min():.3f} to {acme['moneyness'].max():.3f}")
    n.fact("mid price", f"{acme['mid'].min():.2f} to {acme['mid'].max():.2f}")

    n.step("Defining each feed, ingesting it, and having it approved by someone else")
    for name in FEEDS:
        cast.dana.features.create(NS, name, DEFINITIONS[name])
        cast.dana.features.ingest(f"{NS}/{name}", raw[name], fmt="csv", filename=f"{name}.csv")
        cast.dana.features.transition(f"{NS}/{name}", 1, "submit")
        cast.mick.features.transition(f"{NS}/{name}", 1, "approve")
        got = cast.mick.features.get(f"{NS}/{name}")["versions"][0]
        index = ", ".join(DEFINITIONS[name]["index"])
        n.fact(name, f"v1 {got['state']}, on ({index})")
    n.say(
        "Four feeds, three grains, four lags, one declaration each. Step 2 puts them on one index."
    )


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
