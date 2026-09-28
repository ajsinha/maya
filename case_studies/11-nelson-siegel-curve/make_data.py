"""
The curve desk's three feeds, written to ``data/``.

    .venv/bin/python case_studies/11-nelson-siegel-curve/make_data.py

A zero curve does not arrive from one place. The quotes arrive from the broking screens,
the curve itself arrives from the team that bootstraps it, and the report of how that build
went arrives with it:

* ``ois_par_quotes.csv`` — the closing par rate of the GBP OIS swap at each benchmark
  tenor, with the bid and the ask around it. Every business day from 2024-07-01 to
  2026-06-30. Published at 16:15 UTC, the fixing.
* ``zero_yields.csv`` — the continuously compounded zero rate the curve team publishes for
  each of those tenors, bootstrapped from those quotes. 18:40 UTC the same evening: two
  hours and twenty-five minutes after the quotes, because somebody had to build it.
* ``zero_curve_build_report.csv`` — one row a day describing that build: how many instruments went in,
  the largest residual it left against the quotes, and the method. The construction report
  of a piece of mathematics nobody governs, arriving in MAYA as a CSV.

**The recipe.** Seed 20260413. Every day's *true* zero curve is a Nelson–Siegel curve

    z     = tau / lambda
    slope = (1 - exp(-z)) / z
    curve = slope - exp(-z)
    y     = beta0 + beta1 slope + beta2 curve

whose factors move slowly, day to day, the way a curve's do:

* ``beta0`` — the long rate — is an Ornstein–Uhlenbeck process around 4.30% reverting at
  0.03 a day with a daily shock of 4 basis points, so it wanders over a range of tens of
  basis points across two years and never jumps;
* ``beta1`` — the short-end spread — drifts from −1.90% to −2.55% with its own OU noise:
  an upward-sloping curve, instantaneous rate near 2.1% against a long rate near 4.3%,
  steepening slowly, which is what a curve looks like after an easing cycle;
* ``beta2`` — the curvature — is an OU process around −0.85%, a mild dip through the belly;
* ``lambda`` is **fixed at 1.30 on every single day**, which matters: the case study
  measures how far a day-by-day estimate of it wanders when the truth does not move at all.

On top of that truth, two things a real published curve has and a textbook one does not.

**Observation noise that is larger at the short end.** Each pillar's noise has standard
deviation ``1.0bp + 6.0bp * exp(-tau / 0.8)``: about 6.4 basis points at one month, 2.7 at
one year, 1.0 from five years out. The front of an OIS curve is where meeting-date
expectations, turn-of-year effects and thin broking live, and it is genuinely noisier than
the ten-year point.

**A pillar bias the shape cannot represent.** A fixed, seeded vector of per-pillar offsets
of a basis point or two, the same every day. A real curve has kinks a three-factor shape
cannot reach — the two-year point sits where the market thinks the policy path turns — so a
per-day Nelson–Siegel fit has an irreducible residual that is not noise and does not
average away. Without it, calibration would be recovering nothing but its own error term.

The par quotes are then computed back *from* the noisy zeros, so the two feeds are
consistent the way a bootstrap makes them consistent: a money-market simple rate inside a
year and an annual-coupon par swap rate beyond it, discounting with ``D(t) = exp(-y(t) t)``
and interpolating the zero curve linearly in the maturity for coupon dates that are not
pillars. Bid and ask sit a quarter of a basis point either side.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
SEED = 20260413
FIRST, LAST = dt.date(2024, 7, 1), dt.date(2026, 6, 30)

# The benchmark tenors a sterling OIS book is quoted on, and their year fractions.
PILLARS: tuple[tuple[str, float], ...] = (
    ("1M", 1.0 / 12.0),
    ("2M", 2.0 / 12.0),
    ("3M", 0.25),
    ("6M", 0.5),
    ("9M", 0.75),
    ("1Y", 1.0),
    ("18M", 1.5),
    ("2Y", 2.0),
    ("3Y", 3.0),
    ("4Y", 4.0),
    ("5Y", 5.0),
    ("6Y", 6.0),
    ("7Y", 7.0),
    ("8Y", 8.0),
    ("9Y", 9.0),
    ("10Y", 10.0),
    ("12Y", 12.0),
    ("15Y", 15.0),
    ("20Y", 20.0),
    ("25Y", 25.0),
    ("30Y", 30.0),
)
LAMBDA_TRUE = 1.30
BETA0_MEAN = 0.0430
BETA1_START, BETA1_END = -0.0190, -0.0255
BETA2_MEAN = -0.0085
METHOD = "log-linear DF bootstrap, OIS discounting"


def business_days() -> list[dt.date]:
    return [d.date() for d in pd.bdate_range(FIRST, LAST)]


def loadings(tau: np.ndarray, lam: float) -> tuple[np.ndarray, np.ndarray]:
    """The Nelson–Siegel slope and curvature loadings at maturity ``tau``."""
    z = tau / lam
    decay = np.exp(-z)
    slope = (1.0 - decay) / z
    return slope, slope - decay


def ou(n: int, mean: float, sigma: float, speed: float, rng: np.random.Generator) -> np.ndarray:
    """An Ornstein–Uhlenbeck path: a level that wanders and comes back, and never jumps."""
    out = np.empty(n)
    value = mean
    for i in range(n):
        value += speed * (mean - value) + float(rng.normal(0.0, sigma))
        out[i] = value
    return out


def factors(dates: list[dt.date], rng: np.random.Generator) -> pd.DataFrame:
    """The true factor path: the curve the feeds are generated from, day by day."""
    n = len(dates)
    return pd.DataFrame(
        {
            "date": dates,
            "beta0": ou(n, BETA0_MEAN, 0.00040, 0.03, rng),
            "beta1": np.linspace(BETA1_START, BETA1_END, n) + ou(n, 0.0, 0.00035, 0.05, rng),
            "beta2": ou(n, BETA2_MEAN, 0.00050, 0.03, rng),
            "lambda": LAMBDA_TRUE,
        }
    )


def zero_panel(truth: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """The published zero curve: the true curve, a pillar bias, and short-end noise."""
    tenors = [name for name, _ in PILLARS]
    tau = np.array([years for _, years in PILLARS])
    slope, curve = loadings(tau, LAMBDA_TRUE)
    bias = rng.normal(0.0, 0.00010, len(tau))  # the kinks a three-factor shape cannot reach
    sigma = 0.00010 + 0.00060 * np.exp(-tau / 0.8)  # noisier at the front, as a curve is
    rows = []
    for row in truth.itertuples():
        true = row.beta0 + row.beta1 * slope + row.beta2 * curve
        observed = true + bias + rng.normal(0.0, 1.0, len(tau)) * sigma
        for i, tenor in enumerate(tenors):
            rows.append(
                {
                    "date": row.date,
                    "tenor": tenor,
                    "tau": round(float(tau[i]), 6),
                    "zeroYield": round(float(observed[i]), 7),
                    "trueYield": round(float(true[i]), 7),
                    "kt": f"{row.date}T18:40:00Z",
                }
            )
    return pd.DataFrame(rows)


def discount(tau: np.ndarray, yields: np.ndarray, at: float) -> float:
    """``exp(-y(t) t)`` with the zero curve interpolated linearly in the maturity."""
    return math.exp(-float(np.interp(at, tau, yields)) * at)


def par_rate(tau: np.ndarray, yields: np.ndarray, maturity: float) -> float:
    """A money-market simple rate inside a year, an annual-coupon par swap rate beyond it."""
    df_end = discount(tau, yields, maturity)
    if maturity <= 1.0:
        return (1.0 / df_end - 1.0) / maturity
    dates = [float(k) for k in range(1, int(math.floor(maturity)) + 1)]
    if dates[-1] < maturity - 1e-9:
        dates.append(maturity)
    annuity, previous = 0.0, 0.0
    for when in dates:
        annuity += (when - previous) * discount(tau, yields, when)
        previous = when
    return (1.0 - df_end) / annuity


def par_panel(zeros: pd.DataFrame) -> pd.DataFrame:
    """The screens the curve was built from, implied back out of the curve itself."""
    tau_all = np.array([years for _, years in PILLARS])
    rows = []
    for date, day in zeros.groupby("date", sort=True):
        yields = day.sort_values("tau")["zeroYield"].to_numpy()
        for tenor, years in PILLARS:
            rate = par_rate(tau_all, yields, years)
            rows.append(
                {
                    "date": date,
                    "tenor": tenor,
                    "parYield": round(rate, 7),
                    "bidYield": round(rate - 0.000025, 7),
                    "askYield": round(rate + 0.000025, 7),
                    "kt": f"{date}T16:15:00Z",
                }
            )
    return pd.DataFrame(rows)


def build_panel(dates: list[dt.date], rng: np.random.Generator) -> pd.DataFrame:
    """One row a day: what the curve team says about the build it has just published.

    ``maxResidualBp`` is the largest error the bootstrap left against the quotes it was
    given — a bootstrap reprices its own instruments to a fraction of a basis point, so
    this is small and, on a bad day, less small. It is the error of a piece of mathematics
    that has no specification, no parameter set and no owner of record in MAYA, reported by
    the team that ran it, in a data column.
    """
    return pd.DataFrame(
        {
            "date": dates,
            "instruments": len(PILLARS) + rng.integers(0, 4, len(dates)),
            "maxResidualBp": np.round(np.abs(rng.normal(0.18, 0.09, len(dates))) + 0.02, 4),
            "method": METHOD,
            "kt": [f"{d}T18:40:00Z" for d in dates],
        }
    )


def generate() -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    dates = business_days()
    truth = factors(dates, rng)
    zeros = zero_panel(truth, rng)
    feeds = {
        "ois_par_quotes": par_panel(zeros),
        "zero_yields": zeros.drop(columns=["trueYield"]),
        "zero_curve_build_report": build_panel(dates, rng),
    }
    return feeds, truth, zeros


def main() -> int:
    DATA.mkdir(exist_ok=True)
    feeds, truth, zeros = generate()
    total = 0.0
    for name, frame in feeds.items():
        path = DATA / f"{name}.csv"
        frame.to_csv(path, index=False, lineterminator="\n")
        size = path.stat().st_size / 1e6
        total += size
        print(f"wrote {path.relative_to(HERE.parent.parent)}  {len(frame):,} rows, {size:.2f} MB")
    print(f"{total:.2f} MB in total")

    print("\nThe factors the curve was generated from, over the window:")
    for name in ("beta0", "beta1", "beta2", "lambda"):
        col = truth[name]
        print(
            f"    {name:<8} first {col.iloc[0]:+.5f}  last {col.iloc[-1]:+.5f}  "
            f"min {col.min():+.5f}  max {col.max():+.5f}"
        )
    print(f"    lambda is {LAMBDA_TRUE} on every one of {len(truth):,} days.")

    print("\nThe observation error a calibration has to see through, by pillar:")
    err = zeros.assign(bp=(zeros["zeroYield"] - zeros["trueYield"]) * 1e4)
    stats = err.groupby("tenor")["bp"].agg(["mean", "std"])
    for tenor, _ in PILLARS:
        row = stats.loc[tenor]
        print(f"    {tenor:<4} bias {row['mean']:+6.2f} bp   noise sd {row['std']:5.2f} bp")

    print("\nThe curve on the last day, as published:")
    last = zeros[zeros["date"] == zeros["date"].max()]
    for row in last.itertuples():
        print(f"    {row.tenor:<4} tau {row.tau:7.4f}   {row.zeroYield * 100:.4f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
