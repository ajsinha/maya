"""
Write the study's input feed: corporate exposures at four quarter-ends, with the capital
the regulator's reference calculator gives for each.

    .venv/bin/python case_studies/09-basel-irb-capital/make_data.py

The recipe, seeded so every run writes the same file:

* 300 corporate obligors, observed at the four quarter-ends of 2025.
* ``pd`` — the rating system's one-year probability of default, log-uniform between three
  basis points (the regulatory floor) and 20%.
* ``lgd`` — loss given default, uniform between 25% and 60%; ``ead`` — exposure at default,
  log-normal around 5 million.
* ``maturity`` — effective maturity in years, uniform between 0.1 and 9. A fifth of the book
  is shorter than a year and another fifth longer than five, which is what makes the
  regulation's floor and cap matter.
* ``reference_k`` — the capital requirement per unit of EAD computed by the regulator's
  reference implementation of the corporate IRB formula, with the maturity floored at one
  year and capped at five (CRR Article 162, Basel CRE31). It is the benchmark the governed
  model is reconciled against, not an input to it.
* ``kt`` — when the quarter's figures were known: twenty-five days after the quarter-end.

Everything is synthetic; no obligor is real.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
QUARTERS = [dt.date(2025, 3, 31), dt.date(2025, 6, 30), dt.date(2025, 9, 30), dt.date(2025, 12, 31)]
N = NormalDist()


def reference_k(pd_: float, lgd: float, maturity: float) -> float:
    """The corporate IRB capital requirement per unit of EAD, as the regulation states it."""
    corr = 0.12 * (1 - math.exp(-50 * pd_)) / (1 - math.exp(-50)) + 0.24 * (
        1 - (1 - math.exp(-50 * pd_)) / (1 - math.exp(-50))
    )
    b = (0.11852 - 0.05478 * math.log(pd_)) ** 2
    m = min(max(maturity, 1.0), 5.0)
    adjustment = (1 + (m - 2.5) * b) / (1 - 1.5 * b)
    conditional = N.cdf((N.inv_cdf(pd_) + math.sqrt(corr) * N.inv_cdf(0.999)) / math.sqrt(1 - corr))
    return (lgd * conditional - pd_ * lgd) * adjustment


def main() -> None:
    rng = np.random.default_rng(909)
    obligors = [f"C{i:04d}" for i in range(300)]
    base_pd = np.exp(rng.uniform(np.log(0.0003), np.log(0.20), len(obligors)))
    base_lgd = rng.uniform(0.25, 0.60, len(obligors))
    base_ead = rng.lognormal(np.log(5e6), 0.8, len(obligors))
    base_m = rng.uniform(0.1, 9.0, len(obligors))
    rows = []
    for q, day in enumerate(QUARTERS):
        drift = np.exp(rng.normal(0, 0.10, len(obligors)))  # ratings migrate a little
        for i, name in enumerate(obligors):
            # rounded first, and the reference computed from exactly what the file holds, so
            # a correct implementation reconciles to the last digit rather than to rounding
            pd_ = round(float(min(max(base_pd[i] * drift[i], 0.0003), 0.25)), 6)
            lgd = round(float(base_lgd[i]), 4)
            m = round(float(max(base_m[i] - 0.25 * q, 0.05)), 3)
            rows.append(
                {
                    "date": day.isoformat(),
                    "obligor": name,
                    "pd": pd_,
                    "lgd": lgd,
                    "ead": round(float(base_ead[i]), 2),
                    "maturity": m,
                    "reference_k": reference_k(pd_, lgd, m),
                    "kt": f"{day + dt.timedelta(days=25)}T12:00:00Z",
                }
            )
    frame = pd.DataFrame(rows)
    (HERE / "data").mkdir(exist_ok=True)
    frame.to_csv(HERE / "data" / "corporate_exposures.csv", index=False)
    print(f"wrote {len(frame):,} rows to data/corporate_exposures.csv")


if __name__ == "__main__":
    main()
