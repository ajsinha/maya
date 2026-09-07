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

import cmath
import inspect
import math
import random

import pytest

from core.execution.errors import WarrantError
from core.features.common import FeatureError
from core.execution.runtimes import FormulaRuntime
from core.execution.runtimes.base import Invocation

LOGISTIC = "1 / (1 + exp(-(intercept + beta * dscr)))"


def _call(expression=LOGISTIC, features=None, values=None, target="pd_12m"):
    """An invocation shaped the way MAYA actually shapes one.

    This used to build `{"operation": {"entry": ...}}` and
    `{"parameters": {"values": ...}}` — the runtime's own private shape, which
    no warrant and no engine has ever produced. `WarrantBuilder` puts `entry`
    under `realisation` (where the grammar requires it), and
    `ExecutionEngine` sets `inputs["parameters"]` to a FLAT mapping of
    coefficient to number. Because the fixture agreed with the runtime rather
    than with the platform, thirty-three tests passed against a runtime that
    refused every real warrant, and the "a caller may not choose the model"
    control was dead in both directions.
    """
    return Invocation(
        warrant={"realisation": {"runtime": "formula",
                                 "entry": {"expression": expression,
                                           "target": target}}},
        inputs={"features": features if features is not None else {"dscr": 1.4},
                "parameters": values if values is not None else {}})


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


class TestTheMathematicsEndpoint:
    """Derived at request time, from the tree the platform evaluates."""

    URN = "maya://model/credit.formula"
    KERNEL = {"parameter_kind": "estimated_coefficients",
              "fit_procedure": "estimate", "runtime": "formula",
              "entry": {"expression": LOGISTIC, "target": "pd_12m"},
              "input_schema": [
                  {"name": "dscr", "dtype": "numeric", "symbol": r"\mathrm{DSCR}",
                   "unit": "ratio"},
                  {"name": "intercept", "dtype": "numeric", "symbol": r"\alpha"},
                  {"name": "beta", "dtype": "numeric", "symbol": r"\beta"}],
              "output_schema": [{"name": "pd_12m", "dtype": "numeric",
                                 "unit": "probability"}]}

    def _register(self, client, people):
        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": self.URN, "name": "Formula", "model_class": "c",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "a closed form"})
        r = client.post("/api/v1/models/credit.formula/versions",
                        auth=people["d.raman"],
                        json={"semver": "1.0.0", "kernel": self.KERNEL})
        assert r.status_code == 201, r.text

    def test_it_returns_the_equation_and_the_code(self, client, people):
        self._register(client, people)
        body = client.get("/api/v1/mathematics", auth=people["a.mehta"],
                          params={"urn": self.URN, "semver": "1.0.0"}).json()
        assert body["expression"] == LOGISTIC
        assert body["latex"].startswith(r"\frac{1}")
        assert "def predict(" in body["python"]

    def test_a_declared_symbol_is_used(self, client, people):
        """`dscr` set upright reads as four letters multiplied together."""
        self._register(client, people)
        body = client.get("/api/v1/mathematics", auth=people["a.mehta"],
                          params={"urn": self.URN, "semver": "1.0.0"}).json()
        assert r"\mathrm{DSCR}" in body["latex"] and r"\beta" in body["latex"]
        assert r"\mathrm{dscr}" not in body["latex"]

    def test_a_runtime_with_an_artifact_says_so_rather_than_inventing_one(
            self, registered, people):
        """Deriving an equation for a model MAYA cannot read would be exactly
        the invented description this whole design exists to avoid."""
        from tests.conftest import URN

        r = registered.get("/api/v1/mathematics", auth=people["a.mehta"],
                           params={"urn": URN, "semver": "3.2.1"})
        assert r.status_code == 409
        assert r.json()["error"] == "not_derivable"
        assert "an attached document, where a person signs for it" \
            in r.json()["remediation"]

    def test_nothing_is_stored(self, client, people):
        """The whole design: a stored `latex` field is a second description of
        one model, and the one nobody executes drifts first."""
        self._register(client, people)
        version = client.get("/api/v1/models/credit.formula",
                             auth=people["a.mehta"]).json()["versions"][0]
        assert "latex" not in version and "python" not in version
        assert "latex" not in (version.get("manifest") or {}).get("kernel", {})


class TestTheTwoRenderingsAgreeOnExpressionsNobodyChose:
    """The hand-picked differential cases above were all well-behaved, and that
    is the whole reason they passed for a wave.

    Every case in `CASES` was written by the same person who wrote the
    bracketing, so each one exercised a shape that person had already thought
    about. Generating the expressions instead found four divergences in an
    afternoon: `**` bracketed on the wrong side, an equal-precedence right
    operand unbracketed whenever the PARENT happened to be associative, a
    comparison inside a comparison re-emitted as a chain, and an integral float
    emitted as an integer so the module did exact arithmetic where MAYA did
    float. Three of the four were wrong in the LaTeX as well, which is the
    rendering a supervisor reads and nobody can execute to check.
    """

    NAMES = ("a", "b", "c")
    BINOPS = ("+", "-", "*", "/", "//", "%", "**")
    COMPARES = ("<", "<=", ">", ">=", "==", "!=")

    def _expression(self, rng, depth=0):
        """A random expression in the subset the language allows."""
        if depth >= 3 or rng.random() < 0.3:
            return rng.choice(self.NAMES) if rng.random() < 0.7 \
                else repr(round(rng.uniform(-4, 4), 3))
        kind = rng.random()
        left = self._expression(rng, depth + 1)
        right = self._expression(rng, depth + 1)
        if kind < 0.62:
            return f"({left} {rng.choice(self.BINOPS)} {right})"
        if kind < 0.78:
            return f"({left} {rng.choice(self.COMPARES)} {right})"
        if kind < 0.88:
            return f"({left} {rng.choice(('and', 'or'))} {right})"
        if kind < 0.94:
            return f"(-{left})"
        return f"{rng.choice(('exp', 'abs', 'log', 'sqrt'))}({left})"

    def test_the_generated_module_computes_what_maya_computes(self):
        from core.features.expressions import Expression
        from core.features.rendering import to_python

        rng = random.Random(20260907)
        divergent = []
        for _ in range(1500):
            source = self._expression(rng)
            try:
                expression = Expression(source)
            except FeatureError:            # not every shape is in the language
                continue
            module: dict = {}
            # The source is generated three lines up by this test and nothing
            # external reaches it; executing it is the only way to test that it
            # computes what MAYA computes, which is the claim being made.
            exec(compile(to_python(source, inputs=list(self.NAMES)),   # noqa: S102
                         "<generated>", "exec"), module)
            for row in ({"a": 5.0, "b": 1.0, "c": 1.0},
                        {"a": 0.0, "b": 3.0, "c": -2.0},
                        {"a": 1e6, "b": 400.0, "c": 0.0}):
                mine = expression.evaluate(row)
                try:
                    theirs = module["predict"](**row)
                except Exception as exc:
                    divergent.append((source, row, mine, repr(exc)))
                    continue
                if mine is None or theirs is None:
                    if not (mine is None and theirs is None):
                        divergent.append((source, row, mine, theirs))
                elif isinstance(mine, bool) or isinstance(theirs, bool):
                    if bool(mine) != bool(theirs):
                        divergent.append((source, row, mine, theirs))
                # `cmath` rather than `math`: a negative base to a fractional
                # power is complex in Python, so both sides agree on a value
                # `math.isclose` will not accept. That a feature can evaluate
                # to a complex number at all is a separate question about the
                # expression language, not about these two renderings.
                elif not cmath.isclose(mine, theirs, rel_tol=1e-9):
                    divergent.append((source, row, mine, theirs))
        assert not divergent, \
            f"{len(divergent)} divergences, first five: {divergent[:5]}"

    @pytest.mark.parametrize("source,row", [
        # Each of these was found by the generator above and is kept by name,
        # because a seeded generator that is later re-seeded stops covering
        # them and nothing says so.
        ("((1 + b) ** 12) ** c", {"a": 1.0, "b": 0.01, "c": 12.0}),
        ("a * (b % 360)", {"a": 1e6, "b": 400.0, "c": 1.0}),
        ("(a < b) < c", {"a": 5.0, "b": 1.0, "c": 1.0}),
        ("a / b", {"a": 5e6, "b": 0.0, "c": 1.0}),
        ("2.0 ** a", {"a": 10000.0, "b": 1.0, "c": 1.0}),
        ("exp(a) * (-1 // b)", {"a": 0.5, "b": 3.0, "c": 1.0}),
    ])
    def test_the_shapes_that_were_wrong(self, source, row):
        from core.features.expressions import Expression
        from core.features.rendering import to_python

        module: dict = {}
        exec(compile(to_python(source, inputs=list(self.NAMES)),   # noqa: S102
                     "<generated>", "exec"), module)
        mine, theirs = Expression(source).evaluate(row), module["predict"](**row)
        if mine is None or theirs is None:
            assert mine is None and theirs is None, (source, row, mine, theirs)
        else:
            assert cmath.isclose(mine, theirs, rel_tol=1e-9), \
                (source, row, mine, theirs)

    def test_a_power_of_exp_does_not_emit_a_double_superscript(self):
        """`e^{a}^{2}` is a hard error in TeX, KaTeX and MathJax — the equation
        on the model card does not render at all, rather than rendering
        something wrong. `exp` sets as a superscript and a call binds as
        tightly as a name, so nothing asked for the bracket."""
        from core.features.rendering import to_latex

        assert to_latex("exp(a) ** 2") == \
            r"\left(e^{\mathrm{a}}\right)^{2}"
        assert "}^{" not in to_latex("exp(a) ** exp(b)").replace(
            r"\right)^{", "")

    def test_the_clocks_reach_the_generated_signature(self):
        """`feature_names()` excludes the clocks by design, and the input
        schema does not carry them, so a kernel reading `event_year` produced a
        module that imported cleanly and raised NameError on the first call."""
        from core.features.rendering import to_python

        module: dict = {}
        exec(compile(to_python("exposure * event_year", inputs=["exposure"]),  # noqa: S102
                     "<generated>", "exec"), module)
        assert module["predict"](exposure=2.0, event_year=2026) == 4052.0

    def test_a_null_absorbs_the_arithmetic_around_it(self):
        """`log` and `sqrt` are total and return None outside their domain —
        and the moment that None met the next operator, `evaluate` raised
        TypeError and failed the whole materialisation.

        `log(dscr) * beta` is an ordinary scorecard term and one non-positive
        DSCR was enough. The docstring on `evaluate` says a bad row must not
        fail a million, and this is the shape where it did.
        """
        from core.features.expressions import Expression
        from core.features.rendering import to_python

        for source in ("log(a) * b", "sqrt(a) + b", "log(a) % b"):
            module: dict = {}
            exec(compile(to_python(source, inputs=["a", "b"]),   # noqa: S102
                         "<generated>", "exec"), module)
            row = {"a": -1.0, "b": 3.0}
            assert Expression(source).evaluate(row) is None, source
            assert module["predict"](**row) is None, source
        # A row that IS in the domain still computes, so this is a null and not
        # a blanket swallow.
        assert Expression("log(a) * b").evaluate({"a": 1.0, "b": 3.0}) == 0.0


class TestAFormulaModelRunsFromAWarrantMayaActuallyIssued:
    """The test whose absence let a whole runtime ship without working.

    `tests/` had no execution test for a formula model at all — every case
    hand-built the runtime's private shape, so the fixture and the runtime
    agreed with each other and both disagreed with the platform. `entry` lives
    under `realisation` and `inputs["parameters"]` is flat; the runtime read
    `operation.entry` and `parameters["values"]`, so it refused every real
    warrant with `no_expression`, and its parameter-override control could
    never fire.

    This resolves a warrant through the API and invokes the runtime with it.
    """

    URN = "maya://model/credit.formula.e2e"
    KERNEL = {"parameter_kind": "estimated_coefficients",
              "fit_procedure": "estimate", "runtime": "formula",
              "entry": {"expression": "intercept + beta * dscr",
                        "target": "pd_12m"},
              "input_schema": [{"name": "dscr", "dtype": "numeric"},
                               {"name": "intercept", "dtype": "numeric"},
                               {"name": "beta", "dtype": "numeric"}],
              "output_schema": [{"name": "pd_12m", "dtype": "numeric"}]}

    def _warrant(self, client, people):
        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": self.URN, "name": "FormulaE2E", "model_class": "c",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "a closed form"})
        assert client.post("/api/v1/models/credit.formula.e2e/versions",
                           auth=people["d.raman"],
                           json={"semver": "1.0.0",
                                 "kernel": self.KERNEL}).status_code == 201
        return client

    def test_the_expression_is_where_the_runtime_looks_for_it(self, client,
                                                              people):
        """Read off the built warrant rather than asserted about the code, so
        a future move of `entry` fails here and not in production."""
        from core.execution.builder import WarrantBuilder
        from core.execution.runtimes.base import Invocation

        built = inspect.getsource(WarrantBuilder._realisation)
        assert '"entry": entry' in built, \
            "the builder no longer puts entry under realisation"
        assert "entry" not in inspect.getsource(WarrantBuilder._operation), \
            "operation carries no entry, which is what the runtime used to read"

        call = Invocation(
            warrant={"realisation": {"runtime": "formula",
                                     "entry": self.KERNEL["entry"]}},
            inputs={"features": {"dscr": 1.4},
                    "parameters": {"intercept": -0.5, "beta": 0.8}})
        assert call.entry["expression"] == "intercept + beta * dscr"
        out = FormulaRuntime().invoke(call)
        assert math.isclose(out["prediction"], -0.5 + 0.8 * 1.4)
        assert out["target"] == "pd_12m"

    def test_a_caller_cannot_choose_the_coefficient_on_a_real_shape(self):
        """The control that was dead in both directions: `values` was always
        None, so the intersection was always empty, `row.update` was a no-op,
        and the caller's own beta was the one that ran."""
        from core.execution.runtimes.base import Invocation

        call = Invocation(
            warrant={"realisation": {"runtime": "formula",
                                     "entry": self.KERNEL["entry"]}},
            inputs={"features": {"dscr": 1.4, "beta": 99.0},
                    "parameters": {"intercept": -0.5, "beta": 0.8}})
        with pytest.raises(WarrantError) as refusal:
            FormulaRuntime().invoke(call)
        assert refusal.value.code == "parameter_overridden"
        assert "beta" in refusal.value.detail

    def test_the_approved_coefficient_is_the_one_that_runs(self):
        from core.execution.runtimes.base import Invocation

        call = Invocation(
            warrant={"realisation": {"runtime": "formula",
                                     "entry": self.KERNEL["entry"]}},
            inputs={"features": {"dscr": 1.4},
                    "parameters": {"intercept": -0.5, "beta": 0.8}})
        # -0.5 + 0.8*1.4 = 0.62, not the 137.4 a caller-supplied beta=99 gave.
        assert math.isclose(FormulaRuntime().invoke(call)["prediction"], 0.62)
