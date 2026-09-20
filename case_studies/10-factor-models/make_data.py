"""
The two feeds this case study ingests, written to ``data/`` as CSV.

    .venv/bin/python case_studies/10-factor-models/make_data.py

The files are committed, so the study runs with no generation step and a reader can open
the data and see exactly what MAYA was given.

* ``equity_daily.csv`` — a daily return tape for thirty stocks, indexed on
  ``(date, stock)``. It carries the total return and the excess return over the daily
  risk-free rate, and its knowledge time is the **evening of the same day**: a close is
  known when the market closes.
* ``factor_daily.csv`` — the factor library: the market, size, value, profitability and
  investment factors, plus the risk-free rate. **One row per date**, indexed on ``date``
  alone, because a factor return is not a property of any stock. MAYA joins it onto the
  ``(date, stock)`` panel on the index the two share. Its knowledge time is the **fourth
  day of the following month**, because a factor library is rebuilt and republished after
  the month it describes has ended — which is the bitemporal fact the whole study turns
  on, and the reason a factor model is an attribution model and not a forecast.

The truth underneath is a five-factor structure with no alpha in it at all:

    excess_return[i,t] = b[i]*mktRf[t] + s[i]*smb[t] + h[i]*hml[t]
                       + r[i]*rmw[t] + c[i]*cma[t] + e[i,t]

Every stock's true alpha is exactly zero. The loadings are drawn per stock, and the
universe is deliberately **tilted small and value** — the average size loading is +0.60
and the average value loading is +0.40 — over a window in which SMB and HML both earned
money. So a CAPM regression on this book, which sees only the market factor, must report
a positive alpha; that alpha is the size and value premium the model cannot see, and it
is exactly what version 2 of the model exists to absorb. The average investment loading
is zero on purpose, so that one of the five coefficients comes back insignificant and the
study has to say so.

Two quantities are set **exactly** rather than drawn, for the same reason case study 3
draws its rate path down and then up instead of sampling it: what the window has to
contain is not random.

* Each factor's realised mean over the 504 days is the stated premium, to the last
  decimal place — the noise is random, the premium is not. A window in which size earned
  nothing would leave version 1 with no alpha for version 2 to explain, and the study
  would be about a coincidence.
* The equal-weighted mean of the thirty loadings is the stated loading exactly. A pooled
  regression over the universe estimates that mean, so stating it exactly is what makes
  the *fitted against generated* table in the README a comparison rather than a guess.

The idiosyncratic noise is drawn per stock (a daily volatility between 0.9% and 1.6%),
which is what stops the fit being exact and makes the standard errors worth quoting.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
STOCKS = 30
DAYS = 504  # two years of trading days from 2023-01-02
FIRST = dt.date(2023, 1, 2)
SEED = 20260920

# The truth, reported in the README so the fits can be compared against it. These are the
# *means* of the per-stock loadings: what a pooled regression over the whole universe is
# estimating is the equal-weighted universe's exposure, not any one stock's.
TRUE_LOADINGS = {"beta": 1.00, "bSmb": 0.60, "bHml": 0.40, "bRmw": 0.05, "bCma": 0.00}
LOADING_SD = {"beta": 0.25, "bSmb": 0.50, "bHml": 0.50, "bRmw": 0.30, "bCma": 0.30}
TRUE_ALPHA = 0.0

# Daily factor means and volatilities, in decimal. The size and value means are at the top
# of what has been realised over a two-year run, which is what makes the omitted-factor
# alpha in version 1 large enough to read rather than large enough to argue about.
FACTOR_MEAN = {"mkt_rf": 0.00030, "smb": 0.00060, "hml": 0.00040, "rmw": 0.00010, "cma": 0.00005}
FACTOR_SD = {"mkt_rf": 0.0100, "smb": 0.0060, "hml": 0.0060, "rmw": 0.0050, "cma": 0.0050}
FACTORS = tuple(FACTOR_MEAN)


def trading_days() -> list[dt.date]:
    """``DAYS`` weekdays from ``FIRST``. Public holidays are not modelled, and the study
    says so: a missing holiday changes nothing a factor regression can see."""
    out, day = [], FIRST
    while len(out) < DAYS:
        if day.weekday() < 5:
            out.append(day)
        day += dt.timedelta(days=1)
    return out


def library_published(day: dt.date) -> str:
    """When a factor library first knows ``day``: the 4th of the following month, noon UTC.

    This is the shape of a real factor library. The month's returns are assembled from the
    cross-section after the month has closed, so a value for the 2nd of a month is not
    knowable until a month and four days later."""
    first_next = dt.date(day.year + day.month // 12, day.month % 12 + 1, 1)
    return f"{first_next + dt.timedelta(days=3)}T12:00:00Z"


def exactly(draws: np.ndarray, mean: float) -> np.ndarray:
    """``draws`` recentred so their mean is ``mean`` exactly (see the module docstring)."""
    return draws - draws.mean() + mean


def generate() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    dates = trading_days()
    stocks = [f"SYN{n:02d}" for n in range(1, STOCKS + 1)]

    factors = {
        name: exactly(rng.normal(0.0, FACTOR_SD[name], DAYS), FACTOR_MEAN[name]) for name in FACTORS
    }
    # The risk-free rate drifts from about 4.0% to about 5.0% annualised across the window.
    rf = np.linspace(0.00016, 0.00020, DAYS)

    loadings = {
        name: exactly(rng.normal(0.0, LOADING_SD[name], STOCKS), TRUE_LOADINGS[name])
        for name in TRUE_LOADINGS
    }
    idio = rng.uniform(0.009, 0.016, STOCKS)

    rows = []
    for i, stock in enumerate(stocks):
        excess = (
            TRUE_ALPHA
            + loadings["beta"][i] * factors["mkt_rf"]
            + loadings["bSmb"][i] * factors["smb"]
            + loadings["bHml"][i] * factors["hml"]
            + loadings["bRmw"][i] * factors["rmw"]
            + loadings["bCma"][i] * factors["cma"]
            + rng.normal(0.0, idio[i], DAYS)
        )
        total = excess + rf
        for t, day in enumerate(dates):
            rows.append(
                {
                    "date": day,
                    "stock": stock,
                    "total_return": round(float(total[t]), 6),
                    "excess_return": round(float(excess[t]), 6),
                    "kt": f"{day}T21:00:00Z",
                }
            )

    factor_rows = [
        {
            "date": day,
            **{name: round(float(factors[name][t]), 6) for name in FACTORS},
            "rf": round(float(rf[t]), 6),
            "kt": library_published(day),
        }
        for t, day in enumerate(dates)
    ]
    return {
        "equity_daily": pd.DataFrame(rows),
        "factor_daily": pd.DataFrame(factor_rows),
    }


def main() -> int:
    DATA.mkdir(exist_ok=True)
    frames = generate()
    for name, frame in frames.items():
        path = DATA / f"{name}.csv"
        frame.to_csv(path, index=False, lineterminator="\n")
        size = path.stat().st_size / 1e6
        print(f"wrote {path.relative_to(HERE.parent.parent)}  {len(frame):,} rows, {size:.2f} MB")
    print("\nrealised factor premia over the window, annualised at 252 days:")
    for name in FACTORS:
        print(f"  {name:<8} {frames['factor_daily'][name].mean() * 252:+.2%}")
    print("\nthe universe's mean loadings, which a pooled regression estimates:")
    for name, value in TRUE_LOADINGS.items():
        print(f"  {name:<8} {value:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
