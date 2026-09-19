"""
Cache hit rates (§20), counted where the caches actually are.

MAYA's caches are small, deliberate and scattered: a session's principal for two
seconds (ADR-026), an API key's verified secret, the health page's audit-chain
walk. Each was added because something was being recomputed many times a
second, and each therefore has a hit rate that says whether it is still earning
its keep — and, when it is not, whether the answer is a longer TTL or deleting
the cache. Before this the rates were unknowable: a cache that never hit looked
exactly like one that always did.

A cache registers a name and calls ``hit`` or ``miss``. The counters are
exported as ``maya_cache_hits_total`` and ``maya_cache_misses_total``, labelled
by that name, and a registered cache reports zeros until it is used, so a
missing series never has to be read as "no traffic or no cache, we cannot tell".

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_names: set[str] = set()


def register(name: str) -> None:
    """Declare a cache, so /metrics carries its zeros before its first lookup."""
    with _lock:
        _names.add(name)


def hit(name: str) -> None:
    from maya.observability.metrics import METRICS

    register(name)
    METRICS.inc("maya_cache_hits_total", {"cache": name})


def miss(name: str) -> None:
    from maya.observability.metrics import METRICS

    register(name)
    METRICS.inc("maya_cache_misses_total", {"cache": name})


def registered() -> tuple[str, ...]:
    with _lock:
        return tuple(sorted(_names))


def seed() -> None:
    """Start both counters of every registered cache at zero."""
    from maya.observability.metrics import METRICS

    for name in registered():
        for metric in ("maya_cache_hits_total", "maya_cache_misses_total"):
            METRICS.inc(metric, {"cache": name}, value=0.0)


__all__ = ["register", "hit", "miss", "registered", "seed"]
