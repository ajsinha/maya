"""
The shipped Grafana dashboards: valid, current, and reading only metrics MAYA exports.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from maya.observability.metrics import METRICS

ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = ("_bucket", "_count", "_sum")


def _builder():
    spec = importlib.util.spec_from_file_location(
        "build_dashboards", ROOT / "tools/ops/build_dashboards.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["maya-platform.json", "maya-governance.json"])
def test_the_committed_dashboard_is_what_the_builder_writes(name):
    builder = _builder()
    committed = (ROOT / "config" / "grafana" / name).read_text(encoding="utf-8")
    assert committed == builder.render(builder.DASHBOARDS[name]), (
        f"config/grafana/{name} is stale: run python tools/ops/build_dashboards.py"
    )


@pytest.mark.parametrize("name", ["maya-platform.json", "maya-governance.json"])
def test_every_query_reads_a_metric_maya_exports(name):
    board = json.loads((ROOT / "config" / "grafana" / name).read_text(encoding="utf-8"))
    described = set(METRICS._help)
    panels = [p for p in board["panels"] if p["type"] != "row"]
    assert len(panels) >= 15
    ids = [p["id"] for p in board["panels"]]
    assert len(ids) == len(set(ids))
    for panel in panels:
        assert all(p <= 24 for p in (panel["gridPos"]["x"] + panel["gridPos"]["w"],))
        for target in panel["targets"]:
            for metric in re.findall(r"\bmaya_[a-z_]+", target["expr"]):
                base = next((metric[: -len(s)] for s in SUFFIXES if metric.endswith(s)), metric)
                assert base in described, (
                    f"{panel['title']} reads {metric}, which MAYA does not export"
                )
