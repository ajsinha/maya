"""
The feature algebra (§5.8): operators closed over features.

Every operator takes operand features and yields a feature *definition*.
Each has two halves:

* ``typecheck(op, options, metas) -> meta`` runs at definition time, with no
  data. Index compatibility, type unification and unit/tag conflicts are
  errors here, never at run time. Non-causality propagates.
* ``execute(op, options, frames, metas) -> DataFrame`` replays the operator
  over resolved operand frames.

A meta is ``{"index": [...], "schema": [...], "non_causal": bool}``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from maya.core.errors import ValidationFailed
from maya.resolution.expr import compile_expr
from maya.resolution.transforms import (apply_pipeline, canonical_pipeline,
                                        pipeline_output_schema)
from maya.resolution.types import unify

Meta = dict[str, Any]
KT = "_knowledge_time"


def _attrs(meta: Meta) -> list[str]:
    return [a["name"] for a in meta["schema"]]


def _by_name(meta: Meta) -> dict[str, dict[str, Any]]:
    return {a["name"]: a for a in meta["schema"]}


def _arity(op: str, metas: list[Meta], lo: int, hi: int | None) -> None:
    if len(metas) < lo or (hi is not None and len(metas) > hi):
        want = f"{lo}" if lo == hi else f"{lo}..{hi or 'n'}"
        raise ValidationFailed(f"operator '{op}' takes {want} operand(s), got {len(metas)}")


def _same_index(op: str, metas: list[Meta]) -> list[str]:
    first = list(metas[0]["index"])
    for m in metas[1:]:
        if list(m["index"]) != first:
            raise ValidationFailed(
                f"operator '{op}' needs identical indexes; got {first} and {list(m['index'])}")
    return first


def _unify_schemas(op: str, metas: list[Meta]) -> list[dict[str, Any]]:
    names = _attrs(metas[0])
    for m in metas[1:]:
        if sorted(_attrs(m)) != sorted(names):
            raise ValidationFailed(f"operator '{op}' needs identical attributes; "
                                   f"got {sorted(names)} and {sorted(_attrs(m))}")
    out = []
    for n in names:
        merged = _by_name(metas[0])[n]
        for m in metas[1:]:
            merged = unify(merged, _by_name(m)[n])
        out.append(merged)
    return out


def _nc(metas: list[Meta], extra: bool = False) -> bool:
    return extra or any(bool(m.get("non_causal")) for m in metas)


def _meta(index: list[str], schema: list[dict[str, Any]], metas: list[Meta],
          change: str = "additive", extra_nc: bool = False) -> Meta:
    return {"index": list(index), "schema": schema, "non_causal": _nc(metas, extra_nc),
            "change_class": change}


# ---------------------------------------------------------------- typecheck

def _tc_project(o: dict[str, Any], m: list[Meta]) -> Meta:
    _arity("project", m, 1, 1)
    have = _by_name(m[0])
    unknown = [a for a in o.get("attrs", []) if a not in have]
    if unknown or not o.get("attrs"):
        raise ValidationFailed(f"project names unknown or no attribute(s) {unknown}")
    return _meta(m[0]["index"], [have[a] for a in o["attrs"]], m)


def _tc_rename(o: dict[str, Any], m: list[Meta]) -> Meta:
    _arity("rename", m, 1, 1)
    mapping = o.get("mapping", {})
    if set(mapping) & set(m[0]["index"]):
        raise ValidationFailed("rename cannot rename index columns")
    unknown = [a for a in mapping if a not in _by_name(m[0])]
    if unknown:
        raise ValidationFailed(f"rename names unknown attribute(s) {unknown}")
    schema = [dict(a, name=mapping.get(a["name"], a["name"])) for a in m[0]["schema"]]
    if len({a["name"] for a in schema}) != len(schema):
        raise ValidationFailed("rename produces duplicate attribute names")
    return _meta(m[0]["index"], schema, m)


def _tc_transform(o: dict[str, Any], m: list[Meta]) -> Meta:
    _arity("transform", m, 1, 1)
    schema = pipeline_output_schema(m[0]["schema"], o.get("pipeline", []), m[0]["index"])
    return _meta(m[0]["index"], schema, m, "behavioral")


def _tc_union(o: dict[str, Any], m: list[Meta]) -> Meta:
    _arity("union", m, 2, None)
    if o.get("collision", "error") not in {"error", "prefer_left", "prefer_right"}:
        raise ValidationFailed("union collision must be error, prefer_left or prefer_right")
    return _meta(_same_index("union", m), _unify_schemas("union", m), m)


def _tc_intersect(o: dict[str, Any], m: list[Meta]) -> Meta:
    _arity("intersect", m, 2, 2)
    if o.get("priority", "left") not in {"left", "right"}:
        raise ValidationFailed("intersect priority must be left or right")
    return _meta(_same_index("intersect", m), _unify_schemas("intersect", m), m)


def _tc_difference(o: dict[str, Any], m: list[Meta]) -> Meta:
    _arity("difference", m, 2, 2)
    return _meta(_same_index("difference", m), m[0]["schema"], m)


def _compose_index(m: list[Meta], broadcast: bool) -> list[str]:
    a, b = list(m[0]["index"]), list(m[1]["index"])
    if a == b:
        return a
    if broadcast and (set(b) <= set(a) or set(a) <= set(b)):
        return a if len(a) >= len(b) else b
    raise ValidationFailed(f"compose needs identical indexes or a declared broadcast; "
                           f"got {a} and {b}")


def _tc_compose(o: dict[str, Any], m: list[Meta]) -> Meta:
    _arity("compose", m, 2, 2)
    index = _compose_index(m, bool(o.get("broadcast")))
    prefixes = o.get("prefixes") or ["", ""]
    left = [dict(a, name=prefixes[0] + a["name"]) for a in m[0]["schema"]]
    right = [dict(a, name=prefixes[1] + a["name"]) for a in m[1]["schema"]]
    clash = sorted({a["name"] for a in left} & {a["name"] for a in right})
    if clash:
        raise ValidationFailed(f"compose attribute name clash {clash}; declare prefixes",
                               clash=clash)
    return _meta(index, left + right, m)


def _tc_coalesce(o: dict[str, Any], m: list[Meta]) -> Meta:
    _arity("coalesce", m, 2, None)
    return _meta(_same_index("coalesce", m), _unify_schemas("coalesce", m), m)


def _tc_aggregate(o: dict[str, Any], m: list[Meta]) -> Meta:
    _arity("aggregate", m, 1, 1)
    by, agg = list(o.get("by", [])), dict(o.get("agg", {}))
    if not by or not set(by) <= set(m[0]["index"]):
        raise ValidationFailed("aggregate 'by' must be a non-empty subset of the index")
    have = _by_name(m[0])
    unknown = [a for a in agg if a not in have]
    if unknown or not agg:
        raise ValidationFailed(f"aggregate needs an aggregation per attribute; unknown {unknown}")
    schema = [dict(have[a], type="int64" if fn == "count" else
                   ("float64" if fn in {"mean", "std"} else have[a]["type"]))
              for a, fn in agg.items()]
    return _meta(by, schema, m, "breaking")


def _tc_lag(o: dict[str, Any], m: list[Meta]) -> Meta:
    _arity("lag", m, 1, 1)
    if int(o.get("n", 1)) < 0:
        raise ValidationFailed("lag n must be non-negative; a negative lag is look-ahead")
    return _meta(m[0]["index"], m[0]["schema"], m, "breaking")


def _tc_resample(o: dict[str, Any], m: list[Meta]) -> Meta:
    _arity("resample", m, 1, 1)
    if o.get("freq") not in {"W", "M", "Q"}:
        raise ValidationFailed("resample freq must be W, M or Q")
    return _meta(m[0]["index"], m[0]["schema"], m, "breaking")


def _tc_case(o: dict[str, Any], m: list[Meta]) -> Meta:
    _arity("case", m, 2, 2)
    expr = compile_expr(o.get("cond", ""))
    known = set(_attrs(m[0])) | set(m[0]["index"])
    unknown = sorted(expr.refs - known)
    if unknown:
        raise ValidationFailed(f"case condition refers to unknown name(s) {unknown}")
    return _meta(_same_index("case", m), _unify_schemas("case", m), m)


# ------------------------------------------------------------------ execute

def _prep(df: pd.DataFrame, meta: Meta) -> pd.DataFrame:
    cols = list(meta["index"]) + [c for c in _attrs(meta) if c in df.columns]
    if KT in df.columns:
        cols.append(KT)
    return df[cols].copy()


def _ex_project(o: dict[str, Any], f: list[pd.DataFrame], m: list[Meta]) -> pd.DataFrame:
    return f[0][list(m[0]["index"]) + list(o["attrs"])].copy()


def _ex_rename(o: dict[str, Any], f: list[pd.DataFrame], m: list[Meta]) -> pd.DataFrame:
    return f[0].rename(columns=o.get("mapping", {}))


def _ex_transform(o: dict[str, Any], f: list[pd.DataFrame], m: list[Meta]) -> pd.DataFrame:
    return apply_pipeline(f[0], o.get("pipeline", []), m[0]["index"])


def _ex_union(o: dict[str, Any], f: list[pd.DataFrame], m: list[Meta]) -> pd.DataFrame:
    idx = list(m[0]["index"])
    parts = [_prep(df, mm) for df, mm in zip(f, m)]
    both = pd.concat(parts, ignore_index=True)
    dup = both.duplicated(subset=idx, keep=False)
    policy = o.get("collision", "error")
    if dup.any() and policy == "error":
        raise ValidationFailed(f"union has {int(dup.sum())} colliding index row(s) and "
                               "collision policy 'error'", rows=int(dup.sum()))
    keep = "first" if policy != "prefer_right" else "last"
    return both.drop_duplicates(subset=idx, keep=keep).sort_values(idx, kind="mergesort") \
        .reset_index(drop=True)


def _keys(df: pd.DataFrame, idx: list[str]) -> pd.MultiIndex:
    return pd.MultiIndex.from_frame(df[idx])


def _ex_intersect(o: dict[str, Any], f: list[pd.DataFrame], m: list[Meta]) -> pd.DataFrame:
    idx = list(m[0]["index"])
    pri, other = (f[0], f[1]) if o.get("priority", "left") == "left" else (f[1], f[0])
    mask = _keys(pri, idx).isin(_keys(other, idx))
    return pri[mask].sort_values(idx, kind="mergesort").reset_index(drop=True)


def _ex_difference(o: dict[str, Any], f: list[pd.DataFrame], m: list[Meta]) -> pd.DataFrame:
    idx = list(m[0]["index"])
    mask = ~_keys(f[0], idx).isin(_keys(f[1], idx))
    return f[0][mask].reset_index(drop=True)


def _ex_compose(o: dict[str, Any], f: list[pd.DataFrame], m: list[Meta]) -> pd.DataFrame:
    prefixes = o.get("prefixes") or ["", ""]
    frames = []
    for df, mm, p in zip(f, m, prefixes):
        d = df[list(mm["index"]) + _attrs(mm)].rename(columns={a: p + a for a in _attrs(mm)})
        frames.append(d)
    on = [c for c in m[0]["index"] if c in m[1]["index"]]
    left, right = frames[0], frames[1]
    how = "outer"
    if list(m[0]["index"]) != list(m[1]["index"]):
        # Broadcast: the wider index drives the rows, the narrower is joined on.
        how = "left"
        if len(m[0]["index"]) < len(m[1]["index"]):
            left, right = frames[1], frames[0]
    out = left.merge(right, on=on, how=how)
    index = _compose_index(m, bool(o.get("broadcast")))
    return out.sort_values(index, kind="mergesort").reset_index(drop=True)


def _ex_coalesce(o: dict[str, Any], f: list[pd.DataFrame], m: list[Meta]) -> pd.DataFrame:
    idx, attrs = list(m[0]["index"]), _attrs(m[0])
    base = pd.concat([df[idx] for df in f]).drop_duplicates().sort_values(idx, kind="mergesort")
    out = base.reset_index(drop=True)
    for i, df in enumerate(f):
        part = df[idx + attrs].rename(columns={a: f"{a}__{i}" for a in attrs})
        out = out.merge(part, on=idx, how="left")
    for a in attrs:
        cols = [f"{a}__{i}" for i in range(len(f))]
        out[a] = out[cols].bfill(axis=1).iloc[:, 0]
        out = out.drop(columns=cols)
    return out


def _ex_aggregate(o: dict[str, Any], f: list[pd.DataFrame], m: list[Meta]) -> pd.DataFrame:
    return f[0].groupby(list(o["by"]), sort=True).agg(o["agg"]).reset_index()


def _ex_lag(o: dict[str, Any], f: list[pd.DataFrame], m: list[Meta]) -> pd.DataFrame:
    idx, n = list(m[0]["index"]), int(o.get("n", 1))
    df = f[0].sort_values(idx, kind="mergesort").reset_index(drop=True)
    attrs = o.get("attrs") or _attrs(m[0])
    grp = idx[1:]
    for a in attrs:
        df[a] = df.groupby(grp, sort=False)[a].shift(n) if grp else df[a].shift(n)
    return df


def _ex_resample(o: dict[str, Any], f: list[pd.DataFrame], m: list[Meta]) -> pd.DataFrame:
    step = {"op": "resample", "freq": o["freq"],
            "agg": o.get("agg") or {a: "last" for a in _attrs(m[0])}}
    return apply_pipeline(f[0][list(m[0]["index"]) + _attrs(m[0])], [step], m[0]["index"])


def _ex_case(o: dict[str, Any], f: list[pd.DataFrame], m: list[Meta]) -> pd.DataFrame:
    idx, attrs = list(m[0]["index"]), _attrs(m[0])
    a = f[0][idx + attrs]
    b = f[1][idx + attrs].rename(columns={x: f"{x}__else" for x in attrs})
    both = a.merge(b, on=idx, how="outer").sort_values(idx, kind="mergesort").reset_index(drop=True)
    cond = compile_expr(o["cond"]).evaluate(both).fillna(False).astype(bool).to_numpy()
    for x in attrs:
        both[x] = np.where(cond, both[x], both[f"{x}__else"])
    return both[idx + attrs]


@dataclass(frozen=True)
class Operator:
    """One algebra operator: its notation, typing rule and executor."""

    name: str
    notation: str
    typecheck: Callable[[dict[str, Any], list[Meta]], Meta]
    execute: Callable[[dict[str, Any], list[pd.DataFrame], list[Meta]], pd.DataFrame]
    commutative: bool = False


OPERATORS: dict[str, Operator] = {op.name: op for op in (
    Operator("project", "π[attrs](F)", _tc_project, _ex_project),
    Operator("rename", "ρ[a→b](F)", _tc_rename, _ex_rename),
    Operator("transform", "τ[pipeline](F)", _tc_transform, _ex_transform),
    Operator("union", "F₁ ∪ F₂", _tc_union, _ex_union, commutative=True),
    Operator("intersect", "F₁ ∩ F₂", _tc_intersect, _ex_intersect),
    Operator("difference", "F₁ ∖ F₂", _tc_difference, _ex_difference),
    Operator("compose", "F₁ ⋈ F₂", _tc_compose, _ex_compose),
    Operator("coalesce", "⊕(F₁, F₂, …)", _tc_coalesce, _ex_coalesce),
    Operator("aggregate", "γ[by, agg](F)", _tc_aggregate, _ex_aggregate),
    Operator("lag", "lag[n](F)", _tc_lag, _ex_lag),
    Operator("resample", "resample[freq](F)", _tc_resample, _ex_resample),
    Operator("case", "σ[cond](F₁, F₂)", _tc_case, _ex_case),
)}


def _get(op: str) -> Operator:
    if op not in OPERATORS:
        raise ValidationFailed(f"unknown algebra operator '{op}'", allowed=sorted(OPERATORS))
    return OPERATORS[op]


def typecheck(op: str, options: dict[str, Any] | None, operand_metas: list[Meta]) -> Meta:
    """Definition-time typing: returns the output meta or raises ValidationFailed."""
    return _get(op).typecheck(dict(options or {}), list(operand_metas))


def execute(op: str, options: dict[str, Any] | None, operand_frames: list[pd.DataFrame],
            operand_metas: list[Meta]) -> pd.DataFrame:
    """Replay an operator over resolved operand frames."""
    opts = dict(options or {})
    typecheck(op, opts, operand_metas)
    return _get(op).execute(opts, list(operand_frames), list(operand_metas))


def canonical_derivation(op: str, options: dict[str, Any] | None,
                         operand_refs: list[str]) -> dict[str, Any]:
    """Normalized derivation for the definition hash.

    Operands of a commutative operator are sorted when its options make order
    irrelevant (``union`` with ``collision: error``), so ``A ∪ B`` and ``B ∪ A``
    hash the same and the duplicate is caught at creation.
    """
    _get(op)
    opts = dict(options or {})
    if "pipeline" in opts:
        opts["pipeline"] = canonical_pipeline(opts["pipeline"])
    if "cond" in opts:
        opts["cond"] = compile_expr(opts["cond"]).canonical()
    refs = list(operand_refs)
    if OPERATORS[op].commutative and opts.get("collision", "error") == "error":
        opts["collision"] = "error"
        refs = sorted(refs)
    return json.loads(json.dumps({"op": op, "options": opts, "operands": refs},
                                 sort_keys=True, default=str))
