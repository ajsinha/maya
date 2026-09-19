"""
The column-at-a-time canonical encoder equals the reference, row for row.

``maya.core.canonical`` defines a content hash; ``canonical_fast`` only computes it
faster. Every supported type is compared on randomised tables — nulls, NaN, signed
zeros, infinities, integer extremes, empty and non-ASCII strings, dates before
1970, timestamps in three units and with a zone — and on chunked columns.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import decimal

import numpy as np
import pyarrow as pa
import pytest

from maya.core import canonical, canonical_fast


def _reference(table: pa.Table) -> list[bytes]:
    return canonical.row_digests(canonical.table_columns(table))


def _as_float32(values: list) -> list:
    with np.errstate(over="ignore"):              # 1e308 becomes inf, deliberately
        return [np.float32(x).item() if np.isfinite(x) else x for x in values]


def _masked(values: list, rng, rate: float = 0.2) -> list:
    return [None if rng.random() < rate else v for v in values]


@pytest.mark.parametrize("seed", range(12))
def test_every_supported_type_encodes_identically(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(0, 400))
    floats = rng.standard_normal(n).tolist()
    specials = [float("nan"), -0.0, 0.0, float("inf"), float("-inf"), 1e308, -5e-324]
    floats = [specials[int(rng.integers(len(specials)))] if rng.random() < 0.15 else x
              for x in floats]
    ints = [int(x) for x in rng.integers(-2**63, 2**63 - 1, size=n, dtype=np.int64)]
    ints = [(-2**63 if rng.random() < 0.05 else 2**63 - 1 if rng.random() < 0.05 else x)
            for x in ints]
    words = ["", "a", "équité", "株式", "x" * 300, "tab\t", "emoji 😀"]
    strings = [words[int(rng.integers(len(words)))] + str(i) * int(rng.integers(0, 3))
               for i in range(n)]
    days = [dt.date(1970, 1, 1) + dt.timedelta(days=int(d))
            for d in rng.integers(-40000, 40000, size=n)]
    stamps = [dt.datetime(2000, 1, 1) + dt.timedelta(microseconds=int(us))
              for us in rng.integers(-10**15, 10**15, size=n)]
    table = pa.table({
        "f64": pa.array(_masked(floats, rng), pa.float64()),
        "f32": pa.array(_masked(_as_float32(floats), rng), pa.float32()),
        "i64": pa.array(_masked(ints, rng), pa.int64()),
        "i8": pa.array(_masked([int(x) for x in rng.integers(-128, 127, n)], rng), pa.int8()),
        "u32": pa.array(_masked([int(x) for x in rng.integers(0, 2**32 - 1, n)], rng),
                        pa.uint32()),
        "b": pa.array(_masked([bool(x) for x in rng.integers(0, 2, n)], rng), pa.bool_()),
        "s": pa.array(_masked(strings, rng), pa.string()),
        "ls": pa.array(_masked(strings, rng), pa.large_string()),
        "d": pa.array(_masked(days, rng), pa.date32()),
        "ts_us": pa.array(_masked(stamps, rng), pa.timestamp("us")),
        "ts_ms": pa.array(_masked([s.replace(microsecond=s.microsecond // 1000 * 1000)
                                   for s in stamps], rng), pa.timestamp("ms")),
        "ts_s": pa.array(_masked([s.replace(microsecond=0) for s in stamps], rng),
                         pa.timestamp("s")),
        "ts_utc": pa.array(_masked(stamps, rng), pa.timestamp("us", tz="UTC")),
        "all_null": pa.array([None] * n, pa.float64()),
    })
    assert canonical_fast.row_digests(table) == _reference(table)


def test_chunked_columns_and_empty_tables():
    a = pa.table({"x": pa.array([1.5, None, -0.0]), "s": pa.array(["a", None, ""])})
    b = pa.table({"x": pa.array([float("nan")]), "s": pa.array(["zz"])})
    chunked = pa.concat_tables([a, b])
    assert chunked.column("x").num_chunks == 2
    assert canonical_fast.row_digests(chunked) == _reference(chunked)
    empty = a.slice(0, 0)
    assert canonical_fast.row_digests(empty) == _reference(empty) == []
    sliced = chunked.slice(1, 2)                   # an offset into the buffers
    assert canonical_fast.row_digests(sliced) == _reference(sliced)


@pytest.mark.parametrize("column", [
    pa.array([decimal.Decimal("1.50")], pa.decimal128(5, 2)),
    pa.array([[1, 2]], pa.list_(pa.int64())),
    pa.array([2**63 + 1], pa.uint64()),
])
def test_uncovered_types_are_left_to_the_reference(column):
    assert canonical_fast.row_digests(pa.table({"c": column})) is None


def test_the_lake_plans_fragments_with_it_and_the_hash_is_unchanged(monkeypatch, tmp_path):
    """A pin's fragments and content hash are the same whichever path computes them."""
    from maya.storage.lake import LakeStore
    rng = np.random.default_rng(3)
    t = pa.table({"date": pa.array([dt.date(2026, 1, 1) + dt.timedelta(days=i % 40)
                                    for i in range(3000)]),
                  "symbol": pa.array([f"S{i % 7}" for i in range(3000)]),
                  "v": pa.array(rng.standard_normal(3000))})
    lake = LakeStore(tmp_path)
    fast = lake.plan_fragments(t)
    monkeypatch.setattr(canonical_fast, "row_digests", lambda table: None)
    assert lake.plan_fragments(t) == fast
