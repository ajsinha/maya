"""
The two feeds this case study ingests, written to ``data/`` as CSV.

    .venv/bin/python case_studies/04-heloc-exposure/make_data.py

A home equity line of credit is a *commitment*, not a loan. The bank has promised money it
has not yet lent, the borrower decides when to take it, and the bank's exposure is
therefore something to be forecast rather than read off a balance.

* ``heloc_month.csv`` — the monthly tape: the committed line, how much of it is drawn, the
  combined loan-to-value, the rate the borrower pays, how long the account has been open,
  and whether it is still in its **draw period** or has entered **repayment**. Cut three
  business days after month end.
* ``exposure_later.csv`` — the drawn balance twelve months after each observation month.
  This is the target, and it cannot be known until those twelve months have passed, which
  is what makes it a target rather than an input.

The behaviour underneath is deliberately in two regimes, because that is what a HELOC
actually does and it is the reason this study builds a *composite* model:

* **In the draw period** a borrower can take more, and does so in proportion to the equity
  still available, the room left on the line, and how expensive the money is. The draw
  fraction is a logistic function of those, and it is substantial.
* **In repayment** the line is closed to new draws. The balance falls on a schedule. The
  draw fraction is near zero and the small residual is noise, not behaviour.

One model with an interaction term would average those two regimes together and be wrong
about both. Two models and a router is the honest structure, and it is what §8.7 exists for.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
ACCOUNTS = 430
FIRST = (2023, 1)
MONTHS = 24  # 2023-01 .. 2024-12, and the target reaches twelve months past each
SEED = 20260922
DRAW_PERIOD_MONTHS = 120  # ten years, the usual HELOC structure

# The generating coefficients for each regime, reported in the README so the fit can be
# compared against them.
TRUE_DRAW = {"d0": -1.55, "dEq": 1.30, "dRoom": 0.95, "dRate": -0.11}
TRUE_REPAY = {"r0": -4.20, "rEq": 0.38}


def month_ends(n: int) -> list[dt.date]:
    out = []
    year, month = FIRST
    for _ in range(n):
        first_next = dt.date(year + month // 12, month % 12 + 1, 1)
        out.append(first_next - dt.timedelta(days=1))
        year, month = first_next.year, first_next.month
    return out


def generate() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    # The tape runs MONTHS months; the target needs twelve more, so the account paths are
    # simulated for MONTHS + 12 and only the first MONTHS are published as the tape.
    dates = month_ends(MONTHS + 12)
    tape, later = [], []
    for k in range(ACCOUNTS):
        account = f"H{k:05d}"
        commitment = round(float(rng.uniform(25_000, 250_000)), 2)
        rate = round(float(np.clip(rng.normal(0.082, 0.014), 0.04, 0.14)), 5)
        opened = int(rng.integers(1, 190))  # months since origination at the window's start
        drawn = commitment * float(np.clip(rng.beta(2.0, 3.0), 0.0, 0.97))
        cltv = float(np.clip(rng.normal(0.68, 0.14), 0.15, 0.98))
        path = []
        for m in range(len(dates)):
            seasoning = opened + m
            in_draw = int(seasoning <= DRAW_PERIOD_MONTHS)
            room = max(commitment - drawn, 0.0) / commitment
            equity = max(1.0 - cltv, 0.0)
            if in_draw:
                z = (
                    TRUE_DRAW["d0"]
                    + TRUE_DRAW["dEq"] * equity
                    + TRUE_DRAW["dRoom"] * room
                    + TRUE_DRAW["dRate"] * (100.0 * rate - 8.0)
                )
            else:
                z = TRUE_REPAY["r0"] + TRUE_REPAY["rEq"] * equity
            monthly_fraction = 1.0 / (1.0 + np.exp(-z)) / 12.0
            path.append(
                {
                    "date": dates[m],
                    "commitment": round(commitment, 2),
                    "drawn": round(drawn, 2),
                    "cltv": round(cltv, 4),
                    "rate": rate,
                    "seasoning": seasoning,
                    "in_draw": in_draw,
                }
            )
            # the balance moves: new draws against the room, less scheduled repayment
            undrawn = max(commitment - drawn, 0.0)
            draw = undrawn * float(np.clip(monthly_fraction + rng.normal(0, 0.004), 0, 1))
            repay = drawn * (0.004 if in_draw else 0.0115)
            drawn = float(np.clip(drawn + draw - repay, 0.0, commitment))
            cltv = float(np.clip(cltv - 0.0021 + rng.normal(0, 0.0015), 0.05, 0.99))
        for m in range(MONTHS):
            row = path[m]
            tape.append(
                {
                    **row,
                    "account": account,
                    "kt": f"{row['date'] + dt.timedelta(days=3)}T08:00:00Z",
                }
            )
            later.append(
                {
                    "date": row["date"],
                    "account": account,
                    "exposure12": round(path[m + 12]["drawn"], 2),
                    "kt": f"{path[m + 12]['date'] + dt.timedelta(days=3)}T08:00:00Z",
                }
            )
    tape_frame = pd.DataFrame(tape)[
        ["date", "account", "commitment", "drawn", "cltv", "rate", "seasoning", "in_draw", "kt"]
    ]
    return {"heloc_month": tape_frame, "exposure_later": pd.DataFrame(later)}


def main() -> int:
    DATA.mkdir(exist_ok=True)
    frames = generate()
    for name, frame in frames.items():
        path = DATA / f"{name}.csv"
        frame.to_csv(path, index=False, lineterminator="\n")
        print(
            f"wrote {path.relative_to(HERE.parent.parent)}  {len(frame):,} rows, "
            f"{path.stat().st_size / 1e6:.2f} MB"
        )
    tape, later = frames["heloc_month"], frames["exposure_later"]
    joined = tape.merge(later, on=["date", "account"], suffixes=("", "_l"))
    undrawn = joined["commitment"] - joined["drawn"]
    usable = undrawn > 1.0
    fraction = ((joined["exposure12"] - joined["drawn"]) / undrawn)[usable]
    for regime, label in ((1, "draw period"), (0, "repayment")):
        sel = joined.loc[usable, "in_draw"] == regime
        print(
            f"{label:<12} {int(sel.sum()):>7,} rows, "
            f"mean twelve-month draw fraction {fraction[sel].mean():+.3f}"
        )
    print(
        f"utilisation at the tape date: mean {(joined['drawn'] / joined['commitment']).mean():.1%}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
