"""
Tables for MAYA's two small languages and its type system, each row a case
with its answer derived independently (by hand or from ``math``), not read
back from the implementation:

* the restricted expression language (§5.4, §17.3): values, refusals, and the
  runaway-arithmetic guards;
* the formula grammar (§8.1): parse → evaluate agrees with the mathematics,
  including precedence and associativity; LaTeX rendering; Python lifting refusals;
* logical types: parsing, Arrow mapping, casting (with range limits), unification.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest

from maya.core.errors import ValidationFailed
from maya.formula.evaluate import evaluate
from maya.formula.latex import to_latex
from maya.formula.parse import parse_formula, parse_model
from maya.formula.pylift import lift_python
from maya.resolution import types
from maya.resolution.expr import compile_expr

DF = pd.DataFrame({"px": [1.0, 2.0, 3.0], "vol": [10.0, None, 30.0], "sym": ["A", "B", "C"],
                   "d": pd.to_datetime(["2026-01-31", "2026-02-15", "2027-03-01"]),
                   "n": pd.array([1, 2, None], dtype="Int64")})


def ev(text: str) -> list:
    out = compile_expr(text).evaluate(DF).tolist()
    return [None if (isinstance(v, float) and math.isnan(v)) else v for v in out]


@pytest.mark.parametrize("text,expected", [
    ("px + 1", [2.0, 3.0, 4.0]), ("px * 2 - 1", [1.0, 3.0, 5.0]), ("px / 2", [0.5, 1.0, 1.5]),
    ("px // 2", [0.0, 1.0, 1.0]), ("px % 2", [1.0, 0.0, 1.0]), ("-px", [-1.0, -2.0, -3.0]),
    ("+px", [1.0, 2.0, 3.0]), ("px ** 2", [1.0, 4.0, 9.0]), ("2 ** px", [2.0, 4.0, 8.0]),
    ("px > 1", [False, True, True]), ("px >= 2", [False, True, True]),
    ("px == 2", [False, True, False]), ("px != 2", [True, False, True]),
    ("1 < px < 3", [False, True, False]), ("px > 1 and px < 3", [False, True, False]),
    ("px < 2 or px > 2", [True, False, True]), ("not px > 1", [True, False, False]),
    ("sym in ['A', 'C']", [True, False, True]), ("sym not in ['A']", [False, True, True]),
    ("sym == 'B'", [False, True, False]), ("abs(px - 2)", [1.0, 0.0, 1.0]),
    ("sqrt(px * px)", [1.0, 2.0, 3.0]), ("round(px / 3, 2)", [0.33, 0.67, 1.0]),
    ("max(px, 2)", [2.0, 2.0, 3.0]), ("min(px, 2, 1.5)", [1.0, 1.5, 1.5]),
    ("clip(px, 1.5, 2.5)", [1.5, 2.0, 2.5]), ("where(px > 1, px, 0)", [0.0, 2.0, 3.0]),
    ("px if px > 2 else -1", [-1.0, -1.0, 3.0]), ("isnull(vol)", [False, True, False]),
    ("notnull(vol)", [True, False, True]), ("vol / 10", [1.0, None, 3.0]),
    ("year(d)", [2026, 2026, 2027]), ("month(d)", [1, 2, 3]), ("day(d)", [31, 15, 1]),
    ("n * 2", [2.0, 4.0, None]), ("3", [3, 3, 3]), ("sym + '!'", ["A!", "B!", "C!"]),
    ("True", [True, True, True]), ("exp(0) + log(1)", [1.0, 1.0, 1.0]),
])
def test_expression_values(text, expected):
    got = ev(text)
    for g, e in zip(got, expected):
        assert (g is None and e is None) or g == pytest.approx(e), (text, got, expected)


@pytest.mark.parametrize("text,match", [
    ("__import__('os')", "not permitted"), ("px.real", "Attribute"), ("DF[0]", "Subscript"),
    ("lambda: 1", "Lambda"), ("[x for x in px]", "ListComp"), ("open('f')", "'open'"),
    ("len(sym)", "'len'"), ("abs(px, 2)", "takes 1..1"), ("round(px, ndigits=2)", "keyword"),
    ("sym in names", "literal list"), ("sym in [px]", "literals"), ("px @ px", "MatMult"),
    ("px << 2", "LShift"), ("~px", "Invert"), ("px is None", "Is"), ("", "empty"),
    ("px +", "does not parse"), ("(1).bit_length()", "Attribute"), ("b'x'", "only numbers"),
    ("__class__", "dunder"),
])
def test_expressions_refuse_everything_off_the_whitelist(text, match):
    with pytest.raises(ValidationFailed, match=match):
        compile_expr(text)


@pytest.mark.parametrize("text", ["px > 10**10**10", "px < 9**9**9**9", "2**100000 > px"])
def test_power_cannot_run_away(text):
    """Evaluated in floating point: a tower of powers is inf in no time, not a
    billion-digit integer that hangs the resolver."""
    assert all(isinstance(v, bool) for v in ev(text))


@pytest.mark.parametrize("text", ["'a' * 10**9 == 'b'", "sym * 3 == 'AAA'",
                                  "'%999999999d' % 1 == 'x'", "sym - 'A' == ''"])
def test_text_only_takes_part_in_concatenation(text):
    with pytest.raises(ValidationFailed, match="text may only be joined"):
        ev(text)


def test_an_unknown_attribute_is_named_at_evaluation():
    with pytest.raises(ValidationFailed, match=r"unknown attribute\(s\) \['price'\]"):
        ev("price > 1")


# -------------------------------------------------------------------- formulas
X = {"x": 2.0, "y": 3.0, "z": 0.5}


def fx(text: str) -> float:
    node = parse_formula(text, inputs=set(X))
    ir = {"outputs": [{"name": "out"}], "inputs": [{"name": n} for n in X], "lets": {},
          "body": node}
    return float(evaluate(ir, {k: np.array([v]) for k, v in X.items()})["out"][0])


@pytest.mark.parametrize("text,expected", [
    ("x + y * z", 2 + 3 * 0.5), ("(x + y) * z", (2 + 3) * 0.5), ("x - y - z", 2 - 3 - 0.5),
    ("x / y / z", 2 / 3 / 0.5), ("x^y", 2 ** 3), ("x**y", 2 ** 3), ("x^y^z", 2 ** (3 ** 0.5)),
    ("-x^2", -(2 ** 2)), ("x^{-1}", 0.5), ("2x", 4.0), ("x y", 6.0), ("x(y + 1)", 8.0),
    ("\\frac{x}{y}", 2 / 3), ("\\sqrt{x}", math.sqrt(2)), ("e^{x}", math.exp(2)),
    ("\\exp(x)", math.exp(2)), ("\\ln(x)", math.log(2)), ("log(y)", math.log(3)),
    ("|x - y|", 1.0), ("\\max(x, y)", 3.0), ("min(x, y, z)", 0.5), ("N(0)", 0.5),
    ("npdf(0)", 1 / math.sqrt(2 * math.pi)), ("x \\cdot y", 6.0), ("x \\times y", 6.0),
    ("\\left(x + y\\right) z", 2.5), ("1.5e2 + x", 152.0), (".5 + x", 2.5),
    ("where(x > y, x, y)", 3.0), ("where(x <= y, 1, 0)", 1.0), ("where(x == 2, 7, 0)", 7.0),
])
def test_formulas_evaluate_as_the_mathematics_says(text, expected):
    assert fx(text) == pytest.approx(expected, rel=1e-12), text


@pytest.mark.parametrize("text", ["x +", "(x", "x ) y", "\\frac{x}", "x ^",
                                  "\\sqrt", "x $ y", ""])
def test_formula_parse_errors_are_refused(text):
    with pytest.raises(ValidationFailed):
        parse_formula(text, inputs=set(X))


@pytest.mark.parametrize("model,snippet", [
    ("y = a*x + b", "a"), ("y = \\frac{a}{b}", "\\frac{a}{b}"), ("y = sqrt(x)", "\\sqrt{x}"),
    ("y = exp(x)", "e^{x}"), ("y = log(x)", "\\ln"), ("y = N(x)", "N\\left(x\\right)"),
    ("y = x^2", "x^{2}"), ("y = abs(x)", "\\left|x\\right|"), ("y = max(a, b)", "\\max"),
    ("y = sigma*x", "\\sigma"), ("d1 = x + 1\ny = d1 * 2", "d_{1}"),
    ("y = where(x > 0, x, 0)", "\\begin{cases}"),
])
def test_latex_renders_each_construct(model, snippet):
    assert snippet in to_latex(parse_model(model))


@pytest.mark.parametrize("source,match", [
    ("def f(x):\n    for i in x:\n        pass\n    return x\n", "For"),
    ("def f(x):\n    if x > 0:\n        return x\n    return 0\n", "If"),
    ("def f(x):\n    return x.mean()\n", "call to 'mean' cannot be lifted"),
    ("def f(x):\n    return x[0]\n", "subscripts lift"),
    ("def f(x):\n    return 'a'\n", "numeric constants"),
    ("def f(x):\n    y = 1\n", "no return"),
    ("def f(x):\n    return x\n    y = 2\n", "after return"),
    ("def f(x:\n    return x\n", "syntax error"),
    ("x = 1\n", "no function"),
])
def test_python_lifting_refuses_what_it_cannot_express(source, match):
    with pytest.raises(ValidationFailed, match=match):
        lift_python(source)


# ------------------------------------------------------------------------ types
@pytest.mark.parametrize("text,kind", [
    ("int32", "int32"), ("int64", "int64"), ("float64", "float64"), ("bool", "bool"),
    ("string", "string"), ("date", "date"), ("timestamp", "timestamp"),
    ("decimal(18, 4)", "decimal"), ("list<float64>", "list"),
    ("fixed_vector<float64,4>", "fixed_vector"), ("tensor<float32,[2,3]>", "tensor"),
    ("map<string,int64>", "map"), ("struct<a:float64,b:string>", "struct"),
    ("list<list<int64>>", "list"),
])
def test_logical_types_parse_and_map_to_arrow(text, kind):
    lt = types.parse_type(text)
    assert lt.kind == kind
    assert isinstance(types.arrow_type(text), pa.DataType)


@pytest.mark.parametrize("text", [
    "int128", "float", "list<>", "list<nope>", "fixed_vector<float64,x>",
    "fixed_vector<float64,0>", "fixed_vector<nope,3>", "tensor<float64,[2,x]>",
    "tensor<float64,[0]>", "map<string>", "map<string,nope>", "struct<a:nope>", "struct<:int64>",
    "decimal(x,2)", "vector<float64>",
])
def test_malformed_types_are_refused_by_name(text):
    with pytest.raises(ValidationFailed, match="logical type"):
        types.parse_type(text)


def test_arrow_shapes_of_nested_types():
    assert types.arrow_type("fixed_vector<float64,4>") == pa.list_(pa.float64(), 4)
    assert types.arrow_type("tensor<float32,[2,3]>") == pa.list_(pa.float32(), 6)
    assert types.parse_type("tensor<float32,[2,3]>").shape == (2, 3)
    assert types.arrow_type("decimal(10,2)") == pa.decimal128(10, 2)


@pytest.mark.parametrize("values,logical,expected", [
    (["1", "2.0", None], "int64", [1, 2, None]), (["1.5", "x2"], "float64", "cannot be cast"),
    (["yes", "N", "t", "0"], "bool", [True, False, True, False]), (["maybe"], "bool", "cannot"),
    (["1.2345"], "decimal(10,2)", ["1.23"]), (["2026-03-01T10:00:00+02:00"], "timestamp",
                                             ["2026-03-01 08:00:00+00:00"]),
    (["2026-03-01"], "date", ["2026-03-01"]), ([3.5], "int64", "cannot be cast"),
    ([2 ** 31], "int32", "cannot be cast"), ([-2 ** 31], "int32", [-2 ** 31]),
    ([2 ** 63], "int64", "cannot be cast"), ([12], "string", ["12"]),
])
def test_casting(values, logical, expected):
    s = pd.Series(values, name="v", dtype=object)
    if isinstance(expected, str):
        with pytest.raises(ValidationFailed, match=expected):
            types.cast_series(s, logical)
        preview = types.cast_preview(s, logical)
        assert preview["failures"] >= 1 and preview["examples"]
        return
    out = types.cast_series(s, logical)
    got = [None if pd.isna(v) else (str(v) if logical in ("decimal(10,2)", "timestamp")
                                    else (str(v.date()) if logical == "date" else v))
           for v in out.tolist()]
    assert got == expected


@pytest.mark.parametrize("a,b,ok", [
    ({"name": "px", "type": "float64"}, {"name": "px", "type": "float64"}, True),
    ({"name": "px", "type": "float64", "unit": "USD"}, {"name": "px", "type": "float64"}, True),
    ({"name": "px", "type": "float64", "unit": "USD"},
     {"name": "px", "type": "float64", "unit": "EUR"}, False),
    ({"name": "px", "type": "float64", "tag": "price"},
     {"name": "px", "type": "float64", "tag": "yield"}, False),
    ({"name": "px", "type": "float64"}, {"name": "px", "type": "int64"}, False),
])
def test_unification(a, b, ok):
    if ok:
        merged = types.unify(a, b)
        assert merged["unit"] if a.get("unit") else "unit" not in merged
        assert merged["nullable"] is True
    else:
        with pytest.raises(ValidationFailed, match="conflicting"):
            types.unify(a, b)


def test_schema_inference_and_its_warnings():
    df = pd.DataFrame({"d": pd.to_datetime(["2026-01-01"]), "px": [1.5], "n": [3],
                       "flag": [True], "s": ["x"], "vec": [[1.0, 2.0]]})
    schema = {a["name"]: a["type"] for a in types.infer_schema(df)}
    assert schema["px"] == "float64" and schema["n"] == "int64" and schema["flag"] == "bool"
    assert schema["s"] == "string" and schema["vec"] == "fixed_vector<float64,2>"
    warnings = types.schema_warnings(types.infer_schema(pd.DataFrame({"x": ["1", "2"]})))
    assert isinstance(warnings, list)
