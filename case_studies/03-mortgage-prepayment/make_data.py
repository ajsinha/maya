"""
The four feeds this case study ingests, written to ``data/`` as CSV.

    .venv/bin/python case_studies/03-mortgage-prepayment/make_data.py

Case study 2 said prepayment was out of its scope and needed a model of its own. This
is that model, and its data is shaped by what actually drives a borrower to refinance:

* ``loan_month.csv`` — the monthly tape again, but with what a prepayment model reads
  rather than what a cashflow model reads: the loan's own coupon, how seasoned it is,
  and how much equity the borrower has. Cut two business days after month end.
* ``mortgage_rate.csv`` — the prevailing thirty-year mortgage rate, **one number a
  month, indexed on date alone**. It is not a property of any loan, and MAYA joins it
  onto the loan panel on the index the two share. Published the first business day
  after the month it describes.
* ``seasonality.csv`` — also date-indexed: whether the month is in the moving season.
  House moves cluster in summer, and a prepayment model that ignores that will blame
  the rate incentive for a turnover effect.
* ``prepaid.csv`` — whether the loan paid off in full that month. Known a month later,
  when the servicer's remittance settles, which is the bitemporal fact that makes the
  target a target.

The truth underneath is a logistic hazard in four things, in this order of strength:
the rate incentive (the loan's coupon less the market rate — a borrower paying 6.5%
when the market offers 4.5% has two points of reason to move), the seasoning ramp (a
loan two months old almost never prepays, whatever the incentive), the borrower's
equity (refinancing needs equity to refinance into), and the moving season.

The rate path falls for the first year and rises through the second, so the book moves
from out of the money to in and back. Without that a prepayment model has nothing to
learn: a constant incentive cannot tell you the coefficient on incentive.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
LOANS = 600
FIRST = (2023, 7)
MONTHS = 30  # 2023-07 .. 2025-12
SEED = 20260921

# The truth. Reported in the README so a reader can compare the fit against it.
TRUE = {"a0": -6.10, "aInc": 0.62, "aAge": 0.34, "aEq": 1.45, "aSum": 0.38}
MOVING_SEASON = (5, 6, 7, 8)  # May to August


def month_ends() -> list[dt.date]:
    out = []
    year, month = FIRST
    for _ in range(MONTHS):
        first_next = dt.date(year + month // 12, month % 12 + 1, 1)
        out.append(first_next - dt.timedelta(days=1))
        year, month = first_next.year, first_next.month
    return out


def rate_path(n: int, rng: np.random.Generator) -> np.ndarray:
    """A market rate that falls for a year and rises through the next, with noise.

    A prepayment model fitted on a flat rate path learns nothing about incentive: the
    coefficient is unidentified, and a fit will report one anyway."""
    half = n // 2
    down = np.linspace(0.0685, 0.0455, half)
    up = np.linspace(0.0455, 0.0640, n - half)
    return np.clip(np.concatenate([down, up]) + rng.normal(0, 0.0007, n), 0.02, 0.12)


def generate() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    dates = month_ends()
    market = rate_path(MONTHS, rng)
    rates = [
        {
            "date": date,
            "mkt_rate": round(float(market[m]), 5),
            # the survey is published on the first business day after the month
            "kt": f"{date + dt.timedelta(days=1)}T11:00:00Z",
        }
        for m, date in enumerate(dates)
    ]
    season = [
        {
            "date": date,
            "moving_season": int(date.month in MOVING_SEASON),
            "kt": f"{date - dt.timedelta(days=365)}T00:00:00Z",  # a calendar fact, known a year out
        }
        for date in dates
    ]

    tape, outcome = [], []
    for k in range(LOANS):
        loan = f"P{k:05d}"
        wac = round(float(np.clip(rng.normal(0.0605, 0.0105, 1)[0], 0.028, 0.098)), 5)
        age0 = int(rng.integers(1, 140))
        ltv0 = float(np.clip(rng.normal(0.72, 0.13), 0.20, 0.97))
        balance = round(float(rng.uniform(90_000, 700_000)), 2)
        alive = True
        for m, date in enumerate(dates):
            if not alive:
                break
            age = age0 + m
            # equity builds as the loan amortises and, more, as prices drift up
            ltv = float(np.clip(ltv0 * (1 - 0.004 * m) - 0.0025 * m, 0.05, 0.99))
            tape.append(
                {
                    "date": date,
                    "loan": loan,
                    "wac": wac,
                    "age": age,
                    "ltv": round(ltv, 4),
                    "balance": round(balance, 2),
                    "kt": f"{date + dt.timedelta(days=2)}T07:00:00Z",
                }
            )
            incentive = 100.0 * (wac - float(market[m]))  # percentage points
            seasoning = min(age, 36) / 12.0  # the ramp flattens after three years
            z = (
                TRUE["a0"]
                + TRUE["aInc"] * incentive
                + TRUE["aAge"] * seasoning
                + TRUE["aEq"] * (1.0 - ltv)
                + TRUE["aSum"] * float(date.month in MOVING_SEASON)
            )
            prepaid = int(rng.random() < 1.0 / (1.0 + np.exp(-z)))
            outcome.append(
                {
                    "date": date,
                    "loan": loan,
                    "prepaid": prepaid,
                    # known when the next remittance settles
                    "kt": f"{date + dt.timedelta(days=31)}T12:00:00Z",
                }
            )
            if prepaid:
                alive = False  # a loan that pays off in full leaves the book
            else:
                balance *= 0.9965
    return {
        "loan_month": pd.DataFrame(tape),
        "mortgage_rate": pd.DataFrame(rates),
        "seasonality": pd.DataFrame(season),
        "prepaid": pd.DataFrame(outcome),
    }


def main() -> int:
    DATA.mkdir(exist_ok=True)
    frames = generate()
    for name, frame in frames.items():
        path = DATA / f"{name}.csv"
        frame.to_csv(path, index=False, lineterminator="\n")
        size = path.stat().st_size / 1e6
        print(f"wrote {path.relative_to(HERE.parent.parent)}  {len(frame):,} rows, {size:.2f} MB")
    smm = frames["prepaid"]["prepaid"].mean()
    print(f"monthly prepayment rate {smm:.3%}  (annualised CPR {1 - (1 - smm) ** 12:.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
