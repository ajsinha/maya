"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The value the model was trained on, and the value it was actually given.

`core/features/serving.py` already holds engines to `L-17` at the level of
**namespaces**: what was served must be what the contract pinned. This is the
level below — the value itself, for one entity at one moment — and it is the
level where the damaging kind of skew lives.

**MAYA does not hold the online store, and building one to satisfy this would
put the platform on the serving path**, which `docs/10 §7` says in as many words
it must never be. So the shape is the same as everywhere else: the engine says
what it served, and MAYA compares it against what the offline store says. The
platform does not perform the act; it holds whoever did to what they said.

**The finding this makes possible is the one that matters, and it needs both
clocks.** Skew is almost never *the two stores disagree*. It is that **the two
stores were asked different questions**: the online store answered *what is the
value now*, and training asked *what was the value knowable at the moment of the
decision*. Those agree on most rows and diverge exactly on the ones where
something arrived late — which is to say, on the interesting ones.

A bitemporal store can tell those apart, and this does:

  * **agrees** — the served value is what was knowable at the decision time.
  * **future_value** — the served value describes a state of the world *after*
    the decision; it was not true yet. The classic point-in-time bug, and the
    most damaging kind because every backtest looked fine: the model was trained
    on what was knowable and served tomorrow's value.
  * **late_arrival** — the served value *was* true before the decision and did
    not **arrive** until afterwards, so the online store answered with something
    the decision path could not legitimately have had. The subtler leak, and the
    one the second clock exists to make visible: an event-time-only store cannot
    tell this from a correct answer.
  * **stale** — the served value matches an *older* offline value. The online
    store did not get the update. The ordinary kind, and the one everybody
    already looks for.
  * **unmatched** — the served value matches nothing the offline store has. The
    two are computing different things, which is the worst case and the one a
    freshness SLA would never catch.

**A freshness SLA is not skew detection**, and conflating them is the common
error. Freshness answers *how old is the online value*; only the comparison above
answers *is it the value the model was trained to expect*, and a perfectly fresh
online store computing a subtly different feature passes every freshness check
ever written.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.features.common import FeatureError
from core.log import get_logger

logger = get_logger(__name__)

VALID_TIME, INGEST_TIME = "event_ts", "ingest_ts"

AGREES = "agrees"
FUTURE_VALUE = "future_value"
LATE_ARRIVAL = "late_arrival"
STALE = "stale"
UNMATCHED = "unmatched"
UNKNOWN = "unknown"

#: What each verdict means and how bad it is. The ranking matters: `leaked` and
#: `point_in_time` are worse than `stale` and are the two nobody looks for.
VERDICTS: Dict[str, Dict[str, str]] = {
    AGREES: {"severity": "none",
             "means": "the served value is what was knowable at the decision "
                      "time, which is what the model was trained to expect"},
    FUTURE_VALUE: {
        "severity": "high",
        "means": "the served value describes a state of the world AFTER the "
                 "decision — it was not true yet. The classic point-in-time "
                 "bug, and the most damaging kind because every backtest "
                 "looked fine: the model was trained on what was knowable and "
                 "served tomorrow's value"},
    LATE_ARRIVAL: {
        "severity": "high",
        "means": "the served value was true before the decision and did not "
                 "ARRIVE until afterwards, so the online store answered with "
                 "something the decision path could not legitimately have had. "
                 "The subtler leak, and the one the second clock exists to "
                 "make visible — an event-time-only store cannot tell this "
                 "from a correct answer"},
    STALE: {"severity": "medium",
            "means": "the served value matches an older offline value, so the "
                     "online store did not get the update. The ordinary kind, "
                     "and the one everybody already looks for"},
    UNMATCHED: {
        "severity": "high",
        "means": "the served value matches nothing the offline store holds for "
                 "this entity. The two are computing different things, which "
                 "is the worst case and the one a freshness SLA would never "
                 "catch"},
    UNKNOWN: {"severity": "none",
              "means": "the offline store has no row for this entity at all, "
                       "so there is nothing to compare against — a different "
                       "fact from agreement"},
}

#: How close two floats must be to count as the same value. Loose enough that
#: a float32 online store and a float64 offline one agree, tight enough that a
#: genuinely different computation does not.
TOLERANCE = 1e-6


def _same(a: Any, b: Any) -> bool:
    """Whether two values are the same value.

    Numeric comparison is filtered rather than caught: a feature column can
    hold a string or a category beside its numbers, and a handler here would
    fire per row per comparison — a control nobody reads drowning the one they
    do. Non-numeric values fall through to equality, which is the right test
    for them anyway.
    """
    if a is None or b is None:
        return a is b
    numeric = (isinstance(a, (int, float)) and not isinstance(a, bool)
               and isinstance(b, (int, float)) and not isinstance(b, bool))
    if not numeric:
        return a == b
    left, right = float(a), float(b)
    scale = max(abs(left), abs(right), 1.0)
    return abs(left - right) / scale <= TOLERANCE


class SkewDetector:
    """Compares what an engine says it served against both offline clocks."""

    def __init__(self, evidence=None):
        self.evidence = evidence

    # -------------------------------------------------------------- compare
    def compare(self, rows: Sequence[Dict[str, Any]], column: str,
                served: Any, at: float,
                now: Optional[float] = None) -> Dict[str, Any]:
        """One served value against the offline history for that entity.

        `rows` are the offline observations for one entity, each with both
        clocks. Everything below is decided from those two columns, which is
        what makes the point-in-time and leakage cases separable at all.
        """
        moment = now if now is not None else time.time()
        history = [r for r in rows if r.get(column) is not None]
        if not history:
            return self._verdict(UNKNOWN, served, None, at)

        knowable = [r for r in history
                    if (r.get(VALID_TIME) is None or r[VALID_TIME] <= at)
                    and (r.get(INGEST_TIME) is None or r[INGEST_TIME] <= at)]
        expected = self._latest(knowable, column)

        if knowable and _same(served, expected):
            return self._verdict(AGREES, served, expected, at)

        # Everything the offline store knows NOW, which is what an online store
        # that ignores the decision time would have answered with.
        current = self._latest(
            [r for r in history
             if (r.get(VALID_TIME) is None or r[VALID_TIME] <= moment)
             and (r.get(INGEST_TIME) is None or r[INGEST_TIME] <= moment)],
            column)
        if current is not None and _same(served, current):
            # It matches today's value, so it was not knowable then. WHICH kind
            # of leak depends on the EVENT clock: a value that was not yet true
            # is tomorrow's value, and a value that was true but had not arrived
            # is one the decision path could not legitimately have had. Both are
            # leakage; only a bitemporal store can tell them apart, and they
            # have different causes and different fixes.
            source = self._row_for(history, column, served) or {}
            not_yet_true = (source.get(VALID_TIME) or 0) > at
            return self._verdict(
                FUTURE_VALUE if not_yet_true else LATE_ARRIVAL,
                served, expected, at,
                matched_event=source.get(VALID_TIME),
                matched_ingest=source.get(INGEST_TIME))

        older = self._row_for(knowable, column, served)
        if older is not None:
            return self._verdict(STALE, served, expected, at,
                                 matched_event=(older or {}).get(VALID_TIME))
        return self._verdict(UNMATCHED, served, expected, at)

    @staticmethod
    def _latest(rows: Sequence[Dict[str, Any]], column: str) -> Any:
        """The most recently true value among these, by event time."""
        if not rows:
            return None
        best = max(rows, key=lambda r: (r.get(VALID_TIME) or 0,
                                        r.get(INGEST_TIME) or 0))
        return best.get(column)

    @staticmethod
    def _row_for(rows: Sequence[Dict[str, Any]], column: str,
                 value: Any) -> Optional[Dict[str, Any]]:
        for row in rows:
            if _same(row.get(column), value):
                return row
        return None

    @staticmethod
    def _verdict(kind: str, served: Any, expected: Any, at: float,
                 **extra: Any) -> Dict[str, Any]:
        spec = VERDICTS[kind]
        return {"verdict": kind, "severity": spec["severity"],
                "means": spec["means"], "served": served,
                "expected_at_decision": expected, "at": at, **extra,
                "detail": (f"served {served!r} where the value knowable at the "
                           f"decision was {expected!r}: {spec['means']}"
                           if kind != AGREES else
                           f"served {served!r}, which is what was knowable "
                           f"then")}

    # ---------------------------------------------------------------- batch
    def observe(self, observations: Sequence[Dict[str, Any]], *,
                urn: str = "", column: str = "value",
                now: Optional[float] = None,
                actor: str = "system") -> Dict[str, Any]:
        """A batch of served values, each with the offline history behind it.

        Each observation is `{"entity": ..., "at": ..., "served": ...,
        "history": [...]}`. The engine supplies what it served; the history
        comes from the offline store, so nothing here is taken on the engine's
        word except the one thing only the engine knows.
        """
        if not observations:
            raise FeatureError(
                "nothing to compare: a skew check over no observations reports "
                "no skew, which is the same answer as a clean estate and a "
                "different fact")
        results: List[Dict[str, Any]] = []
        by_verdict: Dict[str, int] = {}
        for row in observations:
            verdict = self.compare(row.get("history") or (), column,
                                   row.get("served"), row.get("at") or 0.0,
                                   now)
            results.append({"entity": row.get("entity"), **verdict})
            by_verdict[verdict["verdict"]] = by_verdict.get(
                verdict["verdict"], 0) + 1

        serious = [r for r in results if r["severity"] == "high"]
        if self.evidence is not None and urn:
            with self.evidence.recording():
                self.evidence.append(
                    "skew_checked", "model", urn,
                    {"observations": len(results),
                     "by_verdict": by_verdict,
                     "serious": len(serious)}, actor=actor)
        return {
            "observations": len(results), "results": results,
            "by_verdict": by_verdict, "serious": len(serious),
            "verdicts": {k: v for k, v in VERDICTS.items()},
            "detail": self._detail(results, by_verdict, serious),
        }

    @staticmethod
    def _detail(results, by_verdict, serious) -> str:
        if not serious:
            return (f"{len(results)} observation(s) compared and none diverged "
                    f"seriously. Note what this is NOT: a freshness check. "
                    f"Freshness answers *how old is the online value*, and a "
                    f"perfectly fresh store computing a subtly different "
                    f"feature passes every freshness check ever written")
        kinds = sorted({r["verdict"] for r in serious})
        out = (f"{len(serious)} of {len(results)} observation(s) diverged "
               f"seriously: {', '.join(kinds)}")
        if FUTURE_VALUE in kinds or LATE_ARRIVAL in kinds:
            out += (". Those are the two nobody looks for. A stale value is "
                    "visible to any freshness check; a value that is correct "
                    "TODAY but was not knowable at the decision is invisible "
                    "to all of them, and every backtest of that model looked "
                    "fine")
        return out
