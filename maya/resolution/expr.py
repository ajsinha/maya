"""
The restricted expression language (§5.4, §17.3).

One grammar, used everywhere an expression appears: feature transforms,
feature set filters, ACL row filters and workflow check conditions. It is a
strict subset of Python expression syntax, parsed with ``ast`` and then
walked against a whitelist — anything not on the list (attribute access,
subscripts, lambdas, comprehensions, unlisted calls) is refused with the
construct named. Membership is written ``x in [a, b]`` — a list, never a tuple,
so there is one spelling to learn, to document and to teach the editor.
Evaluation is vectorized over a pandas frame and has no side
effects: there is no ``eval`` anywhere in this module.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import ast
import operator
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd

from maya.core.errors import ValidationFailed

_BINOPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}

_CMPOPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def _where(cond: Any, a: Any, b: Any) -> Any:
    return np.where(np.asarray(cond, dtype=bool), a, b)


def _dt(part: str) -> Callable[[Any], Any]:
    def call(x: Any) -> Any:
        return getattr(pd.Series(x).dt, part).to_numpy()

    return call


FUNCTIONS: dict[str, tuple[Callable[..., Any], int, int]] = {
    "abs": (np.abs, 1, 1),
    "sqrt": (np.sqrt, 1, 1),
    "log": (np.log, 1, 1),
    "exp": (np.exp, 1, 1),
    "min": (lambda *a: np.minimum.reduce(np.broadcast_arrays(*a)), 2, 8),
    "max": (lambda *a: np.maximum.reduce(np.broadcast_arrays(*a)), 2, 8),
    "where": (_where, 3, 3),
    "isnull": (lambda x: pd.isna(pd.Series(x)).to_numpy(), 1, 1),
    "notnull": (lambda x: pd.notna(pd.Series(x)).to_numpy(), 1, 1),
    "round": (lambda x, n=0: np.round(x, int(n)), 1, 2),
    "clip": (lambda x, lo, hi: np.clip(x, lo, hi), 3, 3),
    "year": (_dt("year"), 1, 1),
    "month": (_dt("month"), 1, 1),
    "day": (_dt("day"), 1, 1),
}


def _refuse(node: ast.AST, why: str = "") -> None:
    name = type(node).__name__
    raise ValidationFailed(
        f"expression construct '{name}' is not permitted{': ' + why if why else ''}",
        construct=name,
    )


class _Checker(ast.NodeVisitor):
    """Walks a parsed expression, refusing anything off the whitelist."""

    def __init__(self) -> None:
        self.refs: set[str] = set()

    def generic_visit(self, node: ast.AST) -> None:
        _refuse(node)

    def visit_Expression(self, node: ast.Expression) -> None:
        self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, (int, float, str, bool)) and node.value is not None:
            _refuse(node, "only numbers, strings, booleans and None")

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("__"):
            _refuse(node, f"dunder name '{node.id}'")
        if node.id not in {"True", "False", "None"}:
            self.refs.add(node.id)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if type(node.op) not in _BINOPS:
            _refuse(node.op)
        self.visit(node.left)
        self.visit(node.right)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        if not isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)):
            _refuse(node.op)
        self.visit(node.operand)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        for v in node.values:
            self.visit(v)

    def visit_Compare(self, node: ast.Compare) -> None:
        self.visit(node.left)
        for op, comp in zip(node.ops, node.comparators):
            if isinstance(op, (ast.In, ast.NotIn)):
                # One spelling, not two. A tuple used to pass here while ``(1)`` — the
                # same thing to anybody reading it, but a plain constant to the parser —
                # was refused, so the language accepted a form nothing documented and
                # refused the form a user would write next. A list is the documented one.
                if not isinstance(comp, ast.List):
                    _refuse(comp, "'in' needs a literal list, written [a, b]")
                for elt in comp.elts:
                    if not isinstance(elt, ast.Constant):
                        _refuse(elt, "'in' list must hold literals")
            elif type(op) not in _CMPOPS:
                _refuse(op)
            else:
                self.visit(comp)

    def visit_Call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Name):
            _refuse(node.func, "only whitelisted function names may be called")
        name = node.func.id
        if name not in FUNCTIONS:
            raise ValidationFailed(
                f"function '{name}' is not permitted", construct="Call", allowed=sorted(FUNCTIONS)
            )
        if node.keywords:
            _refuse(node.keywords[0], "keyword arguments")
        _, lo, hi = FUNCTIONS[name]
        if not lo <= len(node.args) <= hi:
            raise ValidationFailed(f"function '{name}' takes {lo}..{hi} arguments")
        for a in node.args:
            self.visit(a)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.visit(node.test)
        self.visit(node.body)
        self.visit(node.orelse)


@dataclass
class Expr:
    """A compiled, validated expression."""

    text: str
    tree: ast.Expression
    refs: set[str] = field(default_factory=set)

    def canonical(self) -> str:
        """Normalized text: whitespace and redundant parentheses do not matter."""
        return ast.unparse(self.tree.body)

    def evaluate(self, df: pd.DataFrame) -> pd.Series:
        """Evaluate vectorized over ``df``; the result is aligned to ``df.index``."""
        missing = sorted(r for r in self.refs if r not in df.columns)
        if missing:
            raise ValidationFailed(
                f"expression refers to unknown attribute(s) {missing}",
                missing=missing,
                expr=self.text,
            )
        value = _eval(self.tree.body, df)
        if np.ndim(value) == 0:
            return pd.Series([value] * len(df), index=df.index)
        return pd.Series(
            np.asarray(value) if not isinstance(value, pd.Series) else value.to_numpy(),
            index=df.index,
        )


def _col(df: pd.DataFrame, name: str) -> Any:
    s = df[name]
    if pd.api.types.is_extension_array_dtype(s.dtype) and pd.api.types.is_numeric_dtype(s.dtype):
        return s.astype("float64").to_numpy()
    return s.to_numpy()


def _eval(node: ast.AST, df: pd.DataFrame) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in {"True", "False", "None"}:
            return {"True": True, "False": False, "None": None}[node.id]
        return _col(df, node.id)
    if isinstance(node, ast.BinOp):
        return _binop(node, _eval(node.left, df), _eval(node.right, df))
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, df)
        if isinstance(node.op, ast.Not):
            return np.logical_not(np.asarray(v, dtype=bool))
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BoolOp):
        vals = [np.asarray(_eval(v, df), dtype=bool) for v in node.values]
        fn = np.logical_and if isinstance(node.op, ast.And) else np.logical_or
        return fn.reduce(np.broadcast_arrays(*vals))
    if isinstance(node, ast.Compare):
        return _eval_compare(node, df)
    if isinstance(node, ast.Call):
        fn = FUNCTIONS[node.func.id][0]  # type: ignore[attr-defined]
        return fn(*[_eval(a, df) for a in node.args])
    if isinstance(node, ast.IfExp):
        return _where(_eval(node.test, df), _eval(node.body, df), _eval(node.orelse, df))
    _refuse(node)
    return None


def _is_text(value: Any) -> bool:
    """A string, or a column holding strings (numpy keeps those as object or U/S arrays)."""
    if isinstance(value, str):
        return True
    if isinstance(value, np.ndarray):
        if value.dtype.kind in "US":
            return True
        return value.dtype.kind == "O" and any(isinstance(v, str) for v in value.ravel())
    return False


def _binop(node: ast.BinOp, left: Any, right: Any) -> Any:
    """Arithmetic that cannot be made to run away: ``**`` is computed in floating point
    (``10**10**10`` is inf, not a billion-digit integer), and text takes part only in
    concatenation (``'a' * 10**9`` and ``'%999999999d' % 1`` would allocate gigabytes)."""
    if not isinstance(node.op, ast.Add) and (_is_text(left) or _is_text(right)):
        raise ValidationFailed(
            "text may only be joined with '+' in an expression", construct=type(node.op).__name__
        )
    if isinstance(node.op, ast.Pow):
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            return np.power(np.asarray(left, dtype="float64"), np.asarray(right, dtype="float64"))
    return _BINOPS[type(node.op)](left, right)


def _eval_compare(node: ast.Compare, df: pd.DataFrame) -> Any:
    left = _eval(node.left, df)
    result: Any = True
    for op, comp in zip(node.ops, node.comparators):
        if isinstance(op, (ast.In, ast.NotIn)):
            values = [e.value for e in comp.elts]  # type: ignore[attr-defined]
            hit = pd.Series(left).isin(values).to_numpy()
            part = hit if isinstance(op, ast.In) else ~hit
            right = left
        else:
            right = _eval(comp, df)
            part = _CMPOPS[type(op)](left, right)
        result = np.logical_and(result, np.asarray(part, dtype=bool))
        left = right
    return result


def compile_expr(text: str) -> Expr:
    """Parse and validate an expression. Raises ValidationFailed naming the construct."""
    if not isinstance(text, str) or not text.strip():
        raise ValidationFailed("expression is empty")
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValidationFailed(f"expression does not parse: {exc.msg}", expr=text) from exc
    checker = _Checker()
    checker.visit(tree)
    return Expr(text=text, tree=tree, refs=checker.refs)
