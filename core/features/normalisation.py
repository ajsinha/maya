"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Point-in-time normalisation.

Normalising a feature needs statistics — a mean, a spread, a range — and where
those statistics come from decides whether the result is usable or quietly
worthless.

Computing them over the whole column is the ordinary way, and it is **leakage**.
A z-score fitted on the full history encodes what the mean turned out to be,
including the part of the history that had not happened when the row was scored.
A model trained on it performs beautifully in back-test and disappoints in
production, and the reason is invisible because the column looks unremarkable.

So the statistics are fitted from what was **knowable at a stated moment**:

    event_ts <= as_of  AND  ingest_ts <= as_of

Both clocks, exactly as the point-in-time assembly rule reads, because the same
argument applies. A request with no ``as_of`` is refused rather than served from
the full column — the leaky answer is the one somebody would have got by
accident, so it is the one that must not be the default.

**The fitted statistics come back with the data.** They are not an implementation
detail: a consumer scoring one row later has to apply the *same* transform, and a
reviewer asking what was done to a column deserves an answer that is a number
rather than a method name.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.features.common import INGEST_TIME, VALID_TIME, FeatureError
from core.log import get_logger, swallowed

logger = get_logger(__name__)

NONE, ZSCORE, MINMAX, ROBUST, RANK = "none", "zscore", "minmax", "robust", "rank"
METHODS: Tuple[str, ...] = (NONE, ZSCORE, MINMAX, ROBUST, RANK)

METHOD_MEANING: Dict[str, str] = {
    NONE: "leave the values alone; stated explicitly so a request can say so",
    ZSCORE: "(x − mean) / standard deviation",
    MINMAX: "(x − min) / (max − min), onto [0, 1]",
    ROBUST: "(x − median) / interquartile range; unmoved by outliers",
    RANK: "the value's quantile within the fitting window, onto [0, 1]",
}

# Fitted from fewer rows than this, a statistic is a guess with a decimal point.
MIN_SAMPLE = 30


class Statistics:
    """The numbers a normalisation was fitted with, and how to apply them."""

    def __init__(self, method: str, params: Dict[str, Any], sample: int,
                 as_of: float, column: str, note: str = ""):
        self.method, self.params, self.sample = method, params, sample
        self.as_of, self.column, self.note = as_of, column, note

    def apply(self, value: Any) -> Any:
        if value is None or self.method == NONE:
            return value
        if isinstance(value, (list, tuple)):
            return [self.apply(v) for v in value]
        return self._scalar(float(value))

    def _scalar(self, x: float) -> Optional[float]:
        p = self.params
        if self.method == ZSCORE:
            spread = p.get("stdev") or 0.0
            return 0.0 if spread == 0 else (x - p["mean"]) / spread
        if self.method == MINMAX:
            span = (p.get("max") or 0.0) - (p.get("min") or 0.0)
            return 0.0 if span == 0 else (x - p["min"]) / span
        if self.method == ROBUST:
            spread = p.get("iqr") or 0.0
            return 0.0 if spread == 0 else (x - p["median"]) / spread
        if self.method == RANK:
            ordered = p.get("quantiles") or []
            if not ordered:
                return 0.0
            below = sum(1 for q in ordered if q <= x)
            return below / len(ordered)
        return x

    def as_dict(self) -> Dict[str, Any]:
        return {"column": self.column, "method": self.method,
                "parameters": self.params, "fitted_on": self.sample,
                "as_of": self.as_of, "note": self.note}


def fit(rows: Sequence[Dict[str, Any]], column: str, method: str,
        as_of: Optional[float]) -> Statistics:
    """Fit from what was knowable at ``as_of``, and from nothing else."""
    if method not in METHODS:
        raise FeatureError(
            f"'{method}' is not a normalisation; expected one of "
            f"{', '.join(METHODS)}")
    if method == NONE:
        return Statistics(NONE, {}, 0, as_of or 0.0, column,
                          "left alone, as asked")
    if as_of is None:
        raise FeatureError(
            f"normalising '{column}' needs an as_of. statistics fitted over the "
            f"whole column encode what the mean turned out to be, including the "
            f"part of the history that had not happened when the row was scored "
            f"— which is leakage, and it is invisible because the column looks "
            f"unremarkable afterwards")

    values = knowable(rows, column, as_of)
    if len(values) < MIN_SAMPLE:
        raise FeatureError(
            f"only {len(values)} value(s) of '{column}' were knowable at that "
            f"moment; fewer than {MIN_SAMPLE} makes a statistic a guess with a "
            f"decimal point. widen the window, or normalise later")
    return Statistics(method, _parameters(method, values), len(values),
                      as_of, column, _note(method, values))


def knowable(rows: Sequence[Dict[str, Any]], column: str,
             as_of: float) -> List[float]:
    """The values both true and known by ``as_of``. Both clocks, as ever."""
    out: List[float] = []
    for row in rows:
        if row.get(column) is None:
            continue
        if row.get(VALID_TIME) is not None and row[VALID_TIME] > as_of:
            continue
        if row.get(INGEST_TIME) is not None and row[INGEST_TIME] > as_of:
            continue
        value = row[column]
        candidates = _flatten(value) if isinstance(value, (list, tuple)) else [value]
        # A NaN is not an observation. It arrives from a division with no answer
        # or an overflow, and folding it into a mean makes the mean a NaN — which
        # then propagates through every value the statistic touches.
        out.extend(float(v) for v in candidates if _observed(v))
    return out


def _observed(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        # Not a number at all. Counted as unobserved rather than raised: a
        # single odd cell must not fail a statistic over a million rows, and
        # the fitting count in the report says how many were usable.
        swallowed(logger, exc, "read a value while fitting a statistic",
                  f"{value!r} is not a number; treated as unobserved",
                  logging.DEBUG)
        return False
    return not (math.isnan(number) or math.isinf(number))


def _flatten(value: Any) -> List[Any]:
    if not isinstance(value, (list, tuple)):
        return [value]
    out: List[Any] = []
    for item in value:
        out.extend(_flatten(item))
    return out


def _parameters(method: str, values: List[float]) -> Dict[str, Any]:
    ordered = sorted(values)
    n = len(ordered)
    if method == ZSCORE:
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / max(n - 1, 1)
        return {"mean": mean, "stdev": math.sqrt(variance)}
    if method == MINMAX:
        return {"min": ordered[0], "max": ordered[-1]}
    if method == ROBUST:
        q1, median, q3 = (_quantile(ordered, q) for q in (0.25, 0.5, 0.75))
        return {"median": median, "q1": q1, "q3": q3, "iqr": q3 - q1}
    if method == RANK:
        # A sample of the fitting distribution rather than all of it: a hundred
        # points place a value to a percentile, and carrying a million would
        # make the statistics larger than the data they describe.
        step = max(n // 100, 1)
        return {"quantiles": ordered[::step][:100]}
    return {}


def _quantile(ordered: List[float], q: float) -> float:
    if not ordered:
        return 0.0
    position = q * (len(ordered) - 1)
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[int(position)]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _note(method: str, values: List[float]) -> str:
    if method == ZSCORE:
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / max(len(values) - 1, 1)
        if variance == 0:
            return ("the column is constant over the fitting window, so every "
                    "normalised value is zero; that is arithmetic rather than a "
                    "failure, and it is worth knowing")
    if method == MINMAX and values and min(values) == max(values):
        return ("the column has no range over the fitting window, so every "
                "normalised value is zero")
    return f"fitted on {len(values):,} values knowable at the stated moment"


def normalise(rows: Sequence[Dict[str, Any]], spec: Dict[str, str],
              as_of: Optional[float]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Apply a per-column normalisation, returning the rows and what was fitted.

    The statistics are returned because they are part of the answer: whoever
    scores one row tomorrow has to apply the same transform, and whoever reviews
    this wants a number rather than the name of a method.
    """
    if not spec:
        return list(rows), {}
    fitted = {column: fit(rows, column, method, as_of)
              for column, method in spec.items() if method != NONE}
    if not fitted:
        return list(rows), {}
    out = []
    for row in rows:
        changed = dict(row)
        for column, stats in fitted.items():
            if column in changed:
                changed[column] = stats.apply(changed[column])
        out.append(changed)
    return out, {c: s.as_dict() for c, s in fitted.items()}


def describe() -> Dict[str, Any]:
    """What is on offer, and why the as_of is not optional."""
    return {
        "methods": [{"method": m, "means": METHOD_MEANING[m]} for m in METHODS],
        "rule": f"statistics are fitted from rows where {VALID_TIME} <= as_of "
                f"and {INGEST_TIME} <= as_of, and from nothing else",
        "why": "a statistic fitted over the whole column encodes what the mean "
               "turned out to be, including the part of the history that had not "
               "happened when the row was scored. that is leakage, and it is "
               "invisible afterwards because the column looks unremarkable",
        "as_of_required": True,
        "min_sample": MIN_SAMPLE,
        "returns": "the fitted statistics travel with the data, so the same "
                   "transform can be applied to one row later and a reviewer can "
                   "see a number rather than a method name",
    }
