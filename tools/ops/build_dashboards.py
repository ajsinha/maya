"""
Build MAYA's Grafana dashboards into config/grafana/.

Two dashboards, written from the panel lists below so they stay small enough to review:

* **MAYA — platform**: requests, latency and errors; the job queue; resolution and pins; the
  database; security and integrity posture.
* **MAYA — model governance**: live models and their warrants; restatements under them; the
  inventory's reviews, findings and review queue; the AI gateway's calls, failures and tokens.

Both take a Prometheus data source chosen on import (``DS_PROMETHEUS``). Every query names
only metrics MAYA exports; tests/test_dashboards.py checks that, and that the committed
JSON is what this script writes. Run it after changing a panel::

    python tools/ops/build_dashboards.py

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "config" / "grafana"
DS = {"type": "prometheus", "uid": "${DS_PROMETHEUS}"}

# (title, kind, unit, [(expr, legend)], width)
Panel = tuple[str, str, str, list[tuple[str, str]], int]

PLATFORM: list[tuple[str, list[Panel]]] = [
    (
        "Service",
        [
            (
                "Requests by status",
                "timeseries",
                "reqps",
                [("sum by (status) (rate(maya_http_requests_total[5m]))", "{{status}}")],
                8,
            ),
            (
                "Latency p50 / p95 / p99",
                "timeseries",
                "s",
                [
                    (
                        f"histogram_quantile({q}, sum by (le) (rate(maya_http_request_duration_seconds_bucket[5m])))",
                        f"p{int(q * 100)}",
                    )
                    for q in (0.5, 0.95, 0.99)
                ],
                8,
            ),
            (
                "Server errors",
                "stat",
                "percentunit",
                [
                    (
                        'sum(rate(maya_http_requests_total{status=~"5.."}[5m])) / clamp_min(sum(rate(maya_http_requests_total[5m])), 1e-9)',
                        "5xx",
                    )
                ],
                4,
            ),
            ("Active sessions", "stat", "short", [("sum(maya_sessions_active)", "sessions")], 4),
        ],
    ),
    (
        "Jobs",
        [
            (
                "Queue depth by type",
                "timeseries",
                "short",
                [("sum by (type) (maya_job_queue_depth)", "{{type}}")],
                8,
            ),
            (
                "Oldest queued job",
                "stat",
                "s",
                [("max(maya_job_oldest_queued_seconds)", "oldest")],
                4,
            ),
            (
                "Jobs finished by outcome",
                "timeseries",
                "ops",
                [("sum by (outcome) (rate(maya_job_runs_total[5m]))", "{{outcome}}")],
                6,
            ),
            (
                "Job run time p95 by type",
                "timeseries",
                "s",
                [
                    (
                        "histogram_quantile(0.95, sum by (le, type) (rate(maya_job_duration_seconds_bucket[15m])))",
                        "{{type}}",
                    )
                ],
                6,
            ),
        ],
    ),
    (
        "Data",
        [
            (
                "Resolution rows per second",
                "timeseries",
                "short",
                [
                    (
                        "sum by (kind) (rate(maya_resolution_rows_total[5m])) / clamp_min(sum by (kind) (rate(maya_resolution_seconds_total[5m])), 1e-9)",
                        "{{kind}}",
                    )
                ],
                8,
            ),
            (
                "Pins by state",
                "bargauge",
                "short",
                [("sum by (kind, state) (maya_pins)", "{{kind}} {{state}}")],
                8,
            ),
            (
                "New pin bytes written",
                "timeseries",
                "Bps",
                [("sum(rate(maya_pin_new_bytes_total[15m]))", "bytes/s")],
                8,
            ),
        ],
    ),
    (
        "Database",
        [
            (
                "Pool connections",
                "timeseries",
                "short",
                [("sum by (state) (maya_db_pool_connections)", "{{state}}")],
                8,
            ),
            (
                "Statements per second",
                "timeseries",
                "ops",
                [("sum(rate(maya_db_statements_total[5m]))", "statements")],
                8,
            ),
            (
                "Slow queries per minute",
                "timeseries",
                "short",
                [("sum(rate(maya_db_slow_queries_total[5m])) * 60", "slow")],
                8,
            ),
        ],
    ),
    (
        "Security and integrity",
        [
            (
                "Authorization denials",
                "timeseries",
                "short",
                [("sum by (action) (increase(maya_authz_denials_total[15m]))", "{{action}}")],
                8,
            ),
            (
                "Integrity drift (24 h)",
                "stat",
                "short",
                [("sum(increase(maya_integrity_drift_total[1d]))", "drifted pins")],
                4,
            ),
            (
                "Default admin password",
                "stat",
                "short",
                [("max(maya_default_admin_password)", "still default")],
                4,
            ),
            ("Restore drill age", "stat", "d", [("max(maya_restore_drill_age_days)", "days")], 4),
            ("Webhook backlog", "stat", "short", [("sum(maya_webhook_backlog)", "waiting")], 4),
        ],
    ),
]

GOVERNANCE: list[tuple[str, list[Panel]]] = [
    (
        "Live models",
        [
            (
                "Live execution warrants",
                "stat",
                "short",
                [('sum(maya_execution_warrants{status="live"})', "live")],
                4,
            ),
            (
                "Suspended",
                "stat",
                "short",
                [('sum(maya_execution_warrants{status="suspended"})', "suspended")],
                4,
            ),
            (
                "Expiring within 7 days",
                "stat",
                "short",
                [('sum(maya_execution_warrants_expiring{within_days="7"})', "7 days")],
                4,
            ),
            (
                "Expiring within 30 days",
                "stat",
                "short",
                [('sum(maya_execution_warrants_expiring{within_days="30"})', "30 days")],
                4,
            ),
            (
                "Execution warrants by status",
                "bargauge",
                "short",
                [("sum by (status) (maya_execution_warrants)", "{{status}}")],
                8,
            ),
            (
                "Covenant breaches by kind",
                "timeseries",
                "short",
                [("sum by (kind) (increase(maya_covenant_breaches_total[1h]))", "{{kind}}")],
                24,
            ),
        ],
    ),
    (
        "Restated data under live models",
        [
            (
                "Open impacts",
                "stat",
                "short",
                [('sum(maya_restatement_impacts{state="open"})', "open")],
                6,
            ),
            (
                "Oldest unacknowledged",
                "stat",
                "s",
                [("max(maya_restatement_oldest_open_seconds)", "age")],
                6,
            ),
            (
                "Acknowledged",
                "stat",
                "short",
                [('sum(maya_restatement_impacts{state="acknowledged"})', "acknowledged")],
                6,
            ),
            (
                "Impacts found per day",
                "timeseries",
                "short",
                [("sum(increase(maya_restatement_impacts_total[1d]))", "impacts")],
                6,
            ),
        ],
    ),
    (
        "Inventory",
        [
            (
                "Models past periodic review, by tier",
                "bargauge",
                "short",
                [("sum by (tier) (maya_models_review_overdue)", "tier {{tier}}")],
                8,
            ),
            (
                "Open findings by severity",
                "bargauge",
                "short",
                [("sum by (severity) (maya_findings_open)", "{{severity}}")],
                8,
            ),
            (
                "Waiting for a reviewer",
                "bargauge",
                "short",
                [('sum by (kind) (maya_versions{state="in_review"})', "{{kind}}")],
                8,
            ),
            (
                "Versions by state",
                "timeseries",
                "short",
                [("sum by (kind, state) (maya_versions)", "{{kind}} {{state}}")],
                12,
            ),
            (
                "Training warrants by state",
                "bargauge",
                "short",
                [("sum by (state) (maya_training_warrants)", "{{state}}")],
                6,
            ),
            (
                "Documents by state",
                "bargauge",
                "short",
                [("sum by (state) (maya_documents)", "{{state}}")],
                6,
            ),
        ],
    ),
    (
        "AI gateway",
        [
            (
                "Calls by purpose and outcome",
                "timeseries",
                "ops",
                [
                    (
                        "sum by (purpose, outcome) (rate(maya_ai_completions_total[5m]))",
                        "{{purpose}} {{outcome}}",
                    )
                ],
                8,
            ),
            (
                "Failure ratio by provider",
                "timeseries",
                "percentunit",
                [
                    (
                        'sum by (provider) (rate(maya_ai_completions_total{outcome="unavailable"}[15m])) / clamp_min(sum by (provider) (rate(maya_ai_completions_total[15m])), 1e-9)',
                        "{{provider}}",
                    )
                ],
                8,
            ),
            (
                "Call time p95 by provider",
                "timeseries",
                "s",
                [
                    (
                        "histogram_quantile(0.95, sum by (le, provider) (rate(maya_ai_completion_seconds_bucket[15m])))",
                        "{{provider}}",
                    )
                ],
                8,
            ),
            (
                "Tokens per hour by provider",
                "timeseries",
                "short",
                [
                    (
                        "sum by (provider, direction) (increase(maya_ai_tokens_total[1h]))",
                        "{{provider}} {{direction}}",
                    )
                ],
                16,
            ),
            (
                "Tokens in the last 24 h",
                "stat",
                "short",
                [("sum(increase(maya_ai_tokens_total[1d]))", "tokens")],
                8,
            ),
        ],
    ),
]


def _panel(pid: int, x: int, y: int, panel: Panel) -> dict[str, Any]:
    title, kind, unit, targets, width = panel
    height = 4 if kind == "stat" else 8
    out: dict[str, Any] = {
        "id": pid,
        "type": kind,
        "title": title,
        "datasource": DS,
        "gridPos": {"h": height, "w": width, "x": x, "y": y},
        "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
        "targets": [
            {"refId": chr(65 + i), "datasource": DS, "expr": expr, "legendFormat": legend}
            for i, (expr, legend) in enumerate(targets)
        ],
    }
    if kind == "stat":
        out["options"] = {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value"}
    if kind == "bargauge":
        out["options"] = {"orientation": "horizontal", "displayMode": "basic"}
        out["targets"][0]["instant"] = True
    return out


def dashboard(
    uid: str, title: str, description: str, rows: list[tuple[str, list[Panel]]]
) -> dict[str, Any]:
    panels: list[dict[str, Any]] = []
    pid, y = 1, 0
    for row_title, row_panels in rows:
        panels.append(
            {
                "id": pid,
                "type": "row",
                "title": row_title,
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": y},
                "panels": [],
            }
        )
        pid, y, x, tallest = pid + 1, y + 1, 0, 0
        for panel in row_panels:
            if x + panel[4] > 24:
                x, y, tallest = 0, y + tallest, 0
            built = _panel(pid, x, y, panel)
            panels.append(built)
            pid, x = pid + 1, x + panel[4]
            tallest = max(tallest, built["gridPos"]["h"])
        y += tallest
    return {
        "__inputs": [
            {
                "name": "DS_PROMETHEUS",
                "label": "Prometheus",
                "type": "datasource",
                "pluginId": "prometheus",
                "pluginName": "Prometheus",
            }
        ],
        "uid": uid,
        "title": title,
        "description": description,
        "tags": ["maya"],
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "refresh": "1m",
        "time": {"from": "now-24h", "to": "now"},
        "templating": {"list": []},
        "annotations": {"list": []},
        "links": [],
        "panels": panels,
    }


DASHBOARDS = {
    "maya-platform.json": dashboard(
        "maya-platform",
        "MAYA — platform",
        "Requests, latency, the job queue, resolution and pins, the database, and security posture.",
        PLATFORM,
    ),
    "maya-governance.json": dashboard(
        "maya-governance",
        "MAYA — model governance",
        "Live models and their warrants, restatements under them, reviews and findings, and the AI gateway.",
        GOVERNANCE,
    ),
}


def render(board: dict[str, Any]) -> str:
    return json.dumps(board, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, board in DASHBOARDS.items():
        (OUT / name).write_text(render(board), encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT) / name}")


if __name__ == "__main__":
    main()
