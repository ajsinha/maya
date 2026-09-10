"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What must be true of a feature's values, checked every time they are loaded.

Most "model failures" are data failures, and the ones that hurt are not the
loads that fail — those get noticed — but the loads that succeed while being
wrong. A column that arrives 60% null because an upstream join changed, a rate
that arrives in basis points instead of percent, an identifier that stopped
being unique: each of these materialises cleanly, passes every schema check the
platform has, and is discovered a quarter later by somebody reconciling a
number.

So an assertion is a claim a person makes about the feature, in advance, and the
platform checks it on every materialisation. Four kinds and no more, because
each one has to be checkable against a column of values without knowing anything
about what the feature means:

  * `not_null`   — at most this fraction of values may be missing
  * `in_range`   — every value between these bounds
  * `in_set`     — every value one of these
  * `unique`     — at most this fraction may be duplicates

**Assertions live on the FEATURE, not the view.** A null rate that is
unacceptable in one table is unacceptable in the next, and an assertion attached
to a view would have to be restated every time somebody built another one —
which is how assertions stop being restated.

**A failing load is quarantined, not rejected.** The rows are written, the
version is recorded, and the report says exactly which assertion failed and by
how much. Deleting the evidence of a bad load is how nobody finds out what
arrived; refusing the write outright loses the same thing and additionally
leaves the operator with nothing to look at. What quarantine buys is that
nothing may *pin* it — a featureset that could bind a quarantined version would
make every assertion advisory.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import logging

from core.features.common import FeatureError
from core.log import get_logger, swallowed

logger = get_logger(__name__)

#: The four kinds. Closed, because each has to be checkable against a column of
#: values with no knowledge of what the feature means, and an open list would
#: become a place to put prose.
KINDS: Tuple[str, ...] = ("not_null", "in_range", "in_set", "unique")

KIND_MEANING: Dict[str, str] = {
    "not_null": "at most `max_null_rate` of the values may be missing. The "
                "default is zero: a feature that may be null usually says so, "
                "and one that says nothing usually should not be",
    "in_range": "every value lies between `minimum` and `maximum`. This is the "
                "one that catches a unit change — a rate arriving in basis "
                "points instead of percent is still a number, and every other "
                "check passes",
    "in_set": "every value is one of `allowed`. For a categorical whose "
              "vocabulary is meant to be closed, and where a new member is "
              "usually an upstream change nobody mentioned",
    "unique": "at most `max_duplicate_rate` of the values repeat. An "
              "identifier that stopped being unique breaks a join somewhere "
              "downstream and never breaks it here",
}


def validate(assertions: Optional[Sequence[Dict[str, Any]]]
             ) -> List[Dict[str, Any]]:
    """Check the shape of declared assertions, and fill in their defaults.

    Refused rather than ignored, because an assertion the platform silently
    dropped would be one somebody believes is running.
    """
    out: List[Dict[str, Any]] = []
    for raw in assertions or ():
        if not isinstance(raw, dict):
            raise FeatureError("an assertion must be an object with a 'kind'")
        kind = raw.get("kind")
        if kind not in KINDS:
            raise FeatureError(
                f"'{kind}' is not a kind of assertion; the four are "
                f"{', '.join(KINDS)} — each checkable against a column of "
                f"values without knowing what the feature means, which is why "
                f"the list is closed")
        made: Dict[str, Any] = {"kind": kind}
        if kind == "not_null":
            made["max_null_rate"] = float(raw.get("max_null_rate", 0.0))
        elif kind == "in_range":
            low, high = raw.get("minimum"), raw.get("maximum")
            if low is None and high is None:
                raise FeatureError(
                    "an 'in_range' assertion with neither a minimum nor a "
                    "maximum asserts nothing")
            if low is not None and high is not None and float(low) > float(high):
                raise FeatureError(
                    f"an 'in_range' assertion with minimum {low} above maximum "
                    f"{high} can never hold, so every load would quarantine")
            made["minimum"] = None if low is None else float(low)
            made["maximum"] = None if high is None else float(high)
        elif kind == "in_set":
            allowed = list(raw.get("allowed") or ())
            if not allowed:
                raise FeatureError(
                    "an 'in_set' assertion with an empty set can never hold")
            made["allowed"] = allowed
        else:
            made["max_duplicate_rate"] = float(raw.get("max_duplicate_rate", 0.0))
        if raw.get("note"):
            made["note"] = str(raw["note"])
        out.append(made)
    return out


def evaluate(assertion: Dict[str, Any],
             values: Sequence[Any]) -> Dict[str, Any]:
    """Check one assertion against one column. Returns the verdict and the number.

    The number matters as much as the verdict. *`balance` failed not_null* sends
    somebody to look; *`balance` is 61% null against a limit of 1%* tells them
    what happened before they get there.
    """
    total = len(values)
    kind = assertion["kind"]
    if total == 0:
        # An empty column cannot violate anything, and reporting it as a pass
        # would be the wrong kind of reassuring — so it is a pass that says so.
        return {"kind": kind, "passed": True, "observed": None,
                "detail": "no rows to check"}

    if kind == "not_null":
        missing = sum(1 for v in values if v is None)
        rate = missing / total
        limit = assertion["max_null_rate"]
        return {"kind": kind, "passed": rate <= limit, "observed": round(rate, 6),
                "limit": limit,
                "detail": f"{missing} of {total} values are null "
                          f"({rate:.1%}); the limit is {limit:.1%}"}

    if kind == "in_range":
        low, high = assertion.get("minimum"), assertion.get("maximum")
        outside = []
        for value in values:
            if value is None:
                continue                    # nulls are `not_null`'s business
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                # Not a number at all, in a column asserted to lie in a range.
                # Counted as outside, which is the safe direction: a string
                # where a rate should be is exactly what this assertion is for.
                swallowed(logger, exc, "counted a non-numeric value as out of range",
                          detail=f"{value!r} would not convert to a number",
                          level=logging.DEBUG)
                outside.append(value)
                continue
            if (low is not None and number < low) or \
               (high is not None and number > high):
                outside.append(value)
        rate = len(outside) / total
        return {"kind": kind, "passed": not outside,
                "observed": round(rate, 6), "offending_examples": outside[:5],
                "detail": (f"{len(outside)} of {total} values fall outside "
                           f"[{low}, {high}]"
                           if outside else
                           f"every value lies within [{low}, {high}]")}

    if kind == "in_set":
        allowed = set(map(str, assertion["allowed"]))
        strangers = sorted({str(v) for v in values
                            if v is not None and str(v) not in allowed})
        return {"kind": kind, "passed": not strangers,
                "observed": len(strangers), "offending_examples": strangers[:5],
                "detail": (f"{len(strangers)} value(s) outside the declared "
                           f"set: {', '.join(strangers[:5])}"
                           if strangers else
                           "every value is one of the declared set")}

    present = [v for v in values if v is not None]
    seen: List[Any] = []
    duplicates = 0
    for value in present:
        try:
            if value in seen:
                duplicates += 1
            else:
                seen.append(value)
        except (TypeError, ValueError) as exc:
            # Unhashable or incomparable: counted as distinct, which
            # UNDER-reports duplicates. Said out loud because the safe
            # direction here is arguable and this one was chosen so that a
            # shaped feature does not quarantine every load.
            swallowed(logger, exc, "counted an incomparable value as distinct",
                      detail="a shaped feature's values do not compare; "
                             "duplicates are under-reported rather than "
                             "quarantining every load",
                      level=logging.DEBUG)
            seen.append(value)
    rate = duplicates / len(present) if present else 0.0
    limit = assertion["max_duplicate_rate"]
    return {"kind": kind, "passed": rate <= limit, "observed": round(rate, 6),
            "limit": limit,
            "detail": f"{duplicates} of {len(present)} non-null values repeat "
                      f"({rate:.1%}); the limit is {limit:.1%}"}


def check(rows: Sequence[Dict[str, Any]],
          by_feature: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Every declared assertion, against the rows about to be recorded.

    Returns a report and a verdict. The verdict quarantines the version; the
    report is what somebody reads at three in the morning, so it names the
    feature, the assertion and the number rather than saying that quality
    checks failed.
    """
    results: Dict[str, List[Dict[str, Any]]] = {}
    failures: List[str] = []
    for name, assertions in sorted(by_feature.items()):
        if not assertions:
            continue
        values = [r.get(name) for r in rows]
        verdicts = [evaluate(a, values) for a in assertions]
        results[name] = verdicts
        for verdict in verdicts:
            if not verdict["passed"]:
                failures.append(f"{name}: {verdict['detail']}")
    checked = sum(len(v) for v in results.values())
    return {
        "checked": checked, "features": results,
        "failed": failures, "passed": not failures,
        "detail": (f"{checked} assertion(s) checked; all held" if not failures
                   else f"{len(failures)} of {checked} assertion(s) failed — "
                        + "; ".join(failures[:3])
                        + (f"; and {len(failures) - 3} more"
                           if len(failures) > 3 else "")),
    }
