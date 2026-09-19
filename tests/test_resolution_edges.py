"""
Edge cases for every transform step, resolution rule, quality check and
algebra operator: empty input, nulls, duplicate index keys, type clashes,
missing options, and the look-ahead guards (a negative lag, in any of its three
spellings, is refused).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from maya.core.errors import QualityCheckFailed, ValidationFailed
from maya.resolution import algebra, quality, rules, transforms

IDX = ["date", "symbol"]


def frame(rows: list[tuple]) -> pd.DataFrame:
    """rows of (date, symbol, px[, vol])"""
    cols = ["date", "symbol", "px", "vol"][: len(rows[0])] if rows else ["date", "symbol", "px"]
    df = pd.DataFrame(rows, columns=cols)
    df["date"] = pd.to_datetime(df["date"])
    return df


PANEL = frame(
    [
        ("2026-01-02", "A", 1.0, 10.0),
        ("2026-01-05", "A", 2.0, 20.0),
        ("2026-01-06", "A", 4.0, 40.0),
        ("2026-01-02", "B", 10.0, 1.0),
        ("2026-01-05", "B", None, 2.0),
        ("2026-01-06", "B", 30.0, 3.0),
    ]
)
EMPTY = PANEL.iloc[0:0]


def run(df: pd.DataFrame, *steps: dict) -> pd.DataFrame:
    return transforms.apply_pipeline(df, list(steps), IDX)


# ---------------------------------------------------------------- transform steps
def test_every_step_is_registered_and_unknown_steps_are_refused():
    assert set(transforms.STEPS) == {
        "rename",
        "cast",
        "filter",
        "derive",
        "aggregate",
        "pivot",
        "unpivot",
        "window",
        "lag",
        "resample",
        "dedupe",
        "clip",
        "winsorize",
    }
    with pytest.raises(ValidationFailed, match="unknown transform step 'explode'"):
        run(PANEL, {"op": "explode"})


@pytest.mark.parametrize(
    "step,missing",
    [
        ({"op": "rename"}, "mapping"),
        ({"op": "cast", "attr": "px"}, "type"),
        ({"op": "filter"}, "expr"),
        ({"op": "derive", "name": "x"}, "expr"),
        ({"op": "aggregate", "by": ["symbol"]}, "agg"),
        ({"op": "pivot", "index": "date"}, "columns"),
        ({"op": "unpivot", "id_vars": ["date"]}, "var_name"),
        ({"op": "window", "attr": "px"}, "fn"),
        ({"op": "lag", "attr": "px"}, "n"),
        ({"op": "resample", "freq": "M"}, "agg"),
        ({"op": "clip"}, "attr"),
        ({"op": "winsorize", "attr": "px"}, "p"),
    ],
)
def test_a_step_missing_an_option_names_it(step, missing):
    with pytest.raises(ValidationFailed, match=missing):
        run(PANEL, step)


def test_rename_cast_filter_derive():
    out = run(
        PANEL,
        {"op": "rename", "mapping": {"vol": "volume"}},
        {"op": "cast", "attr": "volume", "type": "int64"},
        {"op": "filter", "expr": "px > 1.5"},
        {"op": "derive", "name": "notional", "expr": "px * volume", "type": "float64"},
    )
    assert "vol" not in out.columns and out["volume"].dtype.name in ("int64", "Int64")
    # the null px row is dropped by the filter, never treated as true
    assert out["px"].tolist() == [2.0, 4.0, 10.0, 30.0]
    assert out["notional"].tolist() == [40.0, 160.0, 10.0, 90.0]


def test_filter_and_derive_on_an_empty_frame():
    assert run(EMPTY, {"op": "filter", "expr": "px > 0"}).empty
    out = run(EMPTY, {"op": "derive", "name": "x", "expr": "px * 2"})
    assert out.empty and "x" in out.columns


def test_a_filter_expression_that_does_not_compile_is_refused_before_running():
    with pytest.raises(ValidationFailed):
        transforms.validate_step({"op": "filter", "expr": "__import__('os')"})


def test_aggregate_refuses_unknown_functions_and_keeps_null_groups():
    with pytest.raises(ValidationFailed, match="unknown aggregation 'mode'"):
        run(PANEL, {"op": "aggregate", "by": ["symbol"], "agg": {"px": "mode"}})
    out = run(PANEL, {"op": "aggregate", "by": ["symbol"], "agg": {"px": "mean", "vol": "count"}})
    assert out.set_index("symbol")["px"].to_dict() == {"A": pytest.approx(7 / 3), "B": 20.0}
    assert out.set_index("symbol")["vol"].to_dict() == {"A": 3, "B": 3}


def test_pivot_and_unpivot_round_trip():
    wide = run(PANEL, {"op": "pivot", "index": "date", "columns": "symbol", "values": "px"})
    assert list(wide.columns) == ["date", "px_A", "px_B"] and len(wide) == 3
    assert math.isnan(wide.loc[wide["date"] == "2026-01-05", "px_B"].iloc[0])
    long = run(
        wide, {"op": "unpivot", "id_vars": ["date"], "var_name": "series", "value_name": "px"}
    )
    assert len(long) == 6 and set(long["series"]) == {"px_A", "px_B"}


def test_window_is_per_group_causal_and_named():
    out = run(PANEL, {"op": "window", "attr": "px", "fn": "sum", "size": 2})
    got = out.set_index(["symbol", "date"])["px_sum2"]
    assert got.loc["A"].tolist() == [1.0, 3.0, 6.0]  # never reaches into B
    assert got.loc["B"].tolist() == [10.0, 10.0, 30.0]  # nulls are skipped, not zero
    named = run(PANEL, {"op": "window", "attr": "px", "fn": "max", "size": 3, "name": "hi"})
    assert named.set_index(["symbol", "date"])["hi"].loc["A"].tolist() == [1.0, 2.0, 4.0]
    for bad in ({"fn": "median", "size": 2}, {"fn": "mean", "size": 0}):
        with pytest.raises(ValidationFailed):
            run(PANEL, {"op": "window", "attr": "px", **bad})


def test_lag_shifts_within_groups_and_a_negative_lag_is_refused():
    out = run(PANEL, {"op": "lag", "attr": "px", "n": 1})
    got = out.set_index(["symbol", "date"])["px_lag1"]
    assert math.isnan(got.loc["A"].iloc[0]) and got.loc["A"].tolist()[1:] == [1.0, 2.0]
    assert math.isnan(got.loc["B"].iloc[0])
    with pytest.raises(ValidationFailed, match="look-ahead"):
        run(PANEL, {"op": "lag", "attr": "px", "n": -1})
    with pytest.raises(ValidationFailed, match="look-ahead"):
        transforms.pipeline_output_schema(
            [{"name": "px", "type": "float64"}], [{"op": "lag", "attr": "px", "n": -2}], IDX
        )


@pytest.mark.parametrize("freq,rows", [("W", 4), ("M", 2), ("Q", 2)])
def test_resample_frequencies(freq, rows):
    out = run(PANEL, {"op": "resample", "freq": freq, "agg": {"px": "last"}})
    assert len(out) == rows and set(out["symbol"]) == {"A", "B"}


def test_resample_refuses_an_unknown_frequency():
    with pytest.raises(ValidationFailed, match="unknown resample frequency 'D'"):
        run(PANEL, {"op": "resample", "freq": "D", "agg": {"px": "last"}})


def test_dedupe_keeps_first_or_last_on_the_index():
    dup = pd.concat([PANEL, PANEL.assign(px=PANEL["px"] * 100)], ignore_index=True)
    last = run(dup, {"op": "dedupe"})
    assert len(last) == 6 and last["px"].max() == 3000.0
    first = run(dup, {"op": "dedupe", "keep": "first"})
    assert first["px"].max() == 30.0
    with pytest.raises(ValidationFailed):
        run(dup, {"op": "dedupe", "keep": "middle"})


def test_clip_and_winsorize():
    clipped = run(PANEL, {"op": "clip", "attr": "px", "lo": 2, "hi": 10})
    assert clipped["px"].dropna().tolist() == [2.0, 2.0, 4.0, 10.0, 10.0]
    one_sided = run(PANEL, {"op": "clip", "attr": "px", "hi": 3})
    assert one_sided["px"].max() == 3.0 and one_sided["px"].min() == 1.0
    w = run(PANEL, {"op": "winsorize", "attr": "px", "p": 0.25})
    assert w["px"].max() < 30.0 and w["px"].min() > 1.0 and w["px"].isna().sum() == 1
    for p in (-0.1, 0.5):
        with pytest.raises(ValidationFailed, match="winsorize p"):
            run(PANEL, {"op": "winsorize", "attr": "px", "p": p})


def test_the_output_schema_is_known_before_any_data():
    schema = [{"name": "px", "type": "float64"}, {"name": "vol", "type": "int64"}]
    out = transforms.pipeline_output_schema(
        schema,
        [
            {"op": "rename", "mapping": {"vol": "volume"}},
            {"op": "cast", "attr": "volume", "type": "float64"},
            {"op": "derive", "name": "px", "expr": "px * 2", "type": "float64"},
            {"op": "window", "attr": "px", "fn": "mean", "size": 5},
            {"op": "lag", "attr": "volume", "n": 1, "name": "vol_prev"},
        ],
        IDX,
    )
    assert [(a["name"], a["type"]) for a in out] == [
        ("volume", "float64"),
        ("px", "float64"),
        ("px_mean5", "float64"),
        ("vol_prev", "float64"),
    ]
    agg = transforms.pipeline_output_schema(
        schema, [{"op": "aggregate", "by": ["symbol"], "agg": {"px": "mean"}}], IDX
    )
    assert [a["name"] for a in agg] == ["px"]


def test_canonical_pipeline_ignores_key_order_and_expression_spacing():
    a = transforms.canonical_pipeline([{"op": "filter", "expr": "px>1 and vol<2"}])
    b = transforms.canonical_pipeline([{"expr": "px > 1   and vol < 2", "op": "filter"}])
    assert a == b
    assert a != transforms.canonical_pipeline([{"op": "filter", "expr": "px > 2 and vol < 2"}])


# --------------------------------------------------------------------- rules
DATES = pd.Series(
    pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-10"])
)


def fill(values: list, rule) -> tuple[list, dict]:
    out, stats = rules.apply_rule(pd.Series(values, dtype="float64"), rule, DATES)
    return [None if pd.isna(v) else v for v in out.tolist()], stats


def test_every_rule_on_one_series():
    s = [1.0, None, None, 4.0, None]
    assert fill(s, None)[0] == s
    assert fill(s, "forward_fill")[0] == [1.0, 1.0, 1.0, 4.0, 4.0]
    assert fill(s, "forward_fill(limit=1)")[0] == [1.0, 1.0, None, 4.0, 4.0]
    assert fill(s, "forward_fill(max_age=2)")[0] == [1.0, 1.0, 1.0, 4.0, None]
    assert fill(s, "backward_fill")[0] == [1.0, 4.0, 4.0, 4.0, None]
    assert fill(s, "constant(v=0.5)")[0] == [1.0, 0.5, 0.5, 4.0, 0.5]
    assert fill(s, "zero")[0] == [1.0, 0.0, 0.0, 4.0, 0.0]
    assert fill(s, "previous_period")[0] == [1.0, 1.0, None, 4.0, 4.0]
    assert fill(s, "mean_of_window(n=2)")[0] == [1.0, 1.0, 1.0, 4.0, 4.0]
    assert fill(s, {"rule": "last_known_as_of", "lag": 1})[0] == [1.0, 1.0, 1.0, 4.0, 4.0]
    interp = fill(s, "linear_interp")[0]
    assert interp[:4] == [1.0, 2.0, 3.0, 4.0] and interp[4] is None  # inside only


def test_fill_statistics_count_what_the_rule_did():
    _, stats = fill([1.0, None, None, 4.0, None], "forward_fill(limit=3)")
    assert stats == {"rule": "forward_fill(limit=3)", "filled": 3, "longest_run": 2}
    _, stats = fill([None, None, None, None, None], "forward_fill")
    assert stats["filled"] == 0 and stats["longest_run"] == 0


def test_non_causal_rules_are_flagged_and_causal_ones_are_not():
    parseable = [r for r in rules.PARAMS if r not in ("custom", "spline_interp")]
    flagged = {
        r
        for r in parseable
        if rules.parse_rule("constant(v=1)" if r == "constant" else r).non_causal
    }
    assert flagged == {"backward_fill", "linear_interp"}
    assert rules.RuleSpec("spline_interp").non_causal  # needs scipy to parse


@pytest.mark.parametrize(
    "text",
    [
        "last_known_as_of(lag=-1)",
        "forward_fill(limit=-1)",
        "forward_fill(max_age=-3)",
        "mean_of_window(n=0)",
        "backward_fill(limit=1.5)",
        "forward_fill(limit=True)",
    ],
)
def test_rule_parameters_are_bounded(text):
    with pytest.raises(ValidationFailed, match="must be a whole number"):
        rules.parse_rule(text)


def test_a_negative_as_of_lag_is_named_as_look_ahead():
    with pytest.raises(ValidationFailed, match="look-ahead"):
        rules.parse_rule({"rule": "last_known_as_of", "lag": -5})


@pytest.mark.parametrize(
    "spec,match",
    [
        ("teleport", "unknown resolution rule"),
        ("forward_fill(1, 2, 3)", "at most 2"),
        ("forward_fill(speed=3)", "unknown parameter"),
        ("custom(fn='f')", "sandboxed function"),
        ({"limit": 3}, "needs a 'rule' key"),
        ("forward_fill(", "does not parse"),
        ("x.y", "not a rule call"),
    ],
)
def test_rule_parse_errors_name_the_problem(spec, match):
    with pytest.raises(ValidationFailed, match=match):
        rules.parse_rule(spec)


def test_rule_forms_are_equivalent_and_canonical():
    a = rules.parse_rule("forward_fill(3, 10)")
    b = rules.parse_rule({"rule": "forward_fill", "max_age": 10, "limit": 3})
    assert a == b and a.canonical() == "forward_fill(limit=3, max_age=10)"
    assert rules.parse_rule(a) is a and rules.parse_rule(None).name == "none"
    assert b.to_dict() == {"rule": "forward_fill", "limit": 3, "max_age": 10}


def test_constant_without_a_value_is_refused_when_applied():
    with pytest.raises(ValidationFailed, match="needs a value"):
        fill([1.0, None, 2.0, None, 3.0], "constant")


# -------------------------------------------------------------------- quality
Q = frame(
    [
        ("2026-01-02", "A", 1.0, 5.0),
        ("2026-01-05", "A", 2.0, 6.0),
        ("2026-01-06", "A", 4.0, None),
        ("2026-01-02", "B", 0.0, 1.0),
        ("2026-01-05", "B", 5.0, 1.0),
    ]
)


@pytest.mark.parametrize(
    "check,passes",
    [
        ({"check": "not_null", "attr": "px"}, True),
        ({"check": "not_null", "attr": "vol"}, False),
        ({"check": "unique_on_index"}, True),
        ({"check": "range", "attr": "px", "min": 0, "max": 5}, True),
        ({"check": "range", "attr": "px", "min": 1}, False),
        ({"check": "allowed_values", "attr": "symbol", "values": ["A", "B"]}, True),
        ({"check": "allowed_values", "attr": "symbol", "values": ["A"]}, False),
        ({"check": "monotonic", "attr": "px"}, True),
        ({"check": "monotonic", "attr": "px", "direction": "decreasing"}, False),
        ({"check": "max_daily_change", "attr": "px", "max": 1.0}, False),  # B: 0 -> 5
        ({"check": "max_daily_change", "attr": "vol", "max": 0.25}, True),
        ({"check": "row_count_between", "min": 1, "max": 5}, True),
        ({"check": "row_count_between", "max": 4}, False),
        ({"check": "freshness_within", "days": 3, "as_of": "2026-01-08"}, True),
        ({"check": "freshness_within", "days": 1, "as_of": "2026-01-08"}, False),
    ],
)
def test_each_quality_check(check, passes):
    [result] = quality.run_checks(Q, [check], IDX)
    assert result["passed"] is passes, result


def test_a_move_away_from_zero_breaches_any_relative_change_limit():
    df = frame([("2026-01-02", "A", 0.0), ("2026-01-05", "A", 5.0), ("2026-01-06", "A", 5.0)])
    [r] = quality.run_checks(df, [{"check": "max_daily_change", "attr": "px", "max": 100.0}], IDX)
    assert not r["passed"] and r["detail"].startswith("1 change")
    flat = frame([("2026-01-02", "A", 0.0), ("2026-01-05", "A", 0.0)])
    [r] = quality.run_checks(flat, [{"check": "max_daily_change", "attr": "px", "max": 0.1}], IDX)
    assert r["passed"]  # 0 -> 0 is no change


def test_duplicate_index_keys_fail_uniqueness():
    [r] = quality.run_checks(pd.concat([Q, Q.iloc[:1]]), [{"check": "unique_on_index"}], IDX)
    assert not r["passed"] and r["detail"] == "1 duplicate index key(s)"


def test_freshness_on_no_rows_fails_and_defaults_to_the_run_as_of():
    [r] = quality.run_checks(Q.iloc[0:0], [{"check": "freshness_within", "days": 9}], IDX)
    assert not r["passed"]
    [r] = quality.run_checks(Q, [{"check": "freshness_within", "days": 1}], IDX, as_of="2026-01-30")
    assert not r["passed"] and "24 day(s) old" in r["detail"]


def test_the_short_contract_form_means_the_same_checks():
    short = {
        "row_count_between": [1, 10],
        "unique_on_index": True,
        "attributes": {
            "px": {
                "not_null": True,
                "range": [0, 5],
                "monotonic": "increasing",
                "max_daily_change": 10.0,
            },
            "symbol": {"allowed_values": ["A", "B"]},
            "date": {"freshness_within": {"days": 9, "as_of": "2026-01-08"}},
        },
    }
    results = quality.run_checks(Q, short, IDX)
    assert len(results) == 8 and all(
        r["passed"] for r in results if r["check"] != "max_daily_change"
    )
    assert quality.normalize_contract(None) == []


def test_unknown_checks_and_attributes_are_named_and_enforce_lists_every_failure():
    with pytest.raises(ValidationFailed, match="unknown quality check 'vibes'"):
        quality.run_checks(Q, [{"check": "vibes"}], IDX)
    with pytest.raises(ValidationFailed, match="unknown attribute 'nope'"):
        quality.run_checks(Q, [{"check": "not_null", "attr": "nope"}], IDX)
    results = quality.run_checks(
        Q, [{"check": "not_null", "attr": "vol"}, {"check": "row_count_between", "max": 1}], IDX
    )
    with pytest.raises(QualityCheckFailed) as exc:
        quality.enforce(results)
    assert "not_null(vol)" in exc.value.message and "row_count_between(*)" in exc.value.message
    quality.enforce([r for r in results if r["passed"]])


# -------------------------------------------------------------------- algebra
def meta(
    *attrs: str, types: str = "float64", index: list[str] | None = None, nc: bool = False
) -> dict:
    return {
        "index": index or IDX,
        "schema": [{"name": a, "type": types} for a in attrs],
        "non_causal": nc,
    }


def test_every_operator_is_registered_and_unknown_ones_are_refused():
    assert set(algebra.OPERATORS) == {
        "project",
        "rename",
        "transform",
        "union",
        "intersect",
        "difference",
        "compose",
        "coalesce",
        "aggregate",
        "lag",
        "resample",
        "case",
        "pivot",
        "unpivot",
        "sample",
    }
    with pytest.raises(ValidationFailed, match="unknown algebra operator"):
        algebra.typecheck("zip", {}, [meta("px")])


@pytest.mark.parametrize(
    "op,n",
    [
        ("project", 2),
        ("rename", 0),
        ("union", 1),
        ("intersect", 3),
        ("difference", 1),
        ("compose", 1),
        ("coalesce", 1),
        ("aggregate", 2),
        ("lag", 2),
        ("resample", 0),
        ("case", 1),
        ("transform", 2),
    ],
)
def test_arity_is_checked_for_every_operator(op, n):
    with pytest.raises(ValidationFailed, match="operand"):
        algebra.typecheck(
            op,
            {
                "attrs": ["px"],
                "by": ["symbol"],
                "agg": {"px": "mean"},
                "freq": "M",
                "cond": "px > 0",
            },
            [meta("px")] * n,
        )


@pytest.mark.parametrize(
    "op,options,metas,match",
    [
        ("project", {"attrs": ["nope"]}, [meta("px")], "unknown"),
        ("project", {}, [meta("px")], "unknown or no"),
        ("rename", {"mapping": {"date": "d"}}, [meta("px")], "index columns"),
        ("rename", {"mapping": {"nope": "x"}}, [meta("px")], "unknown attribute"),
        ("rename", {"mapping": {"px": "vol"}}, [meta("px", "vol")], "duplicate"),
        ("union", {"collision": "coin_flip"}, [meta("px"), meta("px")], "collision must be"),
        ("union", {}, [meta("px"), meta("vol")], "identical attributes"),
        ("union", {}, [meta("px"), meta("px", index=["date"])], "identical indexes"),
        ("union", {}, [meta("px"), meta("px", types="string")], "conflicting types"),
        ("intersect", {"priority": "middle"}, [meta("px"), meta("px")], "priority"),
        ("compose", {}, [meta("px"), meta("px")], "name clash"),
        ("compose", {}, [meta("px"), meta("vol", index=["symbol"])], "broadcast"),
        ("aggregate", {"by": [], "agg": {"px": "mean"}}, [meta("px")], "non-empty subset"),
        ("aggregate", {"by": ["sector"], "agg": {"px": "mean"}}, [meta("px")], "subset"),
        ("aggregate", {"by": ["symbol"], "agg": {"nope": "mean"}}, [meta("px")], "unknown"),
        ("lag", {"n": -1}, [meta("px")], "look-ahead"),
        ("resample", {"freq": "D"}, [meta("px")], "W, M or Q"),
        ("case", {"cond": "nope > 0"}, [meta("px"), meta("px")], "unknown name"),
        (
            "transform",
            {"pipeline": [{"op": "lag", "attr": "px", "n": -1}]},
            [meta("px")],
            "look-ahead",
        ),
    ],
)
def test_typing_errors_happen_at_definition_time(op, options, metas, match):
    with pytest.raises(ValidationFailed, match=match):
        algebra.typecheck(op, options, metas)


def test_non_causality_propagates_through_every_binary_operator():
    for op, opts in (
        ("union", {}),
        ("intersect", {}),
        ("difference", {}),
        ("coalesce", {}),
        ("case", {"cond": "px > 0"}),
        ("compose", {"prefixes": ["a_", "b_"]}),
    ):
        out = algebra.typecheck(op, opts, [meta("px"), meta("px", nc=True)])
        assert out["non_causal"] is True, op
        assert algebra.typecheck(op, opts, [meta("px"), meta("px")])["non_causal"] is False


def test_union_collision_policies():
    a = frame([("2026-01-02", "A", 1.0), ("2026-01-05", "A", 2.0)])
    b = frame([("2026-01-05", "A", 20.0), ("2026-01-06", "A", 30.0)])
    m = [meta("px"), meta("px")]
    with pytest.raises(ValidationFailed, match="1 colliding|2 colliding"):
        algebra.execute("union", {}, [a, b], m)
    assert algebra.execute("union", {"collision": "prefer_left"}, [a, b], m)["px"].tolist() == [
        1.0,
        2.0,
        30.0,
    ]
    assert algebra.execute("union", {"collision": "prefer_right"}, [a, b], m)["px"].tolist() == [
        1.0,
        20.0,
        30.0,
    ]
    three = algebra.execute("union", {"collision": "prefer_left"}, [a, b, b], [meta("px")] * 3)
    assert len(three) == 3


def test_operators_on_empty_operands():
    e = frame([("2026-01-02", "A", 1.0)]).iloc[0:0]
    a = frame([("2026-01-02", "A", 1.0)])
    m = [meta("px"), meta("px")]
    assert algebra.execute("union", {}, [a, e], m)["px"].tolist() == [1.0]
    assert algebra.execute("intersect", {}, [a, e], m).empty
    assert algebra.execute("difference", {}, [a, e], m)["px"].tolist() == [1.0]
    assert algebra.execute("coalesce", {}, [e, a], m)["px"].tolist() == [1.0]
    assert algebra.execute("lag", {"n": 1}, [e], [meta("px")]).empty


def test_coalesce_takes_the_first_non_null_in_operand_order():
    a = frame([("2026-01-02", "A", None), ("2026-01-05", "A", 2.0)])
    b = frame([("2026-01-02", "A", 10.0), ("2026-01-05", "A", 20.0), ("2026-01-06", "A", 30.0)])
    out = algebra.execute("coalesce", {}, [a, b], [meta("px"), meta("px")])
    assert out["px"].tolist() == [10.0, 2.0, 30.0]
    back = algebra.execute("coalesce", {}, [b, a], [meta("px"), meta("px")])
    assert back["px"].tolist() == [10.0, 20.0, 30.0]


def test_compose_with_prefixes_is_an_outer_join():
    a = frame([("2026-01-02", "A", 1.0)])
    b = frame([("2026-01-05", "A", 2.0)])
    out = algebra.execute("compose", {"prefixes": ["l_", "r_"]}, [a, b], [meta("px"), meta("px")])
    assert list(out.columns) == ["date", "symbol", "l_px", "r_px"] and len(out) == 2


def test_lag_on_chosen_attributes_only_and_resample_defaults_to_last():
    df = frame([("2026-01-02", "A", 1.0, 10.0), ("2026-01-05", "A", 2.0, 20.0)])
    out = algebra.execute("lag", {"n": 1, "attrs": ["px"]}, [df], [meta("px", "vol")])
    assert out["vol"].tolist() == [10.0, 20.0] and math.isnan(out["px"].iloc[0])
    monthly = algebra.execute("resample", {"freq": "M"}, [df], [meta("px", "vol")])
    assert monthly[["px", "vol"]].values.tolist() == [[2.0, 20.0]]


def test_lag_on_an_unknown_attribute_is_a_typing_error():
    with pytest.raises(ValidationFailed, match="unknown"):
        algebra.typecheck("lag", {"n": 1, "attrs": ["nope"]}, [meta("px")])


def test_case_picks_per_row_and_fills_from_the_else_branch():
    live = frame([("2026-01-02", "A", -1.0), ("2026-01-05", "A", 5.0)])
    eod = frame([("2026-01-02", "A", 9.0), ("2026-01-05", "A", 8.0), ("2026-01-06", "A", 7.0)])
    out = algebra.execute("case", {"cond": "px > 0"}, [live, eod], [meta("px"), meta("px")])
    assert out["px"].tolist() == [9.0, 5.0, 7.0]


def test_canonical_derivation_normalizes_pipelines_and_conditions():
    a = algebra.canonical_derivation("case", {"cond": "px>0"}, ["x", "y"])
    b = algebra.canonical_derivation("case", {"cond": "px > 0"}, ["x", "y"])
    assert a == b and algebra.canonical_derivation("case", {"cond": "px > 0"}, ["y", "x"]) != a
    t1 = algebra.canonical_derivation(
        "transform", {"pipeline": [{"op": "filter", "expr": "px>0"}]}, ["x"]
    )
    t2 = algebra.canonical_derivation(
        "transform", {"pipeline": [{"expr": "px > 0", "op": "filter"}]}, ["x"]
    )
    assert t1 == t2
    with pytest.raises(ValidationFailed):
        algebra.canonical_derivation("zip", {}, ["x"])


def test_winsorize_ignores_nulls_when_choosing_quantiles():
    df = frame(
        [("2026-01-0%d" % (i + 1), "A", float(v)) for i, v in enumerate([1, 2, 3, 4, 100])]
        + [("2026-01-07", "A", None)]
    )
    out = run(df, {"op": "winsorize", "attr": "px", "p": 0.2})
    assert np.isfinite(out["px"].dropna()).all() and out["px"].max() < 100.0
