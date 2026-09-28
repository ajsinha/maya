"""
The feed this case study ingests, written to ``data/`` as CSV.

    .venv/bin/python case_studies/08-arima-garch/make_data.py

Time series are the awkward case for a platform whose models are row-wise expressions,
and the data is shaped to make both halves of that awkwardness visible.

* ``index_daily.csv`` — the daily close of three equity indices and the log return
  computed from it. Known that evening, which for a closing price is the one lag nobody
  argues about.

The returns are generated from a process with two parts, and they are the two halves of
the study:

* the **conditional mean** is an AR(2) — today's return depends on yesterday's and the
  day before's, which is expressible as a row-wise formula once the lags are features;
* the **conditional variance** is a GARCH(1,1) — today's variance depends on yesterday's
  squared shock *and* yesterday's variance, which is not expressible that way at all,
  because the variance is a state carried from row to row.

The generating parameters are stated below and reported in the README so both fits can be
compared against the process. The GARCH persistence is deliberately high but stationary,
α + β = 0.972, because that is where real equity volatility sits and it is where the
constraint MAYA cannot express starts to matter.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
INDICES = ("AZX", "BQI", "CVM")
DAYS = 1_400  # about five and a half years of business days
FIRST = dt.date(2020, 1, 2)
SEED = 20260924

# The conditional mean: an AR(2) on the log return, in basis points a day.
TRUE_AR = {"c": 0.00028, "phi1": 0.062, "phi2": -0.041}
# The conditional variance: GARCH(1,1). omega is scaled so the long-run daily volatility is
# about 1.1%, and alpha + beta = 0.972, which is persistent and stationary — where real
# equity volatility actually sits.
TRUE_GARCH = {"omega": 3.39e-6, "alpha": 0.092, "beta": 0.880}


def business_days(n: int, start: dt.date) -> list[dt.date]:
    out, day = [], start
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day += dt.timedelta(days=1)
    return out


def simulate(rng: np.random.Generator, n: int) -> tuple[np.ndarray, np.ndarray]:
    """One AR(2)-GARCH(1,1) path, and the conditional variance that produced it."""
    omega, alpha, beta = TRUE_GARCH["omega"], TRUE_GARCH["alpha"], TRUE_GARCH["beta"]
    c, phi1, phi2 = TRUE_AR["c"], TRUE_AR["phi1"], TRUE_AR["phi2"]
    burn = 400
    total = n + burn
    variance = np.empty(total)
    shock = np.empty(total)
    returns = np.zeros(total)
    variance[0] = omega / max(1.0 - alpha - beta, 1e-6)  # the unconditional variance
    shock[0] = rng.normal(0.0, np.sqrt(variance[0]))
    returns[0] = c + shock[0]
    for t in range(1, total):
        variance[t] = omega + alpha * shock[t - 1] ** 2 + beta * variance[t - 1]
        shock[t] = rng.normal(0.0, np.sqrt(variance[t]))
        mean = c + phi1 * returns[t - 1] + (phi2 * returns[t - 2] if t >= 2 else 0.0)
        returns[t] = mean + shock[t]
    return returns[burn:], variance[burn:]


def generate() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    dates = business_days(DAYS, FIRST)
    rows = []
    for index in INDICES:
        returns, _ = simulate(rng, DAYS)
        close = 1000.0 * np.exp(np.cumsum(returns))
        for t, date in enumerate(dates):
            rows.append(
                {
                    "date": date,
                    "index": index,
                    "close": round(float(close[t]), 4),
                    "ret": round(float(returns[t]), 8),
                    # a closing price is known that evening
                    "kt": f"{date}T21:30:00Z",
                }
            )

    return {"index_daily": pd.DataFrame(rows)}


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
    daily = frames["index_daily"]
    print(f"generated AR(2)    c={TRUE_AR['c']:.5f} phi1={TRUE_AR['phi1']} phi2={TRUE_AR['phi2']}")
    print(
        f"generated GARCH    omega={TRUE_GARCH['omega']:.3e} alpha={TRUE_GARCH['alpha']} "
        f"beta={TRUE_GARCH['beta']}  (alpha+beta={TRUE_GARCH['alpha'] + TRUE_GARCH['beta']:.3f})"
    )
    for index in INDICES:
        r = daily.loc[daily["index"] == index, "ret"]
        print(
            f"{index}: daily volatility {r.std():.4%}, annualised {r.std() * 252**0.5:.1%}, "
            f"kurtosis {float(((r - r.mean()) ** 4).mean() / r.var() ** 2):.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
