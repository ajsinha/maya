"""
Resolution engine: expressions, calendars, rules, types, quality, and the
bitemporal resolver (SC-11).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from maya.core.calendars import business_days, easter_sunday, is_business_day
from maya.core.errors import QualityCheckFailed, ValidationFailed
from maya.resolution.expr import compile_expr
from maya.resolution.quality import enforce, run_checks
from maya.resolution.resolver import resolve_feature
from maya.resolution.rules import NON_CAUSAL, apply_rule, parse_rule
from maya.resolution.types import (
    arrow_type,
    cast_preview,
    infer_schema,
    logical_from_arrow,
    schema_warnings,
)


def _dates(n: int, start: str = "2026-01-05") -> pd.Series:
    return pd.Series(pd.date_range(start, periods=n, freq="D"))


# ------------------------------------------------------------ expressions


@pytest.mark.parametrize(
    "text",
    [
        "__import__('os')",
        "px.real",
        "px[0]",
        "(lambda x: x)(1)",
        "[x for x in px]",
        "open('f')",
        "eval('1')",
        "getattr(px, 'x')",
        "{'a': 1}",
    ],
)
def test_expr_refuses_unsafe_constructs(text: str) -> None:
    with pytest.raises(ValidationFailed):
        compile_expr(text)


def test_expr_evaluates_vectorized() -> None:
    df = pd.DataFrame({"px": [1.0, 4.0, 9.0], "sym": ["A", "B", "C"]})
    assert compile_expr("sqrt(px) * 2").evaluate(df).tolist() == [2.0, 4.0, 6.0]
    assert compile_expr("sym in ['A', 'C'] and px > 0").evaluate(df).tolist() == [True, False, True]
    assert compile_expr("1 < px <= 4").evaluate(df).tolist() == [False, True, False]
    assert compile_expr("where(px > 2, px, 0)").evaluate(df).tolist() == [0.0, 4.0, 9.0]
    assert compile_expr("px +  1").refs == {"px"}


def test_expr_canonical_ignores_formatting() -> None:
    assert compile_expr("(px)+1").canonical() == compile_expr("px + 1").canonical()


def test_expr_unknown_attribute_is_named() -> None:
    with pytest.raises(ValidationFailed) as exc:
        compile_expr("nope + 1").evaluate(pd.DataFrame({"px": [1]}))
    assert "nope" in str(exc.value)


# -------------------------------------------------------------- calendars


def test_nyse_2026_holidays() -> None:
    assert easter_sunday(2026) == date(2026, 4, 5)
    assert not is_business_day("NYSE", date(2026, 4, 3))  # Good Friday
    assert not is_business_day("NYSE", date(2026, 7, 3))  # Independence Day observed
    assert not is_business_day("NYSE", date(2026, 6, 19))  # Juneteenth
    assert not is_business_day("NYSE", date(2026, 11, 26))  # Thanksgiving
    assert is_business_day("NYSE", date(2026, 4, 6))
    # Juneteenth is an NYSE holiday only from 2022, so its 2021 observed Friday was open.
    assert is_business_day("NYSE", date(2021, 6, 18))
    assert not is_business_day("NYSE", date(2027, 6, 18))  # 19 June 2027 is a Saturday


def test_target_and_lse() -> None:
    assert not is_business_day("TARGET", date(2026, 5, 1))
    assert not is_business_day("TARGET", date(2026, 4, 6))  # Easter Monday
    assert not is_business_day("LSE", date(2026, 5, 25))  # spring bank holiday
    assert is_business_day("TARGET", date(2026, 5, 4))


def test_business_days_ranges() -> None:
    assert len(business_days("natural_days", date(2026, 1, 1), date(2026, 1, 31))) == 31
    iso = business_days("ISO_business_days", date(2026, 1, 1), date(2026, 1, 31))
    assert len(iso) == 22 and all(d.weekday() < 5 for d in iso)
    with pytest.raises(ValidationFailed):
        business_days("MARS", date(2026, 1, 1), date(2026, 1, 2))


# ------------------------------------------------------------------- rules


def test_forward_fill_limit_boundary() -> None:
    s = pd.Series([1.0, None, None, None, 5.0])
    out, st = apply_rule(s, "forward_fill(limit=2)", _dates(5))
    assert out.tolist()[:3] == [1.0, 1.0, 1.0]
    assert np.isnan(out.iloc[3]) and st["filled"] == 2 and st["longest_run"] == 2


def test_forward_fill_max_age_boundary() -> None:
    s = pd.Series([1.0, None, None, None])
    out, _ = apply_rule(s, {"rule": "forward_fill", "max_age": 2}, _dates(4))
    assert out.tolist()[:3] == [1.0, 1.0, 1.0] and np.isnan(out.iloc[3])


def test_backward_fill_and_interp_are_non_causal() -> None:
    assert {"backward_fill", "linear_interp", "spline_interp"} <= NON_CAUSAL
    assert parse_rule("backward_fill").non_causal
    out, _ = apply_rule(pd.Series([None, None, 3.0]), "backward_fill(limit=1)", _dates(3))
    assert np.isnan(out.iloc[0]) and out.iloc[1] == 3.0
    out, _ = apply_rule(pd.Series([0.0, None, 4.0]), "linear_interp", _dates(3))
    assert out.tolist() == [0.0, 2.0, 4.0]


def test_other_rules() -> None:
    d = _dates(4)
    s = pd.Series([2.0, None, 4.0, None])
    assert apply_rule(s, "zero", d)[0].tolist() == [2.0, 0.0, 4.0, 0.0]
    assert apply_rule(s, "constant(v=9)", d)[0].tolist() == [2.0, 9.0, 4.0, 9.0]
    assert apply_rule(s, "mean_of_window(n=3)", d)[0].tolist() == [2.0, 2.0, 4.0, 3.0]
    assert apply_rule(s, "previous_period", d)[0].tolist() == [2.0, 2.0, 4.0, 4.0]
    lk = apply_rule(s, "last_known_as_of(lag=2)", d)[0].tolist()
    assert lk[1] != lk[1] and lk[3] == 2.0  # day 1: nothing 2 days back; day 3: day 1 value
    none, st = apply_rule(s, "none", d)
    assert st["filled"] == 0 and none.isna().sum() == 2


def test_rule_parse_errors() -> None:
    for bad in ["teleport", "forward_fill(speed=1)", "custom(fn='x')", {"limit": 3}]:
        with pytest.raises(ValidationFailed):
            parse_rule(bad)


# ------------------------------------------------------------------- types


def test_type_mapping_round_trip() -> None:
    for t in [
        "int64",
        "float64",
        "bool",
        "string",
        "date",
        "decimal(38,12)",
        "list<float64>",
        "fixed_vector<float64,8>",
        "map<string,int64>",
        "struct<a:int64,b:string>",
    ]:
        assert logical_from_arrow(arrow_type(t)) == t
    assert arrow_type("tensor<float64,[8,12]>").list_size == 96


def test_infer_and_cast_preview() -> None:
    df = pd.DataFrame(
        {"d": pd.to_datetime(["2026-01-01"]), "x": [1.5], "n": [3], "s": ["a"], "v": [[1.0, 2.0]]}
    )
    types = {a["name"]: a["type"] for a in infer_schema(df)}
    assert types == {
        "d": "date",
        "x": "float64",
        "n": "int64",
        "s": "string",
        "v": "fixed_vector<float64,2>",
    }
    pv = cast_preview(pd.Series(["1", "2.5", "x", None]), "int64")
    assert pv["failures"] == 2 and "x" in pv["examples"]
    assert schema_warnings([{"name": "px", "type": "float64", "tag": "price"}])


# ----------------------------------------------------------------- quality


def test_quality_checks() -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-02"]),
            "px": [1.0, None, 50.0],
        }
    )
    res = {
        r["check"]: r
        for r in run_checks(
            df,
            {
                "unique_on_index": True,
                "row_count_between": [1, 2],
                "attributes": {
                    "px": {"not_null": True, "range": [0, 10], "monotonic": "increasing"}
                },
            },
            ["date"],
        )
    }
    assert not res["unique_on_index"]["passed"] and not res["row_count_between"]["passed"]
    assert not res["not_null"]["passed"] and not res["range"]["passed"]
    assert res["monotonic"]["passed"]
    with pytest.raises(QualityCheckFailed):
        enforce(list(res.values()))


# ---------------------------------------------------------------- resolver


def _raw() -> pd.DataFrame:
    kt = pd.Timestamp("2026-03-31T18:00Z")
    rows = [
        ("2026-03-27", "A", 10.0, kt),
        ("2026-03-30", "A", 11.0, kt),
        ("2026-03-31", "A", 12.0, kt),
        ("2026-03-30", "B", 20.0, kt),
        # restatement of A on 30 March, known only on 15 April
        ("2026-03-30", "A", 11.5, pd.Timestamp("2026-04-15T09:00Z")),
    ]
    return pd.DataFrame(rows, columns=["date", "symbol", "px", "_knowledge_time"])


def test_bitemporal_restatement_sc11() -> None:
    before, _ = resolve_feature(
        _raw(),
        index=["date", "symbol"],
        attributes=["px"],
        policy={},
        as_of_known="2026-04-01T00:00Z",
    )
    after, _ = resolve_feature(
        _raw(),
        index=["date", "symbol"],
        attributes=["px"],
        policy={},
        as_of_known="2026-04-20T00:00Z",
    )
    key = (before["date"] == "2026-03-30") & (before["symbol"] == "A")
    assert before.loc[key, "px"].item() == 11.0
    assert (
        after.loc[(after["date"] == "2026-03-30") & (after["symbol"] == "A"), "px"].item() == 11.5
    )
    early, _ = resolve_feature(
        _raw(),
        index=["date", "symbol"],
        attributes=["px"],
        policy={},
        as_of_known="2026-03-01T00:00Z",
    )
    assert early.empty


def test_calendar_grid_and_fill_report() -> None:
    df, rep = resolve_feature(
        _raw(),
        index=["date", "symbol"],
        attributes=["px"],
        policy={"grid": {"calendar": "NYSE"}, "rules": {"px": "forward_fill(limit=1)"}},
        as_of_known="2026-04-01T00:00Z",
    )
    b = df[df["symbol"] == "B"]["px"].tolist()
    assert np.isnan(b[0]) and b[1:] == [20.0, 20.0]
    assert rep["attributes"]["px"]["filled"] == 1  # B on 31 March
    assert rep["rows"] == 6 and rep["first_gap"] == "2026-03-27"
    assert rep["non_causal"] == []


def test_resolution_is_deterministic() -> None:
    a, _ = resolve_feature(
        _raw().sample(frac=1, random_state=3),
        index=["date", "symbol"],
        attributes=["px"],
        policy={},
        as_of_known=None,
    )
    b, _ = resolve_feature(
        _raw(), index=["date", "symbol"], attributes=["px"], policy={}, as_of_known=None
    )
    pd.testing.assert_frame_equal(a, b)


def test_missing_source_column_is_named() -> None:
    with pytest.raises(ValidationFailed) as exc:
        resolve_feature(_raw(), index=["date"], attributes=["vol"], policy={})
    assert "vol" in str(exc.value)
