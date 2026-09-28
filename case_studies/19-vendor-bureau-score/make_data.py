"""
Write the study's inputs: a year of credit applications with their twelve-month outcome,
three later months of live applications, and what the vendor delivered.

    .venv/bin/python case_studies/19-vendor-bureau-score/make_data.py

* ``applications.csv`` — 2025: 150 applications a month, with four bureau attributes
  (``utilisation`` of revolving credit, recent ``delinquencies``, ``age_of_file`` in years,
  credit ``inquiries`` in six months) and the applicant's ``region``, all known on the
  application date.
* ``outcomes.csv`` — whether each applicant defaulted within twelve months, drawn from the
  vendor's own scoring function plus noise so the score is informative but not perfect,
  and known only a year after the application.
* ``live_2026.csv`` — January to March 2026, inputs only, as the scoring service sees them.
  Utilisation drifts upward month by month -- a cost-of-living squeeze -- which is what the
  drift covenant is there to catch.
* ``vendor/`` — what the vendor shipped: an MLflow ``MLmodel`` file naming the inputs and
  output, and ``vendor_bureau_credit_score.py``, the scoring code.

Seeded; synthetic; no applicant is real.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
WEIGHTS = {
    "intercept": -3.1,
    "utilisation": 2.4,
    "delinquencies": 0.55,
    "age_of_file": -0.06,
    "inquiries": 0.18,
}
REGIONS = ["north", "south", "east", "west"]


def score(frame: pd.DataFrame) -> np.ndarray:
    z = WEIGHTS["intercept"] + sum(WEIGHTS[k] * frame[k] for k in WEIGHTS if k != "intercept")
    return 1.0 / (1.0 + np.exp(-z))


def applicants(rng: np.random.Generator, n: int, shift: float = 0.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "utilisation": np.clip(rng.beta(2, 3, n) + shift, 0, 1).round(4),
            "delinquencies": rng.poisson(0.4, n),
            "age_of_file": rng.gamma(3, 3, n).round(2),
            "inquiries": rng.poisson(1.2, n),
            "region": rng.choice(REGIONS, n),
        }
    )


def main() -> None:
    rng = np.random.default_rng(1919)
    rows = []
    for month in range(1, 13):
        day = dt.date(2025, month, 28)
        frame = applicants(rng, 150)
        frame.insert(0, "applicant", [f"A{month:02d}{i:04d}" for i in range(150)])
        frame.insert(0, "date", day.isoformat())
        p = np.clip(score(frame) * rng.lognormal(0, 0.25, 150), 0, 0.95)
        outcome = frame[["date", "applicant"]].copy()
        outcome["default_12m"] = (rng.random(150) < p).astype(int)
        outcome["kt"] = f"{day.replace(year=2026)}T00:00:00Z"  # known a year later
        frame["kt"] = f"{day}T18:00:00Z"  # the bureau file, the evening it was pulled
        rows.append((frame, outcome))
    (HERE / "data").mkdir(exist_ok=True)
    pd.concat(r[0] for r in rows).to_csv(HERE / "data" / "applications.csv", index=False)
    pd.concat(r[1] for r in rows).to_csv(HERE / "data" / "outcomes.csv", index=False)
    live = []
    for month, shift in ((1, 0.0), (2, 0.05), (3, 0.10)):
        frame = applicants(rng, 400, shift)
        frame.insert(0, "month", f"2026-{month:02d}")
        live.append(frame)
    pd.concat(live).to_csv(HERE / "data" / "live_2026.csv", index=False)
    print("wrote data/applications.csv, data/outcomes.csv and data/live_2026.csv")


if __name__ == "__main__":
    main()
