"""
Prometheus metrics (§20), in the text exposition format, with no dependency.

Counters and histograms are updated in-process as things happen; gauges that
describe state held elsewhere (queue depth, active sessions) are collected by
callbacks at scrape time, so a scrape never reports a number that was true a
minute ago. Label values are escaped per the format; metric and label names are
fixed in code.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import bisect
import threading
from typing import Any, Callable

DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
Labels = tuple[tuple[str, str], ...]


def _labels(labels: dict[str, Any] | None) -> Labels:
    return tuple(sorted((k, str(v)) for k, v in (labels or {}).items()))


def _fmt(labels: Labels, extra: tuple[tuple[str, str], ...] = ()) -> str:
    pairs = labels + extra
    if not pairs:
        return ""
    body = ",".join(f'{k}="{_escape(v)}"' for k, v in pairs)
    return "{" + body + "}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


class Registry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._help: dict[str, tuple[str, str]] = {}
        self._counters: dict[str, dict[Labels, float]] = {}
        self._hist: dict[str, dict[Labels, list[float]]] = {}
        self._buckets: dict[str, tuple[float, ...]] = {}
        self._collectors: list[Callable[[], list[tuple[str, dict[str, Any], float]]]] = []

    def describe(
        self, name: str, kind: str, text: str, buckets: tuple[float, ...] = DEFAULT_BUCKETS
    ) -> None:
        self._help[name] = (kind, text)
        if kind == "histogram":
            self._buckets[name] = buckets

    def inc(self, name: str, labels: dict[str, Any] | None = None, value: float = 1.0) -> None:
        with self._lock:
            series = self._counters.setdefault(name, {})
            key = _labels(labels)
            series[key] = series.get(key, 0.0) + value

    def observe(self, name: str, value: float, labels: dict[str, Any] | None = None) -> None:
        buckets = self._buckets.get(name, DEFAULT_BUCKETS)
        with self._lock:
            series = self._hist.setdefault(name, {})
            key = _labels(labels)
            row = series.setdefault(key, [0.0] * (len(buckets) + 2))  # buckets, sum, count
            index = bisect.bisect_left(buckets, value)
            for i in range(index, len(buckets)):
                row[i] += 1
            row[-2] += value
            row[-1] += 1

    def collector(self, fn: Callable[[], list[tuple[str, dict[str, Any], float]]]) -> None:
        """Register a scrape-time source of gauge samples: [(name, labels, value)]."""
        self._collectors.append(fn)

    def render(self) -> str:
        lines: list[str] = []
        gauges: dict[str, list[tuple[Labels, float]]] = {}
        for fn in self._collectors:
            try:
                for name, labels, value in fn():
                    gauges.setdefault(name, []).append((_labels(labels), value))
            except Exception as exc:  # noqa: BLE001 - one broken collector must not blank /metrics
                gauges.setdefault("maya_collector_errors", []).append(
                    (
                        (
                            ("collector", getattr(fn, "__name__", "?")),
                            ("error", type(exc).__name__),
                        ),
                        1.0,
                    )
                )
        with self._lock:
            names = sorted(set(self._counters) | set(self._hist) | set(gauges))
            for name in names:
                kind, text = self._help.get(name, ("gauge" if name in gauges else "counter", name))
                lines.append(f"# HELP {name} {text}")
                lines.append(f"# TYPE {name} {kind}")
                for labels, value in sorted(self._counters.get(name, {}).items()):
                    lines.append(f"{name}{_fmt(labels)} {value:g}")
                for labels, value in sorted(gauges.get(name, [])):
                    lines.append(f"{name}{_fmt(labels)} {value:g}")
                buckets = self._buckets.get(name, DEFAULT_BUCKETS)
                for labels, row in sorted(self._hist.get(name, {}).items()):
                    for bound, count in zip(buckets, row):
                        lines.append(
                            f"{name}_bucket{_fmt(labels, (('le', f'{bound:g}'),))} {count:g}"
                        )
                    lines.append(f"{name}_bucket{_fmt(labels, (('le', '+Inf'),))} {row[-1]:g}")
                    lines.append(f"{name}_sum{_fmt(labels)} {row[-2]:g}")
                    lines.append(f"{name}_count{_fmt(labels)} {row[-1]:g}")
        return "\n".join(lines) + "\n"


METRICS = Registry()
for _name, _kind, _text in (
    ("maya_http_requests_total", "counter", "HTTP requests by method, route template and status"),
    ("maya_http_request_duration_seconds", "histogram", "HTTP request latency"),
    ("maya_job_runs_total", "counter", "Jobs finished, by type and outcome"),
    ("maya_job_duration_seconds", "histogram", "Job run time by type"),
    ("maya_pins_sealed_total", "counter", "Pins sealed, by kind"),
    ("maya_pin_new_bytes_total", "counter", "Bytes of new fragments written by pins"),
    ("maya_authz_denials_total", "counter", "Authorization denials, by action"),
    ("maya_audit_events_total", "counter", "Audit entries appended"),
    ("maya_events_total", "counter", "Events emitted, by type"),
    ("maya_webhook_deliveries_total", "counter", "Webhook delivery attempts, by outcome"),
    ("maya_jobs", "gauge", "Jobs by state, at scrape time"),
    ("maya_sessions_active", "gauge", "Unrevoked, unexpired sessions"),
    ("maya_webhook_backlog", "gauge", "Webhook deliveries waiting, by state"),
    ("maya_seam_backend", "gauge", "The resolved backend of each dependency seam (value 1)"),
    ("maya_sandbox_tier", "gauge", "The verified sandbox tier (value 1)"),
    ("maya_build_info", "gauge", "Version and build of the running MAYA (value 1)"),
):
    METRICS.describe(_name, _kind, _text)
