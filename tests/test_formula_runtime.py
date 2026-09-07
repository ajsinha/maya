"""The runtime where the JSON is the model, and the two renderings of it.

Every other runtime names something else — a graph, an image, a script — and
MAYA governs the naming. This one does not: `entry.expression` is the whole of
`f`, in the language the platform already parses for derived features, with no
artifact to locate and no engine to ask.

The gap it closes is the taxonomy's. A scorecard, a logistic link, a
loss-given-default haircut, a Basel risk weight — the hundreds of small
closed-form models a bank runs — had to be registered `descriptor_only`
(governed and unrunnable) or wrapped in a container, which turns four lines of
arithmetic into an artifact somebody has to build, sign and store.
"""
from __future__ import annotations

import math
import random

import pytest

from core.execution.errors import WarrantError
from core.execution.runtimes import FormulaRuntime
from core.execution.runtimes.base import Invocation

LOGISTIC = "1 / (1 + exp(-(intercept + beta * dscr)))"


def _call(expression=LOGISTIC, features=None, values=None, target="pd_12m"):
    return Invocation(
        warrant={"operation": {"entry": {"expression": expression,
                                         "target": target}}},
        inputs={"features": features if features is not None else {"dscr": 1.4},
                "parameters": {"values": values} if values is not None else {}})


class TestTheExpressionIsTheModel:

    def test_it_evaluates_against_features_and_parameters(self):
        out = FormulaRuntime().invoke(
            _call(values={"intercept": -1.2, "beta": 0.8}))
        assert out["family"] == "formula" and out["target"] == "pd_12m"
        assert math.isclose(out["prediction"],
                            1 / (1 + math.exp(-(-1.2 + 0.8 * 1.4))))

    def test_a_caller_may_not_supply_a_coefficient(self):
        """A caller who can set a coefficient is choosing the model, while the
        warrant still says it ran at its approved point of `P`."""
        with pytest.raises(WarrantError) as refusal:
            FormulaRuntime().invoke(
                _call(features={"dscr": 1.4, "beta": 99.0},
                      values={"intercept": -1.2, "beta": 0.8}))
        assert refusal.value.code == "parameter_overridden"
        assert "beta" in str(refusal.value)

    def test_a_missing_input_is_named(self):
        with pytest.raises(WarrantError) as refusal:
            FormulaRuntime().invoke(_call(features={},
                                          values={"intercept": -1.2, "beta": 0.8}))
        assert refusal.value.code == "missing_inputs" and "dscr" in str(refusal.value)

    def test_a_warrant_with_no_expression_is_refused(self):
        with pytest.raises(WarrantError) as refusal:
            FormulaRuntime().invoke(_call(expression=""))
        assert refusal.value.code == "no_expression"

    def test_it_has_no_dependency_to_be_missing(self):
        """Which is most of the argument for a runtime like this one."""
        assert FormulaRuntime().available() is None

    def test_the_grammar_names_it_and_says_what_it_needs(self):
        from core.execution.grammar.vocabulary import RUNTIME_ENTRY

        assert RUNTIME_ENTRY["formula"] == ("expression",)


class TestTheTwoRenderingsAgree:
    """Both come from the same syntax tree, which is the whole design: two
    descriptions of one model drift, and the one nobody executes drifts first.
    """

    CASES = [
        ("exp(-(a + b))", ["a", "b"]),
        ("a - (b - c)", ["a", "b", "c"]),
        ("a / (b + c)", ["a", "b", "c"]),
        ("(a + b) / (a - b)", ["a", "b"]),
        (LOGISTIC, ["intercept", "beta", "dscr"]),
        ("log(x) + sqrt(y)", ["x", "y"]),
        ("a ** 2 - 2 * a * b + b ** 2", ["a", "b"]),
        ("floor(a / b) * b", ["a", "b"]),
        ("x if y > 0 else -x", ["x", "y"]),
        ("min(a, b) + max(a, b)", ["a", "b"]),
    ]

    @pytest.mark.parametrize("source,names", CASES)
    def test_the_generated_python_computes_what_maya_computes(self, source, names):
        from core.features.expressions import Expression
        from core.features.rendering import to_python

        module: dict = {}
        # Executing the generated module is the only way to test that it
        # computes what MAYA computes, which is the claim being made. The
        # source is generated from an expression this file wrote, three lines
        # up, and nothing external reaches it.
        exec(compile(to_python(source, inputs=names), "<generated>", "exec"),  # noqa: S102
             module)
        expression = Expression(source)
        rng = random.Random(source)
        for _ in range(50):
            row = {n: round(rng.uniform(0.5, 4.0), 4) for n in names}
            mine, theirs = expression.evaluate(row), module["predict"](**row)
            if mine is None or theirs is None:
                assert mine is None and theirs is None, row
            else:
                assert math.isclose(mine, theirs, rel_tol=1e-12), row

    def test_the_bracket_that_broke_the_first_attempt(self):
        """`exp(-(a + b))` rendered as `e^{-a + b}` — a different function,
        typeset confidently, in the document a supervisor reads. Python's AST
        does not carry the author's brackets, so they are re-derived from
        precedence, and this is the case that proves it."""
        from core.features.rendering import to_latex

        assert to_latex("exp(-(a + b))") == \
            r"e^{-\left(\mathrm{a} + \mathrm{b}\right)}"
        assert to_latex("exp(-a + b)") == \
            r"e^{-\mathrm{a} + \mathrm{b}}"

    def test_subtraction_keeps_its_right_hand_brackets(self):
        from core.features.rendering import to_latex

        assert to_latex("a - (b - c)") == \
            r"\mathrm{a} - \left(\mathrm{b} - \mathrm{c}\right)"
        assert to_latex("a - b - c") == \
            r"\mathrm{a} - \mathrm{b} - \mathrm{c}"

    def test_a_division_becomes_a_fraction_and_needs_no_brackets(self):
        from core.features.rendering import to_latex

        assert to_latex("a / (b + c)") == \
            r"\frac{\mathrm{a}}{\mathrm{b} + \mathrm{c}}"

    def test_a_name_may_be_given_its_own_symbol(self):
        from core.features.rendering import to_latex

        assert to_latex("sigma * 2", symbols={"sigma": r"\sigma"}) == \
            r"\sigma \cdot 2"

    def test_an_unmapped_name_is_upright_rather_than_a_product(self):
        """`debt_service` in italics is nine letters multiplied together."""
        from core.features.rendering import to_latex

        assert r"\mathrm{debt\_service}" in to_latex("debt_service + 1")

    def test_the_generated_module_imports_and_is_not_a_fragment(self):
        from core.features.rendering import to_python

        source = to_python(LOGISTIC, inputs=["intercept", "beta", "dscr"])
        assert source.startswith('"""Generated by MAYA')
        assert "import math" in source
        assert "def predict(beta, dscr, intercept):" in source
