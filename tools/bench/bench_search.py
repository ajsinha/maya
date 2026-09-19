"""
Catalog search p95 over 100k objects (spec §22): under 500 ms.

Seeds the catalog through the unit of work — each feature written as the
repositories write it, so the search index is maintained by the same hook as
in production — then times the search a signed-in user runs, including its
read-permission filtering, over a mix of name prefixes, words and multi-term
queries.

    python tools/bench/bench_search.py [--objects 100000] [--queries 200]

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as h  # noqa: E402

WORDS = [
    "equity",
    "credit",
    "rates",
    "fx",
    "commodity",
    "volatility",
    "spread",
    "yield",
    "momentum",
    "value",
    "carry",
    "liquidity",
    "adjusted",
    "close",
    "return",
    "beta",
]


def seed(p, n: int) -> None:
    admin = h.principal(p, "admin")
    for i in range(10):
        p.access.create_namespace(admin, name=f"desk{i}")
    with p.uow() as uow:
        namespaces = {r["name"]: r["id"] for r in uow.repo("namespaces").list()}
    rng = random.Random(0)
    batch = 2000
    for start in range(0, n, batch):
        with p.uow("admin") as uow:
            repo = uow.repo("features")
            for i in range(start, min(n, start + batch)):
                a, b = rng.sample(WORDS, 2)
                repo.add(
                    {
                        "namespace_id": namespaces[f"desk{i % 10}"],
                        "name": f"{a}_{b}_{i:06d}",
                        "owner_id": admin.user_id,
                        "description": f"{a} {b} signal number {i}",
                        "tags": [a, f"desk{i % 10}"],
                        "index_spec": ["date", "symbol"],
                    }
                )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--objects", type=int, default=100_000)
    ap.add_argument("--queries", type=int, default=200)
    a = ap.parse_args()
    p = h.platform()
    t_seed, _ = h.timed(lambda: seed(p, a.objects))
    admin = h.principal(p, "admin")
    rng = random.Random(1)
    queries = []
    for _ in range(a.queries):
        kind = rng.random()
        if kind < 0.4:
            queries.append(rng.choice(WORDS)[: rng.randint(2, 5)])  # a prefix
        elif kind < 0.8:
            queries.append(" ".join(rng.sample(WORDS, 2)))  # two words
        else:
            queries.append(f"{rng.choice(WORDS)}_{rng.choice(WORDS)}_{rng.randint(0, 9):01d}")
    for q in queries[:5]:
        p.ops.search(admin, q)  # warm
    samples, hits = [], []
    for q in queries:
        t, out = h.timed(lambda q=q: p.ops.search(admin, q))
        samples.append(t)
        hits.append(len(out))
    with p.uow() as uow:
        terms = uow.repo("search_terms").count()
    p.shutdown()
    s = h.summary(samples)
    print(
        json.dumps(
            {
                "criterion": "catalog search p95 over 100k objects",
                "target_p95_s": 0.5,
                "machine": h.machine(),
                "database": p.db.dialect,
                "objects": a.objects,
                "index_rows": terms,
                "seed_seconds": round(t_seed, 1),
                "search": s,
                "mean_hits": round(sum(hits) / len(hits), 1),
                "pass": s["p95"] < 0.5,
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
