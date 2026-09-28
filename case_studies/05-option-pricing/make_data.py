"""
The option chain, the spot, the dividend forecast and the discount curve, written to ``data/``.

    .venv/bin/python case_studies/05-option-pricing/make_data.py

Four feeds, because a European call needs four kinds of market data and they arrive from
four places on four different lags:

* ``option_quotes.csv`` — the closing mid price of every listed European call on three
  underlyings, on four fixed tenors (1M, 3M, 6M, 1Y) and a fixed strike ladder, every
  business day from 2025-06-02 to 2025-09-30. Published that evening, 21:10 UTC.
* ``underlying_spot.csv`` — the official close of each underlying. 20:45 UTC, the same day.
* ``dividend_forecast.csv`` — the research desk's continuous dividend yield per name,
  revised at the start of each month and republished every morning at 07:00 UTC.
* ``discount_curve.csv`` — the continuously compounded risk-free rate per tenor. 18:30 UTC.

Everything is knowable the evening it happens, which is the whole point of the case study
it feeds: nothing here is a forecast, so the leakage rule has nothing to complain about,
and the model's "training data" is a set of prices the market has already published.

**The recipe.** Seed 20260921. Each underlying has a spot that follows a geometric
Brownian motion at its own volatility, and a *true* volatility surface the quotes are
generated from:

    k     = log(K / F),  F = S e^{(r - q) T}        (log forward moneyness)
    atm   = atm0 (1 + 0.18 (T - 0.5))               (mild upward term structure)
    sigma = atm (1 - 0.30 k / sqrt(T + 0.1) + 1.2 k^2 / (T + 0.1))

That is a skew plus a smile: low strikes carry more volatility than high ones, the
curvature is strongest at the short end, and both flatten as maturity grows — which is
what an equity option surface actually looks like. A Black–Scholes model with **one**
volatility cannot reproduce it, and a nine-bucket piecewise-constant surface can only
approximate it. The mid price is that surface priced through Black–Scholes–Merton and then
disturbed the way a quote is: a relative error of about 35 basis points with a floor of one
and a half cents, rounded to the penny. Calls worth less than two cents are dropped,
because nothing trades there.

So calibration has something real to find — and cannot find it exactly.

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
SEED = 20260921
FIRST, LAST = dt.date(2025, 6, 2), dt.date(2025, 9, 30)
TENORS = {"1M": 1.0 / 12.0, "3M": 0.25, "6M": 0.5, "1Y": 1.0}
STEPS = 252.0

# ticker, spot on day one, its own volatility level, dividend yield, strikes on the ladder.
# ACME is the desk's flagship name and carries a wider ladder; the other two are in the feed
# because a market data feed has more than one name in it — and because the case study is
# about one surface belonging to one underlying.
UNDERLYINGS = (
    ("ACME", 100.0, 0.22, 0.021, 17),
    ("BOREAL", 47.5, 0.31, 0.008, 9),
    ("CYGNET", 268.0, 0.18, 0.034, 9),
)


def business_days() -> list[dt.date]:
    return [d.date() for d in pd.bdate_range(FIRST, LAST)]


def ncdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def black_scholes_call_price(
    spot: float, strike: float, rate: float, div: float, tte: float, vol: float
) -> float:
    """Black–Scholes–Merton European call with a continuous dividend yield."""
    root = vol * math.sqrt(tte)
    d1 = (math.log(spot / strike) + (rate - div + 0.5 * vol * vol) * tte) / root
    return spot * math.exp(-div * tte) * ncdf(d1) - strike * math.exp(-rate * tte) * ncdf(d1 - root)


def true_vol(spot: float, strike: float, rate: float, div: float, tte: float, atm0: float) -> float:
    """The surface the quotes are generated from: a skew, a smile, and both flattening."""
    forward = spot * math.exp((rate - div) * tte)
    k = math.log(strike / forward)
    atm = atm0 * (1.0 + 0.18 * (tte - 0.5))
    shape = 1.0 - 0.30 * k / math.sqrt(tte + 0.1) + 1.2 * k * k / (tte + 0.1)
    return float(np.clip(atm * shape, 0.05, 1.5))


def strike_ladder(spot0: float, count: int) -> list[float]:
    """A fixed ladder of round strikes around day one's spot, in 2.5% steps."""
    step = round(spot0 * 0.025, 2)
    half = count // 2
    return [round(spot0 + (i - half) * step, 2) for i in range(count)]


def spot_paths(dates: list[dt.date], rng: np.random.Generator) -> dict[str, np.ndarray]:
    """One geometric Brownian motion per name, at that name's own volatility."""
    paths = {}
    for ticker, spot0, vol, div, _ in UNDERLYINGS:
        shocks = rng.normal(0.0, 1.0, len(dates))
        drift = (0.045 - div - 0.5 * vol * vol) / STEPS
        log_path = np.cumsum(drift + vol * shocks / math.sqrt(STEPS))
        paths[ticker] = spot0 * np.exp(log_path - log_path[0])
    return paths


def curve(dates: list[dt.date], rng: np.random.Generator) -> pd.DataFrame:
    """A risk-free curve: an overnight level that wanders, and an upward slope in tenor."""
    level = 0.0415 + np.cumsum(rng.normal(0.0, 0.00035, len(dates)))
    rows = []
    for i, date in enumerate(dates):
        for tenor, tte in TENORS.items():
            rows.append(
                {
                    "date": date,
                    "tenor": tenor,
                    "rate": round(float(level[i] + 0.006 * tte), 6),
                    "kt": f"{date}T18:30:00Z",
                }
            )
    return pd.DataFrame(rows)


def dividends(dates: list[dt.date], rng: np.random.Generator) -> pd.DataFrame:
    """The research desk's yield forecast: revised at the start of each month, not daily."""
    rows, current = [], {t: q for t, _, _, q, _ in UNDERLYINGS}
    month = None
    for date in dates:
        if date.month != month:
            month = date.month
            current = {
                t: round(max(q * (1.0 + float(rng.normal(0.0, 0.06))), 0.0), 5)
                for t, q in current.items()
            }
        for ticker, value in current.items():
            rows.append(
                {
                    "date": date,
                    "underlying": ticker,
                    "divYield": value,
                    "kt": f"{date}T07:00:00Z",
                }
            )
    return pd.DataFrame(rows)


def quotes(
    dates: list[dt.date],
    paths: dict[str, np.ndarray],
    rates: pd.DataFrame,
    divs: pd.DataFrame,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every call on the ladder, priced off the true surface and then disturbed."""
    rate_of = {(r.date, r.tenor): r.rate for r in rates.itertuples()}
    div_of = {(d.date, d.underlying): d.divYield for d in divs.itertuples()}
    rows, truth = [], []
    for ticker, spot0, atm0, _, count in UNDERLYINGS:
        ladder = strike_ladder(spot0, count)
        for i, date in enumerate(dates):
            spot = float(paths[ticker][i])
            div = div_of[(date, ticker)]
            for tenor, tte in TENORS.items():
                rate = rate_of[(date, tenor)]
                for strike in ladder:
                    vol = true_vol(spot, strike, rate, div, tte, atm0)
                    fair = black_scholes_call_price(spot, strike, rate, div, tte, vol)
                    if fair < 0.02:
                        continue
                    noise = float(rng.normal(0.0, 1.0)) * max(0.0035 * fair, 0.015)
                    rows.append(
                        {
                            "date": date,
                            "underlying": ticker,
                            "tenor": tenor,
                            "contract": f"{ticker}-{tenor}-C{strike:g}",
                            "strike": strike,
                            "tte": round(tte, 8),
                            "mid": round(max(fair + noise, 0.01), 2),
                            "moneyness": round(strike / spot, 6),
                            "kt": f"{date}T21:10:00Z",
                        }
                    )
                    truth.append(
                        {"underlying": ticker, "tenor": tenor, "m": strike / spot, "vol": vol}
                    )
    return pd.DataFrame(rows), pd.DataFrame(truth)


def spots(dates: list[dt.date], paths: dict[str, np.ndarray]) -> pd.DataFrame:
    rows = []
    for i, date in enumerate(dates):
        for ticker in paths:
            rows.append(
                {
                    "date": date,
                    "underlying": ticker,
                    "spot": round(float(paths[ticker][i]), 4),
                    "kt": f"{date}T20:45:00Z",
                }
            )
    return pd.DataFrame(rows)


def generate() -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    dates = business_days()
    paths = spot_paths(dates, rng)
    rates, divs = curve(dates, rng), dividends(dates, rng)
    chain, truth = quotes(dates, paths, rates, divs, rng)
    feeds = {
        "option_quotes": chain,
        "underlying_spot": spots(dates, paths),
        "dividend_forecast": divs,
        "discount_curve": rates,
    }
    return feeds, truth


def generating_surface(truth: pd.DataFrame) -> pd.DataFrame:
    """The mean volatility the quotes were generated from, in the model's own nine buckets.

    This is what calibration is trying to recover, and printing it is the only honest way
    to say later whether it did.
    """
    acme = truth[truth["underlying"] == "ACME"].copy()
    acme["maturity"] = np.where(
        acme["tenor"] == "1M", "short (T<0.25)", np.where(acme["tenor"] == "1Y", "long", "mid")
    )
    acme["strike band"] = np.where(
        acme["m"] < 0.95, "1 K/S<0.95", np.where(acme["m"] > 1.05, "3 K/S>1.05", "2 at the money")
    )
    return acme.pivot_table(index="maturity", columns="strike band", values="vol", aggfunc="mean")


def main() -> int:
    DATA.mkdir(exist_ok=True)
    feeds, truth = generate()
    for name, frame in feeds.items():
        path = DATA / f"{name}.csv"
        frame.to_csv(path, index=False, lineterminator="\n")
        size = path.stat().st_size / 1e6
        print(f"wrote {path.relative_to(HERE.parent.parent)}  {len(frame):,} rows, {size:.2f} MB")
    print("\nACME's generating surface, averaged over the window, in the model's buckets:")
    print(generating_surface(truth).round(4).to_string())
    print("\nand the 1M smile on day one, across the ladder (spot 100.00, r 4.25%, q 2.1%):")
    for strike in strike_ladder(100.0, 17)[::4]:
        vol = true_vol(100.0, strike, 0.0425, 0.021, TENORS["1M"], 0.22)
        print(f"    K={strike:6.2f}  K/S={strike / 100:.3f}  sigma={vol:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
