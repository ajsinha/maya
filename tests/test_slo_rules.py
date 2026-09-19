"""
The shipped SLO and alert rules (§20: "each SLO has an alert with a runbook link").

A rules file is easy to write and easy to let rot: a metric gets renamed, a
runbook gets moved, and the alert that was supposed to wake somebody up silently
never fires again. These tests hold the file to three things — every alert links
a runbook that exists, every metric it names is one MAYA actually exports, and
the four objectives of §20 each have an alert — so the rot is caught here rather
than during an incident.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "config" / "prometheus" / "maya-slo.rules.yml"
FUNCTIONS = {
    "sum",
    "rate",
    "increase",
    "histogram_quantile",
    "clamp_min",
    "clamp_max",
    "by",
    "le",
    "on",
    "printf",
    "avg",
    "max",
    "min",
    "and",
    "or",
    "unless",
    "without",
    "ignoring",
    "group_left",
    "group_right",
}


@pytest.fixture(scope="module")
def rules() -> dict:
    return yaml.safe_load(RULES.read_text(encoding="utf-8"))


def _alerts(rules: dict) -> list[dict]:
    return [r for g in rules["groups"] for r in g["rules"] if "alert" in r]


def _records(rules: dict) -> list[dict]:
    return [r for g in rules["groups"] for r in g["rules"] if "record" in r]


def test_the_file_is_valid_prometheus_rule_structure(rules):
    assert [g["name"] for g in rules["groups"]] == ["maya-slo-recording", "maya-slo-alerts"]
    for rule in _alerts(rules) + _records(rules):
        assert "expr" in rule and rule["expr"].strip()
    assert len(_alerts(rules)) >= 12


def test_every_alert_links_a_runbook_that_exists(rules):
    """§20's actual requirement. An alert whose runbook link is broken is worse than no
    alert: it fires at two in the morning and then wastes the responder's first minute."""
    missing = []
    for rule in _alerts(rules):
        url = rule.get("annotations", {}).get("runbook_url")
        if not url:
            missing.append(f"{rule['alert']} has no runbook_url")
        elif not (ROOT / url).exists():
            missing.append(f"{rule['alert']} points at {url}, which does not exist")
    assert missing == [], "\n".join(missing)


def test_every_alert_has_a_severity_and_a_summary(rules):
    for rule in _alerts(rules):
        assert rule["labels"]["severity"] in ("warning", "critical"), rule["alert"]
        assert rule["annotations"]["summary"].strip(), rule["alert"]


def test_the_four_objectives_of_section_20_each_have_an_alert(rules):
    """99.9% availability, p95 under 300 ms, pin jobs finishing predictably, and zero
    unrecovered pin sagas."""
    labelled = {r["labels"].get("slo") for r in _alerts(rules)}
    assert {"metadata-availability", "metadata-latency", "pin-duration", "pin-sagas"} <= labelled


def test_every_metric_named_by_a_rule_is_one_maya_exports(rules):
    """The test that keeps the file from rotting: a rule naming maya_foo_total when the
    code exports maya_foo_seconds_total is a rule that can never fire."""
    from maya.observability.metrics import METRICS

    known = set(METRICS._help)
    known |= {f"{n}_bucket" for n, (kind, _) in METRICS._help.items() if kind == "histogram"}
    known |= {f"{n}_sum" for n, (kind, _) in METRICS._help.items() if kind == "histogram"}
    known |= {f"{n}_count" for n, (kind, _) in METRICS._help.items() if kind == "histogram"}
    recorded = {r["record"] for r in _records(rules)}
    unknown = []
    for rule in _alerts(rules) + _records(rules):
        for name in re.findall(r"\b(maya[a-z_:0-9]*)\b", rule["expr"]):
            if name in known or name in recorded or name in FUNCTIONS:
                continue
            unknown.append(f"{rule.get('alert') or rule.get('record')} names unexported {name}")
    assert unknown == [], "\n".join(unknown)


def test_the_file_says_where_it_substitutes_for_an_objective_it_cannot_measure():
    """§20 asks for "99% of pin jobs finishing within their estimated time x 2". MAYA
    stores no estimate, so the rule uses a fixed budget — and the file has to say so
    rather than let a reader believe the objective is met."""
    text = RULES.read_text(encoding="utf-8")
    assert "NOT measurable as" in text and "estimate" in text
    assert "docs/runbooks/" in text
