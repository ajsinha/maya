"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

One expression, rendered as mathematics and as code.

**Both come from the same syntax tree, and that is the whole design.** The
alternative — a `latex` field beside the expression, filled in by whoever wrote
it — was refused by every reviewer who looked at it, for one reason: two
descriptions of one model drift, and the one nobody executes is the one that
drifts. A stored LaTeX string is a claim about the model. A derived one is the
model, typeset.

The same argument makes the Python emitter worth having. A validator who wants
to recompute a kernel independently needs code, and code somebody transcribed
from the equation is a third description. This one is generated from the tree
the platform actually evaluates, so a disagreement between the equation, the
code and the answer is not possible rather than merely unlikely.

**Precedence is the whole difficulty**, and it is worth stating why. A first
attempt at this rendered `exp(-(a + b))` as ``e^{-a + b}`` — a different
function, printed confidently, in the document a supervisor reads. Python's AST
does not carry the author's brackets, so brackets have to be *re-derived* from
the precedence of each node against its parent. Nothing here is emitted without
asking that question.
"""
from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional

from core.features.common import FeatureError

#: Binding power, higher binds tighter. The numbers are Python's own precedence
#: order; only their relative order matters.
_PRECEDENCE: Dict[type, int] = {
    ast.Or: 1, ast.And: 2, ast.Not: 3,
    ast.Eq: 4, ast.NotEq: 4, ast.Lt: 4, ast.LtE: 4, ast.Gt: 4, ast.GtE: 4,
    ast.Add: 6, ast.Sub: 6,
    ast.Mult: 7, ast.Div: 7, ast.FloorDiv: 7, ast.Mod: 7,
    ast.UAdd: 8, ast.USub: 8,
    ast.Pow: 9,
}
_ATOM = 100          # a name, a number, a call: never needs brackets

_LATEX_BINOP = {ast.Add: "+", ast.Sub: "-", ast.Mult: r"\cdot",
                ast.Mod: r"\bmod"}
_LATEX_COMPARE = {ast.Eq: "=", ast.NotEq: r"\neq", ast.Lt: "<",
                  ast.LtE: r"\leq", ast.Gt: ">", ast.GtE: r"\geq"}
_PY_BINOP = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
             ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**"}
_PY_COMPARE = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=",
               ast.Gt: ">", ast.GtE: ">="}

#: How each function of the expression language is written as mathematics.
#: `\operatorname` for the ones with no symbol, so they do not typeset as a
#: product of their letters.
_LATEX_CALL = {
    "log": lambda a: rf"\ln\left({a[0]}\right)",
    "exp": lambda a: rf"e^{{{a[0]}}}",
    "sqrt": lambda a: rf"\sqrt{{{a[0]}}}",
    "abs": lambda a: rf"\left|{a[0]}\right|",
    "min": lambda a: rf"\min\left({', '.join(a)}\right)",
    "max": lambda a: rf"\max\left({', '.join(a)}\right)",
    "round": lambda a: rf"\operatorname{{round}}\left({a[0]}\right)",
    "floor": lambda a: rf"\left\lfloor {a[0]} \right\rfloor",
    "ceil": lambda a: rf"\left\lceil {a[0]} \right\rceil",
}


def _power(node: ast.AST) -> int:
    """How tightly this node binds, for deciding its children's brackets."""
    if isinstance(node, ast.BinOp):
        return _PRECEDENCE.get(type(node.op), _ATOM)
    if isinstance(node, ast.UnaryOp):
        return _PRECEDENCE.get(type(node.op), _ATOM)
    if isinstance(node, ast.BoolOp):
        return _PRECEDENCE.get(type(node.op), _ATOM)
    if isinstance(node, ast.Compare):
        return _PRECEDENCE.get(type(node.ops[0]), _ATOM)
    if isinstance(node, ast.IfExp):
        return 0
    return _ATOM


class _Renderer:
    """Walks the tree once. Subclasses decide only how to spell each node."""

    def render(self, node: ast.AST, parent_power: int = 0,
               equal_binds_elsewhere: bool = False,
               force: bool = False) -> str:
        text = self._render(node)
        mine = _power(node)
        # Brackets when this node binds LOOSER than its parent, when it binds
        # EQUALLY and the operator groups the other way (`a - (b - c)`), or when
        # the caller knows something the binding powers do not — a comparison
        # inside a comparison, which re-reads as a chain and is a different
        # operator entirely.
        if force or mine < parent_power or (mine == parent_power
                                            and equal_binds_elsewhere):
            return self._bracket(text)
        return text

    def _bracket(self, text: str) -> str:
        return f"({text})"

    def _render(self, node: ast.AST) -> str:
        raise NotImplementedError

    # -- shared walk ------------------------------------------------------
    def _children_of_binop(self, node: ast.BinOp):
        power = _power(node)
        # Which side needs its brackets kept at equal precedence is decided by
        # how the operator GROUPS, not by which operator the parent happens to
        # be. Two mistakes lived here:
        #
        #   `**` groups to the RIGHT, so it is the LEFT child that needs them.
        #   `((1 + r) ** 12) ** years` was emitted as `(1 + r) ** 12 ** years`
        #   -- 1.01 ** 144, a different number, while the LaTeX beside it was
        #   right. The generated module is what a validator recomputes from.
        #
        #   Everything else groups to the LEFT, so the RIGHT child needs them
        #   whenever it binds equally -- and that is a fact about the CHILD, not
        #   the parent. `notional * (days % 360)` came out as
        #   `notional * days % 360`, off by a factor of a million, because the
        #   parent `*` was in nobody's list of non-associative operators.
        #
        # `a * (b / c)` and `a * b / c` also differ in floating point, so the
        # bracket is kept at equal precedence unconditionally rather than for
        # the operators where the difference is exact.
        if isinstance(node.op, ast.Pow):
            left = self.render(node.left, power, equal_binds_elsewhere=True)
            return left, self.render(node.right, power)
        left = self.render(node.left, power)
        right = self.render(node.right, power, equal_binds_elsewhere=True)
        return left, right


class _Latex(_Renderer):
    """The expression as mathematics."""

    def __init__(self, symbols: Optional[Dict[str, str]] = None):
        self.symbols = symbols or {}

    def _bracket(self, text: str) -> str:
        return rf"\left({text}\right)"

    def _name(self, name: str) -> str:
        if name in self.symbols:
            return self.symbols[name]
        # `debt_service` typesets as a product of nine italic letters unless it
        # is told not to. Upright text, with the underscore as a space.
        pretty = name.replace("_", r"\_")
        return rf"\mathrm{{{pretty}}}"

    def _render(self, node: ast.AST) -> str:
        if isinstance(node, ast.Expression):
            return self.render(node.body)
        if isinstance(node, ast.Name):
            return self._name(node.id)
        if isinstance(node, ast.Constant):
            return _number(node.value)
        if isinstance(node, ast.BinOp):
            # Division is a fraction, which brackets its own arguments — so its
            # children are rendered at the lowest power rather than at `/`'s.
            if isinstance(node.op, ast.Div):
                return (rf"\frac{{{self.render(node.left)}}}"
                        rf"{{{self.render(node.right)}}}")
            if isinstance(node.op, ast.Pow):
                # `exp` sets as a superscript itself, and a `Call` binds as
                # tightly as a name, so nothing asked for the bracket that keeps
                # `e^{a}^{2}` -- a double superscript, which does not typeset at
                # all -- from reaching the page.
                base = self.render(node.left, _ATOM,
                                   force=_sets_as_superscript(node.left))
                return rf"{base}^{{{self.render(node.right)}}}"
            if isinstance(node.op, ast.FloorDiv):
                return (rf"\left\lfloor \frac{{{self.render(node.left)}}}"
                        rf"{{{self.render(node.right)}}} \right\rfloor")
            left, right = self._children_of_binop(node)
            return f"{left} {_LATEX_BINOP[type(node.op)]} {right}"
        if isinstance(node, ast.UnaryOp):
            power = _power(node)
            operand = self.render(node.operand, power)
            if isinstance(node.op, ast.USub):
                return f"-{operand}"
            if isinstance(node.op, ast.UAdd):
                return f"+{operand}"
            return rf"\lnot {operand}"
        if isinstance(node, ast.Compare):
            power = _power(node)
            # A comparison operand that is itself a comparison is bracketed
            # whatever the binding powers say. `(a < b) < c` emitted flat is the
            # chain `a < b < c`, which Python evaluates as `a < b and b < c` --
            # a different operator, silently. At a=5, b=1, c=1 the two disagree.
            parts = [self.render(node.left, power,
                                 force=isinstance(node.left, ast.Compare))]
            for op, right in zip(node.ops, node.comparators):
                parts.append(_LATEX_COMPARE[type(op)])
                parts.append(self.render(right, power,
                                         force=isinstance(right, ast.Compare)))
            return " ".join(parts)
        if isinstance(node, ast.BoolOp):
            power = _power(node)
            joiner = r"\land" if isinstance(node.op, ast.And) else r"\lor"
            return f" {joiner} ".join(self.render(v, power)
                                      for v in node.values)
        if isinstance(node, ast.IfExp):
            # A conditional is a cases environment, which is how anybody would
            # write it by hand and is unambiguous without brackets.
            return (r"\begin{cases}"
                    rf"{self.render(node.body)} & \text{{if }} "
                    rf"{self.render(node.test)} \\ "
                    rf"{self.render(node.orelse)} & \text{{otherwise}}"
                    r"\end{cases}")
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else ""
            args = [self.render(a) for a in node.args]
            if name not in _LATEX_CALL:
                raise FeatureError(f"'{name}' has no mathematical rendering")
            return _LATEX_CALL[name](args)
        raise FeatureError(f"{type(node).__name__} cannot be rendered")


class _Python(_Renderer):
    """The expression as the body of a function."""

    def _render(self, node: ast.AST) -> str:
        if isinstance(node, ast.Expression):
            return self.render(node.body)
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Constant):
            return _number(node.value, typed=True)
        if isinstance(node, ast.BinOp):
            left, right = self._children_of_binop(node)
            return f"{left} {_PY_BINOP[type(node.op)]} {right}"
        if isinstance(node, ast.UnaryOp):
            operand = self.render(node.operand, _power(node))
            if isinstance(node.op, ast.USub):
                return f"-{operand}"
            if isinstance(node.op, ast.UAdd):
                return f"+{operand}"
            return f"not {operand}"
        if isinstance(node, ast.Compare):
            power = _power(node)
            # A comparison operand that is itself a comparison is bracketed
            # whatever the binding powers say. `(a < b) < c` emitted flat is the
            # chain `a < b < c`, which Python evaluates as `a < b and b < c` --
            # a different operator, silently. At a=5, b=1, c=1 the two disagree.
            parts = [self.render(node.left, power,
                                 force=isinstance(node.left, ast.Compare))]
            for op, right in zip(node.ops, node.comparators):
                parts.append(_PY_COMPARE[type(op)])
                parts.append(self.render(right, power,
                                         force=isinstance(right, ast.Compare)))
            return " ".join(parts)
        if isinstance(node, ast.BoolOp):
            power = _power(node)
            joiner = "and" if isinstance(node.op, ast.And) else "or"
            return f" {joiner} ".join(self.render(v, power)
                                      for v in node.values)
        if isinstance(node, ast.IfExp):
            return (f"{self.render(node.body, 1)} if "
                    f"{self.render(node.test, 1)} else "
                    f"{self.render(node.orelse, 1)}")
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else ""
            args = ", ".join(self.render(a) for a in node.args)
            return f"{_PY_NAME.get(name, name)}({args})"
        raise FeatureError(f"{type(node).__name__} cannot be rendered")


#: The expression language's functions, as the Python they compile to. `log` and
#: `sqrt` are MAYA's own total variants — they return None outside their domain
#: rather than raising — so the emitted module carries them rather than
#: importing `math.log` and quietly differing at zero.
_PY_NAME = {"log": "_log", "exp": "_exp", "sqrt": "_sqrt",
            "floor": "_floor", "ceil": "_ceil"}


_PREAMBLE = '''"""Generated by MAYA from a model version's kernel. Do not edit.

Regenerating this from the kernel gives the same file; editing it makes a
fourth description of the model, which is the thing the generation exists to
prevent. The total variants below are MAYA's own: `log` and `sqrt` return None
outside their domain rather than raising, because a training set with one
non-positive value should not stop a batch. The generated function guards its
whole body for the same reason, catching what MAYA catches and no more: a row
this returns None for is a row MAYA returns None for.
"""
import math


def _log(x):
    return math.log(x) if x > 0 else None


def _exp(x):
    return math.exp(x)


def _sqrt(x):
    return math.sqrt(x) if x >= 0 else None


def _floor(x):
    return math.floor(x)


def _ceil(x):
    return math.ceil(x)


'''


def to_latex(source: str, symbols: Optional[Dict[str, str]] = None) -> str:
    """The expression as a LaTeX body, with no delimiters around it.

    `symbols` maps a feature name to how it should be typeset — `dscr` as
    `\\mathrm{DSCR}`, `sigma_t` as `\\sigma_t`. Where a name has none it is set
    upright, because `debt_service` as nine italic letters reads as a product.
    """
    return _Latex(symbols).render(_parse(source))


def to_python(source: str, name: str = "predict",
              inputs: Optional[List[str]] = None) -> str:
    """The expression as a complete, importable module.

    Whole module rather than a fragment on purpose: a validator's recompute
    should be `import kernel; kernel.predict(**row)`, not an exercise in
    assembling somebody's snippet.
    """
    body = _Python().render(_parse(source))
    # `feature_names()` excludes `event_ts`, `ingest_ts` and `event_year` by
    # design -- they are the row's clocks rather than features -- and the input
    # schema a caller passes as `inputs` does not carry them either. They are
    # still free names in the emitted body, so leaving them out produced a
    # module that imported cleanly and raised NameError on the first call.
    args = ", ".join(sorted(set(inputs or _names(source)) | _clocks(source)))
    # The guard catches exactly what `Expression.evaluate` catches, because
    # the claim this module makes is that the two compute the same thing --
    # including where they decline to. Totalising `log` and `sqrt` covered the
    # two easiest of the five ways a row goes undefined; `ebitda /
    # debt_service` with a zero denominator completed a batch in MAYA and
    # raised ZeroDivisionError in the validator's recompute, which is the
    # argument the preamble makes, failing on its own terms.
    return (_PREAMBLE + f"\n\ndef {name}({args}):\n"
            f"    try:\n"
            f"        return {body}\n"
            f"    except (ZeroDivisionError, ValueError, OverflowError,\n"
            f"            TypeError):\n"
            f"        return None\n")


def _parse(source: str) -> ast.Expression:
    from core.features.expressions import Expression

    return Expression(source).tree


def _names(source: str) -> List[str]:
    from core.features.expressions import Expression

    return Expression(source).feature_names()


def _clocks(source: str) -> set:
    from core.features.expressions import BUILTIN_NAMES, Expression

    return set(Expression(source).names & BUILTIN_NAMES)


def _sets_as_superscript(node: ast.AST) -> bool:
    """Whether this node's LaTeX already ends in a superscript group, so a
    power taken of it needs the base bracketed."""
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "exp")


def _number(value: Any, typed: bool = False) -> str:
    """A constant, without Python's float noise. `0.1 + 0.2` is not what a
    reader wants to see beside a coefficient.

    `typed` is set for the Python rendering, where trimming `2.0` to `2` is not
    cosmetic: it moves the expression from float arithmetic to Python's exact
    integers, so `2.0 ** b` overflowed to None in MAYA and returned a 3,011
    digit integer in the generated module. Mathematics has one `2` and does not
    have this problem, so LaTeX keeps the tidier form."""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float) and value.is_integer():
        return repr(value) if typed else str(int(value))
    return repr(value)
