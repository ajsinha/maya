"""
Resolution engine: feature algebra, feature set assembly, shapes and the
array serialization contract.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from maya.core.errors import ValidationFailed
from maya.resolution import algebra
from maya.resolution.featureset import resolve_featureset
from maya.resolution.shapes import FORMATS, export, import_export, to_shape
from maya.resolution.transforms import apply_pipeline, canonical_pipeline

IDX = ["date", "symbol"]


def _meta(
    *attrs: str,
    types: str = "float64",
    nc: bool = False,
    index: list[str] | None = None,
    policy: dict | None = None,
) -> dict:
    return {
        "index": index or IDX,
        "schema": [{"name": a, "type": types} for a in attrs],
        "non_causal": nc,
        "policy": policy or {},
    }


def _frame(dates: list[str], syms: list[str], **cols: list) -> pd.DataFrame:
    df = pd.DataFrame({"date": pd.to_datetime(dates), "symbol": syms, **cols})
    return df


# ----------------------------------------------------------------- algebra


def test_union_typing_and_collision() -> None:
    a = _frame(["2026-01-02"], ["A"], px=[1.0])
    b = _frame(["2026-01-02", "2026-01-05"], ["A", "A"], px=[9.0, 2.0])
    meta = algebra.typecheck("union", {"collision": "prefer_left"}, [_meta("px"), _meta("px")])
    assert [x["name"] for x in meta["schema"]] == ["px"]
    out = algebra.execute("union", {"collision": "prefer_left"}, [a, b], [_meta("px")] * 2)
    assert out["px"].tolist() == [1.0, 2.0]
    right = algebra.execute("union", {"collision": "prefer_right"}, [a, b], [_meta("px")] * 2)
    assert right["px"].tolist() == [9.0, 2.0]
    with pytest.raises(ValidationFailed):
        algebra.execute("union", {"collision": "error"}, [a, b], [_meta("px")] * 2)


def test_typing_errors_at_definition_time() -> None:
    with pytest.raises(ValidationFailed):
        algebra.typecheck("union", {}, [_meta("px"), _meta("px", types="int64")])
    with pytest.raises(ValidationFailed):
        algebra.typecheck("union", {}, [_meta("px"), _meta("px", index=["date"])])
    with pytest.raises(ValidationFailed):
        algebra.typecheck("compose", {}, [_meta("px"), _meta("px")])
    unit_a = {"index": IDX, "schema": [{"name": "px", "type": "float64", "unit": "USD"}]}
    unit_b = {"index": IDX, "schema": [{"name": "px", "type": "float64", "unit": "EUR"}]}
    with pytest.raises(ValidationFailed):
        algebra.typecheck("coalesce", {}, [unit_a, unit_b])
    with pytest.raises(ValidationFailed):
        algebra.typecheck("project", {"attrs": ["nope"]}, [_meta("px")])
    with pytest.raises(ValidationFailed):
        algebra.typecheck("lag", {"n": -1}, [_meta("px")])
    with pytest.raises(ValidationFailed):
        algebra.typecheck("teleport", {}, [_meta("px")])


def test_non_causality_propagates() -> None:
    out = algebra.typecheck("compose", {}, [_meta("px", nc=True), _meta("vol")])
    assert out["non_causal"] is True


def test_compose_coalesce_intersect_difference_case() -> None:
    a = _frame(["2026-01-02", "2026-01-05"], ["A", "A"], px=[1.0, None])
    b = _frame(["2026-01-05", "2026-01-06"], ["A", "A"], px=[5.0, 6.0])
    ma, mb = _meta("px"), _meta("px")
    co = algebra.execute("coalesce", {}, [a, b], [ma, mb])
    assert co["px"].tolist() == [1.0, 5.0, 6.0]
    inter = algebra.execute("intersect", {"priority": "right"}, [a, b], [ma, mb])
    assert inter["px"].tolist() == [5.0]
    diff = algebra.execute("difference", {}, [a, b], [ma, mb])
    assert diff["date"].dt.day.tolist() == [2]
    vol = _frame(["2026-01-02"], ["A"], vol=[100.0])
    comp = algebra.execute("compose", {}, [a, vol], [ma, _meta("vol")])
    assert list(comp.columns) == ["date", "symbol", "px", "vol"] and len(comp) == 2
    case = algebra.execute("case", {"cond": "px > 0"}, [a, b], [ma, mb])
    assert case["px"].tolist()[:1] == [1.0]


def test_compose_broadcast() -> None:
    panel = _frame(["2026-01-02", "2026-01-02"], ["A", "B"], px=[1.0, 2.0])
    static = pd.DataFrame({"symbol": ["A", "B"], "sector": [10.0, 20.0]})
    metas = [_meta("px"), _meta("sector", index=["symbol"])]
    with pytest.raises(ValidationFailed):
        algebra.typecheck("compose", {}, metas)
    out = algebra.execute("compose", {"broadcast": True}, [panel, static], metas)
    assert out["sector"].tolist() == [10.0, 20.0]


def test_aggregate_and_lag() -> None:
    df = _frame(["2026-01-02", "2026-01-05", "2026-01-02"], ["A", "A", "B"], px=[1.0, 3.0, 5.0])
    agg = algebra.execute(
        "aggregate", {"by": ["symbol"], "agg": {"px": "mean"}}, [df], [_meta("px")]
    )
    assert agg["px"].tolist() == [2.0, 5.0]
    lag = algebra.execute("lag", {"n": 1}, [df], [_meta("px")])
    assert lag[lag["symbol"] == "A"]["px"].tolist()[1] == 1.0


def test_canonical_derivation_commutative_union() -> None:
    a = algebra.canonical_derivation("union", {}, ["maya://feature/b@v1", "maya://feature/a@v1"])
    b = algebra.canonical_derivation(
        "union", {"collision": "error"}, ["maya://feature/a@v1", "maya://feature/b@v1"]
    )
    assert a == b
    c = algebra.canonical_derivation("union", {"collision": "prefer_left"}, ["x", "y"])
    d = algebra.canonical_derivation("union", {"collision": "prefer_left"}, ["y", "x"])
    assert c != d


# -------------------------------------------------------------- transforms


def test_pipeline() -> None:
    df = _frame(["2026-01-02", "2026-01-05", "2026-01-06"], ["A", "A", "A"], px=[1.0, 2.0, 4.0])
    steps = [
        {"op": "derive", "name": "lpx", "expr": "log(px)"},
        {"op": "lag", "attr": "px", "n": 1},
        {"op": "window", "attr": "px", "fn": "mean", "size": 2, "name": "ma2"},
        {"op": "filter", "expr": "px > 1"},
    ]
    out = apply_pipeline(df, steps, IDX)
    assert out["px_lag1"].tolist() == [1.0, 2.0] and out["ma2"].tolist() == [1.5, 3.0]
    assert canonical_pipeline([{"expr": "px>1", "op": "filter"}]) == canonical_pipeline(
        [{"op": "filter", "expr": "(px) > 1"}]
    )
    with pytest.raises(ValidationFailed):
        apply_pipeline(df, [{"op": "exec"}], IDX)


# -------------------------------------------------------------- featureset


def _members() -> dict:
    px = _frame(
        ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-02", "2026-01-06"],
        ["A", "A", "A", "B", "B"],
        adjusted_close=[1.0, None, 3.0, 10.0, 12.0],
        daily_volume=[5.0, None, 7.0, 50.0, 70.0],
    )
    beta = pd.DataFrame({"symbol": ["A", "B"], "beta_mkt": [1.1, 0.9]})
    return {
        "daily": (
            px,
            _meta("adjusted_close", "daily_volume", policy={"rules": {"daily_volume": "zero"}}),
        ),
        "betas": (beta, _meta("beta_mkt", index=["symbol"])),
    }


def test_featureset_precedence_layers_and_broadcast() -> None:
    mapping = [
        {
            "attr": "px",
            "member": "daily",
            "source_attr": "adjusted_close",
            "rule": "forward_fill(limit=3)",
        },
        {"attr": "vol", "member": "daily", "source_attr": "daily_volume"},
        {"attr": "beta", "member": "betas", "source_attr": "beta_mkt"},
    ]
    df, man = resolve_featureset(
        _members(),
        mapping,
        index=IDX,
        alignment={"mode": "outer"},
        inherited_policies=[{"source": "market_panel", "rules": {"beta": "zero"}}],
    )
    layers = {a: (m["layer"], m["source"]) for a, m in man["attributes"].items()}
    assert layers == {
        "px": ("attribute", "featureset"),
        "vol": ("member", "daily"),
        "beta": ("inherited", "market_panel"),
    }
    a = df[df["symbol"] == "A"]
    assert a["px"].tolist() == [1.0, 1.0, 3.0] and a["vol"].tolist() == [5.0, 0.0, 7.0]
    assert set(df["beta"]) == {1.1, 0.9}
    assert any("broadcast" in p for p in man["plan"])


def test_featureset_global_and_group_layers() -> None:
    mapping = [
        {"attr": "px", "member": "daily", "source_attr": "adjusted_close"},
        {"attr": "vol", "member": "daily", "source_attr": "daily_volume"},
    ]
    _, man = resolve_featureset(
        _members(),
        mapping,
        index=IDX,
        global_policy={"rules": {"px": "zero"}},
        group_policies=[{"attrs": ["vol"], "rule": "constant(v=1)"}],
    )
    assert man["attributes"]["px"]["layer"] == "global"
    assert man["attributes"]["vol"]["layer"] == "group"


def test_featureset_calendar_grid_inner_and_universe() -> None:
    mapping = [{"attr": "px", "member": "daily", "source_attr": "adjusted_close"}]
    df, man = resolve_featureset(
        _members(),
        mapping,
        index=IDX,
        alignment={"mode": "inner"},
        grid={"calendar": "NYSE"},
        filters={"universe": ["B"]},
    )
    assert set(df["symbol"]) == {"B"} and len(df) == 3  # 2, 5, 6 Jan
    assert man["attributes"]["px"]["layer"] == "default"


def test_featureset_refuses_unaggregated_extra_index() -> None:
    members = _members()
    mapping = [{"attr": "px", "member": "daily", "source_attr": "adjusted_close"}]
    with pytest.raises(ValidationFailed):
        resolve_featureset(members, mapping, index=["date"])
    mapping[0]["aggregate"] = "mean"
    df, man = resolve_featureset(members, mapping, index=["date"])
    assert df["px"].tolist()[0] == 5.5 and any("aggregate" in p for p in man["plan"])


def test_featureset_asof_alignment() -> None:
    marks = _frame(["2026-01-05", "2026-01-07"], ["A", "A"], mark=[100.0, 101.0])
    funda = _frame(["2026-01-02"], ["A"], eps=[2.5])
    members = {"marks": (marks, _meta("mark")), "funda": (funda, _meta("eps"))}
    mapping = [
        {"attr": "mark", "member": "marks", "source_attr": "mark"},
        {"attr": "eps", "member": "funda", "source_attr": "eps"},
    ]
    df, man = resolve_featureset(
        members,
        mapping,
        index=IDX,
        alignment={"mode": "asof", "member": "marks", "tolerance_days": 3, "direction": "backward"},
    )
    assert df["eps"].tolist()[0] == 2.5 and math.isnan(df["eps"].tolist()[1])
    assert any("asof" in p for p in man["plan"])


def test_non_causal_rule_reported() -> None:
    mapping = [
        {"attr": "px", "member": "daily", "source_attr": "adjusted_close", "rule": "linear_interp"}
    ]
    _, man = resolve_featureset(_members(), mapping, index=IDX)
    assert man["non_causal"] == ["px"]


# ------------------------------------------------------------------ shapes

SCHEMA = [
    {"name": "px", "type": "float64"},
    {"name": "surface", "type": "tensor<float64,[2,3]>"},
    {"name": "tags", "type": "list<int64>"},
]


def _nested() -> pd.DataFrame:
    df = _frame(["2026-01-02", "2026-01-05"], ["A", "B"], px=[1.25, None])
    df["surface"] = [[0.5, 1, 2, 3, 4, 5.125], None]
    df["tags"] = [[1, 2, 3], []]
    return df


@pytest.mark.parametrize(
    "fmt,enc", [(f, None) for f in FORMATS if f != "csv"] + [("csv", "packed"), ("csv", "json")]
)
def test_tensor_round_trip_every_format(fmt: str, enc: str | None) -> None:
    df = _nested()
    back = import_export(export(df, SCHEMA, fmt, enc), fmt)
    assert back["surface"].tolist() == [[0.5, 1.0, 2.0, 3.0, 4.0, 5.125], None]
    assert back["tags"].tolist() == [[1, 2, 3], []]
    assert back["px"].tolist()[0] == 1.25 and math.isnan(back["px"].tolist()[1])
    assert back["date"].tolist() == df["date"].tolist()
    assert back["symbol"].tolist() == ["A", "B"]


def test_csv_wide_and_undeclared_refusal() -> None:
    schema = SCHEMA[:2]
    df = _nested().drop(columns=["tags"])
    with pytest.raises(ValidationFailed):
        export(df, schema, "csv")
    body = export(df, schema, "csv", "wide").decode()
    assert "surface_1_2" in body.splitlines()[1]
    back = import_export(body.encode(), "csv")
    assert back["surface"].tolist()[0] == [0.5, 1.0, 2.0, 3.0, 4.0, 5.125]


def test_shapes() -> None:
    df = _nested().drop(columns=["tags"])
    schema = SCHEMA[:2]
    tab, man = to_shape(df, schema, "tabular")
    assert tab.schema.field("surface").type.list_size == 6
    wide, _ = to_shape(df, schema, "wide")
    assert "surface_0_0" in wide.columns and wide["surface_1_2"].tolist()[0] == 5.125
    tensor, man = to_shape(df, schema, "tensor")
    assert tensor["surface"].shape == (2, 2, 3) and man["axes"]["surface"]["shape"] == [2, 3]
    with pytest.raises(ValidationFailed):
        to_shape(_nested(), SCHEMA, "tensor")  # ragged list


finite = st.floats(allow_nan=False, allow_infinity=False, width=64)


@settings(max_examples=40, deadline=None)
@given(
    rows=st.lists(
        st.tuples(finite, st.lists(finite, min_size=4, max_size=4)), min_size=1, max_size=8
    ),
    fmt=st.sampled_from(["arrow", "parquet", "json", "ndjson", "csv"]),
)
def test_property_round_trip(rows: list, fmt: str) -> None:
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=len(rows)),
            "x": [r[0] for r in rows],
            "v": [r[1] for r in rows],
        }
    )
    schema = [{"name": "x", "type": "float64"}, {"name": "v", "type": "fixed_vector<float64,4>"}]
    back = import_export(export(df, schema, fmt, "packed" if fmt == "csv" else None), fmt)
    assert back["x"].tolist() == df["x"].tolist()
    assert back["v"].tolist() == [list(map(float, r[1])) for r in rows]
    assert np.array_equal(back["date"].to_numpy(), df["date"].to_numpy())


# ------------------------------------------------------------ knowledge clock

KT = "_knowledge_time"


def _clocked(px: list[float], kt: list[str], **extra: list) -> pd.DataFrame:
    df = _frame(["2026-01-02", "2026-01-05", "2026-01-06"], ["AAA"] * 3, px=px, **extra)
    df[KT] = pd.to_datetime(kt)
    return df


A_KT = ["2026-01-03", "2026-01-06", "2026-01-07"]
B_KT = ["2026-01-10", "2026-01-04", "2026-01-12"]


@pytest.mark.parametrize(
    "op, options, operands, metas",
    [
        ("project", {"attrs": ["px"]}, "a2", [_meta("px", "vol")]),
        ("compose", {"prefixes": ["a_", "b_"]}, "ab", [_meta("px"), _meta("px")]),
        ("coalesce", {}, "ab", [_meta("px"), _meta("px")]),
        ("aggregate", {"by": ["symbol"], "agg": {"px": "mean"}}, "a", [_meta("px")]),
        ("resample", {"freq": "W"}, "a", [_meta("px")]),
        ("case", {"cond": "px > 1.5"}, "ab", [_meta("px"), _meta("px")]),
    ],
)
def test_every_operator_carries_the_knowledge_clock(op, options, operands, metas) -> None:
    """A derived row is knowable when the latest input it was built from is knowable.

    Dropping the clock would let the leakage certificate read a derived feature as if it had
    always been known, which is the one thing a bitemporal store is for preventing."""
    a = _clocked([1.0, 2.0, 3.0], A_KT)
    frames = {
        "a": [a],
        "a2": [_clocked([1.0, 2.0, 3.0], A_KT, vol=[5.0, 6.0, 7.0])],
        "ab": [a, _clocked([10.0, 20.0, 30.0], B_KT)],
    }[operands]
    out = algebra.execute(op, options, frames, metas)
    assert KT in out.columns, f"{op} dropped the knowledge clock"
    latest = max(pd.to_datetime(A_KT + (B_KT if operands == "ab" else [])))
    assert out[KT].max() == latest
    if operands == "ab" and op != "aggregate":
        # row by row: the later of the two inputs' clocks
        expected = [max(x, y) for x, y in zip(pd.to_datetime(A_KT), pd.to_datetime(B_KT))]
        assert out[KT].tolist() == expected
