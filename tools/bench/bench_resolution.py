"""
SC-5: p95 resolution of a 50-column, 10-year daily feature set (spec §22:
× 500 symbols). Target: under 15 s warm, under 60 s cold.

Builds one approved 50-attribute feature over 500 symbols × 10 years of
business days (≈1.3M rows) and a feature set mapping all 50 attributes, then
resolves the feature set in a *fresh process* (cold: nothing cached, the lake
read from disk) followed by warm resolutions in the same process.

    python tools/bench/bench_resolution.py [--warm 5] [--symbols 500] [--years 10]

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as h  # noqa: E402

COLS = 50


def build(symbols: int, years: int, rule: str | None) -> dict:
    import numpy as np
    import pandas as pd
    p = h.platform()
    admin = h.principal(p, "admin")
    for name, roles in (("dana", ["feature_designer"]), ("mick", ["feature_manager"])):
        p.access.create_user(admin, username=name, password="Bench-password-1", roles=roles)
    dana, mick = h.principal(p, "dana"), h.principal(p, "mick")
    p.access.create_namespace(admin, name="bench")
    days = pd.bdate_range("2016-01-01", periods=252 * years)
    syms = [f"S{i:04d}" for i in range(symbols)]
    idx = pd.MultiIndex.from_product([days, syms], names=["date", "symbol"])
    rng = np.random.default_rng(0)
    values = rng.standard_normal((len(idx), COLS))
    values[rng.random(values.shape) < 0.02] = np.nan          # 2% gaps for the rules to fill
    frame = pd.DataFrame(values,
                         columns=[f"x{i:02d}" for i in range(COLS)], index=idx).reset_index()
    frame["date"] = frame["date"].dt.date
    buf = io.BytesIO()
    frame.to_parquet(buf, index=False)
    definition = {"index": ["date", "symbol"], "index_types": {"date": "date", "symbol": "string"},
                  "schema": [{"name": f"x{i:02d}", "type": "float64"} for i in range(COLS)],
                  "source": {"type": "parquet"},
                  "resolution": {"grid": "as_is", "rules": {f"x{i:02d}": rule for i in range(COLS)}
                                 if rule else {}}, "transform": [], "quality": []}
    t_ingest, _ = h.timed(lambda: (
        p.features.create(dana, namespace="bench", name="wide", definition=definition),
        p.features.ingest(dana, "bench/wide", buf.getvalue(), fmt="parquet")))
    p.features.transition(dana, "bench/wide", 1, "submit")
    p.features.transition(mick, "bench/wide", 1, "approve")
    fs = {"index": ["date", "symbol"], "grid": "as_is", "alignment": {"mode": "inner"},
          "members": [{"attr": f"x{i:02d}", "ref": "maya://feature/bench/wide@v1",
                       "source_attr": f"x{i:02d}"} for i in range(COLS)]}
    p.featuresets.create(dana, namespace="bench", name="panel", definition=fs)
    p.featuresets.transition(dana, "bench/panel", 1, "submit")
    p.featuresets.transition(mick, "bench/panel", 1, "approve")
    home = os.environ["MAYA_HOME"]
    p.shutdown()
    return {"home": home, "rows": len(frame), "columns": COLS, "symbols": symbols,
            "days": len(days), "ingest_seconds": round(t_ingest, 2),
            "db_url": os.environ.get("MAYA_BENCH_DB_URL")}


def resolve(home: str, warm: int, db_url: str | None) -> dict:
    t_start = time.perf_counter()
    p = h.platform(home, db_url=db_url, init=False)
    startup = time.perf_counter() - t_start
    dana = h.principal(p, "dana")
    ref = "maya://featureset/bench/panel@v1"
    cold, res = h.timed(lambda: p.featuresets.resolve_ref(dana, ref))
    rows, cols = res.df.shape
    warms = [h.timed(lambda: p.featuresets.resolve_ref(dana, ref))[0] for _ in range(warm)]
    p.shutdown()
    return {"startup_seconds": round(startup, 2), "cold_seconds": round(cold, 3),
            "warm": h.summary(warms), "result_rows": rows, "result_columns": cols}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", type=int, default=500)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--warm", type=int, default=5)
    ap.add_argument("--phase", default="all")
    ap.add_argument("--home")
    ap.add_argument("--db-url")
    ap.add_argument("--rule", help="a resolution rule on every attribute, e.g. forward_fill(limit=3)")
    a = ap.parse_args()
    if a.phase == "resolve":
        print(json.dumps(resolve(a.home, a.warm, a.db_url)))
        return
    built = build(a.symbols, a.years, a.rule)
    built["rule"] = a.rule or "none"
    cmd = [sys.executable, __file__, "--phase", "resolve", "--home", built["home"],
           "--warm", str(a.warm)] + (["--db-url", built["db_url"]] if built["db_url"] else [])
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)   # a fresh process: cold
    measured = json.loads(out.stdout.strip().splitlines()[-1])
    print(json.dumps({"criterion": "SC-5", "target": {"warm_p95_s": 15, "cold_s": 60},
                      "machine": h.machine(), "build": built, "resolution": measured,
                      "pass": measured["warm"]["p95"] < 15 and measured["cold_seconds"] < 60},
                     indent=1))


if __name__ == "__main__":
    main()
