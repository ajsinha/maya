"""
Server-drawn line charts for the monitoring pages.

The geometry is computed here and ``_macros/chart.html`` only draws it, so a chart is plain
SVG in the page: no charting library, nothing for the content security policy to allow,
and it prints. One scale places the line, the ticks and the covenant bounds, so a bound is
drawn where the axis says it is; the y range always includes the bounds, because a chart
that crops away the limit it is being compared with hides the one thing it is for.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any

W, H = 640, 170
LEFT, RIGHT, TOP, BOTTOM = 52, 10, 10, 24


def _when(value: Any) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day)
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def nice_ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    """Round tick values covering [lo, hi]: steps of 1, 2 or 5 times a power of ten."""
    if hi <= lo:
        hi = lo + (abs(lo) or 1.0)
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw)
    start = math.floor(lo / step) * step
    ticks, v = [], start
    while v <= hi + step * 1e-9:
        ticks.append(round(v, 10))
        v += step
    if ticks[-1] < hi:
        ticks.append(round(ticks[-1] + step, 10))
    return ticks


def _label(v: float) -> str:
    if v == 0:
        return "0"
    if abs(v) >= 1e6:
        return f"{v / 1e6:g}m"
    if abs(v) >= 1e3:
        return f"{v / 1e3:g}k"
    return f"{v:g}"


def line_chart(
    points: list[dict[str, Any]],
    key: str,
    *,
    bounds: list[tuple[float | None, str]] | None = None,
    marks: list[Any] | None = None,
    floor: float | None = None,
) -> dict[str, Any]:
    """Geometry for one series: ``points`` carry ``at`` and ``key``; ``bounds`` are
    horizontal (value, label) lines; ``marks`` are times to flag on the axis (breaches)."""
    data = [(_when(p["at"]), float(p[key])) for p in points if p.get(key) is not None]
    lines = [(float(v), label) for v, label in (bounds or []) if v is not None]
    if not data:
        return {"empty": True, "w": W, "h": H}
    values = [v for _, v in data] + [v for v, _ in lines]
    lo, hi = min(values), max(values)
    if floor is not None:
        lo = min(lo, floor)
    ticks = nice_ticks(lo, hi)
    y0, y1 = ticks[0], ticks[-1]
    t0, t1 = data[0][0], data[-1][0]
    span = (t1 - t0).total_seconds() or 1.0
    pw, ph = W - LEFT - RIGHT, H - TOP - BOTTOM

    def x(t: dt.datetime) -> float:
        if t1 == t0:
            return LEFT + pw / 2
        return round(LEFT + pw * (t - t0).total_seconds() / span, 1)

    def y(v: float) -> float:
        return round(TOP + ph * (1 - (v - y0) / ((y1 - y0) or 1.0)), 1)

    xs = [t0 + (t1 - t0) * i / 3 for i in range(4)] if t1 != t0 else [t0]
    fmt = "%d %b" if span >= 2 * 86400 else "%H:%M"
    return {
        "empty": False,
        "w": W,
        "h": H,
        "left": LEFT,
        "right": W - RIGHT,
        "top": TOP,
        "bottom": H - BOTTOM,
        "path": " ".join(f"{x(t)},{y(v)}" for t, v in data),
        "dots": [(x(t), y(v), f"{t:%Y-%m-%d %H:%M}  {v:g}") for t, v in data][-120:],
        "yticks": [(y(v), _label(v)) for v in ticks],
        "xticks": [(x(t), t.strftime(fmt)) for t in xs],
        "lines": [(y(v), f"{label} {v:g}") for v, label in lines],
        "marks": [x(_when(m)) for m in (marks or []) if t0 <= _when(m) <= t1],
        "last": data[-1][1],
    }
