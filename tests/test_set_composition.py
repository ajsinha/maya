"""
§6.7, §6.3 and §6.2's composition, which was thin: a feature set may hold another feature
set as a member, be forked into a set of its own, be diffed version by version, filter on a
boolean expression over its own attributes and on a **point-in-time** universe taken from
another feature, and override the alignment for one member.

The universe test is the one that matters: membership is taken on each row's own date, so a
backtest sees the index as it was, not as it is.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import pytest

from maya.core.errors import ValidationFailed

MEMBERSHIP = (
    b"date,symbol,in_index\n"
    b"2026-01-05,AAA,1\n2026-01-05,BBB,0\n"
    b"2026-01-06,AAA,1\n2026-01-06,BBB,1\n"
    b"2026-01-07,AAA,0\n2026-01-07,BBB,1\n"
)
PRICES = (
    b"date,symbol,close\n"
    b"2026-01-05,AAA,10\n2026-01-05,BBB,20\n"
    b"2026-01-06,AAA,11\n2026-01-06,BBB,21\n"
    b"2026-01-07,AAA,12\n2026-01-07,BBB,22\n"
)
PX_DEF = {
    "index": ["date", "symbol"],
    "index_types": {"date": "date", "symbol": "string"},
    "schema": [{"name": "close", "type": "float64"}],
    "source": {"type": "csv"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [],
}
MEMBER_DEF = {
    **PX_DEF,
    "schema": [{"name": "in_index", "type": "int64"}],
}


def _feature(w, name: str, data: bytes, definition: dict) -> str:
    w.p.features.create(w.dana, namespace="cmp", name=name, definition=definition)
    w.p.features.ingest(w.dana, f"cmp/{name}", data, fmt="csv")
    w.p.features.transition(w.dana, f"cmp/{name}", 1, "submit")
    w.p.features.transition(w.mick, f"cmp/{name}", 1, "approve")
    return f"maya://feature/cmp/{name}@v1"


def _set(w, name: str, definition: dict, approve: bool = True) -> str:
    w.p.featuresets.create(w.devi, namespace="cmp", name=name, definition=definition)
    if approve:
        w.p.featuresets.transition(w.devi, f"cmp/{name}", 1, "submit")
        w.p.featuresets.transition(w.mick, f"cmp/{name}", 1, "approve")
    return f"maya://featureset/cmp/{name}@v1"


@pytest.fixture(scope="module")
def composed(world):
    w = world
    w.p.access.create_namespace(w.admin, name="cmp")
    prices = _feature(w, "cmp_px", PRICES, PX_DEF)
    index = _feature(w, "cmp_idx", MEMBERSHIP, MEMBER_DEF)
    base = _set(
        w,
        "cmp_base",
        {
            "index": ["date", "symbol"],
            "members": [{"attr": "px", "ref": prices, "source_attr": "close"}],
        },
    )
    return w, {"prices": prices, "index": index, "base": base}


def test_a_feature_set_may_hold_another_feature_set_as_a_member(composed):
    w, refs = composed
    nested = _set(
        w,
        "cmp_nested",
        {
            "index": ["date", "symbol"],
            "members": [
                {"attr": "px", "ref": refs["base"], "source_attr": "px"},
                {"attr": "flag", "ref": refs["index"], "source_attr": "in_index"},
            ],
        },
    )
    out = w.p.featuresets.preview(w.devi, nested)
    assert out["total_rows"] == 6
    assert {"px", "flag"} <= set(out["rows"][0])


def test_a_boolean_filter_over_the_sets_own_attributes(composed):
    w, refs = composed
    filtered = _set(
        w,
        "cmp_where",
        {
            "index": ["date", "symbol"],
            "members": [{"attr": "px", "ref": refs["prices"], "source_attr": "close"}],
            "filters": {"where": "px > 20"},
        },
    )
    out = w.p.featuresets.preview(w.devi, filtered)
    assert {r["symbol"] for r in out["rows"]} == {"BBB"}
    assert any("filter where px > 20" in step for step in out["manifest"]["plan"])
    bad = _set(
        w,
        "cmp_where_bad",
        {
            "index": ["date", "symbol"],
            "members": [{"attr": "px", "ref": refs["prices"], "source_attr": "close"}],
            "filters": {"where": "nonsense > 1"},
        },
        approve=False,
    )
    with pytest.raises(ValidationFailed, match="does not carry"):
        w.p.featuresets.preview(w.devi, bad)


def test_a_universe_is_taken_on_each_rows_own_date(composed):
    """AAA leaves the index on the 7th and BBB joins on the 6th. A point-in-time universe
    keeps each row only if it was a member *that day*."""
    w, refs = composed
    universed = _set(
        w,
        "cmp_universe",
        {
            "index": ["date", "symbol"],
            "members": [{"attr": "px", "ref": refs["prices"], "source_attr": "close"}],
            "filters": {"universe": {"feature": refs["index"], "attr": "in_index"}},
        },
    )
    out = w.p.featuresets.preview(w.devi, universed)
    kept = {(str(r["date"])[:10], r["symbol"]) for r in out["rows"]}
    assert kept == {
        ("2026-01-05", "AAA"),
        ("2026-01-06", "AAA"),
        ("2026-01-06", "BBB"),
        ("2026-01-07", "BBB"),
    }
    assert any("point-in-time universe" in step for step in out["manifest"]["plan"])


def test_a_member_may_override_the_sets_alignment(composed):
    w, refs = composed
    late = _feature(
        w,
        "cmp_late",
        b"date,symbol,slow\n2026-01-05,AAA,1.0\n2026-01-05,BBB,2.0\n",
        {**PX_DEF, "schema": [{"name": "slow", "type": "float64"}]},
    )
    overridden = _set(
        w,
        "cmp_align",
        {
            "index": ["date", "symbol"],
            "alignment": {"mode": "left", "member": refs["prices"]},
            "members": [
                {"attr": "px", "ref": refs["prices"], "source_attr": "close"},
                {
                    "attr": "slow",
                    "ref": late,
                    "source_attr": "slow",
                    "alignment": {"mode": "asof", "member": refs["prices"], "tolerance_days": 5},
                },
            ],
        },
    )
    out = w.p.featuresets.preview(w.devi, overridden)
    assert out["total_rows"] == 6, "every price row is kept"
    assert any(
        "asof join member" in step and "cmp_late" in step for step in out["manifest"]["plan"]
    )
    assert any("alignment: left" in step for step in out["manifest"]["plan"]), "the set's own mode"
    later = [r for r in out["rows"] if str(r["date"])[:10] == "2026-01-07"]
    assert later and all(r["slow"] is not None for r in later), "carried as of the last value"


def test_a_set_forks_into_one_of_its_own_and_records_where_it_came_from(composed):
    w, refs = composed
    del refs
    forked = w.p.featuresets.fork(w.devi, "cmp/cmp_base", name="cmp_desk")
    assert forked["name"] == "cmp_desk" and "cmp_base" in forked["forked_from"]
    source = w.p.featuresets.get(w.devi, "cmp/cmp_base")
    copy_ = w.p.featuresets.get(w.devi, "cmp/cmp_desk")
    definition = copy_["versions"][0]["definition"]
    assert definition["members"] == source["versions"][0]["definition"]["members"]
    assert "extends" not in definition, "a fork is not an extend: it does not follow the parent"
    assert definition["forked_from"].endswith("cmp_base@v1"), "but it says where it came from"
    graph = w.p.ops.lineage("maya://featureset/cmp/cmp_base@v1", direction="downstream")
    assert any(e["type"] == "forked_from" for e in graph["edges"])


def test_two_versions_of_a_set_are_diffed_member_by_member(composed):
    w, refs = composed
    w.p.featuresets.transition(w.devi, "cmp/cmp_desk", 1, "submit")
    w.p.featuresets.transition(w.mick, "cmp/cmp_desk", 1, "approve")
    w.p.featuresets.new_draft(w.devi, "cmp/cmp_desk")
    w.p.featuresets.update_draft(
        w.devi,
        "cmp/cmp_desk",
        definition={
            "index": ["date", "symbol"],
            "members": [
                {"attr": "px", "ref": refs["prices"], "source_attr": "close"},
                {"attr": "flag", "ref": refs["index"], "source_attr": "in_index"},
            ],
            "filters": {"where": "px > 5"},
        },
    )
    out = w.p.featuresets.diff(w.devi, "cmp/cmp_desk", 1, 2)
    kinds = {c["what"]: c["change"] for c in out["changes"]}
    assert "member flag" in kinds and kinds["member flag"].startswith("added")
    assert "filters" in kinds
    assert out["from"] == 1 and out["to"] == 2
