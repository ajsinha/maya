"""
Quality contracts (§5.5).

Checks run on every resolution and always on pin. A failing check blocks a
pin and a promotion; it never silently passes. A contract is either a list of
``{"check": name, "attr": ..., <params>}`` dicts or the mapping shorthand::

    {"unique_on_index": true, "row_count_between": [1, 1e6],
     "attributes": {"px": {"not_null": true, "range": [0, 1e5]}}}

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

from maya.core.errors import QualityCheckFailed, ValidationFailed

Check = dict[str, Any]
Result = dict[str, Any]


def normalize_contract(contract: Any) -> list[Check]:
    """Turn either contract form into the list form."""
    if not contract:
        return []
    if isinstance(contract, list):
        return [dict(c) for c in contract]
    out: list[Check] = []
    for name, val in contract.items():
        if name == "attributes":
            for attr, checks in val.items():
                for cname, cval in checks.items():
                    out.append(_from_short(cname, cval, attr))
        else:
            out.append(_from_short(name, val, None))
    return out


def _from_short(name: str, val: Any, attr: str | None) -> Check:
    c: Check = {"check": name}
    if attr:
        c["attr"] = attr
    if name in {"range", "row_count_between"} and isinstance(val, (list, tuple)):
        c["min"], c["max"] = val[0], val[1]
    elif name == "allowed_values":
        c["values"] = list(val)
    elif name == "monotonic":
        c["direction"] = val if isinstance(val, str) else "increasing"
    elif name == "max_daily_change":
        c["max"] = val
    elif name == "freshness_within":
        c.update(val if isinstance(val, dict) else {"days": val})
    return c


def _res(c: Check, passed: bool, detail: str) -> Result:
    return {"check": c["check"], "attr": c.get("attr"), "passed": bool(passed), "detail": detail}


def _col(df: pd.DataFrame, c: Check) -> pd.Series:
    attr = c.get("attr")
    if attr not in df.columns:
        raise ValidationFailed(f"quality check '{c['check']}' names unknown attribute '{attr}'")
    return df[attr]


def _not_null(df: pd.DataFrame, c: Check, idx: list[str]) -> Result:
    n = int(_col(df, c).isna().sum())
    return _res(c, n == 0, f"{n} null value(s)")


def _unique(df: pd.DataFrame, c: Check, idx: list[str]) -> Result:
    keys = [k for k in idx if k in df.columns]
    n = int(df.duplicated(subset=keys).sum()) if keys else 0
    return _res(c, n == 0, f"{n} duplicate index key(s)")


def _range(df: pd.DataFrame, c: Check, idx: list[str]) -> Result:
    s = pd.to_numeric(_col(df, c), errors="coerce").dropna()
    lo, hi = c.get("min"), c.get("max")
    bad = ((s < lo) if lo is not None else False) | ((s > hi) if hi is not None else False)
    n = int(np.sum(bad))
    return _res(c, n == 0, f"{n} value(s) outside [{lo}, {hi}]")


def _allowed(df: pd.DataFrame, c: Check, idx: list[str]) -> Result:
    s = _col(df, c).dropna()
    n = int((~s.isin(c.get("values", []))).sum())
    return _res(c, n == 0, f"{n} value(s) not in the allowed set")


def _per_group(df: pd.DataFrame, idx: list[str]) -> list[pd.DataFrame]:
    keys = [k for k in idx[1:] if k in df.columns]
    ordered = df.sort_values([k for k in idx if k in df.columns], kind="mergesort")
    return [g for _, g in ordered.groupby(keys, sort=True)] if keys else [ordered]


def _monotonic(df: pd.DataFrame, c: Check, idx: list[str]) -> Result:
    _col(df, c)
    inc = c.get("direction", "increasing") == "increasing"
    bad = 0
    for g in _per_group(df, idx):
        d = g[c["attr"]].dropna().astype("float64").diff().dropna()
        bad += int((d < 0).sum() if inc else (d > 0).sum())
    return _res(c, bad == 0, f"{bad} step(s) against the {'in' if inc else 'de'}creasing order")


def _max_change(df: pd.DataFrame, c: Check, idx: list[str]) -> Result:
    _col(df, c)
    limit, bad = float(c["max"]), 0
    for g in _per_group(df, idx):
        s = g[c["attr"]].dropna().astype("float64")
        # a move away from zero is an infinite relative change: over any limit, not ignored
        # (0 -> 0 is 0/0, no change, and drops out as NaN)
        rel = s.pct_change(fill_method=None).abs().dropna()
        bad += int((rel > limit).sum())
    return _res(c, bad == 0, f"{bad} change(s) larger than {limit:.4g} relative")


def _row_count(df: pd.DataFrame, c: Check, idx: list[str]) -> Result:
    n, lo, hi = len(df), c.get("min"), c.get("max")
    ok = (lo is None or n >= lo) and (hi is None or n <= hi)
    return _res(c, ok, f"{n} row(s), expected between {lo} and {hi}")


def _freshness(df: pd.DataFrame, c: Check, idx: list[str]) -> Result:
    if not idx or df.empty:
        return _res(c, False, "no rows to judge freshness")
    last = pd.to_datetime(df[idx[0]]).max()
    as_of = pd.Timestamp(c.get("as_of") or last)
    age = (as_of.normalize() - last.normalize()).days
    return _res(c, age <= int(c.get("days", 0)), f"latest event {last.date()} is {age} day(s) old")


CHECKS: dict[str, Callable[[pd.DataFrame, Check, list[str]], Result]] = {
    "not_null": _not_null, "unique_on_index": _unique, "range": _range,
    "allowed_values": _allowed, "monotonic": _monotonic, "max_daily_change": _max_change,
    "row_count_between": _row_count, "freshness_within": _freshness,
}


def run_checks(df: pd.DataFrame, contract: Any, index_cols: list[str],
               as_of: Any = None) -> list[Result]:
    """Evaluate every check of the contract. Never raises on a failing check."""
    results = []
    for c in normalize_contract(contract):
        fn = CHECKS.get(c.get("check", ""))
        if fn is None:
            raise ValidationFailed(f"unknown quality check '{c.get('check')}'",
                                   allowed=sorted(CHECKS))
        if c["check"] == "freshness_within" and as_of is not None and "as_of" not in c:
            c["as_of"] = as_of
        results.append(fn(df, c, index_cols))
    return results


def enforce(results: list[Result]) -> None:
    """Raise QualityCheckFailed naming every failing check."""
    failed = [r for r in results if not r["passed"]]
    if failed:
        names = ", ".join(f"{r['check']}({r['attr'] or '*'})" for r in failed)
        raise QualityCheckFailed(f"quality check(s) failed: {names}", failures=failed)
