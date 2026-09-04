"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Aligning a featureset onto a common axis.

Features arrive on their own clocks. A balance is monthly, a rating is annual, a
market price is daily and misses weekends, and a consumer joining them gets a
ragged frame full of holes it has to reason about. Aligning them onto one axis —
usually a date — and filling the gaps by a stated rule gives an execution engine
a rectangle instead, which is a far easier thing to be handed.

Three fill rules, and **they are not equivalent**:

- **flat forward** carries the last observation forward. It uses only what had
  already happened, and it is the only one of the three that is safe for training.
- **flat backward** carries the next observation back. To fill a gap in March it
  reaches for an observation from April.
- **linear** interpolates between the neighbours on each side. It reaches for
  April as well, and dresses the result up as a smooth line.

The last two are leakage. Not a policy against them — they are the right answer
for drawing a curve, for a backtest that is explicitly retrospective, for
presenting a history to a person — but a model trained on a back-filled column
has been shown values that did not exist when the row it is learning from was
scored.

So this platform does not refuse them. **It stamps them honestly**, and lets the
machinery that is already here do the work: a value derived from a later
observation inherits that observation's ``ingest_ts``, because that is genuinely
when it became knowable. A point-in-time read at the grid point then excludes it
by the ordinary rule, without anybody having to remember a flag.

That is the whole design. The leakage is not caught by a check; it is made
arithmetically impossible to hide, by recording when each filled value actually
became available.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core.features.common import ENTITY, INGEST_TIME, VALID_TIME, FeatureError
from core.features.preparation import is_missing
from core.log import get_logger

logger = get_logger(__name__)

NONE, FORWARD, BACKWARD, LINEAR, NEAREST = (
    "none", "flat_forward", "flat_backward", "linear", "nearest")
RULES: Tuple[str, ...] = (NONE, FORWARD, BACKWARD, LINEAR, NEAREST)

RULE_MEANING: Dict[str, str] = {
    NONE: "leave the gap; the row exists on the grid with no value",
    FORWARD: "carry the last observation forward — uses only what had happened",
    BACKWARD: "carry the next observation back — reaches into the future",
    LINEAR: "interpolate between the neighbours — reaches into the future",
    NEAREST: "take whichever neighbour is closer — reaches into the future when "
             "the closer one is ahead",
}

# Rules that can only be satisfied by an observation later than the gap.
LOOKS_AHEAD: frozenset = frozenset({BACKWARD, LINEAR, NEAREST})

OBSERVED, REGULAR, EXPLICIT = "observed", "regular", "explicit"
GRIDS: Tuple[str, ...] = (OBSERVED, REGULAR, EXPLICIT)

MAX_GRID = 100_000


def grid_for(rows: Sequence[Dict[str, Any]], axis: str,
             kind: str = OBSERVED, start: Optional[float] = None,
             stop: Optional[float] = None, step: Optional[float] = None,
             points: Optional[Sequence[float]] = None) -> List[float]:
    """The axis every entity is put onto."""
    if kind not in GRIDS:
        raise FeatureError(f"'{kind}' is not a grid; expected one of "
                           f"{', '.join(GRIDS)}")
    if kind == EXPLICIT:
        if not points:
            raise FeatureError("an explicit grid needs its points")
        out = sorted({float(p) for p in points})
    elif kind == REGULAR:
        if step is None or step <= 0:
            raise FeatureError(
                "a regular grid needs a positive step; a step of zero is not a "
                "spacing and a negative one is not an order")
        observed = [float(r[axis]) for r in rows if r.get(axis) is not None]
        lo = start if start is not None else (min(observed) if observed else 0.0)
        hi = stop if stop is not None else (max(observed) if observed else lo)
        if hi < lo:
            raise FeatureError("the grid ends before it begins")
        count = int((hi - lo) // step) + 1
        if count > MAX_GRID:
            raise FeatureError(
                f"that grid has {count:,} points; the limit is {MAX_GRID:,}. a "
                f"finer grid than the data does not add information, it adds "
                f"rows")
        out = [lo + i * step for i in range(count)]
    else:
        out = sorted({float(r[axis]) for r in rows if r.get(axis) is not None})
    if len(out) > MAX_GRID:
        raise FeatureError(f"the grid has {len(out):,} points; the limit is "
                           f"{MAX_GRID:,}")
    return out


def align(rows: Sequence[Dict[str, Any]], columns: Sequence[str],
          axis: str = VALID_TIME, rule: str = FORWARD,
          grid: Optional[Sequence[float]] = None,
          entity: str = ENTITY, limit: Optional[float] = None
          ) -> Dict[str, Any]:
    """Put every entity on the same axis and fill the gaps by a stated rule.

    ``limit`` bounds how far a value may be carried: a balance from eighteen
    months ago is not this month's balance, and carrying it forever turns a
    stale observation into a fabricated one.
    """
    if rule not in RULES:
        raise FeatureError(f"'{rule}' is not a fill rule; expected one of "
                           f"{', '.join(RULES)}")
    points = list(grid) if grid is not None else grid_for(rows, axis)
    if not points:
        return {"rows": [], "grid": [], "rule": rule, "axis": axis,
                "filled": 0, "carried_beyond_limit": 0,
                "point_in_time_safe": rule not in LOOKS_AHEAD,
                "detail": "there is nothing on this axis to align"}

    by_entity: Dict[Any, List[Dict[str, Any]]] = {}
    for row in rows:
        if row.get(axis) is None:
            continue
        by_entity.setdefault(row.get(entity), []).append(row)

    out: List[Dict[str, Any]] = []
    filled = beyond = 0
    for key, observations in by_entity.items():
        observations.sort(key=lambda r: float(r[axis]))
        for point in points:
            row, made, stale = _at(observations, point, columns, axis, rule, limit)
            row[entity], row[axis] = key, point
            filled += made
            beyond += stale
            out.append(row)
    return {
        "rows": out, "grid": points, "axis": axis, "rule": rule,
        "entities": len(by_entity), "filled": filled,
        "carried_beyond_limit": beyond,
        "point_in_time_safe": rule not in LOOKS_AHEAD,
        "detail": _detail(rule, len(points), len(by_entity), filled, beyond),
    }


def _at(observations: List[Dict[str, Any]], point: float,
        columns: Sequence[str], axis: str, rule: str,
        limit: Optional[float]) -> Tuple[Dict[str, Any], int, int]:
    """One row of the aligned frame, with an honest ingest stamp."""
    exact = next((o for o in observations if float(o[axis]) == point), None)
    if exact is not None:
        return dict(exact), 0, 0

    before = [o for o in observations if float(o[axis]) < point]
    after = [o for o in observations if float(o[axis]) > point]
    row: Dict[str, Any] = {}
    made = stale = 0
    # The clock starts at the grid point and moves FORWARD as sources are used.
    # A value taken from a later observation was not knowable at the grid point,
    # and this is where that becomes a recorded fact rather than an opinion.
    known_at = point

    for column in columns:
        source, why = _source(before, after, column, axis, rule, point, limit)
        if source is None:
            row[column] = None
            continue
        if why == "beyond_limit":
            row[column] = None
            stale += 1
            continue
        if isinstance(source, tuple):                     # linear: two sources
            low, high = source
            row[column] = _interpolate(low, high, column, axis, point)
            known_at = max(known_at, float(low.get(INGEST_TIME) or point),
                           float(high.get(INGEST_TIME) or point))
        else:
            row[column] = source[column]
            known_at = max(known_at, float(source.get(INGEST_TIME) or point))
        made += 1
    row[INGEST_TIME] = known_at
    return row, made, stale


def _source(before: List[Dict[str, Any]], after: List[Dict[str, Any]],
            column: str, axis: str, rule: str, point: float,
            limit: Optional[float]):
    """Which observation, if any, answers for this column at this point."""
    if rule == NONE:
        return None, "none"
    previous = next((o for o in reversed(before)
                     if not is_missing(o.get(column))), None)
    following = next((o for o in after if not is_missing(o.get(column))), None)

    if rule == FORWARD:
        if previous is None:
            return None, "no_prior"
        if limit is not None and point - float(previous[axis]) > limit:
            return previous, "beyond_limit"
        return previous, "carried"
    if rule == BACKWARD:
        if following is None:
            return None, "no_following"
        if limit is not None and float(following[axis]) - point > limit:
            return following, "beyond_limit"
        return following, "carried_back"
    if rule == NEAREST:
        candidates = [c for c in (previous, following) if c is not None]
        if not candidates:
            return None, "no_neighbour"
        closest = min(candidates, key=lambda o: abs(float(o[axis]) - point))
        if limit is not None and abs(float(closest[axis]) - point) > limit:
            return closest, "beyond_limit"
        return closest, "nearest"
    if rule == LINEAR:
        if previous is None or following is None:
            # Interpolation needs a point on each side. Extrapolating from one
            # is a different act with a different error, and doing it silently
            # under the name of interpolation would hide which was done.
            return None, "not_between"
        if limit is not None and (float(following[axis]) -
                                  float(previous[axis])) > limit:
            return previous, "beyond_limit"
        return (previous, following), "interpolated"
    return None, "none"


def _interpolate(low: Dict[str, Any], high: Dict[str, Any], column: str,
                 axis: str, point: float) -> Any:
    x0, x1 = float(low[axis]), float(high[axis])
    y0, y1 = low[column], high[column]
    if x1 == x0:
        return y0
    weight = (point - x0) / (x1 - x0)
    if isinstance(y0, (list, tuple)) and isinstance(y1, (list, tuple)):
        if len(y0) != len(y1):
            raise FeatureError(
                f"'{column}' has {len(y0)} entries at one end and {len(y1)} at "
                f"the other; interpolating between vectors of different length "
                f"would have to invent a correspondence")
        return [a + (b - a) * weight for a, b in zip(y0, y1)]
    return y0 + (y1 - y0) * weight


def _detail(rule: str, points: int, entities: int, filled: int,
            beyond: int) -> str:
    base = (f"{entities:,} entities on a grid of {points:,} points; "
            f"{filled:,} values filled by {rule}")
    if beyond:
        base += (f"; {beyond:,} left empty because carrying them further would "
                 f"have turned a stale observation into a fabricated one")
    if rule in LOOKS_AHEAD:
        base += (". this rule fills from observations later than the gap, so the "
                 "filled values carry the ingest time at which they actually "
                 "became knowable — a point-in-time read at the grid point "
                 "excludes them, which is correct and is the point")
    return base


def describe() -> Dict[str, Any]:
    return {
        "rules": [{"rule": r, "means": RULE_MEANING[r],
                   "point_in_time_safe": r not in LOOKS_AHEAD} for r in RULES],
        "grids": list(GRIDS),
        "default_axis": VALID_TIME,
        "why_not_refused": "back-fill and interpolation are the right answer for "
                           "drawing a curve or for an explicitly retrospective "
                           "backtest. they are wrong for training, and rather "
                           "than forbidding them the platform stamps each filled "
                           "value with the ingest time at which it actually "
                           "became knowable — so an ordinary point-in-time read "
                           "excludes them without anybody remembering a flag",
        "limit": "a carry limit bounds how far an observation may travel; a "
                 "balance from eighteen months ago is not this month's balance",
    }
