"""
§6.8: feature sets are closed under the operator family. Only `extend` and `project` were
built; union, intersect, difference, join, override, pivot, unpivot and sample are here,
and they are the *same* executors the feature algebra uses, so a set operation and the
equivalent feature operation cannot drift apart.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pytest

from maya.core.errors import NotApproved, ValidationFailed
from tests.conftest import approved_feature, price_csv


def _set(w, name: str, definition: dict, ns: str = "alg") -> str:
    w.p.featuresets.create(w.devi, namespace=ns, name=name, definition=definition)
    w.p.featuresets.transition(w.devi, f"{ns}/{name}", 1, "submit")
    w.p.featuresets.transition(w.mick, f"{ns}/{name}", 1, "approve")
    return f"maya://featureset/{ns}/{name}@v1"


def _members(ref: str, attr: str = "px") -> dict:
    return {
        "index": ["date", "symbol"],
        "members": [{"attr": attr, "ref": ref, "source_attr": "close"}],
    }


@pytest.fixture(scope="module")
def sets(world):
    """Two feature sets over different symbols and dates, and one over a third symbol."""
    w = world
    w.p.access.create_namespace(w.admin, name="alg")
    early = approved_feature(w, "alg_early", price_csv(4, ("AAA", "BBB")), ns="alg")
    late = approved_feature(w, "alg_late", price_csv(4, ("AAA", "BBB"), start_day=5), ns="alg")
    other = approved_feature(w, "alg_other", price_csv(4, ("CCC",)), ns="alg")
    return w, {
        "early": _set(w, "s_early", _members(f"maya://feature/{early}@v1")),
        "late": _set(w, "s_late", _members(f"maya://feature/{late}@v1")),
        "other": _set(w, "s_other", _members(f"maya://feature/{other}@v1")),
    }


def _derived(w, name: str, operator: str, operands: list[str], **options) -> dict:
    definition = {
        "index": ["date", "symbol"],
        "derivation": {"operator": operator, "operands": operands, "options": options},
    }
    ref = _set(w, name, definition)
    return w.p.featuresets.preview(w.devi, ref)


def test_union_appends_rows_and_intersect_and_difference_work_on_the_index(sets):
    w, s = sets
    both = _derived(w, "u1", "union", [s["early"], s["late"]])
    assert both["total_rows"] == 16, "four days × two symbols, twice over"
    same = _derived(w, "i1", "intersect", [s["early"], s["early"]])
    assert same["total_rows"] == 8
    none = _derived(w, "i2", "intersect", [s["early"], s["late"]])
    assert none["total_rows"] == 0, "the two cover different dates"
    left = _derived(w, "d1", "difference", [s["early"], s["late"]])
    assert left["total_rows"] == 8, "nothing of early is in late"
    gone = _derived(w, "d2", "difference", [s["early"], s["early"]])
    assert gone["total_rows"] == 0


def test_join_merges_column_wise_and_project_keeps_a_subset(sets):
    w, s = sets
    wide = _set(
        w,
        "j_src",
        {
            "index": ["date", "symbol"],
            "members": [
                {"attr": "px", "ref": _feature(w, "alg_early"), "source_attr": "close"},
                {"attr": "px2", "ref": _feature(w, "alg_early"), "source_attr": "close"},
            ],
        },
    )
    kept = _derived(w, "p1", "project", [wide], attrs=["px"])
    assert set(kept["rows"][0]) >= {"date", "symbol", "px"} and "px2" not in kept["rows"][0]
    joined = _derived(
        w, "jn1", "join", [s["early"], s["other"]], mode="outer", prefixes=["e_", "o_"]
    )
    assert joined["total_rows"] == 12, "two symbols and a third, outer"
    assert {"e_px", "o_px"} <= set(joined["rows"][0])


def _feature(w, name: str) -> str:
    return f"maya://feature/alg/{name}@v1"


def test_sample_is_deterministic_by_date_universe_and_fraction(sets):
    w, s = sets
    window = _derived(
        w,
        "sm1",
        "sample",
        [s["early"]],
        start=str(dt.date(2026, 1, 2)),
        end=str(dt.date(2026, 1, 3)),
    )
    assert {str(r["date"])[:10] for r in window["rows"]} == {"2026-01-02", "2026-01-03"}
    universe = _derived(w, "sm2", "sample", [s["early"]], universe=["AAA"])
    assert {r["symbol"] for r in universe["rows"]} == {"AAA"}
    half = _derived(w, "sm3", "sample", [s["early"]], fraction=0.5, seed=7)
    again = w.p.featuresets.preview(w.devi, "maya://featureset/alg/sm3@v1")
    assert [str(r["date"]) for r in half["rows"]] == [str(r["date"]) for r in again["rows"]]
    assert 0 < half["total_rows"] <= 8
    other_seed = _derived(w, "sm5", "sample", [s["early"]], fraction=0.5, seed=8)
    assert other_seed["total_rows"] != half["total_rows"] or [
        str(r["date"]) for r in other_seed["rows"]
    ] != [str(r["date"]) for r in half["rows"]], "a different seed is a different subset"


def test_pivot_and_unpivot_move_between_long_and_wide(sets):
    w, s = sets
    wide = _derived(w, "pv1", "pivot", [s["early"]], on="symbol", value="px", values=["AAA", "BBB"])
    assert wide["total_rows"] == 4 and {"AAA", "BBB"} <= set(wide["rows"][0])
    long = _derived(w, "pv2", "unpivot", [s["early"]], into="attribute", value="v")
    assert long["total_rows"] == 8 and long["rows"][0]["attribute"] == "px"


def test_override_re_resolves_the_operand_under_a_different_policy(sets):
    w, s = sets
    filtered = _derived(
        w, "ov1", "override", [s["early"]], filters={"universe": {"values": ["AAA"]}}
    )
    assert {r["symbol"] for r in filtered["rows"]} == {"AAA"}
    with pytest.raises(ValidationFailed, match="override may replace"):
        _derived(w, "ov2", "override", [s["early"]], nonsense=True)


def test_a_derived_set_is_refused_when_its_shape_is_wrong(sets):
    w, s = sets
    for operator, operands, options, message in [
        ("union", [s["early"]], {}, "takes 2"),
        ("nonsense", [s["early"]], {}, "operator must be one of"),
        ("override", [s["early"]], {}, "declares what it overrides"),
        ("pivot", [s["early"]], {"on": "symbol", "value": "px"}, "requires option 'values'"),
    ]:
        definition = {
            "index": ["date", "symbol"],
            "derivation": {"operator": operator, "operands": operands, "options": options},
        }
        with pytest.raises(ValidationFailed, match=message):
            w.p.featuresets.create(
                w.devi,
                namespace="alg",
                name=f"bad_{operator}_{len(options)}",
                definition=definition,
            )
            w.p.featuresets.transition(w.devi, f"alg/bad_{operator}_{len(options)}", 1, "submit")


def test_a_derived_set_pins_over_pinned_operands_and_replays(sets):
    """A derived set's inputs are whole feature sets. It pins only when those are pinned —
    so what it reproduces is fixed — and refuses, naming them, when they are not."""
    w, s = sets
    with pytest.raises(NotApproved, match="pins over pinned operands"):
        w.p.featuresets.pin(
            w.mick, "alg/u1", version_no=1, pin_name="q", as_of=dt.date(2026, 1, 8), cascade=True
        )
    for name in ("s_early", "s_late"):
        w.p.featuresets.pin(
            w.mick,
            f"alg/{name}",
            version_no=1,
            pin_name="q",
            as_of=dt.date(2026, 1, 8),
            cascade=True,
        )
    w.drain()
    pinned = _set(
        w,
        "pinnable",
        {
            "index": ["date", "symbol"],
            "derivation": {
                "operator": "union",
                "operands": [
                    "maya://featureset/alg/s_early#q/2026-01-08",
                    "maya://featureset/alg/s_late#q/2026-01-08",
                ],
                "options": {},
            },
        },
    )
    del pinned
    w.p.featuresets.pin(
        w.mick, "alg/pinnable", version_no=1, pin_name="q", as_of=dt.date(2026, 1, 8)
    )
    w.drain()
    pins = w.p.featuresets.get(w.devi, "alg/pinnable")["pins"]
    assert pins and pins[0]["state"] == "sealed", pins
    assert (
        w.p.featuresets.preview(w.devi, "maya://featureset/alg/pinnable#q/2026-01-08")["total_rows"]
        == 16
    )
