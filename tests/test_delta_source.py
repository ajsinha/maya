"""
A feature whose source is a Delta table (§5.2). It had no test, and three defects:
it read any path on the server, it ignored the version asked for, and it stamped every
row as known *now* — so a resolution as of a past instant returned rows that did not
exist then, and the leakage certificate had nothing to catch them with.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pyarrow as pa
import pytest

from maya.core.errors import ValidationFailed

DEF = {
    "index": ["date", "symbol"],
    "index_types": {"date": "date", "symbol": "string"},
    "schema": [{"name": "close", "type": "float64"}],
    "source": {"type": "delta", "path": "vendor/prices"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [],
}


def _rows(day: int, price: float) -> pa.Table:
    return pa.table(
        {
            "date": pa.array([dt.date(2026, 1, day)], pa.date32()),
            "symbol": pa.array(["AAA"]),
            "close": pa.array([price], pa.float64()),
        }
    )


@pytest.fixture(scope="module")
def vendor(world):
    """A Delta table under the lake root with two commits, minutes apart."""
    w = world
    path = w.p.lake.root / "vendor" / "prices"
    w.p.lake.delta.write(path, _rows(5, 100.0), mode="overwrite")
    first = w.p.lake.delta.version(path)
    w.p.lake.delta.write(path, _rows(6, 101.0), mode="append")
    return w, path, first


def test_a_delta_source_is_read_at_the_version_the_definition_names(vendor):
    w, path, first = vendor
    data = w.p.feature_data.delta_frame({"type": "delta", "path": "vendor/prices"})
    assert len(data) == 2
    pinned = w.p.feature_data.delta_frame(
        {"type": "delta", "path": "vendor/prices", "version": first}
    )
    assert len(pinned) == 1 and pinned["close"].tolist() == [100.0]


def test_knowledge_time_is_the_commit_not_the_clock(vendor):
    w, path, first = vendor
    before = pd.Timestamp.now(tz="UTC")
    data = w.p.feature_data.delta_frame({"type": "delta", "path": "vendor/prices"})
    stamps = pd.to_datetime(data["_knowledge_time"], utc=True)
    assert (stamps <= before).all(), "a row cannot become knowable after it was committed"
    history = w.p.lake.delta.history(path)
    assert len(set(stamps)) >= 1 and len(history) >= 2


def test_a_past_cutoff_reads_the_version_that_existed_then(vendor):
    w, path, first = vendor
    history = {h["version"]: h for h in w.p.lake.delta.history(path)}
    at_first = pd.Timestamp(history[first]["timestamp"], unit="ms", tz="UTC")
    data = w.p.feature_data.delta_frame(
        {"type": "delta", "path": "vendor/prices"}, as_of_known=at_first
    )
    assert data["close"].tolist() == [100.0], "the second commit was not knowable yet"
    with pytest.raises(ValidationFailed, match="nothing was knowable then"):
        w.p.feature_data.delta_frame(
            {"type": "delta", "path": "vendor/prices"},
            as_of_known=pd.Timestamp("2000-01-01", tz="UTC"),
        )


def test_the_source_column_wins_when_the_definition_declares_one(world, tmp_path):
    w = world
    path = w.p.lake.root / "vendor" / "stamped"
    table = pa.table(
        {
            "date": pa.array([dt.date(2026, 1, 5)], pa.date32()),
            "symbol": pa.array(["AAA"]),
            "close": pa.array([100.0], pa.float64()),
            "published": pa.array([dt.datetime(2026, 1, 6, 12, tzinfo=dt.timezone.utc)]),
        }
    )
    w.p.lake.delta.write(path, table, mode="overwrite")
    data = w.p.feature_data.delta_frame(
        {"type": "delta", "path": "vendor/stamped", "knowledge_time_column": "published"}
    )
    assert pd.to_datetime(data["_knowledge_time"], utc=True).tolist() == [
        pd.Timestamp("2026-01-06 12:00", tz="UTC")
    ]


def test_a_path_outside_the_configured_roots_is_refused(world, tmp_path):
    w = world
    for outside in ("/etc", str(tmp_path), "../../etc", "vendor/../../../etc"):
        with pytest.raises(ValidationFailed) as exc:
            w.p.feature_data.delta_path(outside)
        assert "outside" in exc.value.message or "no Delta table" in exc.value.message
    with pytest.raises(ValidationFailed, match="no Delta table"):
        w.p.feature_data.delta_path("vendor/not-a-table")


def test_a_feature_on_a_delta_source_resolves_point_in_time(vendor):
    w, path, first = vendor
    w.p.features.create(w.dana, namespace="eq", name="vendor_px", definition=DEF)
    history = {h["version"]: h for h in w.p.lake.delta.history(path)}
    at_first = pd.Timestamp(history[first]["timestamp"], unit="ms", tz="UTC")
    now = w.p.features.preview(w.dana, "maya://feature/eq/vendor_px@v1")
    then = w.p.features.preview(
        w.dana, "maya://feature/eq/vendor_px@v1", as_of_known=at_first.to_pydatetime()
    )
    assert len(now["rows"]) == 2 and len(then["rows"]) == 1
