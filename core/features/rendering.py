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
               right_of_same: bool = False) -> str:
        text = self._render(node)
        mine = _power(node)
        # Brackets when this node binds LOOSER than its parent — and also when
        # it binds EQUALLY and sits on the right of a non-associative operator,
        # which is where `a - (b - c)` lives.
        if mine < parent_power or (mine == parent_power and right_of_same):
            return self._bracket(text)
        return text

    def _bracket(self, text: str) -> str:
        return f"({text})"

    def _render(self, node: ast.AST) -> str:
        raise NotImplementedError

    # -- shared walk ------------------------------------------------------
    def _children_of_binop(self, node: ast.BinOp):
        power = _power(node)
        left = self.render(node.left, power)
        # `-`, `/`, `%`, `//` and `**` are not associative, so the right-hand
        # side of an equal-precedence operator needs its brackets kept.
        non_associative = isinstance(node.op, (ast.Sub, ast.Div, ast.Mod,
                                               ast.FloorDiv, ast.Pow))
        right = self.render(node.right, power, right_of_same=non_associative)
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
                base = self.render(node.left, _ATOM)
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
            parts = [self.render(node.left, power)]
            for op, right in zip(node.ops, node.comparators):
                parts.append(_LATEX_COMPARE[type(op)])
                parts.append(self.render(right, power))
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
            return _number(node.value)
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
            parts = [self.render(node.left, power)]
            for op, right in zip(node.ops, node.comparators):
                parts.append(_PY_COMPARE[type(op)])
                parts.append(self.render(right, power))
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
non-positive value should not stop a batch.
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
    args = ", ".join(sorted(inputs or _names(source)))
    return (_PREAMBLE + f"\n\ndef {name}({args}):\n"
            f"    return {body}\n")


def _parse(source: str) -> ast.Expression:
    from core.features.expressions import Expression

    return Expression(source).tree


def _names(source: str) -> List[str]:
    from core.features.expressions import Expression

    return Expression(source).feature_names()


def _number(value: Any) -> str:
    """A constant, without Python's float noise. `0.1 + 0.2` is not what a
    reader wants to see beside a coefficient."""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return repr(value)
