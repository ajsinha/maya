"""
The grouped, vectorised rules give exactly what the per-group rules give.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from maya.resolution import grouped
from maya.resolution.rules import apply_rule, parse_rule


def _per_group(values, dates, codes, spec):
    out = values.copy()
    filled, longest = 0, 0
    for c in np.unique(codes):
        rows = np.flatnonzero(codes == c)
        rows = rows[np.argsort(dates[rows], kind="stable")]
        s, st = apply_rule(pd.Series(values[rows]), spec, pd.Series(dates[rows]))
        out[rows] = s.to_numpy()
        filled += st["filled"]
        longest = max(longest, st["longest_run"])
    return out, {"filled": filled, "longest_run": longest}


RULES = ["forward_fill", "forward_fill(limit=1)", "forward_fill(limit=3)",
         "forward_fill(max_age=2)", "forward_fill(limit=2, max_age=5)", "zero", "constant(v=7.5)",
         "previous_period"]


@pytest.mark.parametrize("rule", RULES)
@pytest.mark.parametrize("seed", range(12))
def test_vectorised_rules_match_the_per_group_rules(rule, seed):
    rng = np.random.default_rng(seed)
    groups, days = rng.integers(1, 9), rng.integers(1, 40)
    base = np.datetime64("2026-01-01")
    day = np.sort(rng.choice(np.arange(days * 2), size=days, replace=False))
    dates = np.tile(base + day.astype("timedelta64[D]"), groups).astype("datetime64[ns]")
    codes = np.repeat(np.arange(groups), days)
    shuffle = rng.permutation(len(codes))                 # rows arrive in any order
    dates, codes = dates[shuffle], codes[shuffle]
    values = rng.standard_normal(len(codes))
    values[rng.random(len(values)) < rng.uniform(0, 0.8)] = np.nan
    spec = parse_rule(rule)
    assert grouped.eligible(spec.name, spec.params, values)
    fast, fast_stats = grouped.apply_grouped(values, dates, codes, spec.name, spec.params)
    slow, slow_stats = _per_group(values, dates, codes, spec)
    np.testing.assert_array_equal(fast, slow)
    assert fast_stats == slow_stats


def test_only_float_columns_and_numeric_constants_take_the_fast_path():
    assert not grouped.eligible("forward_fill", {}, np.array([1, 2]))
    assert not grouped.eligible("constant", {"v": "x"}, np.array([1.0]))
    assert not grouped.eligible("backward_fill", {}, np.array([1.0]))
    assert grouped.eligible("zero", {}, np.array([np.nan]))
