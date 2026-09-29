"""
The shipped model-governance alert rules, held to the same standard as the SLO rules.

Every alert must link a runbook that exists, carry a severity and a summary, and name only
metrics MAYA exports -- otherwise a renamed gauge leaves an alert that can never fire.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from maya.observability.metrics import METRICS

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "config" / "prometheus" / "maya-governance.rules.yml"


@pytest.fixture(scope="module")
def alerts() -> list[dict]:
    doc = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return [r for g in doc["groups"] for r in g["rules"] if "alert" in r]


def test_every_alert_links_a_runbook_that_exists(alerts):
    assert len(alerts) >= 10
    for rule in alerts:
        url = rule["annotations"]["runbook_url"]
        assert (ROOT / url).exists(), f"{rule['alert']} points at {url}"
        assert rule["labels"]["severity"] in ("warning", "critical"), rule["alert"]
        assert rule["annotations"]["summary"].strip(), rule["alert"]


def test_every_metric_named_is_one_maya_exports(alerts):
    described = set(METRICS._help)
    for rule in alerts:
        for name in re.findall(r"\bmaya_[a-z_]+", rule["expr"]):
            assert name in described, f"{rule['alert']} names {name}, which MAYA does not export"


def test_the_runbooks_are_indexed():
    index = (ROOT / "docs" / "runbooks" / "README.md").read_text(encoding="utf-8")
    for url in {
        r["annotations"]["runbook_url"]
        for r in yaml.safe_load(RULES.read_text())["groups"][0]["rules"]
    }:
        assert Path(url).name in index, url
