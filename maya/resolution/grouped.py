"""
Grouped, vectorised resolution rules: one numpy pass over a whole column.

``apply_rules`` resolves each attribute per non-date group (a symbol, say), in
date order. For the rules applied most, doing that one group at a time costs a
Python-level call per group per attribute — 25,000 calls for 500 symbols × 50
attributes. Here the same rules run over every group at once: rows are ordered
by (group, date), group boundaries are marks in that order, and the running
"last known value" and "length of the gap" reset at each boundary.

Only float columns take this path (the case the rules exist for); anything
else keeps the per-group implementation, so no column's type can change. The
results are those of the per-group rules in ``maya.resolution.rules`` —
``tests/test_resolution_grouped.py`` checks them against each other on
randomised data, gaps, limits and ages.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any

import numpy as np

FAST = frozenset({"forward_fill", "zero", "constant", "previous_period"})


def eligible(name: str, params: dict[str, Any], values: np.ndarray) -> bool:
    if name not in FAST or values.dtype.kind != "f":
        return False
    return name != "constant" or (isinstance(params.get("v"), (int, float))
                                  and not isinstance(params.get("v"), bool))


def _segmented_runs(mask: np.ndarray, starts: np.ndarray) -> np.ndarray:
    """1-based position of each True within its run of Trues; runs end at group starts."""
    count = np.cumsum(mask, dtype=np.int64)
    reset = np.where(~mask, count, np.where(starts, count - 1, 0))
    return (count - np.maximum.accumulate(reset)) * mask


def apply_grouped(values: np.ndarray, dates: np.ndarray, codes: np.ndarray, name: str,
                  params: dict[str, Any]) -> tuple[np.ndarray, dict[str, int]]:
    """Resolve one float column across all groups; ``codes`` labels each row's group.

    Returns the column in the input's row order and {filled, longest_run}.
    """
    n = len(values)
    order = np.lexsort((dates, codes))                # by group, then date; stable
    v = values[order]
    d = dates[order]
    starts = np.ones(n, dtype=bool)
    starts[1:] = codes[order][1:] != codes[order][:-1]
    null = np.isnan(v)
    pos = np.arange(n)
    out = v.copy()
    if name == "forward_fill":
        group_start = np.maximum.accumulate(np.where(starts, pos, 0))
        last = np.maximum.accumulate(np.where(~null, pos, -1))
        ok = null & (last >= group_start)
        if params.get("limit") is not None:
            ok &= _segmented_runs(null, starts) <= int(params["limit"])
        if params.get("max_age") is not None:
            age = (d - d[np.where(ok, last, pos)]).astype("timedelta64[D]").astype(np.int64)
            ok &= age <= int(params["max_age"])
        out[ok] = v[last[ok]]
    elif name in ("zero", "constant"):
        ok = null
        out[ok] = 0.0 if name == "zero" else float(params["v"])
    else:                                                # previous_period: the prior row
        ok = null & ~starts
        out[1:][ok[1:]] = v[:-1][ok[1:]]
    filled = ok & ~np.isnan(out)
    stats = {"filled": int(filled.sum()),
             "longest_run": int(_segmented_runs(filled, starts).max()) if n else 0}
    result = np.empty_like(out)
    result[order] = out
    return result, stats
