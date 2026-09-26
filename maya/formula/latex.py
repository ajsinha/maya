"""
Render the formula IR as LaTeX (§8.1, §8.5).

The spec document's formula blocks are generated from this, never typed,
so the document cannot drift from the implementation.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re
from typing import Any

from maya.formula.ir import let_order
from maya.formula.parse import GREEK

# binding strength, higher binds tighter
_PREC = {
    "or": 1,
    "and": 2,
    "gt": 3,
    "lt": 3,
    "ge": 3,
    "le": 3,
    "eq": 3,
    "add": 4,
    "sub": 4,
    "mul": 5,
    "div": 6,
    "neg": 7,
    "pow": 8,
}
_CMP = {"gt": ">", "lt": "<", "ge": r"\geq", "le": r"\leq", "eq": "="}


def latex_name(name: str) -> str:
    """``sigma`` -> ``\\sigma``, ``d1`` -> ``d_{1}``, ``base.price`` -> ``\\mathrm{base}.price``."""
    if "." in name:
        alias, rest = name.split(".", 1)
        return rf"\mathrm{{{alias}}}.{latex_name(rest)}"
    m = re.match(r"^([A-Za-z]+?)(\d+)$", name)
    stem, sub = (m.group(1), m.group(2)) if m else (name, "")
    if stem in GREEK:
        stem = "\\" + stem
    elif len(stem) > 1:
        stem = rf"\mathit{{{stem}}}"
    return f"{stem}_{{{sub}}}" if sub else stem


def _const(v: float | int) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return repr(v)


def _wrap(node: dict[str, Any], parent_prec: int, strict: bool = False) -> str:
    text = node_latex(node)
    prec = _PREC.get(node.get("op", ""), 10)
    if "const" in node and node["const"] < 0:
        prec = 7
    if prec < parent_prec or (strict and prec == parent_prec):
        return rf"\left({text}\right)"
    return text


def _mul(args: list[dict[str, Any]]) -> str:
    parts = []
    for i, a in enumerate(args):
        piece = _wrap(a, _PREC["mul"])
        if i and ("const" in a or piece[:1].isdigit() or parts[-1][-1:].isdigit()):
            parts.append(r"\cdot " + piece)
        else:
            parts.append(piece)
    return r"\,".join(parts)


def node_latex(node: dict[str, Any]) -> str:  # noqa: C901 - one case per IR operator
    """LaTeX for one node."""
    if "const" in node:
        return _const(node["const"])
    if "ref" in node:
        return latex_name(node["ref"])
    if "param" in node:
        return latex_name(node["param"])
    if node["op"] == "na":
        return r"\mathrm{N/A}"
    op, args = node["op"], node["args"]
    if op == "add":
        out = node_latex(args[0])
        for a in args[1:]:
            if a.get("op") == "neg":
                out += " - " + _wrap(a["args"][0], _PREC["add"], strict=True)
            else:
                out += " + " + _wrap(a, _PREC["add"])
        return out
    if op == "sub":
        return f"{_wrap(args[0], _PREC['sub'])} - {_wrap(args[1], _PREC['sub'], strict=True)}"
    if op == "mul":
        return _mul(args)
    if op == "div":
        return rf"\frac{{{node_latex(args[0])}}}{{{node_latex(args[1])}}}"
    if op == "neg":
        return "-" + _wrap(args[0], _PREC["neg"])
    if op == "pow":
        return f"{_wrap(args[0], _PREC['pow'], strict=True)}^{{{node_latex(args[1])}}}"
    if op == "exp":
        return f"e^{{{node_latex(args[0])}}}"
    if op == "log":
        return rf"\ln\left({node_latex(args[0])}\right)"
    if op == "sqrt":
        return rf"\sqrt{{{node_latex(args[0])}}}"
    if op == "abs":
        return rf"\left|{node_latex(args[0])}\right|"
    if op == "ncdf":
        return rf"N\left({node_latex(args[0])}\right)"
    if op == "ncdfinv":
        return rf"N^{{-1}}\left({node_latex(args[0])}\right)"
    if op == "npdf":
        return rf"\phi\left({node_latex(args[0])}\right)"
    if op in ("max", "min"):
        return rf"\{op}\left(" + ", ".join(node_latex(a) for a in args) + r"\right)"
    if op == "where":
        c, a, b = (node_latex(x) for x in args)
        return rf"\begin{{cases}} {a} & \text{{if }} {c} \\ {b} & \text{{otherwise}} \end{{cases}}"
    if op in _CMP:
        return f"{_wrap(args[0], 4)} {_CMP[op]} {_wrap(args[1], 4)}"
    if op in ("and", "or"):
        joiner = r" \land " if op == "and" else r" \lor "
        return joiner.join(_wrap(a, _PREC[op]) for a in args)
    raise ValueError(f"no LaTeX rendering for op '{op}'")


def body_latex(ir: dict[str, Any]) -> str:
    """The output equation only."""
    if "black_box" in ir:
        return r"\text{declared black box: " + str(ir["black_box"].get("architecture", "")) + "}"
    if "composite" in ir:
        return node_latex(ir["composite"]["combine"])
    out = ir["outputs"][0]["name"] if ir.get("outputs") else "y"
    return f"{latex_name(out)} = {node_latex(ir['body'])}"


def let_latex(ir: dict[str, Any], name: str) -> str:
    """One let binding as an equation."""
    return f"{latex_name(name)} = {node_latex(ir['lets'][name])}"


def to_latex(ir: dict[str, Any]) -> str:
    """The full model: lets (in dependency order) then the output, as aligned equations."""
    lets = ir.get("lets") or {}
    if not lets or "body" not in ir:
        return body_latex(ir)
    lines = [body_latex(ir).replace(" = ", " &= ", 1)]
    lines += [let_latex(ir, n).replace(" = ", " &= ", 1) for n in let_order(lets)]
    return r"\begin{aligned}" + r" \\ ".join(lines) + r"\end{aligned}"
