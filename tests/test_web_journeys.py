"""
Web journeys the page sweep does not reach: every form of the training and
execution warrant lifecycles, the administration pages and the workspace
branch, each driven by the user whose role it is, in their own browser session.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import json
import re

import pytest

from tests.conftest import PASSWORD, World, build_platform
from tests.test_warrants import XY_DEF, complete_spec, xy_csv

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
FLASH_RE = re.compile(r'class="alert alert-(\w+)[^"]*"[^>]*>([^<]*)')


@pytest.fixture(scope="module")
def site():
    from maya.server import build_app
    platform = build_platform(["--observability.webhooks.allow_private=true"])
    w = World(platform)
    p = platform
    p.access.create_user(w.admin, username="mgr2", password=PASSWORD, roles=["model_manager"])
    p.access.create_namespace(w.admin, name="quant", preset="standard")
    p.features.create(w.dana, namespace="quant", name="xy", definition=XY_DEF)
    p.features.ingest(w.dana, "quant/xy", xy_csv(), fmt="csv")
    p.features.transition(w.dana, "quant/xy", 1, "submit")
    p.features.transition(w.mick, "quant/xy", 1, "approve")
    fs_def = {"index": ["date", "symbol"], "grid": "as_is", "alignment": {"mode": "inner"},
              "members": [{"attr": a, "ref": "maya://feature/quant/xy@v1", "source_attr": a}
                          for a in ("x", "y")]}
    p.featuresets.create(w.devi, namespace="quant", name="panel", definition=fs_def)
    p.featuresets.transition(w.devi, "quant/panel", 1, "submit")
    p.featuresets.transition(w.mick, "quant/panel", 1, "approve")
    p.featuresets.pin(w.mick, "quant/panel", version_no=1, pin_name="q1",
                      as_of=dt.date(2026, 2, 28), cascade=True)
    w.drain()
    p.models.create(w.mona, namespace="quant", name="linear", formula="yhat = a*x + b",
                    roles={"a": "parameter", "b": "parameter"})
    p.models.update_draft(w.mona, "quant/linear", spec_latex=complete_spec("linear"))
    p.models.transition(w.mona, "quant/linear", 1, "submit")
    p.models.transition(w.mgr, "quant/linear", 1, "approve")
    yield w, build_app(platform)
    platform.shutdown()


class Browser:
    """One person's session: signs in (changing a first-use password) and posts forms."""

    def __init__(self, app, username: str, password: str) -> None:
        from starlette.testclient import TestClient
        self.c = TestClient(app)
        r = self.c.post("/login", data={"username": username, "password": password,
                                        "csrf_token": self.csrf("/login")},
                        follow_redirects=False)
        assert r.status_code == 303, r.text[:300]
        if r.headers["location"] == "/account/password":
            new = password + "-2"
            r = self.c.post("/account/password", data={
                "old_password": password, "new_password": new, "confirm_password": new,
                "csrf_token": self.csrf("/account/password")}, follow_redirects=False)
            assert r.status_code == 303 and r.headers["location"] == "/", r.text[:300]

    def csrf(self, path: str = "/") -> str:
        return CSRF_RE.search(self.c.get(path).text).group(1)

    def get(self, path: str, status: int = 200):
        r = self.c.get(path)
        assert r.status_code == status, (path, r.status_code, r.text[:300])
        return r

    def post(self, path: str, data: dict | None = None, *, files=None, expect: str | None = None,
             headers: dict | None = None):
        """POST a form; ``expect`` is the flash level that must come back (e.g. success)."""
        body = {**(data or {}), "csrf_token": self.csrf()}
        r = self.c.post(path, data=body, files=files, headers=headers)
        assert r.status_code == 200, (path, r.status_code, r.text[:300])
        flashes = FLASH_RE.findall(r.text)
        if expect is None:
            assert not any(level == "danger" for level, _ in flashes), (path, flashes)
        else:
            assert any(level == expect for level, _ in flashes), (path, expect, flashes)
        return r


def test_a_training_warrant_from_draft_to_bundle_through_forms(site):
    w, app = site
    devi, mgr = Browser(app, "devi", PASSWORD), Browser(app, "mgr", PASSWORD)
    new = devi.get("/warrants/training/new").text
    assert "maya://featureset/quant/panel#q1/2026-02-28" in new and "quant/linear@v1" in new
    r = devi.post("/warrants/training/new", {
        "namespace": "quant", "name": "calib-web", "model": "maya://model/quant/linear@v1",
        "featureset": "maya://featureset/quant/panel#q1/2026-02-28", "target": "y",
        "seed": "7", "bindings": "{}", "train": "0.7", "validation": "0.15", "test": "0.15"},
        expect="success")
    wid = re.search(r"/warrants/training/([0-9a-f-]{32,36})", str(r.url)).group(1)
    assert "certified" in devi.get(f"/warrants/training/{wid}").text
    data = devi.get(f"/warrants/training/{wid}/data")
    manifest = json.loads(data.headers["X-Maya-Manifest"])
    assert data.content[:4] == b"PAR1" and len(manifest["checksum"]) == 64
    devi.post(f"/warrants/training/{wid}/parameters", {
        "values": json.dumps({"a": 2.0, "b": 0.5}), "metrics": json.dumps({"rmse": 0.0}),
        "data_checksum": manifest["checksum"]}, expect="success")
    devi.post(f"/warrants/training/{wid}/parameters", {
        "values": json.dumps({"a": 9.0, "b": 9.0}), "data_checksum": "0" * 64},
        expect="warning")
    sets = w.p.warrants.get(w.devi, wid)["parameter_sets"]
    good = next(s for s in sets if s["verified_data"])
    back = {"referer": f"http://testserver/warrants/training/{wid}?tab=params"}
    devi.post(f"/warrants/parameters/{good['id']}/transition", {"transition": "submit"},
              headers=back, expect="success")
    mgr.post(f"/warrants/parameters/{good['id']}/transition", {"transition": "approve"},
             headers=back, expect="success")
    r = devi.post(f"/warrants/training/{wid}/score", {"parameter_set_id": good["id"]},
                  expect="info")
    assert "Blind score, attempt 1" in r.text
    devi.post(f"/warrants/training/{wid}/transition", {"transition": "submit"}, expect="success")
    mgr.post(f"/warrants/training/{wid}/transition", {"transition": "approve"}, expect="success")
    mgr.post(f"/warrants/training/{wid}/seal", expect="success")
    r = devi.post(f"/warrants/training/{wid}/bundle", expect="success")
    blob = re.search(r"/warrants/bundles/([0-9a-f]{64})", r.text).group(1)
    bundle = devi.get(f"/warrants/bundles/{blob}")
    assert bundle.content[:2] == b"PK"
    report = devi.post("/warrants/verify", files={"file": ("b.zip", bundle.content,
                                                           "application/zip")})
    assert "data content hash" in report.text and "verified" in report.text.lower()
    r = devi.post("/warrants/verify", expect="danger")                  # no file chosen
    assert "Choose a bundle" in r.text
    r = devi.post(f"/warrants/training/{wid}/clone", {"changes": json.dumps({"seed": 11})},
                  expect="success")
    assert "/warrants/training/" in str(r.url) and wid not in str(r.url)
    r = mgr.post(f"/warrants/training/{wid}/revoke", {"reason": "superseded"}, expect="danger")
    assert "Only the model owner or an administrator" in r.text
    Browser(app, "admin", "maya-dev-admin").post(
        f"/warrants/training/{wid}/revoke", {"reason": "superseded by calib-web v2"},
        expect="warning")
    assert w.p.warrants.get(w.devi, wid)["revoked_at"] is not None


def test_an_execution_warrant_lifecycle_through_forms(site):
    w, app = site
    mgr, mgr2 = Browser(app, "mgr", PASSWORD + "-2"), Browser(app, "mgr2", PASSWORD)
    tw = w.p.warrants.create(w.devi, namespace="quant", name="calib-exec",
                             model="quant/linear@v1",
                             featureset="maya://featureset/quant/panel#q1/2026-02-28",
                             spec={"target": "y"})
    ps = w.p.warrants.upload_parameters(w.devi, tw["id"], values={"a": 2.0, "b": 0.5},
                                        data_checksum=w.p.warrants.data(w.devi, tw["id"])
                                        ["manifest"]["checksum"])
    w.p.warrants.parameter_transition(w.devi, ps["id"], "submit")
    w.p.warrants.parameter_transition(w.mgr, ps["id"], "approve")
    w.p.warrants.transition(w.devi, tw["id"], "submit")
    w.p.warrants.transition(w.mgr, tw["id"], "approve")
    w.p.warrants.seal(w.mgr, tw["id"])
    page = mgr.get(f"/warrants/execution/new?training_warrant_id={tw['id']}").text
    assert f"{tw['id']}|{ps['id']}" in page
    r = mgr.c.post("/warrants/execution/new", data={
        "csrf_token": mgr.csrf(), "namespace": "quant", "name": "live-web",
        "choice": f"{tw['id']}|{ps['id']}", "environments": "dev", "contact": "desk@x.test",
        "covenants": json.dumps([{"kind": "input_null_rate", "attr": "x", "max": 0.1}])})
    assert r.status_code == 200 and "/warrants/execution/" in str(r.url)
    eid = str(r.url).rsplit("/", 1)[1]
    mgr.post(f"/warrants/execution/{eid}/transition", {"transition": "submit"}, expect="success")
    mgr2.post(f"/warrants/execution/{eid}/transition", {"transition": "approve"},
              expect="success")
    mgr.post(f"/warrants/execution/{eid}/seal", expect="success")
    r = mgr.post(f"/warrants/execution/{eid}/token", {"environment": "dev"})
    assert "live-web" in r.text and re.search(r"[A-Za-z0-9_-]{40,}\.[A-Za-z0-9+/=_-]{40,}",
                                              r.text)
    mgr.post(f"/warrants/execution/{eid}/report", {
        "environment": "dev", "rows": "10", "input_stats": json.dumps({"x": {"null_rate": 0.0}})},
        expect="success")
    r = mgr.c.post(f"/warrants/execution/{eid}/report", data={
        "csrf_token": mgr.csrf(), "environment": "dev", "rows": "10",
        "input_stats": json.dumps({"x": {"null_rate": 0.5}})})
    assert "SUSPENDED" in r.text
    assert w.p.execution.get(w.mgr, eid)["status"] == "suspended"
    assert "Unattested offline use" not in mgr.get(f"/warrants/execution/{eid}").text
    w.p.execution.reinstate(w.admin, eid, "reset for the offline check")
    w.p.execution.bundle(w.mgr, eid, "dev", offline=True)
    page = mgr.get(f"/warrants/execution/{eid}").text
    assert "Unattested offline use" in page and "1 copy of this warrant was issued" in page
    w.p.execution.report(w.mgr, eid, environment="dev", rows=10,
                         input_stats={"x": {"null_rate": 0.5}})           # suspended again
    admin = Browser(app, "admin", "maya-dev-admin-2")
    admin.post(f"/warrants/execution/{eid}/reinstate", {"reason": "vendor file was late"},
               expect="success")
    admin.post(f"/warrants/execution/{eid}/revoke", {"reason": "model withdrawn"},
               expect="warning")
    assert w.p.execution.get(w.mgr, eid)["status"] == "revoked"


def test_administration_forms(site):
    w, app = site
    admin = Browser(app, "admin", "maya-dev-admin-2")
    admin.post("/admin/users", {"username": "newbie", "password": "Newbie-pass-123",
                                "display_name": "New Bie", "roles": "feature_designer",
                                "desk": "rates"}, expect="success")
    assert w.principal("newbie").desk == "rates"
    admin.post("/admin/users/newbie/roles", {"roles": ["feature_designer", "techops"]},
               expect="success")
    assert set(w.principal("newbie").roles) == {"feature_designer", "techops"}
    admin.post("/admin/users/newbie/password", {"new_password": "Reset-pass-12345"},
               expect="success")
    admin.post("/admin/users/newbie/mfa-reset", expect="success")
    admin.post("/admin/users/newbie/status", {"status": "disabled"}, expect="success")
    with w.p.uow() as uow:
        assert uow.repo("users").find_one(username="newbie")["status"] == "disabled"
    admin.post("/admin/roles", {"name": "auditor", "capabilities": json.dumps(
        {"feature": "R", "model": "R"}), "description": "reads"}, expect="success")
    admin.post("/admin/groups", {"name": "rates-desk", "roles": "feature_designer",
                                 "members": "dana, newbie"}, expect="success")
    admin.post("/admin/namespaces", {"name": "credit", "preset": "regulated",
                                     "production": "1"}, expect="success")
    admin.post("/admin/namespaces/credit", {"sod": "two_person"}, expect="success")
    admin.post("/admin/grants", {"kind": "feature", "ref": "quant/xy", "principal_type": "user",
                                 "principal_id": "tess", "level": "read", "days": "30",
                                 "row_filter": "symbol == 'AAA'", "masks": "y:null",
                                 "until": "2026-12-31"}, expect="success")
    rows = w.p.access.grants_for("feature", w.p.access.resolve_object("feature",
                                                                      "quant/xy")["id"])
    grant = next(g for g in rows if g["conditions"])
    assert grant["conditions"] == {"row_filter": "symbol == 'AAA'", "column_mask": {"y": "null"},
                                   "time_bound": {"until": "2026-12-31"}}
    page = admin.get("/admin/grants?kind=feature&ref=quant/xy").text
    assert "symbol == &#39;AAA&#39;" in page or "symbol == 'AAA'" in page
    admin.post(f"/admin/grants/{grant['id']}/revoke", expect="success")
    import sqlite3
    db = w.p.root / "warehouse.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE px (d TEXT, sym TEXT, close REAL)")
    admin.post("/admin/sources", {"name": "warehouse", "url": f"sqlite:///{db}",
                                  "description": "test"}, expect="success")
    admin.post("/admin/sources/warehouse/test", expect="success")
    admin.post("/admin/sources", {"name": "missing", "url": f"sqlite:///{db}.nope"},
               expect="success")
    r = admin.post("/admin/sources/missing/test", expect="danger")
    assert "unable to open database file" in r.text          # read-only: never creates one
    admin.post("/admin/sources/warehouse/delete", expect="info")
    audit = admin.get("/admin/audit?action=access.granted").text
    assert "access.granted" in audit and "access.revoked" not in audit     # the filter holds
    assert "db.dialect" in admin.get("/admin/config").text
    r = admin.post("/admin/integrity", expect="success")
    assert re.search(r"Integrity verified: [1-9]\d* pin\(s\), 0 with drift", r.text)
    assert "Integrity verified" not in admin.get("/admin/storage").text     # shown once
    estate = admin.get("/admin/estate")
    assert estate.content[:2] == b"PK"


def test_admin_forms_refuse_a_non_administrator(site):
    _, app = site
    dana = Browser(app, "dana", PASSWORD)
    r = dana.post("/admin/users", {"username": "sneaky", "password": "Sneaky-pass-123"},
                  expect="danger")
    assert "PermissionDenied" in r.text or "not" in r.text.lower()


def test_job_actions_from_the_jobs_page(site):
    w, app = site
    admin = Browser(app, "admin", "maya-dev-admin-2")
    out = w.p.featuresets.pin(w.mick, "quant/panel", version_no=1, pin_name="q2",
                              as_of=dt.date(2026, 1, 31), cascade=True)
    job_id = out["job"]["id"]
    def state() -> str:
        with w.p.uow() as uow:
            return uow.repo("jobs").require(job_id)["state"]
    admin.post(f"/admin/jobs/{job_id}/cancel", expect="info")
    assert state() == "cancelled"
    r = admin.post(f"/admin/jobs/{job_id}/retry", expect="danger")
    assert "Only failed or dead-lettered jobs are retried" in r.text and state() == "cancelled"
    w.drain()
    assert "feature" in admin.get("/admin/jobs").text


def test_a_workspace_branch_through_forms(site):
    w, app = site
    dana = Browser(app, "dana", PASSWORD + "-2")
    r = dana.post("/workbench/workspaces", {"name": "tighter-fill", "description": "try it"})
    ws_id = str(r.url).rsplit("/", 1)[1]
    page = dana.get(f"/workbench/workspaces/{ws_id}?ref=quant/xy&kind=feature").text
    assert "resolution" in page
    definition = dict(XY_DEF, resolution={"grid": "as_is", "rules": {"x": "forward_fill(limit=1)"}})
    dana.post(f"/workbench/workspaces/{ws_id}/stage", {
        "kind": "feature", "ref": "quant/xy", "definition": json.dumps(definition),
        "note": "cap the fill"}, expect="success")
    ws = w.p.workspaces.get(w.dana, ws_id)
    assert len(ws["changes"]) == 1
    page = dana.get(f"/workbench/workspaces/{ws_id}?preview=quant/xy").text
    assert "quant/panel" in page or "downstream" in page.lower()
    dana.post(f"/workbench/workspaces/{ws_id}/replay", expect="info")
    w.drain()
    dana.post(f"/workbench/workspaces/{ws_id}/changes/{ws['changes'][0]['id']}/unstage")
    assert w.p.workspaces.get(w.dana, ws_id)["changes"] == []
    dana.post(f"/workbench/workspaces/{ws_id}/abandon", expect="info")
    assert w.p.workspaces.get(w.dana, ws_id)["state"] == "abandoned"
