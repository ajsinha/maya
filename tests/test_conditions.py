"""
Grant conditions (§11.4) on every path that returns rows: feature preview and
download (live and pinned), feature sets (member conditions through the mapping,
live and pinned), and warrant training data. Plus validation at grant time and
the most-restrictive combination of tied grants.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import io

import pyarrow.parquet as pq
import pytest

from maya.core.errors import NotFound, ValidationFailed
from maya.security.conditions import combine
from tests.conftest import approved_feature, price_csv

CONDS = {"row_filter": "symbol == 'AAA'", "time_bound": {"until": "2026-01-03"},
         "column_mask": {"close": "hash"}}


def _grant(w, ref, who, conditions, kind="feature", level="read"):
    obj = w.p.access.resolve_object(kind, ref)
    return w.p.access.grant(w.admin, kind=kind, obj=obj, principal_type="user",
                            principal_id=who, level=level, conditions=conditions)


def test_feature_reads_are_narrowed_on_every_path(world):
    ref = approved_feature(world, "cond_px", price_csv(5))
    world.p.features.pin(world.mick, ref, version_no=1, pin_name="c", as_of=dt.date(2026, 1, 5))
    world.drain()
    g = _grant(world, ref, "tess", CONDS)          # by name: stored as the user id
    assert g["principal_id"] == world.tess.user_id
    for target in (f"maya://feature/{ref}@v1", f"maya://feature/{ref}#c/2026-01-05"):
        full = world.p.features.preview(world.dana, target)
        narrowed = world.p.features.preview(world.tess, target)
        assert full["total_rows"] == 10 and narrowed["total_rows"] == 3
        assert {r["symbol"] for r in narrowed["rows"]} == {"AAA"}
        assert all(len(r["close"]) == 64 for r in narrowed["rows"]), "close must be hashed"
        assert narrowed["access_conditions"]["rows_after"] == 3
    out = world.p.features.download(world.tess, f"maya://feature/{ref}#c/2026-01-05")
    table = pq.read_table(io.BytesIO(out["data"]))
    assert table.num_rows == 3 and set(table.column("symbol").to_pylist()) == {"AAA"}
    assert out["manifest"]["access_conditions"]["masked"] == {"close": "hash"}


def test_member_conditions_follow_the_feature_set_mapping(world):
    ref = approved_feature(world, "cond_member", price_csv(4))
    fs_def = {"index": ["date", "symbol"], "members": [
        {"attr": "px", "ref": f"maya://feature/{ref}@v1", "source_attr": "close"}]}
    world.p.featuresets.create(world.dana, namespace="eq", name="cond_set", definition=fs_def)
    world.p.featuresets.transition(world.dana, "eq/cond_set", 1, "submit")
    world.p.featuresets.transition(world.mick, "eq/cond_set", 1, "approve")
    world.p.featuresets.pin(world.mick, "eq/cond_set", version_no=1, pin_name="p",
                            as_of=dt.date(2026, 1, 4), cascade=True)
    world.drain()
    _grant(world, ref, "tess", {"column_mask": {"close": "null"},
                                "row_filter": "symbol == 'BBB'"})
    for target in ("maya://featureset/eq/cond_set@v1", "maya://featureset/eq/cond_set#p/2026-01-04"):
        out = world.p.featuresets.preview(world.tess, target)
        assert out["total_rows"] == 4
        assert {r["symbol"] for r in out["rows"]} == {"BBB"}
        assert all(r["px"] is None for r in out["rows"]), "the member mask applies as 'px'"
        assert world.p.featuresets.preview(world.dana, target)["total_rows"] == 8


def test_conditions_are_validated_at_grant_time(world):
    ref = approved_feature(world, "cond_valid", price_csv(2))
    for bad, why in (({"column_mask": {"close": "blur"}}, "Mask"),
                     ({"sneaky": 1}, "Unknown"),
                     ({"time_bound": {"until": "soon"}}, "YYYY-MM-DD"),
                     ({"row_filter": "__import__('os')"}, None),
                     ({"row_filter": "desk == @user.salary"}, "@user")):
        with pytest.raises(ValidationFailed, match=why):
            _grant(world, ref, "tess", bad)
    with pytest.raises(NotFound):
        _grant(world, ref, "nobody-at-all", {})


def test_tied_grants_combine_to_the_most_restrictive():
    out = combine([{"row_filter": "a > 1", "column_mask": {"x": "hash"},
                    "time_bound": {"until": "2026-06-30"}},
                   {"row_filter": "b < 2", "column_mask": {"x": "null", "y": "hash"},
                    "time_bound": {"until": "2026-03-31"}}])
    assert out == {"row_filter": "(a > 1) and (b < 2)",
                   "column_mask": {"x": "null", "y": "hash"},
                   "time_bound": {"until": "2026-03-31"}}
