"""
The pandas → Arrow conversion, vectorised, gives exactly the values the per-value
path gave: dates floored as ``.date()`` floors them (before 1970 and with a time
of day), NaN and None as null, and every scalar type.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest

from maya.resolution import shapes
from maya.resolution.types import arrow_type


def _old(series: pd.Series, logical: str) -> pa.Array:
    at = arrow_type(logical)
    if logical == "date":
        vals = pd.to_datetime(series)
        return pa.array([None if pd.isna(v) else v.date() for v in vals], type=at)
    return pa.array(series.astype(object).where(series.notna(), None).tolist(), type=at)


@pytest.mark.parametrize("seed", range(5))
def test_vectorised_conversion_equals_the_per_value_one(seed):
    rng = np.random.default_rng(seed)
    n = 300
    stamps = pd.Series(pd.to_datetime(rng.integers(-3 * 10**9, 3 * 10**9, n), unit="s"))
    stamps[rng.random(n) < 0.1] = pd.NaT
    floats = pd.Series(rng.standard_normal(n))
    floats[rng.random(n) < 0.1] = np.nan
    ints = pd.Series(rng.integers(-(10**12), 10**12, n))
    words = pd.Series(["a", "é", None, "", "long" * 20] * (n // 5))
    flags = pd.Series([True, False, None] * (n // 3), dtype=object)
    for series, logical in (
        (stamps, "date"),
        (floats, "float64"),
        (ints, "int64"),
        (words, "string"),
        (flags, "bool"),
        (pd.Series([dt.date(1969, 12, 31), None, dt.date(2026, 9, 19)]), "date"),
    ):
        assert shapes._array(series, logical).equals(_old(series, logical)), logical
