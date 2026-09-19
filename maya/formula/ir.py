"""
The formula IR (§8.1): a model's mathematics as a typed expression tree.

JSON is the envelope; the tree is the content. Every other representation —
LaTeX, reference Python, semantic diff, evaluation — is generated from it.

Node forms:
    {"op": <name>, "args": [node, ...]}
    {"ref": name}      an input, a let, or ``alias.output`` inside a composite
    {"const": number}
    {"param": name}    a trained parameter

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterator

# op name -> (min arity, max arity); None max means variadic
OPS: dict[str, tuple[int, int | None]] = {
    "add": (2, None),
    "sub": (2, 2),
    "mul": (2, None),
    "div": (2, 2),
    "pow": (2, 2),
    "neg": (1, 1),
    "exp": (1, 1),
    "log": (1, 1),
    "sqrt": (1, 1),
    "abs": (1, 1),
    "ncdf": (1, 1),
    "npdf": (1, 1),
    "max": (2, None),
    "min": (2, None),
    "where": (3, 3),
    "gt": (2, 2),
    "lt": (2, 2),
    "ge": (2, 2),
    "le": (2, 2),
    "eq": (2, 2),
    "and": (2, None),
    "or": (2, None),
    "na": (0, 0),  # "not available" (Excel's #N/A): evaluates to NaN
}

INPUT_ROLES = ("feature", "parameter", "constant")


def iter_nodes(node: Any) -> Iterator[dict[str, Any]]:
    """Depth-first walk over every node of a tree."""
    if not isinstance(node, dict):
        return
    yield node
    for arg in node.get("args", []) or []:
        yield from iter_nodes(arg)


def refs_of(node: Any) -> set[str]:
    """Names referenced by ``{"ref": ...}`` nodes."""
    return {n["ref"] for n in iter_nodes(node) if "ref" in n}


def params_of(node: Any) -> set[str]:
    """Names referenced by ``{"param": ...}`` nodes."""
    return {n["param"] for n in iter_nodes(node) if "param" in n}


def _node_errors(node: Any, where: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(node, dict):
        return [f"{where}: node must be an object, got {type(node).__name__}"]
    kinds = [k for k in ("op", "ref", "const", "param") if k in node]
    if len(kinds) != 1:
        return [f"{where}: node must have exactly one of op/ref/const/param"]
    kind = kinds[0]
    if kind == "const":
        if not isinstance(node["const"], (int, float)) or isinstance(node["const"], bool):
            errors.append(f"{where}: const must be a number")
        return errors
    if kind in ("ref", "param"):
        if not isinstance(node[kind], str) or not node[kind]:
            errors.append(f"{where}: {kind} must be a non-empty string")
        return errors
    op = node["op"]
    if op not in OPS:
        return [f"{where}: unknown op '{op}'"]
    args = node.get("args")
    if not isinstance(args, list):
        return [f"{where}: op '{op}' needs an args list"]
    lo, hi = OPS[op]
    if len(args) < lo or (hi is not None and len(args) > hi):
        want = f"{lo}" if lo == hi else f"{lo}..{hi if hi is not None else 'n'}"
        errors.append(f"{where}: op '{op}' takes {want} args, got {len(args)}")
    for i, arg in enumerate(args):
        errors.extend(_node_errors(arg, f"{where}.{op}[{i}]"))
    return errors


def let_order(lets: dict[str, Any]) -> list[str]:
    """Topological order of lets; raises ValueError naming a cycle."""
    order: list[str] = []
    state: dict[str, int] = {}

    def visit(name: str, path: list[str]) -> None:
        if state.get(name) == 2:
            return
        if state.get(name) == 1:
            raise ValueError("cycle among lets: " + " -> ".join(path + [name]))
        state[name] = 1
        for dep in sorted(refs_of(lets[name])):
            if dep in lets:
                visit(dep, path + [name])
        state[name] = 2
        order.append(name)

    for name in sorted(lets):
        visit(name, [])
    return order


def _black_box_errors(ir: dict[str, Any]) -> list[str]:
    bb = ir["black_box"]
    if not isinstance(bb, dict):
        return ["black_box must be an object"]
    errors = []
    if not str(bb.get("estimates", "")).strip():
        errors.append("black_box: a prose statement of what the model estimates is mandatory")
    if not str(bb.get("architecture", "")).strip():
        errors.append("black_box: architecture description is required")
    return errors


def _io_errors(ir: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    names: set[str] = set()
    for inp in ir.get("inputs", []):
        name = inp.get("name") if isinstance(inp, dict) else None
        if not name:
            errors.append("input without a name")
            continue
        if name in names:
            errors.append(f"input '{name}' declared twice")
        names.add(name)
        if inp.get("role", "feature") not in INPUT_ROLES:
            errors.append(f"input '{name}': role must be one of {INPUT_ROLES}")
        if "value" in inp and (
            inp.get("role") != "constant"
            or isinstance(inp["value"], bool)
            or not isinstance(inp["value"], (int, float))
        ):
            errors.append(f"input '{name}': only a constant carries a value, and it is a number")
        bounds = inp.get("bounds")
        if bounds is not None and (len(bounds) != 2 or bounds[0] > bounds[1]):
            errors.append(f"input '{name}': bounds must be [lo, hi] with lo <= hi")
    if not ir.get("outputs"):
        errors.append("at least one output is required")
    return errors


def validate_ir(ir: dict[str, Any]) -> list[str]:
    """Every structural error in an IR document; empty means valid."""
    if not isinstance(ir, dict):
        return ["IR must be an object"]
    errors = _io_errors(ir)
    if "black_box" in ir:
        return errors + _black_box_errors(ir)
    if "composite" in ir:
        from maya.formula.composite import validate_composite

        return errors + validate_composite(ir["composite"])
    lets = ir.get("lets") or {}
    if "body" not in ir:
        return errors + ["body is required unless the model is a declared black box"]
    for name, node in lets.items():
        errors.extend(_node_errors(node, f"lets.{name}"))
    errors.extend(_node_errors(ir["body"], "body"))
    if errors:
        return errors
    try:
        let_order(lets)
    except ValueError as exc:
        errors.append(str(exc))
    known = {i["name"] for i in ir.get("inputs", [])} | set(lets)
    for where, node in [("body", ir["body"])] + [(f"lets.{k}", v) for k, v in lets.items()]:
        for ref in sorted(refs_of(node) - known):
            errors.append(f"{where}: unknown ref '{ref}'")
    declared_params = {i["name"] for i in ir.get("inputs", []) if i.get("role") == "parameter"}
    for node in [ir["body"], *lets.values()]:
        for p in sorted(params_of(node) - declared_params):
            errors.append(f"param '{p}' is used but not declared as a parameter input")
    return sorted(set(errors), key=errors.index)


def canonical_json(obj: Any) -> str:
    """Sorted keys, no whitespace — the hashed form."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ir_hash(ir: dict[str, Any]) -> str:
    """sha256 over the canonical IR, excluding the cosmetic ``latex`` field."""
    body = {k: v for k, v in ir.items() if k != "latex"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def input_contract(ir: dict[str, Any]) -> list[dict[str, Any]]:
    """Feature inputs the bound feature set must supply (§8.2)."""
    return [
        {
            "name": i["name"],
            "type": i.get("type", "float64"),
            "unit": i.get("unit"),
            "role": "feature",
        }
        for i in ir.get("inputs", [])
        if i.get("role", "feature") == "feature"
    ]


def parameter_inputs(ir: dict[str, Any]) -> list[dict[str, Any]]:
    """Declared parameter inputs, with bounds."""
    return [i for i in ir.get("inputs", []) if i.get("role") == "parameter"]


def constant_inputs(ir: dict[str, Any]) -> list[dict[str, Any]]:
    """Declared constants: fixed, not learned; a declared ``value`` is used when no parameter
    set supplies one."""
    return [i for i in ir.get("inputs", []) if i.get("role") == "constant"]


def supplied_inputs(ir: dict[str, Any]) -> list[dict[str, Any]]:
    """Everything a parameter set supplies: the parameters and the constants."""
    return parameter_inputs(ir) + constant_inputs(ir)


def is_opaque(ir: dict[str, Any]) -> bool:
    """True when the model is (or contains only) a declared black box."""
    return "black_box" in ir


def typecheck(ir: dict[str, Any], available: dict[str, str]) -> list[str]:
    """Check the feature inputs against attributes offered by a feature set."""
    numeric = {"int32", "int64", "float32", "float64", "decimal", "bool"}
    errors = []
    for item in input_contract(ir):
        name = item["name"]
        if name not in available:
            errors.append(f"input '{name}' is not provided by the feature set")
            continue
        have, want = available[name], item["type"]
        if want in numeric and not any(have.startswith(t) for t in numeric):
            errors.append(f"input '{name}' needs {want}, feature set provides {have}")
    return errors
