"""
Workspaces and shadow replay (§28.3, §29.2): a change is rehearsed on a branch
of the catalog, its downstream impact is found, the dependent model is replayed
numerically, and approval is the merge — with nothing production-facing touched
before it, and a base that moved on refused as a conflict.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import copy
import datetime as dt

import pytest

from maya.core.errors import ConflictError, PermissionDenied
from tests.test_warrants import XY_DEF, complete_spec, xy_csv

CLIPPED = dict(copy.deepcopy(XY_DEF), transform=[{"op": "clip", "attr": "x", "lo": 0, "hi": 3}])


@pytest.fixture(scope="module")
def branch(world):
    w = world
    w.p.access.create_namespace(w.admin, name="wsn")
    w.p.features.create(w.dana, namespace="wsn", name="xy", definition=XY_DEF)
    w.p.features.ingest(w.dana, "wsn/xy", xy_csv(), fmt="csv")
    w.p.features.transition(w.dana, "wsn/xy", 1, "submit")
    w.p.features.transition(w.mick, "wsn/xy", 1, "approve")
    fs = {
        "index": ["date", "symbol"],
        "members": [
            {"attr": "x", "ref": "maya://feature/wsn/xy@v1", "source_attr": "x"},
            {"attr": "y", "ref": "maya://feature/wsn/xy@v1", "source_attr": "y"},
        ],
    }
    w.p.featuresets.create(w.devi, namespace="wsn", name="panel", definition=fs)
    w.p.featuresets.transition(w.devi, "wsn/panel", 1, "submit")
    w.p.featuresets.transition(w.mick, "wsn/panel", 1, "approve")
    w.p.featuresets.pin(
        w.mick, "wsn/panel", version_no=1, pin_name="q1", as_of=dt.date(2026, 2, 28), cascade=True
    )
    w.drain()
    w.p.models.create(
        w.mona,
        namespace="wsn",
        name="lin",
        formula="yhat = a*x + b",
        roles={"a": "parameter", "b": "parameter"},
    )
    w.p.models.update_draft(w.mona, "wsn/lin", spec_latex=complete_spec("lin"))
    w.p.models.transition(w.mona, "wsn/lin", 1, "submit")
    w.p.models.transition(w.mgr, "wsn/lin", 1, "approve")
    tw = w.p.warrants.create(
        w.devi,
        namespace="wsn",
        name="tw",
        model="wsn/lin@v1",
        featureset="maya://featureset/wsn/panel#q1/2026-02-28",
        spec={"target": "y"},
    )
    checksum = w.p.warrants.data(w.devi, tw["id"])["manifest"]["checksum"]
    ps = w.p.warrants.upload_parameters(
        w.devi, tw["id"], values={"a": 2.0, "b": 0.5}, data_checksum=checksum
    )
    w.p.warrants.parameter_transition(w.devi, ps["id"], "submit")
    w.p.warrants.parameter_transition(w.mgr, ps["id"], "approve")
    return w, tw


def test_rehearsal_is_visible_inside_and_invisible_outside(branch):
    w, _ = branch
    ws = w.p.workspaces.create(w.dana, "clip-x")
    w.p.workspaces.stage(w.dana, ws["id"], kind="feature", ref="wsn/xy", definition=CLIPPED)
    inside = w.p.workspaces.preview(w.dana, ws["id"], "maya://feature/wsn/xy@v1")
    outside = w.p.features.preview(w.dana, "maya://feature/wsn/xy@v1")
    assert max(r["x"] for r in inside["rows"]) <= 3.0
    assert max(r["x"] for r in outside["rows"]) > 3.0
    via_set = w.p.workspaces.preview(w.dana, ws["id"], "maya://featureset/wsn/panel@v1")
    assert max(r["x"] for r in via_set["rows"]) <= 3.0, "the change reaches through members"
    assert [v["state"] for v in w.p.features.get(w.dana, "wsn/xy")["versions"]] == ["approved"]


def test_impact_and_shadow_replay_measure_the_shift(branch):
    w, tw = branch
    ws = w.p.workspaces.create(w.dana, "clip-x-replay")
    w.p.workspaces.stage(w.dana, ws["id"], kind="feature", ref="wsn/xy", definition=CLIPPED)
    impact = w.p.workspaces.impact(w.dana, ws["id"])
    assert "maya://warrant/train/wsn/tw@v1" in impact["warrants"]
    w.p.workspaces.request_replay(w.dana, ws["id"])
    w.drain()
    report = w.p.workspaces.get(w.dana, ws["id"])["replay"]
    entry = next(r for r in report["warrants"] if r["warrant"].endswith("wsn/tw@v1"))
    assert entry["replayed"] and entry["rows_over_materiality"] > 0
    assert entry["max_abs_shift"] > 0 and "moves 1 of" in report["summary"]
    assert report["sample_rows"] == 5000 and "not proof" in report["basis"]


def test_shadow_replay_reaches_execution_warrants(branch):
    """An execution warrant is replayed through the training warrant it was issued from,
    scored with its own sealed parameters — never reported as 'warrant not found'."""
    w, tw = branch
    with w.p.uow() as uow:
        ps = uow.repo("parameter_sets").find_one(training_warrant_id=tw["id"])
    ew = w.p.execution.create(
        w.mgr, namespace="wsn", name="live", training_warrant_id=tw["id"], parameter_set_id=ps["id"]
    )
    ws = w.p.workspaces.create(w.dana, "clip-x-exec")
    w.p.workspaces.stage(w.dana, ws["id"], kind="feature", ref="wsn/xy", definition=CLIPPED)
    uri = "maya://warrant/exec/wsn/live@v1"
    assert uri in w.p.workspaces.impact(w.dana, ws["id"])["warrants"]
    w.p.workspaces.request_replay(w.dana, ws["id"])
    w.drain()
    report = w.p.workspaces.get(w.dana, ws["id"])["replay"]
    entry = next(r for r in report["warrants"] if r["warrant"] == uri)
    assert entry["replayed"], entry
    train = next(r for r in report["warrants"] if r["warrant"].endswith("train/wsn/tw@v1"))
    assert entry["max_abs_shift"] == pytest.approx(train["max_abs_shift"])
    with w.p.uow() as uow:
        uow.repo("execution_warrants").update(ew["id"], {"training_warrant_id": None})
        assert "no feature set to replay" in w.p.workspaces._target(uow, uri)[1]


def test_workspace_pages_render(branch):
    """Runs before the merge test: once xy v2 is approved, the feature set (bound to
    xy@v1) is no longer downstream of a change staged against v2 — correctly."""
    import re
    from starlette.testclient import TestClient
    from maya.server import build_app

    w, _ = branch
    ws = w.p.workspaces.create(w.dana, "ui-check")
    w.p.workspaces.stage(w.dana, ws["id"], kind="feature", ref="wsn/xy", definition=CLIPPED)
    w.p.workspaces.request_replay(w.dana, ws["id"])
    w.drain()
    web = TestClient(build_app(w.p))
    login = web.get("/login")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', login.text).group(1)
    web.post("/login", data={"username": "dana", "password": "Test-password-1", "csrf_token": csrf})
    listing = web.get("/workbench/workspaces")
    if "/account/password" in str(listing.url):
        page = web.get("/account/password")
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        web.post(
            "/account/password",
            data={
                "old_password": "Test-password-1",
                "new_password": "Changed-pass-22",
                "confirm_password": "Changed-pass-22",
                "csrf_token": csrf,
            },
        )
        listing = web.get("/workbench/workspaces")
    assert listing.status_code == 200 and "ui-check" in listing.text
    page = web.get(
        f"/workbench/workspaces/{ws['id']}?preview=maya://feature/wsn/xy@v1&kind=feature&ref=wsn/xy"
    )
    assert page.status_code == 200
    assert "Shadow replay" in page.text and "maya://warrant/train/wsn/tw@v1" in page.text
    assert "data-maya-table" in page.text and "Proposed definition" in page.text


def test_approval_is_the_merge_and_a_moved_base_is_a_conflict(branch):
    w, _ = branch
    stale = w.p.workspaces.create(w.dana, "stale")
    w.p.workspaces.stage(
        w.dana,
        stale["id"],
        kind="feature",
        ref="wsn/xy",
        definition=dict(CLIPPED, transform=[{"op": "clip", "attr": "x", "lo": 0, "hi": 4}]),
    )
    ws = w.p.workspaces.create(w.dana, "merge-me")
    w.p.workspaces.stage(w.dana, ws["id"], kind="feature", ref="wsn/xy", definition=CLIPPED)
    with pytest.raises(PermissionDenied):
        w.p.workspaces.stage(w.mick, ws["id"], kind="feature", ref="wsn/xy", definition=XY_DEF)
    out = w.p.workspaces.submit(w.dana, ws["id"])
    assert out["submitted"][0]["version_no"] == 2
    assert w.p.workspaces.get(w.dana, ws["id"])["state"] == "in_review"
    w.p.features.transition(w.mick, "wsn/xy", 2, "approve")
    assert w.p.workspaces.get(w.dana, ws["id"])["state"] == "merged"
    with pytest.raises(ConflictError, match="rebase"):
        w.p.workspaces.submit(w.dana, stale["id"])
