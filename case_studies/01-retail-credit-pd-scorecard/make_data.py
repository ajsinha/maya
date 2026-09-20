"""
The book this case study ingests, written to ``data/`` as CSV.

    .venv/bin/python case_studies/01-retail-credit-pd-scorecard/make_data.py

The files are committed, so the study runs with no generation step and a reader can
open the data and see exactly what MAYA was given. This script is here because
synthetic data with no visible recipe is worse than no data: the recipe is the part
that says what the study is actually demonstrating.

Three feeds, deliberately imperfect in the ways real feeds are:

* ``servicing_monthly.csv`` — the monthly servicing extract, cut five days after month
  end, so every value is *known* five days after the date it is about;
* ``bureau_file.csv`` — a credit bureau file on a quarterly cycle, delivered a
  fortnight after the quarter it describes, so at most observation months it is stale;
* ``default_outcome.csv`` — whether the account defaulted in the twelve months after
  the observation month, which cannot be known until a year and a day later.

The truth underneath is a logistic hazard in utilisation, debt-to-income, the
delinquency count and a latent borrower quality that the bureau score sees noisily. A
scorecard fitted on the three observable drivers and the bureau score can therefore
find something real, and will not find it perfectly — which is what makes the
validation evidence in the model's specification worth reading.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
ACCOUNTS = 1_200
FIRST = (2023, 1)
MONTHS = 30  # 2023-01 .. 2025-06
SEED = 20260919


def month_ends() -> list[dt.date]:
    """The last day of each of ``MONTHS`` months from ``FIRST``."""
    out = []
    year, month = FIRST
    for _ in range(MONTHS):
        first_next = dt.date(year + month // 12, month % 12 + 1, 1)
        out.append(first_next - dt.timedelta(days=1))
        year, month = first_next.year, first_next.month
    return out


def generate() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    dates = month_ends()
    accounts = [f"A{n:05d}" for n in range(ACCOUNTS)]
    quality = rng.normal(size=ACCOUNTS)  # latent, never observed by the model
    servicing, outcome, bureau = [], [], []
    for i, account in enumerate(accounts):
        drift = rng.normal(0, 0.10, MONTHS).cumsum() * 0.05
        util = np.clip(0.45 - 0.18 * quality[i] + drift, 0.0, 1.0)
        dti = np.clip(0.32 - 0.08 * quality[i] + rng.normal(0, 0.03, MONTHS), 0.01, 0.95)
        delinq = rng.poisson(np.clip(0.25 - 0.12 * quality[i], 0.01, None), MONTHS)
        mob = np.arange(MONTHS) + int(rng.integers(6, 120))
        for m, date in enumerate(dates):
            servicing.append(
                {
                    "date": date,
                    "account": account,
                    "utilisation": round(float(util[m]), 4),
                    "dti": round(float(dti[m]), 4),
                    "delinquencies": int(delinq[m]),
                    "months_on_book": int(mob[m]),
                    "kt": f"{date + dt.timedelta(days=5)}T02:00:00Z",
                }
            )
            z = -3.1 + 2.4 * util[m] + 1.9 * dti[m] + 0.55 * delinq[m] - 0.40 * quality[i]
            outcome.append(
                {
                    "date": date,
                    "account": account,
                    "default_12m": int(rng.random() < 1.0 / (1.0 + np.exp(-z))),
                    "kt": f"{date + dt.timedelta(days=366)}T00:00:00Z",
                }
            )
            if date.month in (3, 6, 9, 12):
                score = float(np.clip(680 + 55 * quality[i] + rng.normal(0, 18), 300, 850))
                bureau.append(
                    {
                        "date": date,
                        "account": account,
                        "bureau_score": round(score, 1),
                        "kt": f"{date + dt.timedelta(days=15)}T06:00:00Z",
                    }
                )
    return {
        "servicing_monthly": pd.DataFrame(servicing),
        "bureau_file": pd.DataFrame(bureau),
        "default_outcome": pd.DataFrame(outcome),
    }


def main() -> int:
    DATA.mkdir(exist_ok=True)
    for name, frame in generate().items():
        path = DATA / f"{name}.csv"
        frame.to_csv(path, index=False, lineterminator="\n")
        size = path.stat().st_size / 1e6
        print(f"wrote {path.relative_to(HERE.parent.parent)}  {len(frame):,} rows, {size:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
