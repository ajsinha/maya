"""
§24.3 capacity targets on one machine: pin write throughput, job-queue throughput,
object counts without degradation, and cold start to serving.

    python tools/bench/bench_capacity.py [--symbols 500] [--years 10] [--jobs 200]
                                         [--featuresets 20000] [--models 10000]
                                         [--pins 100000]

* **Pin write throughput** (target 50 MB/s per worker): one job pins a 50-attribute
  feature of symbols × years of business days; logical bytes over elapsed seconds.
* **Job throughput** (1,000 small jobs an hour per worker): pins of a tiny feature,
  one worker, draining the queue.
* **Objects without degradation** (100k features — see bench_search — 20k feature
  sets, 10k models, 100k pins): the catalog pages timed on an empty catalog, then
  again after seeding those counts through the repositories; the ratio is reported.
* **Cold start** (under 30 s): ``run_maya_web.py`` started on the seeded storage,
  timed to the first 200 from ``/readyz``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as h  # noqa: E402

PASSWORD = "Bench-password-1"
COLS = 50


def _people(p) -> tuple:
    admin = h.principal(p, "admin")
    for name, roles in (("dana", ["feature_designer"]), ("mick", ["feature_manager"])):
        p.access.create_user(admin, username=name, password=PASSWORD, roles=roles)
    p.access.create_namespace(admin, name="cap")
    return admin, h.principal(p, "dana"), h.principal(p, "mick")


def _approved(p, dana, mick, name: str, frame) -> str:
    buf = io.BytesIO()
    frame.to_parquet(buf, index=False)
    cols = [c for c in frame.columns if c not in ("date", "symbol")]
    definition = {"index": ["date", "symbol"],
                  "index_types": {"date": "date", "symbol": "string"},
                  "schema": [{"name": c, "type": "float64"} for c in cols],
                  "source": {"type": "parquet"}, "resolution": {"grid": "as_is", "rules": {}},
                  "transform": [], "quality": []}
    p.features.create(dana, namespace="cap", name=name, definition=definition)
    p.features.ingest(dana, f"cap/{name}", buf.getvalue(), fmt="parquet")
    p.features.transition(dana, f"cap/{name}", 1, "submit")
    p.features.transition(mick, f"cap/{name}", 1, "approve")
    p.jobs.drain()                  # the reviews' challenge memos, before anything is timed
    return f"cap/{name}"


def pin_throughput(p, dana, mick, symbols: int, years: int) -> dict:
    import numpy as np
    import pandas as pd
    days = pd.bdate_range("2016-01-01", periods=252 * years)
    idx = pd.MultiIndex.from_product([days, [f"S{i:04d}" for i in range(symbols)]],
                                     names=["date", "symbol"])
    values = np.random.default_rng(0).standard_normal((len(idx), COLS))
    frame = pd.DataFrame(values, columns=[f"x{i:02d}" for i in range(COLS)],
                         index=idx).reset_index()
    frame["date"] = frame["date"].dt.date
    ref = _approved(p, dana, mick, "wide", frame)
    out = p.features.pin(mick, ref, version_no=1, pin_name="tp", as_of=days[-1].date())
    t, _ = h.timed(lambda: p.jobs.drain())
    with p.uow() as uow:
        pin = uow.repo("feature_pins").require(out["pin"]["id"])
    assert pin["state"] == "sealed", pin.get("failure")
    mb = pin["bytes_total"] / 1e6
    return {"target_mb_s": 50, "rows": pin["row_count"], "logical_mb": round(mb, 1),
            "seconds": round(t, 2), "mb_per_s": round(mb / t, 1), "pass": mb / t >= 50}


def job_throughput(p, dana, mick, jobs: int) -> dict:
    import pandas as pd
    frame = pd.DataFrame({"date": [dt.date(2026, 1, d) for d in range(1, 6)] * 2,
                          "symbol": ["A"] * 5 + ["B"] * 5, "v": [float(i) for i in range(10)]})
    ref = _approved(p, dana, mick, "tiny", frame)
    for i in range(jobs):
        p.features.pin(mick, ref, version_no=1, pin_name=f"j{i:04d}", as_of=dt.date(2026, 1, 5))
    t, done = h.timed(lambda: p.jobs.drain(limit=jobs + 10))
    rate = done / t * 3600
    return {"target_per_hour": 1000, "jobs": done, "seconds": round(t, 2),
            "per_hour_one_worker": round(rate), "pass": rate >= 1000}


def _page_times(p, admin, repeats: int = 15) -> dict:
    out = {}
    calls = {"features": lambda: p.features.page(admin, page_size=25, total=True),
             "featuresets": lambda: p.featuresets.page(admin, page_size=25, total=True),
             "models": lambda: p.models.page(admin, page_size=25, total=True),
             "feature_detail": lambda: p.features.get(admin, "cap/tiny")}
    for name, fn in calls.items():
        fn()
        out[name] = h.summary([h.timed(fn)[0] for _ in range(repeats)])["p95"]
    return out


def seed_objects(p, admin, featuresets: int, models: int, pins: int) -> float:
    with p.uow() as uow:
        ns = uow.repo("namespaces").find_one(name="cap")["id"]
        tiny = uow.repo("features").find_one(name="tiny")
        tiny_v = uow.repo("feature_versions").find_one(feature_id=tiny["id"])
    t0 = time.perf_counter()
    batch = 2000
    for start in range(0, featuresets, batch):
        with p.uow("admin") as uow:
            for i in range(start, min(featuresets, start + batch)):
                fs = uow.repo("feature_sets").add({"namespace_id": ns, "name": f"fs{i:06d}",
                                                   "owner_id": admin.user_id,
                                                   "description": f"set {i}"})
                uow.repo("feature_set_versions").add({"feature_set_id": fs["id"],
                                                      "version_no": 1, "state": "draft",
                                                      "definition": {"members": []}})
    for start in range(0, models, batch):
        with p.uow("admin") as uow:
            for i in range(start, min(models, start + batch)):
                m = uow.repo("models").add({"namespace_id": ns, "name": f"m{i:06d}",
                                            "owner_id": admin.user_id, "kind": "formula"})
                uow.repo("model_versions").add({"model_id": m["id"], "version_no": 1,
                                                "state": "draft"})
    base = dt.date(2000, 1, 1)
    for start in range(0, pins, batch * 5):
        with p.uow("admin") as uow:
            for i in range(start, min(pins, start + batch * 5)):
                uow.repo("feature_pins").add({
                    "feature_id": tiny["id"], "feature_version_id": tiny_v["id"],
                    "pin_name": f"s{i % 50:02d}", "as_of_date": base + dt.timedelta(days=i // 50),
                    "as_of_known": dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
                    "state": "sealed", "fragments": [], "content_hash": f"{i:064x}"})
    return time.perf_counter() - t0


def cold_start(home: str) -> dict:
    import httpx
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(os.environ, MAYA_HOME=home)
    t0 = time.perf_counter()
    proc = subprocess.Popen([sys.executable, str(h.ROOT / "run_maya_web.py"),
                             f"--server.port={port}", "--logging.level=WARNING"],
                            cwd=h.ROOT, env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        while time.perf_counter() - t0 < 120:
            try:
                if httpx.get(f"http://127.0.0.1:{port}/readyz", timeout=1).status_code == 200:
                    t = time.perf_counter() - t0
                    return {"target_s": 30, "seconds": round(t, 2), "pass": t < 30}
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        return {"target_s": 30, "seconds": None, "pass": False}
    finally:
        proc.terminate()
        proc.wait(30)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", type=int, default=500)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--jobs", type=int, default=200)
    ap.add_argument("--featuresets", type=int, default=20_000)
    ap.add_argument("--models", type=int, default=10_000)
    ap.add_argument("--pins", type=int, default=100_000)
    a = ap.parse_args()
    p = h.platform()
    admin, dana, mick = _people(p)
    report = {"machine": h.machine(), "database": p.db.dialect}
    report["pin_write_throughput"] = pin_throughput(p, dana, mick, a.symbols, a.years)
    report["job_throughput"] = job_throughput(p, dana, mick, a.jobs)
    before = _page_times(p, admin)
    seeded = seed_objects(p, admin, a.featuresets, a.models, a.pins)
    after = _page_times(p, admin)
    report["objects"] = {
        "target": "no degradation at 20k feature sets, 10k models, 100k pins",
        "counts": {"featuresets": a.featuresets, "models": a.models, "pins": a.pins},
        "seed_seconds": round(seeded, 1), "p95_before_s": before, "p95_after_s": after,
        "ratio": {k: round(after[k] / before[k], 2) if before[k] else None for k in before},
        "pass": all(after[k] < 0.3 for k in after)}
    home = os.environ["MAYA_HOME"]
    p.shutdown()
    report["cold_start"] = cold_start(home)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
