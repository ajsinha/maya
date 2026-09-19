"""
Feature resolution (§5.1, §5.3, §29.1): raw bitemporal rows in, a resolved
frame and its fill report out.

Resolution happens in a fixed, deterministic order:

1. **Bitemporal cut.** Rows whose ``_knowledge_time`` is after ``as_of_known``
   are dropped, so "what did we know on 31 March" is a filter, not an
   exercise. A restatement is a later knowledge row, never an overwrite.
2. **Latest knowledge per key.** For each full index key, the row with the
   greatest knowledge time wins.
3. **Grid.** ``as_is`` keeps the source's own rows; a calendar grid is the
   calendar's open days across the range, crossed with every distinct
   non-date key (every symbol, for a panel).
4. **Rules**, per attribute, per non-date group, in event-time order.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from maya.core.calendars import business_days
from maya.core.errors import ValidationFailed
from maya.resolution import grouped
from maya.resolution.rules import apply_rule, parse_rule

KT = "_knowledge_time"


def parse_grid(grid: Any) -> str | None:
    """Return the calendar name of a grid spec, or None for ``as_is``."""
    if grid in (None, "as_is"):
        return None
    if isinstance(grid, dict) and "calendar" in grid:
        return str(grid["calendar"])
    if isinstance(grid, str) and grid.startswith("calendar"):
        name = grid.split(":", 1)[-1].split(" ", 1)[-1].strip()
        if name and name != "calendar":
            return name
    raise ValidationFailed(f"unknown grid '{grid}'; use 'as_is' or {{'calendar': NAME}}")


def rule_for(policy: dict[str, Any] | None, attr: str) -> Any:
    """The rule the feature's own policy assigns to ``attr`` (None when unset)."""
    policy = policy or {}
    return (policy.get("rules") or {}).get(attr, policy.get("default"))


def to_event_dates(s: pd.Series) -> pd.Series:
    """Normalize an event-time column to tz-naive midnight datetime64[ns]."""
    out = pd.to_datetime(s)
    if isinstance(out.dtype, pd.DatetimeTZDtype):
        out = out.dt.tz_convert("UTC").dt.tz_localize(None)
    return out.dt.normalize().astype("datetime64[ns]")


def _to_utc(ts: Any) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def bitemporal_cut(raw: pd.DataFrame, index: list[str], as_of_known: Any) -> pd.DataFrame:
    """Apply steps 1 and 2: the knowledge-time filter and latest row per key."""
    df = raw.copy()
    if not index:
        raise ValidationFailed("a feature must declare an index")
    df[index[0]] = to_event_dates(df[index[0]])
    if KT not in df.columns:
        df[KT] = pd.NaT
        df[KT] = pd.to_datetime(df[KT], utc=True)
    else:
        df[KT] = pd.to_datetime(df[KT], utc=True)
    if as_of_known is not None:
        df = df[df[KT].isna() | (df[KT] <= _to_utc(as_of_known))]
    df = df.sort_values(index + [KT], kind="mergesort", na_position="first")
    return df.drop_duplicates(subset=index, keep="last").reset_index(drop=True)


def _calendar_grid(df: pd.DataFrame, index: list[str], cal: str,
                   start: date | None, end: date | None) -> pd.DataFrame:
    dcol = index[0]
    if df.empty and (start is None or end is None):
        return df
    lo = start or df[dcol].min().date()
    hi = end or df[dcol].max().date()
    days = pd.DataFrame({dcol: pd.to_datetime(business_days(cal, lo, hi)).astype("datetime64[ns]")})
    others = index[1:]
    if others:
        keys = df[others].drop_duplicates().sort_values(others, kind="mergesort")
        days = days.merge(keys, how="cross")
    return days.merge(df, on=index, how="left")


def _range_filter(df: pd.DataFrame, dcol: str, start: date | None, end: date | None) -> pd.DataFrame:
    if start is not None:
        df = df[df[dcol] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df[dcol] <= pd.Timestamp(end)]
    return df.reset_index(drop=True)


def apply_rules(df: pd.DataFrame, index: list[str], attributes: list[str],
                rules: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply one rule per attribute, per non-date group, in date order.

    Groups are computed once for all attributes and indexed by position; the ``none``
    rule is the identity and does no per-group work at all.
    """
    dcol, groups = index[0], index[1:]
    out = df.sort_values(index, kind="mergesort").reset_index(drop=True)
    report: dict[str, Any] = {}
    parts: list[Any] | None = None
    dates: Any = None
    codes: Any = None
    for attr in attributes:
        spec = parse_rule(rules.get(attr))
        if spec.name == "none":
            report[attr] = {"rule": spec.canonical(), "filled": 0, "longest_run": 0,
                            "non_causal": False}
            continue
        if parts is None:
            parts = list(out.groupby(groups, sort=False).indices.values()) if groups \
                else [np.arange(len(out))]
            codes = out.groupby(groups, sort=False).ngroup().to_numpy() if groups \
                else np.zeros(len(out), dtype=np.int64)
            dates = pd.to_datetime(out[dcol]).to_numpy()
        values = out[attr].to_numpy()
        if grouped.eligible(spec.name, spec.params, values):
            resolved, st = grouped.apply_grouped(values, dates, codes, spec.name, spec.params)
            out[attr] = resolved
            report[attr] = {"rule": spec.canonical(), "filled": st["filled"],
                            "longest_run": st["longest_run"], "non_causal": spec.non_causal}
            continue
        filled, longest, results = 0, 0, []
        for rows in parts:
            s, st = apply_rule(pd.Series(values[rows]), spec, pd.Series(dates[rows]))
            results.append(s.to_numpy())
            filled += st["filled"]
            longest = max(longest, st["longest_run"])
        if parts:
            new = out[attr].copy()
            new.iloc[np.concatenate(parts)] = np.concatenate(results)   # one write, pandas upcasting
            out[attr] = new
        report[attr] = {"rule": spec.canonical(), "filled": filled, "longest_run": longest,
                        "non_causal": spec.non_causal}
    return out, report


def _gaps(df: pd.DataFrame, dcol: str, attributes: list[str]) -> tuple[str | None, str | None]:
    if df.empty or not attributes:
        return None, None
    missing = df[attributes].isna().any(axis=1)
    if not missing.any():
        return None, None
    dates = df.loc[missing, dcol]
    return str(dates.min().date()), str(dates.max().date())


def resolve_feature(raw: pd.DataFrame, *, index: list[str], attributes: list[str],
                    policy: dict[str, Any] | None, as_of_known: Any = None,
                    start: date | None = None, end: date | None = None,
                    ) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Resolve raw bitemporal rows into a feature frame plus its fill report."""
    policy = policy or {}
    missing = [c for c in index + attributes if c not in raw.columns]
    if missing:
        raise ValidationFailed(f"source is missing column(s) {missing}", missing=missing)
    dcol = index[0]
    df = bitemporal_cut(raw[index + attributes + ([KT] if KT in raw.columns else [])],
                        index, as_of_known)
    raw_rows = len(df)
    cal = parse_grid(policy.get("grid"))
    if cal:
        df = _calendar_grid(df, index, cal, start, end)
    df = _range_filter(df, dcol, start, end)
    first_gap, last_gap = _gaps(df, dcol, attributes)
    rules = {a: rule_for(policy, a) for a in attributes}
    df, per_attr = apply_rules(df, index, attributes, rules)
    df = df[index + attributes + [KT]].sort_values(index, kind="mergesort").reset_index(drop=True)
    report = {
        "rows": int(len(df)),
        "source_rows": int(raw_rows),
        "grid": cal or "as_is",
        "as_of_known": str(_to_utc(as_of_known)) if as_of_known is not None else None,
        "attributes": per_attr,
        "first_gap": first_gap,
        "last_gap": last_gap,
        "non_causal": sorted(a for a, r in per_attr.items() if r["non_causal"]),
    }
    return df, report
