"""Formula IR: parse, render, evaluate, diff, codegen, lift, composite, conformance, spec document."""
from __future__ import annotations

import numpy as np
import pytest

from maya.core.errors import ContractMismatch, ValidationFailed
from maya.formula import composite as comp
from maya.formula.codegen import compile_reference, to_python
from maya.formula.conformance import conformance_test, sample_inputs
from maya.formula.diff import semantic_diff
from maya.formula.evaluate import evaluate, evaluate_composite, ncdf
from maya.formula.ir import input_contract, ir_hash, is_opaque, typecheck, validate_ir
from maya.formula.latex import to_latex
from maya.formula.parse import parse_formula, parse_model
from maya.formula.pylift import lift_python
from maya.formula.specdoc import (bound_formulas, default_document, expand_macros, is_complete,
                                  outline, section_completeness)

BS_PY = """
d1 = (log(S/K) + (r + sigma**2/2)*T) / (sigma*sqrt(T))
d2 = d1 - sigma*sqrt(T)
price = S*ncdf(d1) - K*exp(-r*T)*ncdf(d2)
"""
BS_TEX = r"""
d_1 = \frac{\ln(S/K) + (r + \sigma^2/2)T}{\sigma\sqrt{T}}
d_2 = d_1 - \sigma\sqrt{T}
C = S N(d_1) - K e^{-rT} N(d_2)
"""
ROLES = {"sigma": "parameter"}
POINT = {"S": 100.0, "K": 100.0, "r": 0.05, "T": 1.0}


@pytest.mark.parametrize("text", [BS_PY, BS_TEX])
def test_black_scholes_both_syntaxes(text: str) -> None:
    ir = parse_model(text, roles=ROLES)
    assert validate_ir(ir) == []
    out = evaluate(ir, POINT, {"sigma": 0.2})
    assert abs(float(next(iter(out.values()))[0]) - 10.4506) < 1e-4
    assert "sigma" not in [i["name"] for i in input_contract(ir)]
    assert r"\frac" in ir["latex"] and r"\sigma" in ir["latex"] and "N\\left(" in ir["latex"]


def test_python_and_latex_forms_evaluate_identically() -> None:
    a = parse_model(BS_PY, roles=ROLES)
    b = parse_model(BS_TEX, roles=ROLES)
    grid = {"S": np.linspace(50, 150, 11), "K": 100.0, "r": 0.03, "T": 0.5}
    np.testing.assert_allclose(next(iter(evaluate(a, grid, {"sigma": 0.3}).values())),
                               next(iter(evaluate(b, grid, {"sigma": 0.3}).values())), rtol=1e-12)


def test_ncdf_precision() -> None:
    assert abs(float(ncdf(1.96)) - 0.9750021048517795) < 1e-12
    assert abs(float(ncdf(-8.0)) - 6.22096057427178e-16) < 1e-20


def test_validation_errors_are_named() -> None:
    bad = {"outputs": [{"name": "y"}], "inputs": [{"name": "x", "role": "feature"}],
           "lets": {"a": {"ref": "b"}, "b": {"ref": "a"}}, "body": {"op": "frob", "args": []}}
    errs = validate_ir(bad)
    assert any("unknown op 'frob'" in e for e in errs)
    bad["body"] = {"op": "add", "args": [{"ref": "a"}, {"ref": "zz"}]}
    errs = validate_ir(bad)
    assert any("cycle" in e for e in errs) or any("unknown ref 'zz'" in e for e in errs)
    black = {"outputs": [{"name": "pd"}], "inputs": [], "black_box": {"architecture": "GBM"}}
    assert any("estimates" in e for e in validate_ir(black))
    assert is_opaque(black)


def test_parse_refuses_garbage_with_position() -> None:
    with pytest.raises(ValidationFailed) as exc:
        parse_formula("S * @ K")
    assert "position" in exc.value.message
    with pytest.raises(ValidationFailed):
        parse_formula(r"\weird{x}")


def test_hash_ignores_latex_but_not_math() -> None:
    ir = parse_model(BS_PY, roles=ROLES)
    other = dict(ir, latex="whatever")
    assert ir_hash(ir) == ir_hash(other)
    changed = parse_model(BS_PY.replace("sigma**2/2", "sigma**2/3"), roles=ROLES)
    assert ir_hash(changed) != ir_hash(ir)


def test_diff_detects_compounding_change() -> None:
    old = parse_model(BS_PY, roles=ROLES)
    new = parse_model(BS_PY.replace("exp(-r*T)", "1/(1+r*T)"), roles=ROLES)
    msgs = semantic_diff(old, new)
    assert any("continuous to simple compounding" in m for m in msgs)
    assert semantic_diff(old, old) == []


def test_diff_bounds_and_inputs() -> None:
    old = parse_model("y = a*x", roles={"a": "parameter"})
    new = parse_model("y = a*x + b", roles={"a": "parameter"})
    old["inputs"][0]["bounds"] = [0, 5]
    new["inputs"][0]["bounds"] = [0, 3]
    msgs = semantic_diff(old, new)
    assert "feature 'b' added" in msgs
    assert any("bounds changed from [0, 5] to [0, 3]" in m for m in msgs)


def test_codegen_agrees_with_evaluate() -> None:
    ir = parse_model(BS_PY, roles=ROLES)
    src = to_python(ir)
    assert "import os" not in src
    predict = compile_reference(ir)
    X = {"S": np.array([90.0, 100, 110]), "K": np.array([100.0] * 3), "r": np.array([0.05] * 3),
         "T": np.array([1.0] * 3)}
    np.testing.assert_allclose(predict(X, {"sigma": 0.2})["price"],
                               evaluate(ir, X, {"sigma": 0.2})["price"], rtol=1e-14)


def test_pylift() -> None:
    src = """
import math
def score(X, params):
    z = params["beta"] * X["x"] + params["alpha"]
    return 1 / (1 + math.exp(-z))
"""
    ir = lift_python(src)
    roles = {i["name"]: i["role"] for i in ir["inputs"]}
    assert roles == {"alpha": "parameter", "beta": "parameter", "x": "feature"}
    val = evaluate(ir, {"x": np.array([0.0])}, {"alpha": 0.0, "beta": 1.0})["y"]
    assert abs(float(val[0]) - 0.5) < 1e-12
    with pytest.raises(ValidationFailed, match="line"):
        lift_python("def f(x):\n    for i in x:\n        pass\n    return x\n")


def test_composite_union_maturity_seeds_and_eval() -> None:
    base = parse_model("price = S*a", roles={"a": "parameter"})
    skew = parse_model("adj = S*b + v", roles={"b": "parameter"})
    contract = comp.union_contract({"base": base, "skew": skew})
    assert [c["name"] for c in contract] == ["S", "v"]
    assert contract[0]["needed_by"] == ["base", "skew"]
    bad = parse_model("adj = S*b", roles={"b": "parameter"})
    bad["inputs"][0]["type"] = "string"
    with pytest.raises(ContractMismatch):
        comp.union_contract({"base": base, "skew": bad})
    assert comp.capped_maturity({"a": "approved", "b": "experimental"}) == "experimental"
    assert comp.blocking_members({"a": "approved", "b": "experimental"}, "approved") == ["b"]
    seeds = comp.member_seeds(42, ["base", "skew"])
    assert seeds == comp.member_seeds(42, ["base", "skew"]) and seeds["base"] != seeds["skew"]
    ir = {"outputs": [{"name": "price"}], "inputs": [{"name": "w_skew", "role": "parameter"}],
          "composite": {"kind": "ensemble", "members": [{"alias": "base", "ref": "maya://model/b@v1"},
                                                        {"alias": "skew", "ref": "maya://model/s@v1"}],
                        "combine": {"op": "add", "args": [{"ref": "base.price"}, {"op": "mul", "args": [
                            {"param": "w_skew"}, {"ref": "skew.adj"}]}]},
                        "train": {"mode": "sequential", "order": ["base", "skew"], "shared_split": True}}}
    assert validate_ir(ir) == []
    out = evaluate_composite(ir, {"base": base, "skew": skew}, {"S": np.array([2.0]), "v": np.array([1.0])},
                             {"base.a": 3.0, "skew.b": 1.0, "w_skew": 0.5})
    assert float(out["price"][0]) == pytest.approx(6.0 + 0.5 * 3.0)
    with pytest.raises(ValidationFailed, match="cycle"):
        comp.check_structure({"a": ["b"], "b": ["a"]}, "a")
    with pytest.raises(ValidationFailed, match="depth"):
        comp.check_structure({"a": ["b"], "b": ["c"], "c": ["d"], "d": ["e"], "e": ["f"]}, "a")


def test_conformance_finds_counterexample() -> None:
    ir = parse_model(BS_PY, roles=ROLES)
    good = compile_reference(ir)

    def buggy(X, params):  # noqa: ANN001, ANN202
        out = good(X, params)["price"].copy()
        out[np.asarray(X["S"]) > 140] += 0.01
        return {"price": out}

    samples = sample_inputs(ir, {"S": np.linspace(50, 150, 101), "K": np.full(5, 100.0),
                                 "r": np.array([0.01, 0.05]), "T": np.array([0.5, 1.0])}, n=2000)
    ok = conformance_test(ir, good, samples, {"sigma": 0.2})
    assert ok["agreed"] == ok["total"] == 2000 and "not proof" in ok["statement"]
    bad = conformance_test(ir, buggy, samples, {"sigma": 0.2})
    assert bad["agreed"] < bad["total"] and bad["counterexamples"][0]["S"] > 140


def test_typecheck_against_featureset() -> None:
    ir = parse_model(BS_PY, roles=ROLES)
    assert typecheck(ir, {"S": "float64", "K": "float64", "r": "float64", "T": "float64"}) == []
    errs = typecheck(ir, {"S": "string", "K": "float64", "r": "float64"})
    assert any("'T' is not provided" in e for e in errs) and any("'S' needs" in e for e in errs)


def test_specdoc_completeness_and_macros() -> None:
    ir = parse_model(BS_PY, roles=ROLES)
    doc = default_document("black_scholes", ir)
    status = {s["section"]: s for s in section_completeness(doc)}
    assert status["Mathematical Formulation"]["empty"] is False  # carries \mayaformula
    assert status["Scope and Limitations"]["empty"] is True
    assert not is_complete(doc)
    assert bound_formulas(doc) == ["body"]
    filled = doc
    for s in section_completeness(doc):
        if s["empty"]:
            filled = filled.replace(f"\\section{{{s['section']}}}\n", f"\\section{{{s['section']}}}\nText.\n", 1)
    assert is_complete(filled)
    expanded = expand_macros(r"\mayaformula{let:d1} see \mayaref{maya://feature/x@v1}", ir,
                             lambda uri: f"[{uri}]")
    assert r"d_{1} =" in expanded and "[maya://feature/x@v1]" in expanded
    assert any(o["section"] == "Purpose" and o["required"] for o in outline(doc))


def test_latex_renders_lets_aligned() -> None:
    ir = parse_model(BS_PY, roles=ROLES)
    tex = to_latex(ir)
    assert tex.startswith(r"\begin{aligned}") and "d_{1} &=" in tex


def test_constants_declare_a_value_that_evaluation_and_code_both_use() -> None:
    """A constant is fixed, not learned: its declared value fills in when no parameter set
    supplies one; one without a value must be supplied, and a value on anything else is refused."""
    from maya.services.models import ModelService
    from maya.services.warrants import WarrantService
    ir = parse_model(BS_PY, roles={"sigma": "parameter", "r": "constant"})
    X = {k: np.array([v]) for k, v in POINT.items() if k != "r"}
    assert WarrantService.check_bounds(ir, {"sigma": 0.2}) == [
        "missing constant 'r' (the model declares no value for it)"]
    next(i for i in ir["inputs"] if i["name"] == "r")["value"] = 0.05
    assert validate_ir(ir) == [] and WarrantService.check_bounds(ir, {"sigma": 0.2}) == []
    expected = evaluate(ir, {**X, "r": np.array([0.05])}, {"sigma": 0.2})["price"]
    np.testing.assert_allclose(evaluate(ir, X, {"sigma": 0.2})["price"], expected)
    np.testing.assert_allclose(compile_reference(ir)(X, {"sigma": 0.2})["price"], expected)
    assert ModelService._default_params({"formula_ir": ir}) == {"sigma": 0.5, "r": 0.05}
    bad = dict(ir, inputs=[dict(i, value=1.0) if i["name"] == "S" else i for i in ir["inputs"]])
    assert any("only a constant carries a value" in e for e in validate_ir(bad))
