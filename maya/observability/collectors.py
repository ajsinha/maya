"""
Scrape-time gauges for the §20 metrics that describe state rather than events.

A counter can be incremented where the thing happens; a gauge cannot, because
"how many jobs are queued" is not an event anybody emits. These functions are
asked for their numbers when Prometheus scrapes, so ``/metrics`` never reports a
figure that was true a minute ago.

Two of them cost real work — listing every lake table's files, and walking pin
rows to attribute bytes to a namespace — so those answers are held for
``observability.metrics.cache_seconds``. That is a deliberate trade against the
"never stale" rule above: a Delta file count that is a minute old is still worth
having, and a scrape that reads the whole lake on a large estate is not. The
cheap gauges (queue depth, pool, sessions) are always computed fresh, and the
expensive pair can be turned off entirely.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import time
from typing import Any

from maya.core.clock import utcnow
from maya.observability import caches

Sample = tuple[str, dict[str, Any], float]


class Collectors:
    """Every scrape-time gauge of one platform, with the TTL the costly ones share."""

    def __init__(self, platform: Any) -> None:
        self.p = platform
        s = platform.settings
        self.ttl = float(s.int("observability.metrics.cache_seconds", 60))
        self.namespace_gauges = s.bool("observability.metrics.namespace_gauges", True)
        self._held: dict[str, tuple[float, list[Sample]]] = {}
        caches.register("metrics_lake")
        caches.register("metrics_namespaces")
        caches.register("metrics_governance")

    def all(self) -> list[Sample]:
        out: list[Sample] = []
        out += self.queue()
        out += self.pool()
        out += self.posture()
        out += self._cached("metrics_lake", self.lake)
        out += self._cached("metrics_governance", self.governance)
        if self.namespace_gauges:
            out += self._cached("metrics_namespaces", self.namespaces)
        return out

    def _cached(self, name: str, fn: Any) -> list[Sample]:
        now = time.monotonic()
        held = self._held.get(name)
        if held is not None and now - held[0] < self.ttl:
            caches.hit(name)
            return held[1]
        caches.miss(name)
        samples = fn()
        self._held[name] = (now, samples)
        return samples

    def governance(self) -> list[Sample]:
        from maya.observability import governance

        return governance.collect(self.p)

    # -- the queue (§15.2, §20) -----------------------------------------------------
    def queue(self) -> list[Sample]:
        """Depth by type, how many people are waiting, and the oldest wait — the three
        numbers that say whether the queue is busy or unfair."""
        out: list[Sample] = []
        with self.p.uow() as uow:
            queued = uow.repo("jobs").list(state="queued", limit=10000)
        by_type: dict[str, int] = {}
        for job in queued:
            by_type[job["job_type"]] = by_type.get(job["job_type"], 0) + 1
        for job_type in sorted(set(by_type) | set(self.p.jobs.handlers)):
            out.append(("maya_job_queue_depth", {"type": job_type}, by_type.get(job_type, 0)))
        out.append(("maya_job_queue_owners", {}, len({j["owner"] for j in queued})))
        oldest = min((j["created_at"] for j in queued), default=None)
        out.append(
            (
                "maya_job_oldest_queued_seconds",
                {},
                0.0 if oldest is None else (utcnow() - oldest).total_seconds(),
            )
        )
        return out

    # -- the things an SLO alert fires on (§20) --------------------------------------
    def posture(self) -> list[Sample]:
        """Pin states, the default password, and how stale the last restore drill is.

        These three exist because §20 asks each SLO to have an alert: "zero unrecovered
        pin sagas" needs a pin-state gauge, "the drill result is recorded and visible"
        needs the drill's age where a rule can read it, and a deployment still running on
        the shipped administrator password should be shouted about rather than mentioned
        on a page nobody opens.
        """
        out: list[Sample] = []
        with self.p.uow() as uow:
            for kind, table in (("feature", "feature_pins"), ("featureset", "feature_set_pins")):
                for state in ("sealed", "materializing", "failed", "retired"):
                    out.append(
                        (
                            "maya_pins",
                            {"kind": kind, "state": state},
                            uow.repo(table).count(state=state),
                        )
                    )
            last = uow.repo("restore_drills").list(order_by=["-performed_at"], limit=1)
        age = -1.0
        if last:
            age = (utcnow() - last[0]["performed_at"]).total_seconds() / 86400.0
        out.append(("maya_restore_drill_age_days", {}, age))
        out.append(
            (
                "maya_default_admin_password",
                {},
                1.0 if self.p.auth.default_admin_password_active() else 0.0,
            )
        )
        return out

    # -- the database pool (§20) ----------------------------------------------------
    def pool(self) -> list[Sample]:
        status = self.p.db.pool_status()
        return [
            ("maya_db_pool_connections", {"state": state}, float(status.get(state, 0)))
            for state in ("in_use", "available", "overflow")
        ] + [
            ("maya_db_pool_limit", {"kind": kind}, float(status.get(kind, 0)))
            for kind in ("size", "max_overflow")
        ]

    # -- the lake (§20: Delta file counts and small-file ratio per table) -----------
    def lake(self) -> list[Sample]:
        target = self.p.settings.int("lake.maintenance.target_size_mb", 128) * 1024 * 1024
        out: list[Sample] = []
        for path in self.p.lake.tables():
            try:
                files = self.p.lake.delta.files(path)
            except Exception:  # noqa: BLE001 - a table being rewritten never blanks /metrics
                continue
            sizes = [int(f.get("size") or 0) for f in files]
            table = self.p.lake.rel(path)
            small = sum(1 for n in sizes if n < target)
            out.append(("maya_delta_files", {"table": table}, float(len(sizes))))
            out.append(("maya_delta_bytes", {"table": table}, float(sum(sizes))))
            out.append(
                (
                    "maya_delta_small_file_ratio",
                    {"table": table},
                    (small / len(sizes)) if sizes else 0.0,
                )
            )
        return out

    # -- pins and bytes per namespace (§20) -----------------------------------------
    def namespaces(self) -> list[Sample]:
        """Pins and stored bytes attributed to the namespace that owns them.

        The §20 line is "pins created and bytes stored per namespace". Counters cannot
        carry the namespace label — a pin is sealed deep inside the feature services —
        so this is the stock at scrape time instead, which is the number an operator
        watching for a namespace filling the lake actually wants.
        """
        out: list[Sample] = []
        with self.p.uow() as uow:
            names = {n["id"]: n["name"] for n in uow.repo("namespaces").list(limit=10000)}
            for kind, table, owner_table, fk in (
                ("feature", "feature_pins", "features", "feature_id"),
                ("featureset", "feature_set_pins", "feature_sets", "feature_set_id"),
            ):
                owners = {
                    o["id"]: o["namespace_id"] for o in uow.repo(owner_table).list(limit=100000)
                }
                pins = uow.repo(table).list(state="sealed", limit=100000)
                counts: dict[str, list[float]] = {}
                for pin in pins:
                    ns = names.get(owners.get(pin[fk], ""), "?")
                    row = counts.setdefault(ns, [0.0, 0.0])
                    row[0] += 1
                    row[1] += float(pin.get("bytes_total") or 0)
                for ns, (n, nbytes) in sorted(counts.items()):
                    out.append(("maya_namespace_pins", {"namespace": ns, "kind": kind}, n))
                    out.append(
                        ("maya_namespace_pin_bytes", {"namespace": ns, "kind": kind}, nbytes)
                    )
        return out


__all__ = ["Collectors", "Sample"]
