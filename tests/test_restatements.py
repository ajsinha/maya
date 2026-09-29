"""
Restatement alerts: a correction under a live model's training pin is measured and told.

The pin never moves. What the check does is resolve the pin's definition again with what is
known now and, if that differs, score the live parameters both ways and notify the owners.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pytest

from maya.core.errors import PermissionDenied, ValidationFailed
from tests.conftest import PASSWORD
from tests.test_warrants import XY_DEF, complete_spec, xy_csv

PIN = "maya://featureset/restate/panel#q1/2026-02-28"


@pytest.fixture(scope="module")
def live(world):
    w = world
    w.p.access.create_user(w.admin, username="mgr3", password=PASSWORD, roles=["model_manager"])
    w.p.access.create_namespace(w.admin, name="restate", preset="standard")
    w.p.features.create(w.dana, namespace="restate", name="xy", definition=XY_DEF)
    w.p.features.ingest(w.dana, "restate/xy", xy_csv(), fmt="csv")
    w.p.features.transition(w.dana, "restate/xy", 1, "submit")
    w.p.features.transition(w.mick, "restate/xy", 1, "approve")
    fs_def = {
        "index": ["date", "symbol"],
        "grid": "as_is",
        "alignment": {"mode": "inner"},
        "members": [
            {"attr": "x", "ref": "maya://feature/restate/xy@v1", "source_attr": "x"},
            {"attr": "y", "ref": "maya://feature/restate/xy@v1", "source_attr": "y"},
        ],
    }
    w.p.featuresets.create(w.devi, namespace="restate", name="panel", definition=fs_def)
    w.p.featuresets.transition(w.devi, "restate/panel", 1, "submit")
    w.p.featuresets.transition(w.mick, "restate/panel", 1, "approve")
    w.p.featuresets.pin(
        w.mick,
        "restate/panel",
        version_no=1,
        pin_name="q1",
        as_of=dt.date(2026, 2, 28),
        cascade=True,
    )
    w.drain()
    w.p.models.create(
        w.mona,
        namespace="restate",
        name="linear",
        formula="yhat = a*x + b",
        roles={"a": "parameter", "b": "parameter"},
    )
    w.p.models.update_draft(w.mona, "restate/linear", spec_latex=complete_spec("linear"))
    w.p.models.transition(w.mona, "restate/linear", 1, "submit")
    w.p.models.transition(w.mgr, "restate/linear", 1, "approve")
    tw = w.p.warrants.create(
        w.devi,
        namespace="restate",
        name="calib",
        model="restate/linear@v1",
        featureset=PIN,
        spec={"target": "y", "seed": 7},
    )
    checksum = w.p.warrants.data(w.devi, tw["id"])["manifest"]["checksum"]
    ps = w.p.warrants.upload_parameters(
        w.devi, tw["id"], values={"a": 2.0, "b": 0.5}, data_checksum=checksum
    )
    w.p.warrants.parameter_transition(w.devi, ps["id"], "submit")
    w.p.warrants.parameter_transition(w.mgr, ps["id"], "approve")
    w.p.warrants.transition(w.devi, tw["id"], "submit")
    w.p.warrants.transition(w.mgr, tw["id"], "approve")
    w.p.warrants.seal(w.mgr, tw["id"])
    ew = w.p.execution.create(
        w.mgr,
        namespace="restate",
        name="live",
        training_warrant_id=tw["id"],
        parameter_set_id=ps["id"],
        spec={"environments": ["dev"], "contact": "risk@example.com"},
    )
    w.p.execution.transition(w.mgr, ew["id"], "submit")
    w.p.execution.transition(w.principal("mgr3"), ew["id"], "approve")
    w.p.execution.seal(w.mgr, ew["id"])
    w.ew = ew
    return w


def _restate(w, days, bump, known="2026-03-15"):
    """Corrected x for the first ``days`` days, reported in March."""
    lines = ["date,symbol,x,y,kt"]
    for i in range(days):
        d = dt.date(2026, 1, 1) + dt.timedelta(days=i)
        for j, s in enumerate(("AAA", "BBB", "CCC")):
            x = 1.0 + i * 0.1 + j + bump
            y = 2.0 * (1.0 + i * 0.1 + j) + 0.5
            lines.append(f"{d},{s},{x:.3f},{y:.3f},{known}T18:00:00Z")
    return w.p.features.ingest(w.dana, "restate/xy", ("\n".join(lines) + "\n").encode(), fmt="csv")


def test_nothing_is_said_while_the_data_under_the_pin_is_unchanged(live):
    w = live
    assert w.p.restatements.assess(w.ew["id"]) is None
    assert w.p.restatements.list(w.devi, w.ew["id"]) == []


def test_a_restatement_is_measured_scored_both_ways_and_told(live):
    w = live
    row = _restate(w, 10, bump=0.5)
    assert row["restatement"] is True
    w.drain()  # the ingest queued the assessment
    impacts = w.p.restatements.list(w.devi, w.ew["id"])
    assert len(impacts) == 1
    impact = impacts[0]
    assert impact["trigger"] == "maya://feature/restate/xy" and impact["state"] == "open"
    assert impact["rows"]["changed"] == 30 and impact["rows"]["added"] == 0
    assert impact["rows"]["changed_in_holdout"] <= 30
    # yhat = 2x + 0.5 moved by 2 * 0.5 on every restated row, and on no other
    assert impact["shift"]["max_abs"] == pytest.approx(1.0, abs=1e-6)
    assert 0 < impact["shift"]["share_moved"] < 1
    before, after = impact["metrics_sealed"], impact["metrics_corrected"]
    assert before["rows"] == after["rows"] and before["rmse"] < 1e-2
    if impact["rows"]["changed_in_holdout"]:
        assert after["rmse"] > before["rmse"]
    # the pin itself did not move, and the holdout was not spent
    with w.p.uow() as uow:
        pin = uow.repo("feature_set_pins").get(impact["feature_set_pin_id"])
        tw = uow.repo("training_warrants").get(impact["training_warrant_id"])
        notes = uow.repo("notifications").list(kind="restatement")
        audit = uow.repo("audit_events").find_one(action="restatement.impact")
    assert pin["content_hash"] == impact["sealed_hash"] != impact["corrected_hash"]
    assert tw["holdout_attempts"] == 0
    told = {n["user_id"] for n in notes}
    assert w.mgr.user_id in told and w.principal("mgr3").user_id in told
    assert "restated" in notes[0]["message"] and "RMSE" in notes[0]["message"]
    assert audit["detail"]["impact"] == impact["id"]
    # the same correction is not reported twice
    assert w.p.restatements.assess(w.ew["id"]) is None


def test_the_owner_acknowledges_with_a_note(live):
    w = live
    impact = w.p.restatements.list(w.devi, w.ew["id"])[0]
    with pytest.raises(PermissionDenied):
        w.p.restatements.acknowledge(w.dana, impact["id"], "not mine")
    with pytest.raises(ValidationFailed, match="Say what"):
        w.p.restatements.acknowledge(w.mgr, impact["id"], "  ")
    out = w.p.restatements.acknowledge(w.mgr, impact["id"], "Refit queued as calib v2")
    assert out["state"] == "acknowledged" and out["acknowledged_by"] == w.mgr.username
    with pytest.raises(ValidationFailed, match="already"):
        w.p.restatements.acknowledge(w.mgr, impact["id"], "again")


def test_a_check_can_be_asked_for_and_a_second_correction_is_a_second_impact(live):
    w = live
    _restate(w, 3, bump=1.5, known="2026-03-20")
    w.p.restatements.check(w.mgr, w.ew["id"])
    w.drain()
    impacts = w.p.restatements.list(w.devi, w.ew["id"])
    assert len(impacts) == 2 and impacts[0]["state"] == "open"
    with pytest.raises(PermissionDenied):
        w.p.restatements.check(w.dana, w.ew["id"])


def test_the_warrant_page_shows_impacts_and_takes_an_acknowledgement(live):
    import re

    from starlette.testclient import TestClient

    from maya.server import build_app

    w = live
    web = TestClient(build_app(w.p))
    page = web.get("/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    web.post(
        "/login", data={"username": "admin", "password": "maya-dev-admin", "csrf_token": token}
    )
    view = web.get(f"/warrants/execution/{w.ew['id']}")
    assert view.status_code == 200 and "Restated data" in view.text
    assert "1 restatement to acknowledge" in view.text and "Check now" in view.text
    impact = next(i for i in w.p.restatements.list(w.devi, w.ew["id"]) if i["state"] == "open")
    token = re.search(r'name="csrf_token" value="([^"]+)"', view.text).group(1)
    r = web.post(
        f"/warrants/execution/{w.ew['id']}/restatements/{impact['id']}/acknowledge",
        data={"note": "Immaterial: three days, holdout unchanged", "csrf_token": token},
    )
    assert r.status_code == 200 and "Immaterial: three days" in r.text
    assert "to acknowledge" not in r.text


def test_governance_gauges_count_warrants_restatements_and_documents(live):
    from maya.observability import governance
    from maya.observability.metrics import METRICS

    w = live
    samples = {
        (name, tuple(sorted(labels.items()))): v for name, labels, v in governance.collect(w.p)
    }
    assert samples[("maya_execution_warrants", (("status", "live"),))] >= 1
    assert samples[("maya_restatement_impacts", (("state", "acknowledged"),))] >= 1
    assert samples[("maya_restatement_impacts", (("state", "open"),))] == 0
    assert samples[("maya_restatement_oldest_open_seconds", ())] == 0
    assert ("maya_models_review_overdue", (("tier", "1"),)) in samples
    assert ("maya_findings_open", (("severity", "critical"),)) in samples
    assert samples[("maya_versions", (("kind", "model"), ("state", "approved")))] >= 1
    # no label names a model or a warrant: the series stay bounded
    assert all(
        set(dict(k[1])) <= {"status", "state", "kind", "tier", "severity", "within_days"}
        for k in samples
    )
    assert "maya_restatement_impacts_total" in METRICS.render()
