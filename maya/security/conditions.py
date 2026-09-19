"""
Grant conditions (§11.4): row filters, column masks and time bounds.

A grant may narrow what it gives. The conditions travel with the decision that
authorized the read and are applied, in this order, to every frame returned to
that principal:

1. ``row_filter`` — an expression in MAYA's one expression language, over the
   row's attributes and index, with ``@user.username`` and ``@user.desk``
   substituted from the principal (``symbol in @user.desk_symbols`` is written
   with a literal list, or ``desk == @user.desk`` against a desk column);
2. ``time_bound`` — ``{"until": "YYYY-MM-DD"}``: no row whose event date is
   after the cut-off, for a validator who must not see the out-of-sample period;
3. ``column_mask`` — ``{attr: "null" | "hash"}``: the column stays, its values
   do not. ``hash`` is SHA-256 of the value's text, so joins still work and the
   values do not leak.

Several applicable grants of equal standing combine to the most restrictive:
filters are AND-ed, masks unioned (where two grants mask one column differently,
``null`` beats ``hash``), and the earliest cut-off wins.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

import pandas as pd

from maya.core.errors import ValidationFailed

MASKS = ("null", "hash")
KEYS = ("row_filter", "column_mask", "time_bound")


def validate(conditions: dict[str, Any]) -> dict[str, Any]:
    """Refuse malformed conditions at grant time, not at first read."""
    from maya.resolution.expr import compile_expr
    unknown = set(conditions) - set(KEYS)
    if unknown:
        raise ValidationFailed(f"Unknown grant condition(s): {', '.join(sorted(unknown))}; "
                               f"allowed: {', '.join(KEYS)}")
    if conditions.get("row_filter"):
        compile_expr(_substitute(conditions["row_filter"], {"username": "x", "desk": "x"}))
    for attr, how in (conditions.get("column_mask") or {}).items():
        if how not in MASKS:
            raise ValidationFailed(f"Mask for '{attr}' must be one of {', '.join(MASKS)}")
    until = (conditions.get("time_bound") or {}).get("until")
    if until:
        try:
            dt.date.fromisoformat(str(until))
        except ValueError as exc:
            raise ValidationFailed("time_bound.until must be YYYY-MM-DD") from exc
    return conditions


def combine(many: list[dict[str, Any]]) -> dict[str, Any]:
    """The most restrictive combination of several grants' conditions."""
    many = [c for c in many if c]
    if not many:
        return {}
    filters = [c["row_filter"] for c in many if c.get("row_filter")]
    masks: dict[str, str] = {}
    for c in many:
        for attr, how in (c.get("column_mask") or {}).items():
            masks[attr] = "null" if "null" in (how, masks.get(attr)) else how
    untils = [str(c["time_bound"]["until"]) for c in many
              if (c.get("time_bound") or {}).get("until")]
    out: dict[str, Any] = {}
    if filters:
        out["row_filter"] = " and ".join(f"({f})" for f in filters)
    if masks:
        out["column_mask"] = masks
    if untils:
        out["time_bound"] = {"until": min(untils)}
    return out


def _substitute(expr: str, user: dict[str, Any]) -> str:
    for key in ("username", "desk"):
        value = user.get(key)
        literal = "None" if value is None else repr(str(value))
        expr = expr.replace(f"@user.{key}", literal)
    if "@user." in expr:
        raise ValidationFailed("Row filters may reference only @user.username and @user.desk")
    return expr


def apply(df: pd.DataFrame, conditions: dict[str, Any], *, event_col: str | None,
          user: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply conditions to a frame; returns the frame and a statement of what was done."""
    if not conditions:
        return df, {}
    from maya.resolution.expr import compile_expr
    report: dict[str, Any] = {"rows_before": int(len(df))}
    out = df
    if conditions.get("row_filter"):
        expr = compile_expr(_substitute(conditions["row_filter"], user))
        missing = expr.refs - set(out.columns)
        if missing:
            # a filter naming a column this frame lacks withholds everything, never nothing
            out = out.iloc[0:0]
        else:
            out = out[expr.evaluate(out).fillna(False).astype(bool)]
        report["row_filter"] = conditions["row_filter"]
    until = (conditions.get("time_bound") or {}).get("until")
    if until and event_col and event_col in out.columns:
        out = out[pd.to_datetime(out[event_col]) <= pd.Timestamp(until)]
        report["time_bound"] = str(until)
    masks = conditions.get("column_mask") or {}
    if masks:
        out = out.copy()
        for attr, how in masks.items():
            if attr in out.columns:
                out[attr] = None if how == "null" else out[attr].map(_hash)
        report["masked"] = masks
    report["rows_after"] = int(len(out))
    return out.reset_index(drop=True), report


def _hash(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and value != value):
        return None
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def apply_mapped(df: pd.DataFrame, conditions: dict[str, Any],
                 mapping: list[tuple[str, str]], *,
                 index: list[str], user: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply a member feature's conditions to a feature set frame.

    The member's conditions name the member's own attributes; ``mapping`` lists which
    set attribute carries each (``(source_attr, set_attr)`` pairs; one source may feed
    several set attributes, and each is masked). Rows the member's filter
    or time bound withholds are withheld from the set; masked member attributes are
    masked under their set names.
    """
    if not conditions:
        return df, {}
    view = pd.DataFrame({c: df[c] for c in index if c in df.columns})
    for src, attr in mapping:
        if attr in df.columns and src not in view.columns:
            view[src] = df[attr].to_numpy()
    probe = view.assign(_row=range(len(view)))
    kept, report = apply(probe, {k: v for k, v in conditions.items() if k != "column_mask"},
                         event_col=index[0] if index else None, user=user)
    out = df.iloc[kept["_row"].to_list()].copy() if len(kept) != len(df) else df.copy()
    masks = conditions.get("column_mask") or {}
    masked: dict[str, str] = {}
    for src, attr in mapping:
        how = masks.get(src)
        if how and attr in out.columns:
            out[attr] = None if how == "null" else out[attr].map(_hash)
            masked[attr] = how
    if masked:
        report["masked"] = masked
    report["rows_after"] = int(len(out))
    return out.reset_index(drop=True), report
