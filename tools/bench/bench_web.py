"""
SC-4 and SC-3: page latency on the metadata screens, alone and under load.

SC-4 — p95 page interaction latency, metadata screens: under 300 ms.
SC-3 — concurrent interactive users on one node without p95 degradation: 200.

Starts a real MAYA server (uvicorn, one process, as configured) over a seeded
catalog, then measures the full stack each page exercises — HTTP, session,
template, the SDK in-process, the API, authorization and the database:

* SC-4: one signed-in user requests each metadata screen repeatedly;
* SC-3: N users, each with their own session, browse random screens with a
  think time between requests (interactive users, not a flood) for a fixed
  duration; p95 under load is compared with the single-user p95.

    python tools/bench/bench_web.py [--features 2000] [--models 200] [--users 200]
                                    [--duration 60] [--workers 1]

With ``--workers N`` above 1 the catalog is seeded in-process, then the server is
started exactly as in production — ``run_maya_web.py --server.workers=N`` — over the
same storage, and measured from outside.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as h  # noqa: E402

PASSWORD = "Bench-password-1"
CSRF = re.compile(r'name="csrf_token" value="([^"]+)"')


def seed(p, features: int, models: int) -> list[str]:
    import copy
    admin = h.principal(p, "admin")
    p.access.create_user(admin, username="analyst", password=PASSWORD,
                         roles=["feature_designer", "model_designer"])
    with p.uow() as uow:
        for name in ("analyst", "admin"):
            u = uow.repo("users").find_one(username=name)
            uow.repo("users").update(u["id"], {"must_change_password": False})
    analyst = h.principal(p, "analyst")
    p.access.create_namespace(admin, name="eq")
    d = {"index": ["date", "symbol"], "index_types": {"date": "date", "symbol": "string"},
         "schema": [{"name": "close", "type": "float64"}], "source": {"type": "csv"},
         "resolution": {"grid": "as_is", "rules": {"close": "forward_fill(limit=3)"}},
         "transform": [], "quality": [{"check": "not_null", "attr": "close"}]}
    for i in range(features):
        p.features.create(analyst, namespace="eq", name=f"f_{i:05d}",
                          definition=copy.deepcopy(d), description=f"equity feature {i}",
                          tags=["equity", f"desk{i % 7}"])
    for i in range(models):
        p.models.create(analyst, namespace="eq", name=f"m_{i:04d}", formula="y = a*x + b",
                        roles={"a": "parameter", "b": "parameter"})
    return ["/", "/catalog/features", f"/catalog/features/eq/f_{features // 2:05d}",
            "/catalog/featuresets", "/models", f"/models/eq/m_{models // 2:04d}", "/workflow",
            "/search?q=f_001", "/inbox", "/help", "/workbench"]


def serve(p) -> tuple[str, object]:
    import uvicorn

    from maya.server import build_app
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(build_app(p), host="127.0.0.1", port=port,
                                           log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}", server


def launch(workers: int) -> tuple[str, subprocess.Popen]:
    """``run_maya_web.py`` with ``workers`` web processes over this run's MAYA_HOME."""
    import httpx
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, str(h.ROOT / "run_maya_web.py"),
                             f"--server.workers={workers}", f"--server.port={port}",
                             "--logging.level=WARNING"], cwd=h.ROOT, env=dict(os.environ),
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 120
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(proc.stderr.read().decode()[-2000:])
        try:
            if httpx.get(base + "/login", timeout=2).status_code == 200:
                return base, proc
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    proc.kill()
    raise RuntimeError("the server did not come up")


async def login(client) -> None:
    r = await client.get("/login")
    token = CSRF.search(r.text).group(1)
    r = await client.post("/login", data={"username": "analyst", "password": PASSWORD,
                                          "csrf_token": token})
    assert r.status_code == 200 and "Sign in" not in r.text[:3000], "login failed"


async def single_user(base: str, pages: list[str], repeats: int) -> dict:
    import httpx
    out = {}
    async with httpx.AsyncClient(base_url=base, follow_redirects=True, timeout=60) as c:
        await login(c)
        for page in pages:
            for _ in range(3):
                await c.get(page)                       # warm the page's caches
            samples = []
            for _ in range(repeats):
                t0 = time.perf_counter()
                r = await c.get(page)
                samples.append(time.perf_counter() - t0)
                assert r.status_code == 200, (page, r.status_code)
            out[page] = h.summary(samples)
    return out


async def load(base: str, pages: list[str], users: int, duration: float,
               think: tuple[float, float]) -> dict:
    import httpx
    samples: list[float] = []
    errors = 0
    limits = httpx.Limits(max_connections=users + 10, max_keepalive_connections=users + 10)
    clients = [httpx.AsyncClient(base_url=base, follow_redirects=True, timeout=120,
                                 limits=limits) for _ in range(users)]
    for c in clients:
        await login(c)                                  # sessions established before the clock
    stop = time.perf_counter() + duration

    async def user(c) -> None:
        nonlocal errors
        rnd = random.Random(id(c))
        await asyncio.sleep(rnd.uniform(0, think[1]))   # stagger arrivals
        while time.perf_counter() < stop:
            t0 = time.perf_counter()
            try:
                r = await c.get(rnd.choice(pages))
                if r.status_code != 200:
                    errors += 1
            except Exception:  # noqa: BLE001 - a timeout under load is a result
                errors += 1
                continue
            samples.append(time.perf_counter() - t0)
            await asyncio.sleep(rnd.uniform(*think))

    await asyncio.gather(*(user(c) for c in clients))
    for c in clients:
        await c.aclose()
    return {"users": users, "duration_s": duration, "think_s": list(think),
            "requests": len(samples), "errors": errors,
            "throughput_rps": round(len(samples) / duration, 1), **h.summary(samples)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", type=int, default=2000)
    ap.add_argument("--models", type=int, default=200)
    ap.add_argument("--users", type=int, default=200)
    ap.add_argument("--duration", type=float, default=60)
    ap.add_argument("--repeats", type=int, default=30)
    ap.add_argument("--think-min", type=float, default=1.0)
    ap.add_argument("--think-max", type=float, default=3.0)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args()
    p = h.platform()
    dialect = p.db.dialect
    t_seed, pages = h.timed(lambda: seed(p, a.features, a.models))
    if a.workers > 1:
        p.shutdown()
        base, proc = launch(a.workers)
    else:
        base, server = serve(p)
    try:
        one = asyncio.run(single_user(base, pages, a.repeats))
        single_p95 = h.pct([s["p95"] for s in one.values()], 95)
        loaded = asyncio.run(load(base, pages, a.users, a.duration,
                                  (a.think_min, a.think_max)))
    finally:
        if a.workers > 1:
            proc.terminate()
            proc.wait(30)
        else:
            server.should_exit = True
    report = {
        "machine": h.machine(), "database": dialect, "web_processes": a.workers,
        "catalog": {"features": a.features, "models": a.models,
                    "seed_seconds": round(t_seed, 1)},
        "SC-4": {"target_p95_s": 0.3, "per_page": one,
                 "worst_page_p95": round(max(s["p95"] for s in one.values()), 4),
                 "pass": all(s["p95"] < 0.3 for s in one.values())},
        "SC-3": {"target": "p95 under 0.3 s with 200 users; no material degradation",
                 "single_user_p95": round(single_p95, 4), "loaded": loaded,
                 "degradation_ratio": round(loaded["p95"] / single_p95, 2) if single_p95 else None,
                 "pass": loaded["p95"] < 0.3 and loaded["errors"] == 0},
    }
    if a.workers == 1:
        p.shutdown()
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
