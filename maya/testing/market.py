"""
The synthetic market dataset (§23): realistic, awkward, and the same for everyone.

``generate(seed)`` builds, deterministically from a numpy ``default_rng`` seed,
a small equity market over a date range. Same arguments → identical frames and
byte-identical CSV; a different seed → different data. Nothing is random at
import time and nothing reads the clock.

Tables
------
``prices`` — one row per listed symbol per open exchange day::

    date        date        the trading day (index)
    symbol      string      ticker (index)
    close       float64     raw, unadjusted close, 4 dp
    volume      int64       shares traded; null (blank in CSV) on ~1% of rows
    adj_factor  float64     multiply ``close`` by it to get split-adjusted prices
    kt          timestamp   knowledge time: the day's date at 21:00Z (after the close)

``fundamentals`` — quarterly results, bitemporal::

    date        date        announcement date, an open exchange day (index)
    symbol      string      (index)
    period_end  date        the fiscal quarter the numbers are for
    eps         float64     earnings per share, 4 dp
    revenue     float64     millions, 3 dp
    revision    int64       0 = as first reported, 1 = restated
    kt          timestamp   original rows: announcement date at 21:30Z;
                            restated rows: 30–90 days later at 12:00Z

``surface`` — a weekly implied-volatility surface per symbol (last open day of
each week)::

    date, symbol, kt        as above (kt at 21:00Z)
    surface     tensor<float64,[3,4]>   3 expiries (1M, 3M, 6M) × 4 moneyness
                            (0.9, 1.0, 1.1, 1.2), row-major, flattened to 12 floats

What is irregular, and where (``MarketData.events`` records each instance)
---------------------------------------------------------------------------
* Calendar: rows only on open days of ``calendar`` (default NYSE) — no weekends,
  no exchange holidays (``events["holidays"]`` lists the ones in range).
* Late listing: the second symbol first trades a third of the way in.
* Early delisting: the third symbol last trades two thirds of the way in.
* Gaps: ~2% of symbol-days are simply missing (``events["gaps"]``), never on a
  symbol's first day or on the split day.
* Corporate action: the first symbol splits 2-for-1 halfway through. From the
  ex-date its raw close halves and its volume doubles; ``adj_factor`` is 0.5 before
  the ex-date and 1.0 from it (``events["split"]``).
* Missing values: ``volume`` is null on ~1% of rows.
* Restatements: about a third of fundamentals rows (always at least one) are
  re-issued with the same ``(date, symbol)`` key, a changed ``eps``/``revenue``,
  ``revision`` 1 and a later ``kt``. Ingested with ``knowledge_time_column: kt``, a
  read ``as_of_known`` before the restatement returns the original numbers (SC-11).

Files
-----
``prices_csv()``, ``fundamentals_csv()`` — clean CSV for
``features.ingest(..., fmt="csv")`` with ``PRICES_DEF`` / ``FUNDAMENTALS_DEF``.
``messy_prices_csv()`` — the same prices as a vendor might send them: a UTF-8
BOM, CRLF line endings, rows in shuffled order, dates in four formats
(``2025-01-02``, ``2025/01/02``, ``02-Jan-2025``, ``01/02/2025`` month first),
quoted fields and stray spaces around numbers. MAYA's CSV ingest reads it to
exactly the rows of the clean file. Two kinds of mess are deliberately left out
because MAYA's ingest does not normalise them: padded identifiers (``" ACME"``
stays a different symbol) and mixed knowledge-time formats (the ``kt`` column is
parsed as one format).
``surface_parquet()`` — the surface as Parquet with a fixed-size-list column, for
``fmt="parquet"`` with ``SURFACE_DEF``; CSV cannot carry a tensor on ingest.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import io
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from maya.core.calendars import business_days, holidays

TICKERS = ("ACME", "BOLT", "CRUX", "DYNA", "EPIC", "FLUX", "GRID", "HALO", "IONS", "JADE",
           "KILN", "LUXE", "MINT", "NOVA", "ONYX", "PEAK")
EXPIRIES = ("1M", "3M", "6M")
MONEYNESS = (0.9, 1.0, 1.1, 1.2)
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d-%b-%Y", "%m/%d/%Y")

_IDX = {"index": ["date", "symbol"], "index_types": {"date": "date", "symbol": "string"}}
_SRC = {"type": "csv", "knowledge_time_column": "kt"}
PRICES_DEF: dict[str, Any] = {
    **_IDX, "source": _SRC, "transform": [],
    "schema": [{"name": "close", "type": "float64"}, {"name": "volume", "type": "int64"},
               {"name": "adj_factor", "type": "float64"}],
    "resolution": {"grid": "as_is", "rules": {}},
    "quality": [{"check": "not_null", "attr": "close"}]}
FUNDAMENTALS_DEF: dict[str, Any] = {
    **_IDX, "source": _SRC, "transform": [],
    "schema": [{"name": "period_end", "type": "date"}, {"name": "eps", "type": "float64"},
               {"name": "revenue", "type": "float64"}, {"name": "revision", "type": "int64"}],
    "resolution": {"grid": "as_is", "rules": {}},
    "quality": [{"check": "not_null", "attr": "eps"}]}
SURFACE_DEF: dict[str, Any] = {
    **_IDX, "source": {"type": "parquet", "knowledge_time_column": "kt"}, "transform": [],
    "schema": [{"name": "surface", "type": "tensor<float64,[3,4]>"}],
    "resolution": {"grid": "as_is", "rules": {}}, "quality": []}


@dataclass
class MarketData:
    """The generated tables plus a record of every irregularity put into them."""

    prices: pd.DataFrame
    fundamentals: pd.DataFrame
    surface: pd.DataFrame
    events: dict[str, Any] = field(default_factory=dict)
    seed: int = 0

    def prices_csv(self) -> bytes:
        return to_csv(self.prices)

    def fundamentals_csv(self) -> bytes:
        return to_csv(self.fundamentals)

    def messy_prices_csv(self) -> bytes:
        return messy_csv(self.prices, self.seed)

    def surface_parquet(self) -> bytes:
        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.table({
            "date": pa.array(self.surface["date"].dt.date, pa.date32()),
            "symbol": pa.array(self.surface["symbol"], pa.string()),
            "surface": pa.array(self.surface["surface"].tolist(), pa.list_(pa.float64(), 12)),
            "kt": pa.array(self.surface["kt"], pa.timestamp("us", tz="UTC"))})
        buf = io.BytesIO()
        pq.write_table(table, buf)
        return buf.getvalue()


def generate(seed: int = 7, *, symbols: int = 6, start: dt.date = dt.date(2025, 1, 1),
             end: dt.date = dt.date(2025, 6, 30), calendar: str = "NYSE") -> MarketData:
    """The dataset for ``symbols`` tickers over the open days of [start, end]."""
    if symbols < 3:
        raise ValueError("the dataset needs at least 3 symbols (split, late listing, delisting)")
    rng = np.random.default_rng(seed)
    days = business_days(calendar, start, end)
    if len(days) < 30:
        raise ValueError("the range needs at least 30 open days")
    names = [TICKERS[i] if i < len(TICKERS) else f"S{i:03d}" for i in range(symbols)]
    n = len(days)
    life = {s: (0, n - 1) for s in names}
    life[names[1]] = (n // 3, n - 1)
    life[names[2]] = (0, 2 * n // 3)
    split_day = n // 2
    events: dict[str, Any] = {
        "calendar": calendar, "symbols": names,
        "holidays": sorted(h for y in range(start.year, end.year + 1)
                           for h in holidays(calendar, y) if start <= h <= end),
        "late_listing": {"symbol": names[1], "first_day": days[life[names[1]][0]]},
        "delisting": {"symbol": names[2], "last_day": days[life[names[2]][1]]},
        "split": {"symbol": names[0], "ex_date": days[split_day], "ratio": 2.0}}
    prices, gaps = _prices(rng, names, days, life, split_day)
    events["gaps"] = gaps
    fundamentals, restated = _fundamentals(rng, names, days, life)
    events["restatements"] = restated
    surface = _surface(rng, prices)
    return MarketData(prices, fundamentals, surface, events, seed)


def _kt(day: dt.date, hour: int, minute: int = 0) -> pd.Timestamp:
    return pd.Timestamp(dt.datetime(day.year, day.month, day.day, hour, minute,
                                    tzinfo=dt.timezone.utc))


def _prices(rng: np.random.Generator, names: list[str], days: list[dt.date],
            life: dict[str, tuple[int, int]], split_day: int
            ) -> tuple[pd.DataFrame, list[tuple[dt.date, str]]]:
    rows, gaps = [], []
    for k, sym in enumerate(names):
        first, last = life[sym]
        price = float(rng.uniform(20, 200))
        base_volume = float(rng.uniform(2e5, 5e6))
        for i in range(first, last + 1):
            price *= float(np.exp(rng.normal(0.0003, 0.02)))
            volume = int(base_volume * rng.lognormal(0.0, 0.4))
            drop, blank = rng.random() < 0.02, rng.random() < 0.01
            split = k == 0 and i >= split_day
            if drop and i != first and not (k == 0 and i == split_day):
                gaps.append((days[i], sym))
                continue
            rows.append({"date": pd.Timestamp(days[i]), "symbol": sym,
                         "close": round(price / 2 if split else price, 4),
                         "volume": None if blank else volume * (2 if split else 1),
                         "adj_factor": 0.5 if (k == 0 and i < split_day) else 1.0,
                         "kt": _kt(days[i], 21)})
    df = pd.DataFrame(rows).sort_values(["date", "symbol"], kind="mergesort")
    df["volume"] = df["volume"].astype("Int64")
    return df.reset_index(drop=True), gaps


def _quarter_ends(start: dt.date, end: dt.date) -> list[dt.date]:
    out = []
    for y in range(start.year - 1, end.year + 1):
        for m, d in ((3, 31), (6, 30), (9, 30), (12, 31)):
            out.append(dt.date(y, m, d))
    return out


def _fundamentals(rng: np.random.Generator, names: list[str], days: list[dt.date],
                  life: dict[str, tuple[int, int]]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    open_days = set(days)
    rows: list[dict[str, Any]] = []
    todo: list[tuple[dict[str, Any], bool, int, float]] = []
    for sym in names:
        lo, hi = days[life[sym][0]], days[life[sym][1]]
        eps, revenue = float(rng.uniform(0.2, 3.0)), float(rng.uniform(200, 5000))
        for qe in _quarter_ends(days[0], days[-1]):
            eps *= float(1 + rng.normal(0.02, 0.1))
            revenue *= float(1 + rng.normal(0.02, 0.05))
            ann = qe + dt.timedelta(days=int(rng.integers(20, 46)))
            while days[0] <= ann <= days[-1] and ann not in open_days:
                ann += dt.timedelta(days=1)
            restate, lag = bool(rng.random() < 0.35), int(rng.integers(30, 91))
            shift = float(rng.choice([-1, 1]) * rng.uniform(0.05, 0.2))
            if lo <= ann <= hi:
                base = {"date": pd.Timestamp(ann), "symbol": sym, "period_end": pd.Timestamp(qe),
                        "eps": round(eps, 4), "revenue": round(revenue, 3), "revision": 0,
                        "kt": _kt(ann, 21, 30)}
                rows.append(base)
                todo.append((base, restate, lag, shift))
    if todo and not any(t[1] for t in todo):          # always at least one restatement
        todo[0] = (todo[0][0], True, todo[0][2], todo[0][3])
    restated = []
    for base, restate, lag, shift in todo:
        if not restate:
            continue
        again = {**base, "eps": round(base["eps"] * (1 + shift), 4),
                 "revenue": round(base["revenue"] * 0.99, 3), "revision": 1,
                 "kt": _kt(base["date"].date() + dt.timedelta(days=lag), 12)}
        rows.append(again)
        restated.append({"date": base["date"].date(), "symbol": base["symbol"],
                         "original_eps": base["eps"], "restated_eps": again["eps"],
                         "original_kt": base["kt"], "restated_kt": again["kt"]})
    df = pd.DataFrame(rows).sort_values(["date", "symbol", "kt"], kind="mergesort")
    df["revision"] = df["revision"].astype("int64")
    restated.sort(key=lambda r: r["restated_kt"])
    return df.reset_index(drop=True), restated


def _surface(rng: np.random.Generator, prices: pd.DataFrame) -> pd.DataFrame:
    """Weekly surfaces: last open day of each ISO week each symbol traded."""
    week = prices["date"].dt.isocalendar()
    last = prices.groupby([week["year"], week["week"], prices["symbol"]])["date"].transform("max")
    picked = prices[prices["date"] == last]
    level = {s: float(rng.uniform(0.15, 0.45)) for s in sorted(prices["symbol"].unique())}
    rows = []
    for _, r in picked.iterrows():
        atm = level[r["symbol"]] * float(np.exp(rng.normal(0, 0.05)))
        grid = [round(atm * (1 + 0.05 * t) + 0.3 * (m - 1.0) ** 2 - 0.05 * (m - 1.0), 4)
                for t in range(len(EXPIRIES)) for m in MONEYNESS]
        rows.append({"date": r["date"], "symbol": r["symbol"], "surface": grid, "kt": r["kt"]})
    return pd.DataFrame(rows).reset_index(drop=True)


def _text(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        s = out[col]
        if col == "kt":
            out[col] = s.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        elif pd.api.types.is_datetime64_any_dtype(s):
            out[col] = s.dt.strftime("%Y-%m-%d")
    return out


def to_csv(df: pd.DataFrame) -> bytes:
    """Clean CSV: ISO dates, ``kt`` as ``YYYY-MM-DDTHH:MM:SSZ``, blanks for nulls."""
    return str(_text(df).to_csv(index=False, lineterminator="\n")).encode()


def messy_csv(df: pd.DataFrame, seed: int = 0) -> bytes:
    """The same rows as ``to_csv`` gives, in the formats a careless vendor sends."""
    rng = np.random.default_rng(seed + 1)
    text = _text(df)
    order = rng.permutation(len(df))
    lines = [",".join(text.columns)]
    for i in order:
        row = df.iloc[i]
        cells = []
        for col in text.columns:
            value = text.iloc[i][col]
            if col == "date":
                fmt = DATE_FORMATS[int(rng.integers(len(DATE_FORMATS)))]
                cells.append(row["date"].strftime(fmt))
            elif col == "symbol":
                cells.append(f'"{value}"' if rng.random() < 0.5 else str(value))
            elif pd.isna(value):
                cells.append("")
            elif isinstance(value, (float, int, np.integer, np.floating)) and rng.random() < 0.3:
                cells.append(f" {value} ")
            else:
                cells.append(str(value))
        lines.append(",".join(cells))
    return ("﻿" + "\r\n".join(lines) + "\r\n").encode("utf-8")
