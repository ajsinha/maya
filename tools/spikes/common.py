"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What every spike result has to carry.

A latency figure with no conditions attached is a number somebody will quote in
a different context and be wrong about. So each result records the machine, the
interpreter, the store and the size it ran at — not as metadata, but as the
part that makes the number mean anything.

The percentiles are computed the boring way, over the whole sample held in
memory. A streaming estimator would be the right choice for a production
metrics pipeline and the wrong one here: a spike runs once, its sample fits, and
an approximation in the thing that exists to produce a *result* is exactly the
wrong place to save memory.
"""
from __future__ import annotations

import platform
import sys
from typing import Any, Dict, List, Sequence


def conditions(**extra: Any) -> Dict[str, Any]:
    """The machine this ran on. Part of the result, not decoration."""
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": _cpus(),
        **extra,
        "note": ("a measurement on this machine under this load. Not a "
                 "capacity plan: a single-process figure extrapolated to an "
                 "estate is arithmetic rather than evidence"),
    }


def _cpus() -> int:
    try:
        import os
        return len(os.sched_getaffinity(0))      # what this process may use
    except (AttributeError, OSError):            # pragma: no cover - platform
        import os
        return os.cpu_count() or 0


def percentiles(samples: Sequence[float]) -> Dict[str, float]:
    """p50/p95/p99 and the ends, in milliseconds.

    `max` is reported beside p99 deliberately. A p99 is a promise about ninety-
    nine percent of calls, and the hundredth is the one that times out a
    caller's scoring loop — reporting only the percentile is how a tail gets
    lost.
    """
    if not samples:
        return {}
    ordered = sorted(samples)
    return {
        "count": len(ordered),
        "p50_ms": round(_at(ordered, 0.50) * 1000, 3),
        "p95_ms": round(_at(ordered, 0.95) * 1000, 3),
        "p99_ms": round(_at(ordered, 0.99) * 1000, 3),
        "min_ms": round(ordered[0] * 1000, 3),
        "max_ms": round(ordered[-1] * 1000, 3),
        "mean_ms": round(sum(ordered) / len(ordered) * 1000, 3),
    }


def _at(ordered: List[float], quantile: float) -> float:
    index = min(round(quantile * (len(ordered) - 1)), len(ordered) - 1)
    return ordered[index]


def against(measured: Dict[str, float], target_ms: float,
            what: str) -> Dict[str, Any]:
    """The measurement beside the target it was written against.

    Both, and the verdict — not a pass/fail. A spike that printed only PASS
    would be a control reporting on itself, and the useful thing about a number
    close to its target is that it is close.
    """
    if not measured:
        return {"target_ms": target_ms, "met": None,
                "detail": "nothing was measured"}
    p99 = measured["p99_ms"]
    met = p99 <= target_ms
    return {
        "target_ms": target_ms, "measured_p99_ms": p99, "met": met,
        "headroom_ms": round(target_ms - p99, 3),
        "detail": (
            f"{what}: p99 {p99} ms against a target of {target_ms} ms"
            + (f", {round(target_ms - p99, 3)} ms of headroom"
               if met else
               f" — OVER by {round(p99 - target_ms, 3)} ms")
            + f". The slowest single call was {measured['max_ms']} ms, which "
              f"is the one that times out somebody's scoring loop and is not "
              f"in the p99"),
    }
