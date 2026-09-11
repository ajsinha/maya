"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Spike 2: the point-in-time join.

`NFR-PERF-006` asks for **a training set over 1 B rows × 500 features in under
30 minutes**, and the requirements table has said *not measured* since the first
release. That figure is the reason `docs/14 §27` lists Spark as infrastructure
the design assumes and the build does not have.

## What is measured, and what is deliberately not

The join is the whole cost. For each spine row and each source view, the
assembly picks **the latest fact true by `label_ts` and known by
`min(label_ts, as_of)`** — `TrainingSetBuilder.latest_admissible`, which is
`L-19`, the point-in-time read, executed once per row per view.

So this measures that, over a synthetic history, through the **real function**
rather than a re-implementation of it. Timing a copy of the rule would measure
the copy, and this platform's whole argument is about the difference.

What is *not* measured is the Delta read, the leakage screen, the digest and
the persist. Each is real and each scales differently — the Delta read with the
view's size rather than the spine's, the leakage screen with the sample rather
than the population — and rolling them into one number would produce a figure
that cannot be reasoned about. The join is the term that scales as
`rows x features` and it is the one the 30-minute target is about.

## The extrapolation is printed as an extrapolation

A measurement of two hundred thousand rows multiplied up to a billion is
arithmetic, not evidence. It is reported because it is the question the target
asks, and it is **labelled** because the honest thing about a linear
extrapolation of an in-memory algorithm is that the memory runs out first — a
billion rows of five hundred features does not fit in this process, and the
extrapolation is describing a program that cannot be run rather than predicting
one that can.

That is the actual finding, and it is more useful than a number: the target is
not reachable in one process at any speed, which is why the answer is a
distributed assembly and not a faster loop.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from typing import Any, Dict, List

from tools.spikes.common import conditions, percentiles

#: From `NFR-PERF-006`.
TARGET_ROWS = 1_000_000_000
TARGET_FEATURES = 500
TARGET_MINUTES = 30.0

#: Roughly what one row of one feature occupies once it is a Python dict entry
#: with a float, a key and the interpreter's overhead. Deliberately crude: it
#: is used only to say *this does not fit*, and a precise figure would invite
#: somebody to plan against it.
BYTES_PER_CELL = 100


def run(rows: int = 200_000, features: int = 50, history: int = 8,
        seed: int = 7) -> Dict[str, Any]:
    """Time the point-in-time pick over a synthetic history."""
    from core.features.assembly import TrainingSetBuilder

    rng = random.Random(seed)
    as_of = 1_800_000_000.0
    spine = [{"entity_id": f"e{i}", "label_ts": as_of - rng.random() * 3e7}
             for i in range(rows)]
    # `history` facts per entity per view, which is what makes the pick a pick.
    # A single fact per entity would measure a dictionary lookup and call it a
    # point-in-time join.
    by_entity = {
        row["entity_id"]: [
            {"entity_id": row["entity_id"],
             "event_ts": as_of - rng.random() * 6e7,
             "ingest_ts": as_of - rng.random() * 5e7,
             "value": rng.random()}
            for _ in range(history)]
        for row in spine}

    pick = TrainingSetBuilder.latest_admissible
    samples: List[float] = []
    started = time.perf_counter()
    for row in spine:
        records = by_entity[row["entity_id"]]
        start = time.perf_counter()
        for _ in range(features):
            pick(records, row["label_ts"], as_of)
        samples.append(time.perf_counter() - start)
    elapsed = time.perf_counter() - started

    cells = rows * features
    per_cell = elapsed / cells if cells else 0.0
    return {
        "spike": "point-in-time-join",
        "requirement": "NFR-PERF-006",
        "conditions": conditions(rows=rows, features=features,
                                 history_per_entity=history,
                                 cells=cells, store="in-memory",
                                 measured="TrainingSetBuilder.latest_admissible"),
        "elapsed_seconds": round(elapsed, 3),
        "cells_per_second": round(cells / elapsed) if elapsed else 0,
        "per_row_ms": percentiles(samples),
        "extrapolation": _extrapolate(per_cell),
        "not_measured": [
            "the Delta read, which scales with the VIEW's size rather than "
            "the spine's",
            "the leakage screen, which scales with the sample rather than the "
            "population",
            "the digest and the persist",
        ],
        "detail": _detail(elapsed, cells, per_cell),
    }


def _extrapolate(per_cell: float) -> Dict[str, Any]:
    """The target, and why the arithmetic is the wrong question.

    Reported because it is what `NFR-PERF-006` asks, and labelled because a
    linear extrapolation of an in-memory algorithm describes a program that
    cannot be run: the memory runs out long before the clock does.
    """
    target_cells = TARGET_ROWS * TARGET_FEATURES
    seconds = per_cell * target_cells
    bytes_needed = target_cells * BYTES_PER_CELL
    return {
        "target": f"{TARGET_ROWS:,} rows x {TARGET_FEATURES} features in "
                  f"{TARGET_MINUTES:.0f} minutes",
        "linear_estimate_minutes": round(seconds / 60, 1),
        "linear_estimate_days": round(seconds / 86400, 1),
        "memory_needed_tb": round(bytes_needed / 1e12, 1),
        "is_evidence": False,
        "detail": (
            f"multiplying this machine's per-cell cost up to "
            f"{target_cells:,} cells gives {round(seconds / 86400, 1)} days "
            f"and about {round(bytes_needed / 1e12, 1)} TB of process memory. "
            f"**Neither figure is a prediction.** The memory is the real "
            f"answer: a billion rows of five hundred features does not fit in "
            f"one process at any speed, so the extrapolation describes a "
            f"program that cannot be run rather than one that is slow. That "
            f"is the finding — the target is not reachable in a single "
            f"process, which is why the answer is a distributed assembly and "
            f"not a faster loop"),
    }


def _detail(elapsed: float, cells: int, per_cell: float) -> str:
    return (
        f"{cells:,} point-in-time picks in {elapsed:.2f}s — "
        f"{round(cells / elapsed) if elapsed else 0:,} per second, "
        f"{per_cell * 1e6:.2f} microseconds each. This is "
        f"`TrainingSetBuilder.latest_admissible`, the real function, over a "
        f"synthetic history rather than a re-implementation of the rule: "
        f"timing a copy would measure the copy. The Delta read, the leakage "
        f"screen and the persist are excluded and each scales differently, so "
        f"rolling them into one figure would produce a number nobody can "
        f"reason about")


def main(argv: Any = None) -> int:
    parser = argparse.ArgumentParser(prog="tools.spikes.pit_join")
    parser.add_argument("--rows", type=int, default=200_000)
    parser.add_argument("--features", type=int, default=50)
    parser.add_argument("--history", type=int, default=8,
                        help="facts per entity per view. More than one, or "
                             "the pick is a dictionary lookup wearing a "
                             "point-in-time name")
    args = parser.parse_args(argv)
    result = run(args.rows, args.features, args.history)
    print(json.dumps(result, indent=2))
    print("\n" + result["detail"], file=sys.stderr)
    print("\n" + result["extrapolation"]["detail"], file=sys.stderr)
    return 0


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(main())
