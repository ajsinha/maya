"""
Properties the evidence depends on, checked against generated input (hypothesis):

* canonical encoding is injective: different values never share bytes, and the
  deliberate identifications (−0.0 = 0.0, every NaN, naive = UTC) are the only ones;
* the content hash ignores column order and notices any change of value;
* content-defined fragment boundaries tile every table exactly, respect their
  size bounds, and an inserted row leaves every earlier fragment untouched;
* a pin's content hash does not depend on the order rows arrived in;
* a restatement never overwrites: every earlier knowledge time still reads back.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import decimal
import random

import pyarrow as pa
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from maya.core import canonical
from maya.core.chunker import ChunkParams, boundaries
from tests.conftest import PX_DEF, World, build_platform

UTC = dt.timezone.utc
scalars = st.one_of(
    st.none(), st.booleans(), st.integers(min_value=-2**63, max_value=2**63 - 1),
    st.floats(allow_nan=False), st.text(max_size=12), st.binary(max_size=12),
    st.dates(), st.datetimes(timezones=st.just(UTC)),
    st.timedeltas(min_value=dt.timedelta(days=-9999), max_value=dt.timedelta(days=9999)),
    st.decimals(allow_nan=False, allow_infinity=False, places=4))
values = st.recursive(scalars, lambda inner: st.one_of(
    st.lists(inner, max_size=4),
    st.dictionaries(st.text(max_size=5), inner, max_size=3)), max_leaves=12)


def _canon(v):
    """The equality canonical encoding promises: the documented identifications only."""
    if isinstance(v, bool) or v is None:
        return (type(v).__name__, v)
    if isinstance(v, float):
        return ("float", 0.0 if v == 0 else v)
    if isinstance(v, decimal.Decimal):
        return ("dec", v.normalize())
    if isinstance(v, dict):
        return ("map", tuple((str(k), _canon(x)) for k, x in v.items()))
    if isinstance(v, (list, tuple)):
        return ("list", tuple(_canon(x) for x in v))
    return (type(v).__name__, v)


@settings(max_examples=400, deadline=None)
@given(a=values, b=values)
def test_canonical_encoding_is_injective(a, b):
    same = canonical.encode_value(a) == canonical.encode_value(b)
    assert same == (_canon(a) == _canon(b)), (a, b)


def test_the_documented_identifications():
    enc = canonical.encode_value
    assert enc(-0.0) == enc(0.0) and enc(float("nan")) == enc(-float("nan"))
    assert enc(dt.datetime(2026, 1, 1)) == enc(dt.datetime(2026, 1, 1, tzinfo=UTC))
    assert enc(decimal.Decimal("1.50")) == enc(decimal.Decimal("1.5"))
    assert enc(1) != enc(1.0) != enc("1") and enc(True) != enc(1) and enc(None) != enc(0)
    assert enc(dt.date(2026, 1, 1)) != enc(dt.datetime(2026, 1, 1))


rows = st.lists(st.tuples(st.dates(min_value=dt.date(2000, 1, 1)), st.text(max_size=3),
                          st.floats(allow_nan=False)), min_size=1, max_size=30)


@settings(max_examples=150, deadline=None)
@given(data=rows)
def test_the_content_hash_ignores_column_order(data):
    cols = {"date": [r[0] for r in data], "symbol": [r[1] for r in data],
            "px": [r[2] for r in data]}
    t1 = pa.table(cols)
    t2 = pa.table({k: cols[k] for k in ("px", "symbol", "date")})
    assert canonical.table_content_hash(t1) == canonical.table_content_hash(t2)


@settings(max_examples=150, deadline=None)
@given(data=rows, pick=st.integers(min_value=0), delta=st.floats(min_value=1e-6, max_value=1e6))
def test_the_content_hash_notices_any_changed_value(data, pick, delta):
    px = [r[2] for r in data]
    i = pick % len(px)
    changed = list(px)
    changed[i] = px[i] + delta
    assume(changed[i] != px[i])
    base = {"date": [r[0] for r in data], "symbol": [r[1] for r in data]}
    assert canonical.table_content_hash(pa.table({**base, "px": px})) != \
        canonical.table_content_hash(pa.table({**base, "px": changed}))


digests = st.lists(st.binary(min_size=32, max_size=32), min_size=0, max_size=400)
params = st.builds(lambda t, lo, hi: ChunkParams(target=t, minimum=lo, maximum=max(lo, hi)),
                   st.integers(1, 64), st.integers(1, 16), st.integers(1, 128))


@settings(max_examples=300, deadline=None)
@given(ds=digests, p=params)
def test_fragment_boundaries_tile_the_rows_within_their_bounds(ds, p):
    runs = boundaries(ds, p)
    if not ds:
        assert runs == []
        return
    assert [s for s, _ in runs] == [0] + [e for _, e in runs[:-1]]
    assert runs[-1][1] == len(ds)
    for s, e in runs:
        assert 0 < e - s <= p.maximum
    for s, e in runs[:-1]:
        assert e - s >= p.minimum


@settings(max_examples=300, deadline=None)
@given(ds=st.lists(st.binary(min_size=32, max_size=32), min_size=1, max_size=400),
       new=st.binary(min_size=32, max_size=32), at=st.integers(min_value=0), p=params)
def test_an_inserted_row_leaves_every_earlier_fragment_untouched(ds, new, at, p):
    """Content-defined chunking's point (§29.3): a month-end pin costs its delta."""
    at = at % (len(ds) + 1)
    before = boundaries(ds, p)
    after = boundaries(ds[:at] + [new] + ds[at:], p)
    untouched = [r for r in before if r[1] <= at]
    # every fragment that ended at or before the insertion point, except the one the
    # insertion could extend (the last of them, when its end is exactly ``at``)
    if untouched and untouched[-1][1] == at:
        untouched = untouched[:-1]
    assert after[:len(untouched)] == untouched


@pytest.fixture(scope="module")
def world():
    platform = build_platform()
    w = World(platform)
    platform.access.create_namespace(w.admin, name="prop", preset="small_team")
    yield w
    platform.shutdown()


_n = iter(range(10**6))


def _csv(lines: list[str]) -> bytes:
    return ("date,symbol,close\n" + "\n".join(lines) + "\n").encode()


price_rows = st.lists(st.tuples(st.integers(0, 40), st.sampled_from(["AAA", "BBB", "CCC"]),
                                st.floats(1, 1000, allow_nan=False).map(lambda f: round(f, 4))),
                      min_size=1, max_size=40, unique_by=lambda r: (r[0], r[1]))


@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=price_rows, seed=st.integers(0, 2**31))
def test_a_pins_hash_does_not_depend_on_arrival_order(world, data, seed):
    w = world
    lines = [f"{dt.date(2026, 1, 1) + dt.timedelta(days=d)},{s},{px}" for d, s, px in data]
    shuffled = list(lines)
    random.Random(seed).shuffle(shuffled)
    hashes = []
    known = dt.datetime(2026, 3, 1, 18, tzinfo=UTC)
    for body in (lines, shuffled):
        name = f"p{next(_n)}"
        w.p.features.create(w.dana, namespace="prop", name=name, definition=PX_DEF)
        w.p.features.ingest(w.dana, f"prop/{name}", _csv(body), fmt="csv", knowledge_time=known)
        w.p.features.transition(w.dana, f"prop/{name}", 1, "submit")
        w.p.features.transition(w.mick, f"prop/{name}", 1, "approve")
        w.p.features.pin(w.mick, f"prop/{name}", version_no=1, pin_name="eom",
                         as_of=dt.date(2026, 2, 28), as_of_known=known + dt.timedelta(hours=1))
        w.drain()
        pin = next(x for x in w.p.features.get(w.admin, f"prop/{name}")["pins"]
                   if x["pin_name"] == "eom")
        assert pin["state"] == "sealed", pin
        hashes.append(pin["content_hash"])
    assert hashes[0] == hashes[1]


@settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(first=st.lists(st.floats(1, 100, allow_nan=False).map(lambda f: round(f, 3)),
                      min_size=3, max_size=10),
       bump=st.floats(0.5, 50, allow_nan=False).map(lambda f: round(f, 3)),
       restated=st.integers(0, 2))
def test_a_restatement_never_overwrites(world, first, bump, restated):
    w = world
    name = f"r{next(_n)}"
    ref = f"prop/{name}"
    w.p.features.create(w.admin, namespace="prop", name=name, definition=PX_DEF)
    day = [str(dt.date(2026, 1, 1) + dt.timedelta(days=i)) for i in range(len(first))]
    k1 = dt.datetime(2026, 2, 1, 18, tzinfo=UTC)
    k2 = k1 + dt.timedelta(days=7)
    w.p.features.ingest(w.admin, ref, _csv([f"{d},AAA,{v}" for d, v in zip(day, first)]),
                        fmt="csv", knowledge_time=k1)
    second = list(first)
    second[restated % len(first)] = round(first[restated % len(first)] + bump, 3)
    w.p.features.ingest(w.admin, ref, _csv([f"{d},AAA,{v}" for d, v in zip(day, second)]),
                        fmt="csv", knowledge_time=k2)
    w.p.features.transition(w.admin, ref, 1, "submit")
    for known, expected in ((k1 + dt.timedelta(hours=1), first), (k2 + dt.timedelta(hours=1),
                                                                   second)):
        rows = w.p.features.preview(w.admin, f"maya://feature/{ref}@v1", as_of_known=known)["rows"]
        assert [r["close"] for r in sorted(rows, key=lambda r: str(r["date"]))] == expected
