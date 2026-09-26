"""
Write the study's input feed: two years of weekly prices and unit sales for forty products.

    .venv/bin/python case_studies/42-demand-elasticity/make_data.py

Demand follows a constant-elasticity law with an elasticity of -1.6 shared across the
range. Each row carries ``price_index`` — the week's price as a multiple of the product's
reference price, moved by promotions and list-price changes between 0.65 and 1.3 — and
``demand_index``, the week's units as a multiple of the product's normal weekly units at
the reference price. Both models in the study explain the one from the other. Sales are known two days after the week closes. Seeded; the
products are fictional.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ELASTICITY = -1.6


def main() -> None:
    rng = np.random.default_rng(4242)
    rows = []
    reference = rng.uniform(2.0, 12.0, 40)
    start = dt.date(2024, 1, 7)
    for week in range(104):
        day = start + dt.timedelta(weeks=week)
        for i in range(40):
            price = reference[i] * rng.choice([1.0, 1.0, 1.0, 0.8, 0.65, 1.15, 1.3])
            index = (price / reference[i]) ** ELASTICITY * rng.lognormal(0, 0.15)
            rows.append(
                {
                    "date": day.isoformat(),
                    "product": f"P{i:02d}",
                    "price_index": round(float(price / reference[i]), 4),
                    "demand_index": round(float(index), 4),
                    "kt": f"{day + dt.timedelta(days=2)}T08:00:00Z",
                }
            )
    (HERE / "data").mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(HERE / "data" / "weekly_sales.csv", index=False)
    print(f"wrote {len(rows):,} rows to data/weekly_sales.csv")


if __name__ == "__main__":
    main()
