"""
Write the study's input feed: ten years of death counts and exposures by age, sex and region.

    .venv/bin/python case_studies/45-gompertz-makeham-mortality/make_data.py

Each row is one cell — a year, an age from 40 to 95, a sex and one of three regions — with
the central exposure (person-years lived) and the deaths observed in it. Deaths are drawn
from a Poisson distribution whose rate follows a Gompertz–Makeham law with mortality
improving over time,

    mu(age, t) = (A + B * exp(gamma * age)) * exp(-lambda * t),   t = years since 2015,

scaled by 1.30 for men and 0.78 for women and by a few percent by region. The ``rate`` column
is deaths over exposure, the observed central death rate. Figures for a year are published
six months after it ends. Seeded; synthetic; no person is real.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
A, B, GAMMA, LAMBDA = 0.0005, 0.000025, 0.105, 0.015
SEX = {"M": 1.30, "F": 0.78}
REGION = {"north": 1.06, "central": 1.00, "south": 0.95}


def main() -> None:
    rng = np.random.default_rng(4545)
    rows = []
    for year in range(2015, 2025):
        day = dt.date(year, 12, 31)
        t = year - 2015
        for sex, s in SEX.items():
            for region, r in REGION.items():
                for age in range(40, 96):
                    exposure = 20_000 * math.exp(-0.035 * (age - 40)) * rng.uniform(0.9, 1.1)
                    mu = (A + B * math.exp(GAMMA * age)) * math.exp(-LAMBDA * t) * s * r
                    deaths = int(rng.poisson(mu * exposure))
                    rows.append(
                        {
                            "date": day.isoformat(),
                            "cell": f"{sex}-{region}-{age}",
                            "age": age,
                            "t": t,
                            "sex": sex,
                            "region": region,
                            "exposure": round(exposure, 1),
                            "deaths": deaths,
                            "rate": round(deaths / exposure, 7),
                            "kt": f"{dt.date(year + 1, 6, 30)}T09:00:00Z",
                        }
                    )
    (HERE / "data").mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(HERE / "data" / "mortality_experience.csv", index=False)
    print(f"wrote {len(rows):,} rows to data/mortality_experience.csv")


if __name__ == "__main__":
    main()
