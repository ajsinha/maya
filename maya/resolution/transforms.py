"""
Transformation pipelines (§5.4): typed, side-effect-free steps between a
source and a feature's output.

A pipeline is a list of step dicts, each ``{"op": <name>, ...}``. Steps are
canonicalized for hashing, so a reordered-key dict hashes the same, and the
output schema can be computed at definition time without running anything.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
from typing import Any, Callable

import numpy as np
import pandas as pd

from maya.core.errors import ValidationFailed
from maya.resolution.expr import compile_expr
from maya.resolution.types import cast_series

AGG_FUNCS = {"mean", "sum", "min", "max", "std", "first", "last", "count", "median"}
FREQS = {"W": "W-FRI", "M": "ME", "Q": "QE"}

Step = dict[str, Any]


def _need(step: Step, *keys: str) -> None:
    missing = [k for k in keys if k not in step]
    if missing:
        raise ValidationFailed(f"transform step '{step.get('op')}' needs {missing}", step=step)


def _groups(df: pd.DataFrame, index_cols: list[str]) -> list[str]:
    return [c for c in index_cols[1:] if c in df.columns]


def _sorted(df: pd.DataFrame, index_cols: list[str]) -> pd.DataFrame:
    keys = [c for c in index_cols if c in df.columns]
    return df.sort_values(keys, kind="mergesort").reset_index(drop=True) if keys else df


def _rename(df: pd.DataFrame, s: Step, idx: list[str]) -> pd.DataFrame:
    _need(s, "mapping")
    return df.rename(columns=s["mapping"])


def _cast(df: pd.DataFrame, s: Step, idx: list[str]) -> pd.DataFrame:
    _need(s, "attr", "type")
    out = df.copy()
    out[s["attr"]] = cast_series(out[s["attr"]], s["type"])
    return out


def _filter(df: pd.DataFrame, s: Step, idx: list[str]) -> pd.DataFrame:
    _need(s, "expr")
    mask = compile_expr(s["expr"]).evaluate(df).fillna(False).astype(bool)
    return df[mask.to_numpy()].reset_index(drop=True)


def _derive(df: pd.DataFrame, s: Step, idx: list[str]) -> pd.DataFrame:
    _need(s, "name", "expr")
    out = df.copy()
    out[s["name"]] = compile_expr(s["expr"]).evaluate(df).to_numpy()
    if s.get("type"):
        out[s["name"]] = cast_series(out[s["name"]], s["type"])
    return out


def _aggregate(df: pd.DataFrame, s: Step, idx: list[str]) -> pd.DataFrame:
    _need(s, "by", "agg")
    for fn in s["agg"].values():
        if fn not in AGG_FUNCS:
            raise ValidationFailed(f"unknown aggregation '{fn}'", allowed=sorted(AGG_FUNCS))
    return df.groupby(list(s["by"]), sort=True, dropna=False).agg(s["agg"]).reset_index()


def _pivot(df: pd.DataFrame, s: Step, idx: list[str]) -> pd.DataFrame:
    _need(s, "index", "columns", "values")
    wide = df.pivot_table(index=s["index"], columns=s["columns"], values=s["values"],
                          aggfunc="first")
    wide.columns = [f"{s['values']}_{c}" for c in wide.columns]
    return wide.reset_index()


def _unpivot(df: pd.DataFrame, s: Step, idx: list[str]) -> pd.DataFrame:
    _need(s, "id_vars", "var_name", "value_name")
    return df.melt(id_vars=s["id_vars"], var_name=s["var_name"], value_name=s["value_name"])


def _window(df: pd.DataFrame, s: Step, idx: list[str]) -> pd.DataFrame:
    _need(s, "attr", "fn", "size")
    if s["fn"] not in {"mean", "sum", "min", "max", "std"}:
        raise ValidationFailed(f"unknown window function '{s['fn']}'")
    out = _sorted(df, idx)
    grp = _groups(out, idx)
    col = out[s["attr"]].astype("float64")
    roll = (col.groupby([out[g] for g in grp]) if grp else col).rolling(int(s["size"]),
                                                                         min_periods=1)
    vals = getattr(roll, s["fn"])()
    if grp:
        vals = vals.reset_index(level=list(range(len(grp))), drop=True).sort_index()
    out[s.get("name") or f"{s['attr']}_{s['fn']}{s['size']}"] = vals.to_numpy()
    return out


def _lag(df: pd.DataFrame, s: Step, idx: list[str]) -> pd.DataFrame:
    _need(s, "attr", "n")
    out = _sorted(df, idx)
    grp = _groups(out, idx)
    col = out[s["attr"]]
    shifted = col.groupby([out[g] for g in grp]).shift(int(s["n"])) if grp else col.shift(int(s["n"]))
    out[s.get("name") or f"{s['attr']}_lag{s['n']}"] = shifted.to_numpy()
    return out


def _resample(df: pd.DataFrame, s: Step, idx: list[str]) -> pd.DataFrame:
    _need(s, "freq", "agg")
    if s["freq"] not in FREQS:
        raise ValidationFailed(f"unknown resample frequency '{s['freq']}'", allowed=sorted(FREQS))
    date_col, grp = idx[0], _groups(df, idx)
    keyed = df.set_index(date_col)
    grouper = pd.Grouper(freq=FREQS[s["freq"]])
    out = keyed.groupby(grp + [grouper] if grp else grouper).agg(s["agg"]).reset_index()
    return out.dropna(subset=list(s["agg"]), how="all").reset_index(drop=True)


def _dedupe(df: pd.DataFrame, s: Step, idx: list[str]) -> pd.DataFrame:
    keep = s.get("keep", "last")
    if keep not in {"first", "last"}:
        raise ValidationFailed("dedupe keep must be 'first' or 'last'")
    keys = [c for c in idx if c in df.columns]
    return df.drop_duplicates(subset=keys or None, keep=keep).reset_index(drop=True)


def _clip(df: pd.DataFrame, s: Step, idx: list[str]) -> pd.DataFrame:
    _need(s, "attr")
    out = df.copy()
    out[s["attr"]] = out[s["attr"]].clip(lower=s.get("lo"), upper=s.get("hi"))
    return out


def _winsorize(df: pd.DataFrame, s: Step, idx: list[str]) -> pd.DataFrame:
    _need(s, "attr", "p")
    p = float(s["p"])
    if not 0 <= p < 0.5:
        raise ValidationFailed("winsorize p must be in [0, 0.5)")
    out = df.copy()
    col = out[s["attr"]].astype("float64")
    lo, hi = np.nanquantile(col, p), np.nanquantile(col, 1 - p)
    out[s["attr"]] = col.clip(lower=lo, upper=hi)
    return out


STEPS: dict[str, Callable[[pd.DataFrame, Step, list[str]], pd.DataFrame]] = {
    "rename": _rename, "cast": _cast, "filter": _filter, "derive": _derive,
    "aggregate": _aggregate, "pivot": _pivot, "unpivot": _unpivot, "window": _window,
    "lag": _lag, "resample": _resample, "dedupe": _dedupe, "clip": _clip,
    "winsorize": _winsorize,
}


def validate_step(step: Step) -> None:
    """Refuse an unknown op or an expression that does not compile."""
    op = step.get("op")
    if op not in STEPS:
        raise ValidationFailed(f"unknown transform step '{op}'", allowed=sorted(STEPS))
    for key in ("expr",):
        if key in step:
            compile_expr(step[key])
    # the same guard the algebra's lag operator has: a transform must not be a back door
    if op == "lag" and "n" in step and int(step["n"]) < 0:
        raise ValidationFailed("lag n must be non-negative; a negative lag is look-ahead")
    if op == "window" and "size" in step and int(step["size"]) < 1:
        raise ValidationFailed("window size must be at least 1")


def apply_pipeline(df: pd.DataFrame, steps: list[Step], index_cols: list[str]) -> pd.DataFrame:
    """Run every step in order. The frame is never mutated in place."""
    out = df
    for step in steps or []:
        validate_step(step)
        out = STEPS[step["op"]](out, step, index_cols)
    return out


def _schema_step(schema: list[dict[str, Any]], step: Step) -> list[dict[str, Any]]:
    op, attrs = step["op"], [dict(a) for a in schema]
    if op == "rename":
        for a in attrs:
            a["name"] = step["mapping"].get(a["name"], a["name"])
    elif op == "cast":
        for a in attrs:
            if a["name"] == step["attr"]:
                a["type"] = step["type"]
    elif op == "derive":
        attrs = [a for a in attrs if a["name"] != step["name"]]
        attrs.append({"name": step["name"], "type": step.get("type", "float64"), "nullable": True})
    elif op in {"window", "lag"}:
        default = f"{step['attr']}_{step['fn']}{step['size']}" if op == "window" \
            else f"{step['attr']}_lag{step['n']}"
        base = next((a for a in attrs if a["name"] == step["attr"]), None)
        typ = "float64" if op == "window" else (base["type"] if base else "float64")
        attrs.append({"name": step.get("name") or default, "type": typ, "nullable": True})
    elif op == "aggregate":
        keep = set(step["agg"])
        attrs = [a for a in attrs if a["name"] in keep]
    return attrs


def pipeline_output_schema(schema: list[dict[str, Any]], steps: list[Step],
                           index_cols: list[str]) -> list[dict[str, Any]]:
    """Best-effort output schema, computed at definition time without data."""
    out = [dict(a) for a in schema]
    for step in steps or []:
        validate_step(step)
        out = _schema_step(out, step)
    return out


def _canon_value(v: Any) -> Any:
    return compile_expr(v).canonical() if isinstance(v, str) else v


def canonical_pipeline(steps: list[Step]) -> list[dict[str, Any]]:
    """Normalized form for the definition hash: sorted keys, canonical expressions."""
    out = []
    for step in steps or []:
        canon = {k: (_canon_value(v) if k == "expr" else v) for k, v in step.items()}
        out.append(json.loads(json.dumps(canon, sort_keys=True, default=str)))
    return out
