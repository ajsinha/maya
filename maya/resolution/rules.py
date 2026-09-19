"""
Resolution rules (§5.3): how a gap in an attribute is filled.

Each rule is bounded and reports what it did. ``forward_fill`` takes a
``limit`` (maximum consecutive filled periods) and a ``max_age`` in days;
beyond either the value stays null rather than quietly propagating a year-old
price. Rules that consume future information are ``NON_CAUSAL`` and the
resolver reports them so a training warrant can refuse them (§5.3, D-3).

Rules operate on one series in event-time order; the resolver applies them
per non-date index group (per symbol, for a panel).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import ast
import importlib.util
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd

from maya.core.errors import ValidationFailed

NON_CAUSAL = frozenset({"backward_fill", "linear_interp", "spline_interp"})

PARAMS: dict[str, tuple[str, ...]] = {
    "none": (),
    "forward_fill": ("limit", "max_age"),
    "backward_fill": ("limit",),
    "linear_interp": ("limit",),
    "spline_interp": ("order",),
    "constant": ("v",),
    "mean_of_window": ("n",),
    "last_known_as_of": ("lag",),
    "zero": (),
    "previous_period": (),
    "custom": ("fn",),
}


@dataclass(frozen=True)
class RuleSpec:
    """A parsed rule: its name and bound parameters."""

    name: str
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def non_causal(self) -> bool:
        return self.name in NON_CAUSAL

    def canonical(self) -> str:
        """Stable text form used in hashes and manifests."""
        if not self.params:
            return self.name
        args = ", ".join(f"{k}={self.params[k]!r}" for k in sorted(self.params))
        return f"{self.name}({args})"

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.name, **self.params}


def _parse_text(text: str) -> RuleSpec:
    try:
        node = ast.parse(text.strip(), mode="eval").body
    except SyntaxError as exc:
        raise ValidationFailed(f"resolution rule '{text}' does not parse") from exc
    if isinstance(node, ast.Name):
        return RuleSpec(node.id)
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
        raise ValidationFailed(f"resolution rule '{text}' is not a rule call")
    name = node.func.id
    params: dict[str, Any] = {}
    names = PARAMS.get(name, ())
    for i, arg in enumerate(node.args):
        if i >= len(names):
            raise ValidationFailed(f"rule '{name}' takes at most {len(names)} arguments")
        params[names[i]] = ast.literal_eval(arg)
    for kw in node.keywords:
        params[str(kw.arg)] = ast.literal_eval(kw.value)
    return RuleSpec(name, params)


def parse_rule(spec: str | dict[str, Any] | RuleSpec | None) -> RuleSpec:
    """Parse ``"forward_fill(limit=3)"``, ``{"rule": "zero"}`` or None (= none)."""
    if spec is None:
        rs = RuleSpec("none")
    elif isinstance(spec, RuleSpec):
        rs = spec
    elif isinstance(spec, dict):
        spec = dict(spec)
        name = spec.pop("rule", None) or spec.pop("name", None)
        if not name:
            raise ValidationFailed("resolution rule dict needs a 'rule' key")
        rs = RuleSpec(str(name), spec)
    else:
        rs = _parse_text(str(spec))
    if rs.name not in PARAMS:
        raise ValidationFailed(f"unknown resolution rule '{rs.name}'", known=sorted(PARAMS))
    unknown = set(rs.params) - set(PARAMS[rs.name])
    if unknown:
        raise ValidationFailed(f"rule '{rs.name}' has unknown parameter(s) {sorted(unknown)}")
    if rs.name == "custom":
        raise ValidationFailed("custom(fn) rules need a registered sandboxed function; "
                               "none are registered in this build")
    if rs.name == "spline_interp" and importlib.util.find_spec("scipy") is None:
        raise ValidationFailed("spline_interp needs the 'scipy' package, which is not installed",
                               package="scipy")
    return rs


def _runs(mask: np.ndarray) -> np.ndarray:
    """For each True position, its 1-based position within its run of Trues."""
    out = np.zeros(len(mask), dtype=np.int64)
    run = 0
    for i, m in enumerate(mask):
        run = run + 1 if m else 0
        out[i] = run
    return out


def _longest(mask: np.ndarray) -> int:
    return int(_runs(mask).max()) if len(mask) else 0


def _ffill(s: pd.Series, dates: pd.Series, p: dict[str, Any]) -> pd.Series:
    limit, max_age = p.get("limit"), p.get("max_age")
    filled = s.ffill()
    null = s.isna().to_numpy()
    ok = np.ones(len(s), dtype=bool)
    if limit is not None:
        ok &= _runs(null) <= int(limit)
    if max_age is not None:
        known_dates = dates.where(s.notna()).ffill()
        age = (dates - known_dates).dt.days.to_numpy()
        ok &= ~(age > int(max_age))
    return s.where(~null, filled.where(ok))


def _bfill(s: pd.Series, dates: pd.Series, p: dict[str, Any]) -> pd.Series:
    rev = s.iloc[::-1]
    null = rev.isna().to_numpy()
    filled = rev.ffill()
    limit = p.get("limit")
    if limit is not None:
        filled = filled.where(_runs(null) <= int(limit))
    return s.where(s.notna(), filled.iloc[::-1])


def _interp(s: pd.Series, dates: pd.Series, p: dict[str, Any], method: str) -> pd.Series:
    x = pd.Series(s.astype("float64").to_numpy(), index=pd.DatetimeIndex(dates.to_numpy()))
    kwargs: dict[str, Any] = {"limit_area": "inside"}
    if method == "spline":
        kwargs["order"] = int(p.get("order", 3))
    out = x.interpolate(method="time" if method == "linear" else "spline", **kwargs).to_numpy()
    if p.get("limit") is not None:
        ok = s.notna().to_numpy() | (_runs(s.isna().to_numpy()) <= int(p["limit"]))
        out = np.where(ok, out, np.nan)
    return pd.Series(out, index=s.index)


def _constant(s: pd.Series, dates: pd.Series, p: dict[str, Any]) -> pd.Series:
    if "v" not in p:
        raise ValidationFailed("constant(v) needs a value")
    return s.where(s.notna(), p["v"])


def _mean_window(s: pd.Series, dates: pd.Series, p: dict[str, Any]) -> pd.Series:
    n = int(p.get("n", 5))
    prev = s.astype("float64").rolling(n, min_periods=1).mean().shift(1)
    return s.where(s.notna(), prev)


def _last_known(s: pd.Series, dates: pd.Series, p: dict[str, Any]) -> pd.Series:
    lag = int(p.get("lag", 0))
    known = pd.DataFrame({"d": dates[s.notna()].to_numpy(), "v": s[s.notna()].to_numpy()})
    probe = pd.DataFrame({"d": (dates - pd.Timedelta(days=lag)).to_numpy(),
                          "pos": np.arange(len(s))})
    if known.empty:
        return s
    known = known.sort_values("d")
    order = probe.sort_values("d")
    merged = pd.merge_asof(order, known, on="d", direction="backward").sort_values("pos")
    return s.where(s.notna(), pd.Series(merged["v"].to_numpy(), index=s.index))


def _zero(s: pd.Series, dates: pd.Series, p: dict[str, Any]) -> pd.Series:
    return s.where(s.notna(), 0)


def _previous(s: pd.Series, dates: pd.Series, p: dict[str, Any]) -> pd.Series:
    return s.where(s.notna(), s.shift(1))


_IMPL: dict[str, Callable[[pd.Series, pd.Series, dict[str, Any]], pd.Series]] = {
    "none": lambda s, d, p: s,
    "forward_fill": _ffill,
    "backward_fill": _bfill,
    "linear_interp": lambda s, d, p: _interp(s, d, p, "linear"),
    "spline_interp": lambda s, d, p: _interp(s, d, p, "spline"),
    "constant": _constant,
    "mean_of_window": _mean_window,
    "last_known_as_of": _last_known,
    "zero": _zero,
    "previous_period": _previous,
}


def apply_rule(series: pd.Series, spec: Any, dates: pd.Series) -> tuple[pd.Series, dict[str, Any]]:
    """Apply one rule to one series (in date order). Returns (series, stats)."""
    rs = parse_rule(spec)
    s = series.reset_index(drop=True)
    d = pd.Series(pd.to_datetime(dates).to_numpy()).reset_index(drop=True)
    before = s.isna().to_numpy()
    out = _IMPL[rs.name](s, d, rs.params)
    after = out.isna().to_numpy()
    filled_mask = before & ~after
    out.index = series.index
    stats = {"rule": rs.canonical(), "filled": int(filled_mask.sum()),
             "longest_run": _longest(filled_mask)}
    return out, stats
