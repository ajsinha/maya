"""
Vectorised numpy interpreter for the formula IR (§8.1, §29.7).

This is the reference semantics: conformance testing compares an uploaded
artifact against it, blind scoring runs on it, and the reproducibility
bundle re-executes with it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Callable

import numpy as np

from maya.core.errors import ValidationFailed
from maya.formula.ir import let_order, validate_ir

_erfc = np.vectorize(math.erfc, otypes=[float])
_SQRT2 = math.sqrt(2.0)
_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)


def ncdf(x: Any) -> np.ndarray:
    """Standard normal CDF via ``math.erfc``, which keeps relative precision in the left tail."""
    arr = np.asarray(x, dtype=float)
    return 0.5 * _erfc(-arr / _SQRT2)


def _probit(p: float) -> float:
    if p != p or p < 0.0 or p > 1.0:
        return math.nan
    if p in (0.0, 1.0):
        return math.inf if p else -math.inf
    return _NORMAL.inv_cdf(p)


_NORMAL = statistics.NormalDist()
_probit_v = np.vectorize(_probit, otypes=[float])


def ncdfinv(p: Any) -> np.ndarray:
    """The standard normal quantile: -inf at 0, +inf at 1, and no answer outside [0, 1]."""
    return _probit_v(np.asarray(p, dtype=float))


def npdf(x: Any) -> np.ndarray:
    """Standard normal density."""
    arr = np.asarray(x, dtype=float)
    return _INV_SQRT_2PI * np.exp(-0.5 * arr * arr)


def _reduce(fn: Callable[[Any, Any], Any], vals: list[Any]) -> Any:
    out = vals[0]
    for v in vals[1:]:
        out = fn(out, v)
    return out


_OPS: dict[str, Callable[[list[Any]], Any]] = {
    "add": lambda v: _reduce(np.add, v),
    "sub": lambda v: np.subtract(v[0], v[1]),
    "mul": lambda v: _reduce(np.multiply, v),
    "div": lambda v: np.divide(v[0], v[1]),
    "pow": lambda v: np.power(np.asarray(v[0], dtype=float), v[1]),
    "neg": lambda v: np.negative(v[0]),
    "exp": lambda v: np.exp(v[0]),
    "log": lambda v: np.log(v[0]),
    "sqrt": lambda v: np.sqrt(v[0]),
    "abs": lambda v: np.abs(v[0]),
    "ncdf": lambda v: ncdf(v[0]),
    "ncdfinv": lambda v: ncdfinv(v[0]),
    "npdf": lambda v: npdf(v[0]),
    "max": lambda v: _reduce(np.maximum, v),
    "min": lambda v: _reduce(np.minimum, v),
    "where": lambda v: np.where(np.asarray(v[0], dtype=bool), v[1], v[2]),
    "gt": lambda v: np.greater(v[0], v[1]),
    "lt": lambda v: np.less(v[0], v[1]),
    "ge": lambda v: np.greater_equal(v[0], v[1]),
    "le": lambda v: np.less_equal(v[0], v[1]),
    "eq": lambda v: np.equal(v[0], v[1]),
    "and": lambda v: _reduce(np.logical_and, v),
    "or": lambda v: _reduce(np.logical_or, v),
    "na": lambda v: np.nan,
}


def eval_node(node: dict[str, Any], env: dict[str, Any], params: dict[str, Any]) -> Any:
    """Evaluate one node against an environment of named arrays."""
    if "const" in node:
        return node["const"]
    if "ref" in node:
        name = node["ref"]
        if name in env:
            return env[name]
        if name in params:
            return params[name]
        raise ValidationFailed(f"no value supplied for '{name}'", name=name)
    if "param" in node:
        if node["param"] not in params:
            raise ValidationFailed(
                f"no value supplied for parameter '{node['param']}'", name=node["param"]
            )
        return params[node["param"]]
    vals = [eval_node(a, env, params) for a in node["args"]]
    with np.errstate(all="ignore"):
        return _OPS[node["op"]](vals)


def _as_array(value: Any) -> np.ndarray:
    return np.asarray(value, dtype=float) if not isinstance(value, np.ndarray) else value


def evaluate(
    ir: dict[str, Any], inputs: dict[str, Any], params: dict[str, Any] | None = None
) -> dict[str, np.ndarray]:
    """Evaluate a closed-form IR; returns ``{output_name: array}``."""
    params = dict(params or {})
    if "black_box" in ir:
        raise ValidationFailed("a declared black box has no closed form to evaluate")
    if "composite" in ir:
        raise ValidationFailed("use evaluate_composite for a composite model")
    errors = validate_ir(ir)
    if errors:
        raise ValidationFailed("invalid IR", errors=errors)
    env = {k: _as_array(v) for k, v in inputs.items()}
    for inp in ir.get("inputs", []):
        if inp.get("role") in ("parameter", "constant") and inp["name"] in params:
            env.setdefault(inp["name"], params[inp["name"]])
        elif inp.get("role") == "constant" and "value" in inp:
            env.setdefault(inp["name"], inp["value"])
    lets = ir.get("lets") or {}
    for name in let_order(lets):
        env[name] = eval_node(lets[name], env, params)
    result = eval_node(ir["body"], env, params)
    size = max((np.size(v) for v in env.values()), default=1)
    out = (
        np.broadcast_to(np.asarray(result, dtype=float), (size,))
        if np.ndim(result) == 0
        else np.asarray(result, dtype=float)
    )
    return {ir["outputs"][0]["name"]: np.array(out)}


def _member_params(params: dict[str, Any], alias: str) -> dict[str, Any]:
    prefix = alias + "."
    return {k[len(prefix) :]: v for k, v in params.items() if k.startswith(prefix)}


def evaluate_composite(
    ir: dict[str, Any],
    member_irs: dict[str, dict[str, Any]],
    inputs: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, np.ndarray]:
    """Evaluate a composite: members first (in train order or declaration order), then combine.

    Member parameters are alias-namespaced (``base.sigma``); the combiner's own
    parameters are bare (``w_skew``). In a ``pipeline`` each member also sees the
    previous members' outputs as ``alias.output``.
    """
    params = dict(params or {})
    comp = ir["composite"]
    order = comp.get("train", {}).get("order") or [m["alias"] for m in comp["members"]]
    env: dict[str, Any] = {k: _as_array(v) for k, v in inputs.items()}
    for alias in order:
        member = member_irs[alias]
        member_inputs = dict(env)
        if "composite" in member:
            nested = {
                m["alias"]: member_irs[f"{alias}/{m['alias']}"]
                for m in member["composite"]["members"]
            }
            outputs = evaluate_composite(
                member, nested, member_inputs, _member_params(params, alias)
            )
        else:
            outputs = evaluate(member, member_inputs, _member_params(params, alias))
        for out_name, arr in outputs.items():
            env[f"{alias}.{out_name}"] = arr
    combined = eval_node(comp["combine"], env, params)
    out_name = ir["outputs"][0]["name"] if ir.get("outputs") else "y"
    return {out_name: np.asarray(combined, dtype=float)}
