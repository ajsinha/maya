"""
Feature set resolution (§6.1–§6.5, §6.8).

A feature set is a view: attributes mapped onto member features, assembled
on a declared index by a declared alignment rule, then filled under a strict
policy precedence that is recorded per attribute so nobody has to guess:

1. attribute-level override            (layer ``attribute``)
2. member-group override                (layer ``group``)
3. the set's global policy             (layer ``global``)
4. inherited policy, nearest ancestor  (layer ``inherited``)
5. the member feature's own policy     (layer ``member``)
6. system default: leave null          (layer ``default``)

Members arrive already resolved under their own policy; re-applying the
winning rule on the set's grid fills only the gaps alignment introduced.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any

import pandas as pd

from maya.core.calendars import business_days
from maya.core.errors import ValidationFailed
from maya.observability.metrics import frame_bytes, observe_resolution
from maya.observability.tracing import span
from maya.resolution.expr import compile_expr
from maya.resolution.resolver import KT, apply_rules, parse_grid, rule_for, to_event_dates
from maya.resolution.rules import parse_rule
from maya.resolution.types import cast_series

Frame = tuple[pd.DataFrame, dict[str, Any]]


def _validate(
    members: dict[str, Frame], mapping: list[dict[str, Any]], index: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """Group mapping entries by member, refusing anything ambiguous."""
    if not mapping:
        raise ValidationFailed("a feature set needs at least one attribute")
    names = [m["attr"] for m in mapping]
    if len(set(names)) != len(names):
        raise ValidationFailed("feature set attribute names must be unique")
    by_member: dict[str, list[dict[str, Any]]] = {}
    for m in mapping:
        if m["member"] not in members:
            raise ValidationFailed(f"attribute '{m['attr']}' maps unknown member '{m['member']}'")
        meta = members[m["member"]][1]
        if m["source_attr"] not in {a["name"] for a in meta["schema"]}:
            raise ValidationFailed(
                f"member '{m['member']}' has no attribute '{m['source_attr']}'", attr=m["attr"]
            )
        extra = [c for c in meta["index"] if c not in index]
        if extra and not m.get("aggregate"):
            raise ValidationFailed(
                f"member '{m['member']}' has index column(s) {extra} the set does not; "
                f"attribute '{m['attr']}' must declare an aggregation",
                attr=m["attr"],
            )
        by_member.setdefault(m["member"], []).append(m)
    return by_member


def _member_frame(
    alias: str, frame: Frame, entries: list[dict[str, Any]], index: list[str], plan: list[str]
) -> tuple[pd.DataFrame, list[str]]:
    df, meta = frame
    midx = list(meta["index"])
    keep = [c for c in index if c in midx]
    out = df.copy()
    if index[0] in midx:
        out[index[0]] = to_event_dates(out[index[0]])
    for e in entries:
        col = out[e["source_attr"]]
        if e.get("filter"):
            mask = compile_expr(e["filter"]).evaluate(out).fillna(False).astype(bool)
            col = col.where(mask.to_numpy())
        if e.get("cast"):
            col = cast_series(col, e["cast"])
        out[f"__{e['attr']}"] = col
    cols = [f"__{e['attr']}" for e in entries]
    if KT in out.columns:
        out[f"_kt__{alias}"] = pd.to_datetime(out[KT], utc=True)
        cols.append(f"_kt__{alias}")
    agg = {c: "last" for c in cols}
    for e in entries:
        if e.get("aggregate"):
            agg[f"__{e['attr']}"] = e["aggregate"]
    if set(keep) != set(midx):
        plan.append(f"aggregate member '{alias}' from {midx} to {keep}")
        out = out.groupby(keep, sort=True).agg(agg).reset_index()
    out = out[keep + cols].rename(columns={f"__{e['attr']}": e["attr"] for e in entries})
    return out, keep


def _keys(
    frames: dict[str, tuple[pd.DataFrame, list[str]]], index: list[str], alignment: dict[str, Any]
) -> pd.DataFrame:
    full = {a: f for a, (f, k) in frames.items() if k == index}
    if not full:
        raise ValidationFailed("at least one member must carry the full set index", index=index)
    mode = alignment.get("mode", "inner")
    if mode in {"left", "asof"}:
        driver = alignment.get("member") or next(iter(full))
        if driver not in full:
            raise ValidationFailed(f"alignment member '{driver}' does not carry the set index")
        return full[driver][index].drop_duplicates()
    keysets = [f[index].drop_duplicates() for f in full.values()]
    out = keysets[0]
    for k in keysets[1:]:
        out = out.merge(k, on=index, how="inner" if mode == "inner" else "outer")
    if mode not in {"inner", "outer"}:
        raise ValidationFailed(f"unknown alignment mode '{mode}'")
    return out


def _apply_grid(
    keys: pd.DataFrame,
    index: list[str],
    grid: Any,
    start: date | None,
    end: date | None,
    plan: list[str],
) -> pd.DataFrame:
    cal = parse_grid(grid)
    if not cal or keys.empty:
        return keys
    dcol = index[0]
    lo = start or keys[dcol].min().date()
    hi = end or keys[dcol].max().date()
    days = pd.DataFrame({dcol: pd.to_datetime(business_days(cal, lo, hi)).astype("datetime64[ns]")})
    if index[1:]:
        days = days.merge(keys[index[1:]].drop_duplicates(), how="cross")
    plan.append(f"grid: {cal} calendar {lo}..{hi}")
    return days


def _join(
    base: pd.DataFrame,
    alias: str,
    frame: pd.DataFrame,
    keep: list[str],
    index: list[str],
    alignment: dict[str, Any],
    plan: list[str],
) -> pd.DataFrame:
    if keep != index:
        plan.append(f"broadcast join member '{alias}' on {keep}")
        return base.merge(frame, on=keep, how="left")
    if alignment.get("mode") == "asof" and alias != alignment.get("member"):
        tol = pd.Timedelta(days=int(alignment.get("tolerance_days", 0)))
        direction = alignment.get("direction", "backward")
        if direction not in {"backward", "forward"}:
            raise ValidationFailed("asof direction must be backward or forward")
        plan.append(f"asof join member '{alias}' {direction} within {tol.days} day(s)")
        left = base.sort_values(index[0], kind="mergesort")
        right = frame.sort_values(index[0], kind="mergesort")
        out = pd.merge_asof(
            left, right, on=index[0], by=index[1:] or None, tolerance=tol, direction=direction
        )
        return out
    plan.append(f"join member '{alias}' on {index}")
    return base.merge(frame, on=index, how="left")


def _filters(
    df: pd.DataFrame, index: list[str], filters: dict[str, Any], plan: list[str]
) -> pd.DataFrame:
    dcol = index[0]
    if filters.get("start"):
        df = df[df[dcol] >= pd.Timestamp(filters["start"])]
    if filters.get("end"):
        df = df[df[dcol] <= pd.Timestamp(filters["end"])]
    uni = filters.get("universe")
    if uni:
        col = (
            uni.get("attr", index[1] if len(index) > 1 else None)
            if isinstance(uni, dict)
            else (index[1] if len(index) > 1 else None)
        )
        values = uni.get("values", []) if isinstance(uni, dict) else list(uni)
        if col is None:
            raise ValidationFailed("a universe filter needs a non-date index column")
        df = df[df[col].isin(values)]
        plan.append(f"universe filter on {col}: {len(values)} value(s)")
    return df.reset_index(drop=True)


def choose_rule(
    attr: str,
    entry: dict[str, Any],
    member_meta: dict[str, Any],
    global_policy: dict[str, Any],
    group_policies: list[dict[str, Any]],
    inherited: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply the precedence stack; return {rule, layer, source}."""
    if entry.get("rule") is not None:
        return {"rule": entry["rule"], "layer": "attribute", "source": "featureset"}
    for i, g in enumerate(group_policies or []):
        if attr in g.get("attrs", []):
            return {"rule": g["rule"], "layer": "group", "source": g.get("name", f"group[{i}]")}
    gp = rule_for(global_policy, attr)
    if gp is not None:
        return {"rule": gp, "layer": "global", "source": "featureset"}
    for anc in inherited or []:
        r = rule_for(anc, attr)
        if r is not None:
            return {"rule": r, "layer": "inherited", "source": anc.get("source", "parent")}
    mr = rule_for(member_meta.get("policy"), entry["source_attr"])
    if mr is not None:
        return {"rule": mr, "layer": "member", "source": entry["member"]}
    return {"rule": "none", "layer": "default", "source": "system"}


def resolve_featureset(
    members: dict[str, Frame],
    mapping: list[dict[str, Any]],
    *,
    index: list[str],
    alignment: dict[str, Any] | None = None,
    grid: Any = "as_is",
    global_policy: dict[str, Any] | None = None,
    group_policies: list[dict[str, Any]] | None = None,
    inherited_policies: list[dict[str, Any]] | None = None,
    filters: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Assemble, align, filter and fill a feature set. Returns (frame, manifest)."""
    with span("resolve feature set", attributes={"maya.members": len(members)}):
        return _resolve_featureset(
            members,
            mapping,
            index=index,
            alignment=alignment,
            grid=grid,
            global_policy=global_policy,
            group_policies=group_policies,
            inherited_policies=inherited_policies,
            filters=filters,
        )


def _resolve_featureset(
    members: dict[str, Frame],
    mapping: list[dict[str, Any]],
    *,
    index: list[str],
    alignment: dict[str, Any] | None = None,
    grid: Any = "as_is",
    global_policy: dict[str, Any] | None = None,
    group_policies: list[dict[str, Any]] | None = None,
    inherited_policies: list[dict[str, Any]] | None = None,
    filters: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    started = time.perf_counter()
    alignment, filters, plan = dict(alignment or {"mode": "inner"}), dict(filters or {}), []
    by_member = _validate(members, mapping, index)
    frames = {a: _member_frame(a, members[a], e, index, plan) for a, e in by_member.items()}
    keys = _keys(frames, index, alignment)
    keys[index[0]] = to_event_dates(keys[index[0]])
    start = pd.Timestamp(filters["start"]).date() if filters.get("start") else None
    end = pd.Timestamp(filters["end"]).date() if filters.get("end") else None
    base = _apply_grid(keys, index, grid, start, end, plan)
    plan.insert(0, f"alignment: {alignment.get('mode', 'inner')}")
    for alias, (frame, keep) in frames.items():
        base = _join(base, alias, frame, keep, index, alignment, plan)
    base = _filters(base, index, filters, plan)
    attrs = [m["attr"] for m in mapping]
    chosen = {
        m["attr"]: choose_rule(
            m["attr"],
            m,
            members[m["member"]][1],
            global_policy or {},
            group_policies or [],
            inherited_policies or [],
        )
        for m in mapping
    }
    base, fill = apply_rules(base, index, attrs, {a: c["rule"] for a, c in chosen.items()})
    kts = [c for c in base.columns if c.startswith("_kt__")]
    base[KT] = base[kts].max(axis=1) if kts else pd.NaT
    if filters.get("expr"):
        mask = compile_expr(filters["expr"]).evaluate(base).fillna(False).astype(bool)
        base = base[mask.to_numpy()]
        plan.append(f"row filter: {compile_expr(filters['expr']).canonical()}")
    out = base[index + attrs + [KT]].sort_values(index, kind="mergesort").reset_index(drop=True)
    manifest = _manifest(mapping, members, chosen, fill, plan, out)
    observe_resolution("featureset", len(out), frame_bytes(out), time.perf_counter() - started)
    return out, manifest


def _manifest(
    mapping: list[dict[str, Any]],
    members: dict[str, Frame],
    chosen: dict[str, dict[str, Any]],
    fill: dict[str, Any],
    plan: list[str],
    out: pd.DataFrame,
) -> dict[str, Any]:
    attributes, non_causal = {}, []
    for m in mapping:
        c = chosen[m["attr"]]
        rule = parse_rule(c["rule"])
        attributes[m["attr"]] = {
            "member": m["member"],
            "source_attr": m["source_attr"],
            "rule": rule.canonical(),
            "layer": c["layer"],
            "source": c["source"],
        }
        if rule.non_causal or members[m["member"]][1].get("non_causal"):
            non_causal.append(m["attr"])
    return {
        "attributes": attributes,
        "plan": plan,
        "rows": int(len(out)),
        "fill_report": fill,
        "non_causal": sorted(non_causal),
    }
