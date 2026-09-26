"""
Lift a formula IR from a Python function (§28.6).

Accepts a function whose body is assignments followed by a ``return`` of an
arithmetic expression, with ``math``/``numpy``/``scipy.stats.norm`` calls
mapped onto IR operators. Anything else — loops, branches, attribute access,
calls it does not know — is refused with the line named rather than
approximated.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import ast
from typing import Any

from maya.core.errors import ValidationFailed

_BINOPS = {ast.Add: "add", ast.Sub: "sub", ast.Mult: "mul", ast.Div: "div", ast.Pow: "pow"}
_CMPS = {ast.Gt: "gt", ast.Lt: "lt", ast.GtE: "ge", ast.LtE: "le", ast.Eq: "eq"}
_CALLS = {
    "exp": "exp",
    "log": "log",
    "sqrt": "sqrt",
    "abs": "abs",
    "fabs": "abs",
    "maximum": "max",
    "minimum": "min",
    "max": "max",
    "min": "min",
    "where": "where",
    "cdf": "ncdf",
    "ncdf": "ncdf",
    "norm_cdf": "ncdf",
    "ppf": "ncdfinv",
    "norm_ppf": "ncdfinv",
    "ncdfinv": "ncdfinv",
    "pdf": "npdf",
    "npdf": "npdf",
}


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    raise ValidationFailed(f"line {func.lineno}: unsupported call target")


class _Lifter:
    def __init__(self, params: set[str]) -> None:
        self.params = params

    def expr(self, node: ast.expr) -> dict[str, Any]:
        method = getattr(self, "_" + type(node).__name__, None)
        if method is None:
            raise ValidationFailed(
                f"line {node.lineno}: cannot lift {type(node).__name__} into the IR",
                line=node.lineno,
            )
        return method(node)

    def _Constant(self, node: ast.Constant) -> dict[str, Any]:
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValidationFailed(f"line {node.lineno}: only numeric constants are allowed")
        return {"const": node.value}

    def _Name(self, node: ast.Name) -> dict[str, Any]:
        return {"ref": node.id}

    def _Subscript(self, node: ast.Subscript) -> dict[str, Any]:
        # X["S"] / params["sigma"]
        if (
            isinstance(node.value, ast.Name)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            if node.value.id in ("params", "theta", "p"):
                self.params.add(node.slice.value)
            return {"ref": node.slice.value}
        raise ValidationFailed(
            f"line {node.lineno}: only X['name'] / params['name'] subscripts lift"
        )

    def _BinOp(self, node: ast.BinOp) -> dict[str, Any]:
        op = _BINOPS.get(type(node.op))
        if op is None:
            raise ValidationFailed(
                f"line {node.lineno}: operator {type(node.op).__name__} not supported"
            )
        return {"op": op, "args": [self.expr(node.left), self.expr(node.right)]}

    def _UnaryOp(self, node: ast.UnaryOp) -> dict[str, Any]:
        if isinstance(node.op, ast.USub):
            inner = self.expr(node.operand)
            return (
                {"const": -inner["const"]} if "const" in inner else {"op": "neg", "args": [inner]}
            )
        if isinstance(node.op, ast.UAdd):
            return self.expr(node.operand)
        raise ValidationFailed(f"line {node.lineno}: unary {type(node.op).__name__} not supported")

    def _Compare(self, node: ast.Compare) -> dict[str, Any]:
        if len(node.ops) != 1 or type(node.ops[0]) not in _CMPS:
            raise ValidationFailed(f"line {node.lineno}: only single comparisons lift")
        return {
            "op": _CMPS[type(node.ops[0])],
            "args": [self.expr(node.left), self.expr(node.comparators[0])],
        }

    def _Call(self, node: ast.Call) -> dict[str, Any]:
        name = _call_name(node.func)
        if name not in _CALLS or node.keywords:
            raise ValidationFailed(
                f"line {node.lineno}: call to '{name}' cannot be lifted", call=name
            )
        return {"op": _CALLS[name], "args": [self.expr(a) for a in node.args]}

    def _Attribute(self, node: ast.Attribute) -> dict[str, Any]:
        if (
            isinstance(node.value, ast.Name)
            and node.value.id in ("math", "np", "numpy")
            and node.attr in ("pi", "e")
        ):
            import math

            return {"const": getattr(math, node.attr)}
        raise ValidationFailed(
            f"line {node.lineno}: attribute access '{node.attr}' cannot be lifted"
        )


def _find_function(tree: ast.Module, name: str | None) -> ast.FunctionDef:
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    if name:
        funcs = [f for f in funcs if f.name == name]
    if not funcs:
        raise ValidationFailed(f"no function {name or ''} found to lift".replace("  ", " "))
    return funcs[0]


def lift_python(source: str, function_name: str | None = None) -> dict[str, Any]:
    """Lift an IR from a simple Python function; refuses anything else by line."""
    from maya.formula.ir import refs_of, validate_ir
    from maya.formula.latex import to_latex

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValidationFailed(f"syntax error on line {exc.lineno}: {exc.msg}") from exc
    fn = _find_function(tree, function_name)
    params: set[str] = set()
    lifter = _Lifter(params)
    lets: dict[str, Any] = {}
    body: dict[str, Any] | None = None
    stmts = [
        s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
    ]
    for stmt in stmts:
        if body is not None:
            raise ValidationFailed(f"line {stmt.lineno}: statements after return cannot be lifted")
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
        ):
            lets[stmt.targets[0].id] = lifter.expr(stmt.value)
        elif isinstance(stmt, ast.Return) and stmt.value is not None:
            body = lifter.expr(stmt.value)
        else:
            raise ValidationFailed(
                f"line {stmt.lineno}: {type(stmt).__name__} cannot be lifted into the IR",
                line=stmt.lineno,
            )
    if body is None:
        raise ValidationFailed(f"function '{fn.name}' has no return expression")
    arg_names = [a.arg for a in fn.args.args]
    free: set[str] = refs_of(body)
    for node in lets.values():
        free |= refs_of(node)
    free -= set(lets)
    free -= {"X", "params"}
    inputs = [
        {"name": n, "type": "float64", "role": "parameter" if n in params else "feature"}
        for n in sorted(free)
    ]
    ir: dict[str, Any] = {
        "outputs": [{"name": "y", "type": "float64"}],
        "inputs": inputs,
        "lets": lets,
        "body": body,
        "lifted_from": {"function": fn.name, "args": arg_names},
    }
    errors = validate_ir(ir)
    if errors:
        raise ValidationFailed("lifted IR is invalid", errors=errors)
    ir["latex"] = to_latex(ir)
    return ir
