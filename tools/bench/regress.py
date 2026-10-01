"""
Gate 26 — no benchmark regression over 10% without a note (plan §7).

Runs scaled-down versions of the three benchmarks — resolution (100 symbols × 2
years × 50 attributes, forward fill), catalog search (10k objects), and single-user
page latency (300 features, 30 models) — three times each, and compares each
metric's median with ``docs/quality/benchmarks/regression-baseline.json``. A metric more than
10% slower fails the gate unless the run carries a note, which is appended to
``docs/quality/benchmarks/regression-notes.md`` with the numbers:

    python tools/bench/regress.py                     # compare
    python tools/bench/regress.py --note "why"        # accept, on the record
    python tools/bench/regress.py --update            # take this run as the baseline

A baseline belongs to one machine: comparing across machines measures the machines.
On a shared workstation, run-to-run noise can exceed 10%; the medians damp it, the
note records any judgement.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs" / "quality" / "benchmarks" / "regression-baseline.json"
NOTES = ROOT / "docs" / "quality" / "benchmarks" / "regression-notes.md"
LIMIT = 0.10
RUNS = {
    "resolution_warm_p95_s": (
        [
            "bench_resolution.py",
            "--symbols",
            "100",
            "--years",
            "2",
            "--warm",
            "3",
            "--rule",
            "forward_fill(limit=3)",
        ],
        lambda d: d["resolution"]["warm"]["p95"],
    ),
    "resolution_cold_s": (None, lambda d: d["resolution"]["cold_seconds"]),
    "search_p95_s": (
        ["bench_search.py", "--objects", "10000", "--queries", "100"],
        lambda d: d["search"]["p95"],
    ),
    "page_worst_p95_s": (
        ["bench_web.py", "--features", "300", "--models", "30", "--users", "0", "--repeats", "15"],
        lambda d: d["SC-4"]["worst_page_p95"],
    ),
}


def _run(args: list[str]) -> dict:
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "bench" / args[0]), *args[1:]],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if r.returncode:
        raise SystemExit(f"{args[0]} failed:\n{r.stderr[-2000:]}")
    return json.loads(r.stdout)


def measure(repeats: int = 3) -> dict[str, float]:
    samples: dict[str, list[float]] = {k: [] for k in RUNS}
    for _ in range(repeats):
        docs: dict[str, dict] = {}
        for key, (args, pick) in RUNS.items():
            if args is not None:
                docs[args[0]] = _run(args)
                last = docs[args[0]]
            samples[key].append(float(pick(last)))
    return {k: round(statistics.median(v), 4) for k, v in samples.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--note")
    ap.add_argument("--repeats", type=int, default=3)
    a = ap.parse_args()
    now = measure(a.repeats)
    if a.update or not BASELINE.exists():
        BASELINE.write_text(
            json.dumps({"measured": dt.date.today().isoformat(), "medians": now}, indent=1) + "\n"
        )
        print(f"baseline written: {now}")
        return 0
    base = json.loads(BASELINE.read_text())["medians"]
    worse = {
        k: (base[k], v)
        for k, v in now.items()
        if k in base and base[k] > 0 and (v - base[k]) / base[k] > LIMIT
    }
    for k, v in now.items():
        b = base.get(k)
        change = f"{(v - b) / b:+.0%}" if b else "new"
        print(f"  {k:<24} {v:>9.4f}  (baseline {b}, {change})")
    if worse and a.note:
        with open(NOTES, "a", encoding="utf-8") as fh:
            fh.write(
                f"\n## {dt.datetime.now().isoformat(timespec='minutes')}\n\n{a.note}\n\n"
                + "".join(f"- {k}: {b} -> {v}\n" for k, (b, v) in worse.items())
            )
        print(f"accepted with a note in {NOTES.relative_to(ROOT)}")
        return 0
    if worse:
        print("REGRESSION over 10%: " + ", ".join(worse) + " (rerun, fix, or --note)")
        return 1
    print("no regression over 10%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
