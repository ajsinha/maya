"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Missing values, and the order things happen in.

A caller retrieving features can ask MAYA to fill the gaps and to normalise. Both
are ordinary requests and both are easy to get subtly wrong, so the platform does
them rather than leaving each consumer to.

**Missing is not one thing.** A null, a NaN and an infinity arrive by different
routes — no observation, a division that had no answer, an overflow — and all
three are unusable. They are treated alike here, and counted separately from each
other only where that helps somebody diagnose the source.

**A fill rate is part of the answer.** Filling forty per cent of a column with
zeros produces a model that trains without complaint and means nothing. The
report says how much of each column was invented, and says so loudly past a
threshold, because the number nobody sees is the one that does the damage.

**Statistics are fitted at a stated moment**, exactly as normalisation is: a
median computed over the whole column is the median it turned out to be, and
using it to fill a row from three years ago puts the future into the past.

**The order is: fit, then fill, then normalise.** It has to be. Fitting the
normalisation on imputed values would shrink the spread by exactly the amount
that was invented — every filled cell sits at the centre and pulls the variance
down — so the statistics are fitted on what was *observed*, and then applied to
everything including what was filled.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.features.common import FeatureError
from core.features.normalisation import (METHOD_MEANING, METHODS, NONE,
                                         Statistics, knowable)
from core.log import get_logger

logger = get_logger(__name__)

KEEP, CONSTANT, ZERO, MEAN, MEDIAN, MOST_FREQUENT = (
    "keep", "constant", "zero", "mean", "median", "most_frequent")
STRATEGIES: Tuple[str, ...] = (KEEP, CONSTANT, ZERO, MEAN, MEDIAN, MOST_FREQUENT)

STRATEGY_MEANING: Dict[str, str] = {
    KEEP: "leave the gaps; the consumer will handle them, and says so explicitly",
    CONSTANT: "a value the caller supplies — say what it means, not just what it is",
    ZERO: "0.0, which is a constant with a common name and the same caveat",
    MEAN: "the mean of what was knowable at the stated moment",
    MEDIAN: "the median of the same, and unmoved by outliers",
    MOST_FREQUENT: "the commonest value; the only one that suits a category",
}

# Strategies that fit a statistic, and therefore need a moment to fit it at.
FITTED = frozenset({MEAN, MEDIAN, MOST_FREQUENT})

# Past this, a filled column is mostly invention and the report says so.
LOUD_FILL_RATE = 0.20


def is_missing(value: Any) -> bool:
    """Null, NaN and infinity all arrive differently and are all unusable."""
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value) or math.isinf(value)
    return False


def missing_in(value: Any) -> int:
    """How many missing numbers a cell holds — a scalar has one, a vector many."""
    if isinstance(value, (list, tuple)):
        return sum(missing_in(v) for v in value)
    return 1 if is_missing(value) else 0


def cells_in(value: Any) -> int:
    if isinstance(value, (list, tuple)):
        return sum(cells_in(v) for v in value)
    return 1


def survey(rows: Sequence[Dict[str, Any]],
           columns: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """What is missing, before anything is done about it."""
    wanted = list(columns) if columns else sorted(
        {k for row in rows for k in row})
    out: Dict[str, Any] = {}
    for column in wanted:
        total = missing = present = 0
        for row in rows:
            if column not in row:
                total += 1
                missing += 1
                continue
            value = row[column]
            total += cells_in(value)
            missing += missing_in(value)
            present += 1
        out[column] = {
            "cells": total, "missing": missing,
            "rate": round(missing / total, 4) if total else 0.0,
            "absent_rows": len(rows) - present,
        }
    return out


def _fill_value(strategy: str, constant: Any, values: List[float],
                column: str) -> Any:
    if strategy == ZERO:
        return 0.0
    if strategy == CONSTANT:
        if constant is None:
            raise FeatureError(
                f"filling '{column}' with a constant needs the constant; say "
                f"what it is, and preferably what it means")
        return constant
    if not values:
        raise FeatureError(
            f"nothing was knowable for '{column}' at that moment, so there is "
            f"no {strategy} to fill it with. a column with no observations "
            f"cannot be imputed from itself")
    if strategy == MEAN:
        return sum(values) / len(values)
    if strategy == MEDIAN:
        ordered = sorted(values)
        middle = len(ordered) // 2
        return (ordered[middle] if len(ordered) % 2
                else (ordered[middle - 1] + ordered[middle]) / 2)
    if strategy == MOST_FREQUENT:
        return max(set(values), key=values.count)
    raise FeatureError(f"'{strategy}' is not a fill strategy; expected one of "
                       f"{', '.join(STRATEGIES)}")


def _fill(value: Any, replacement: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_fill(v, replacement) for v in value]
    return replacement if is_missing(value) else value


def impute(rows: Sequence[Dict[str, Any]], spec: Dict[str, Any],
           as_of: Optional[float] = None
           ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Fill the gaps, and report how much of each column was invented."""
    if not spec:
        return list(rows), {}
    plan: Dict[str, Any] = {}
    for column, ask in spec.items():
        strategy = ask if isinstance(ask, str) else ask.get("strategy", KEEP)
        constant = None if isinstance(ask, str) else ask.get("value")
        if strategy not in STRATEGIES:
            raise FeatureError(
                f"'{strategy}' is not a fill strategy; expected one of "
                f"{', '.join(STRATEGIES)}")
        if strategy == KEEP:
            continue
        if strategy in FITTED and as_of is None:
            raise FeatureError(
                f"filling '{column}' with its {strategy} needs an as_of. the "
                f"{strategy} of the whole column is the one it turned out to be, "
                f"and using it to fill a row from three years ago puts the future "
                f"into the past")
        observed = knowable(rows, column, as_of) if strategy in FITTED else []
        plan[column] = {"strategy": strategy,
                        "value": _fill_value(strategy, constant, observed, column),
                        "fitted_on": len(observed) if strategy in FITTED else None}

    before = survey(rows, list(plan))
    out = [{**row, **{c: _fill(row.get(c), p["value"])
                      for c, p in plan.items() if c in row}}
           for row in rows]
    report = {}
    for column, p in plan.items():
        stat = before.get(column, {})
        rate = stat.get("rate", 0.0)
        report[column] = {
            **p, "filled": stat.get("missing", 0), "cells": stat.get("cells", 0),
            "rate": rate,
            "loud": rate >= LOUD_FILL_RATE,
            "detail": _fill_detail(column, p, stat, rate),
        }
        if rate >= LOUD_FILL_RATE:
            logger.warning("%.0f%% of '%s' was filled with %s; the model will "
                           "train without complaint on invented values",
                           rate * 100, column, p["strategy"])
    return out, report


def _fill_detail(column: str, plan: Dict[str, Any], stat: Dict[str, Any],
                 rate: float) -> str:
    filled = stat.get("missing", 0)
    if not filled:
        return f"nothing was missing in '{column}'"
    base = (f"{filled:,} of {stat.get('cells', 0):,} values "
            f"({rate:.1%}) filled with {plan['strategy']}")
    if rate >= LOUD_FILL_RATE:
        return (base + " — past a fifth of the column, what comes back is mostly "
                       "invention, and a model will train on it without complaint")
    return base


def prepare(rows: Sequence[Dict[str, Any]],
            fill: Optional[Dict[str, Any]] = None,
            normalise_spec: Optional[Dict[str, str]] = None,
            as_of: Optional[float] = None) -> Dict[str, Any]:
    """Fit, fill, normalise — in that order, and the order is the point.

    The normalisation statistics are fitted on what was **observed**, before
    anything is filled. Fitting them afterwards would shrink the spread by
    exactly the amount that was invented, because every filled cell sits at the
    centre and pulls the variance down.
    """
    original = list(rows)
    fitted: Dict[str, Statistics] = {}
    for column, method in (normalise_spec or {}).items():
        if method != NONE:
            from core.features.normalisation import fit
            fitted[column] = fit(original, column, method, as_of)

    filled, fill_report = impute(original, fill or {}, as_of)

    out = filled
    if fitted:
        out = [{**row, **{c: s.apply(row[c]) for c, s in fitted.items()
                          if c in row}} for row in filled]
    return {
        "rows": out, "count": len(out),
        "missing_before": survey(original,
                                 sorted(set(fill or {}) | set(fitted))),
        "filled": fill_report,
        "normalised": {c: s.as_dict() for c, s in fitted.items()},
        "as_of": as_of,
        "order": "statistics fitted on observed values, then gaps filled, then "
                 "normalisation applied to everything including what was filled",
    }


def describe() -> Dict[str, Any]:
    """What a caller may ask for on the way out."""
    return {
        "fill": [{"strategy": s, "means": STRATEGY_MEANING[s]}
                 for s in STRATEGIES],
        "normalise": [{"method": m, "means": METHOD_MEANING[m]} for m in METHODS],
        "missing": "null, NaN and infinity are all treated as missing; they "
                   "arrive by different routes and are equally unusable",
        "fitted_strategies": sorted(FITTED),
        "as_of_required_for": sorted(FITTED | {"zscore", "minmax", "robust", "rank"}),
        "loud_fill_rate": LOUD_FILL_RATE,
        "order": "fit on observed, then fill, then normalise — fitting after "
                 "filling would shrink the spread by exactly the amount that was "
                 "invented",
    }
