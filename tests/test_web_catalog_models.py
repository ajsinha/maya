"""
Web journeys for the catalog, models, workflow and account pages: every form a
feature manager, model designer, reviewer or policy administrator uses, driven
in their own browser session, with the state change checked behind the page.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import pytest

from maya.core import totp
from tests.conftest import PASSWORD, price_csv
from tests.test_warrants import complete_spec
from tests.test_web_journeys import Browser, site  # noqa: F401 - the shared estate fixture


@pytest.fixture(scope="module")
def people(site):  # noqa: F811
    w, app = site
    people = {
        u: Browser(app, u, PASSWORD) for u in ("dana", "mick", "mona", "mgr", "devi", "admin2")
    }
    people["admin"] = Browser(app, "admin", "maya-dev-admin")
    return w, app, people


def test_feature_pages_pin_clone_compare_and_comment(people):
    w, app, b = people
    dana, mick = b["dana"], b["mick"]
    w.p.features.create(
        w.dana,
        namespace="quant",
        name="px",
        definition=json.loads(
            json.dumps(
                {
                    "index": ["date", "symbol"],
                    "index_types": {"date": "date", "symbol": "string"},
                    "schema": [{"name": "close", "type": "float64"}],
                    "source": {"type": "csv"},
                    "resolution": {"grid": "as_is", "rules": {}},
                    "transform": [],
                    "quality": [],
                }
            )
        ),
    )
    w.p.features.ingest(w.dana, "quant/px", price_csv(10), fmt="csv")
    page = dana.get("/catalog/features/quant/px").text
    vid = w.p.features.get(w.dana, "quant/px")["versions"][0]["id"]
    dana.post(
        "/catalog/features/quant/px/transition",
        {"version_no": "1", "transition": "submit"},
        expect="success",
    )
    back = {"referer": "http://testserver/catalog/features/quant/px"}
    mick.post(
        "/catalog/comment",
        {
            "object_type": "feature_version",
            "object_id": vid,
            "body": "units of close?",
            "blocking": "1",
        },
        headers=back,
        expect="success",
    )
    r = mick.post(
        "/catalog/features/quant/px/transition",
        {"version_no": "1", "transition": "approve"},
        expect="danger",
    )
    assert "no_open_blocking_comments" in r.text
    note = w.p.workflow_svc.comments("feature_version", vid)[0]
    mick.post(f"/catalog/comments/{note['id']}/resolve", headers=back)
    mick.post(
        "/catalog/features/quant/px/transition",
        {"version_no": "1", "transition": "approve"},
        expect="success",
    )
    r = mick.post(
        "/catalog/features/quant/px/pin",
        {"version_no": "1", "pin_name": "eom", "as_of": "2026-01-10"},
        expect="info",
    )
    assert "Pin job queued" in r.text
    w.drain()
    pin = w.p.features.get(w.dana, "quant/px")["pins"][0]
    assert pin["state"] == "sealed"
    from urllib.parse import quote

    csv = dana.get(f"/catalog/download?ref={quote(pin['ref'], safe='')}&format=csv")
    assert csv.text.splitlines()[1].startswith("date,symbol,close")
    r = mick.post(
        f"/catalog/pins/{pin['id']}/retire", {"reason": "superseded"}, headers=back, expect="danger"
    )
    assert "Only an administrator retires a pin" in r.text
    b["admin"].post(
        f"/catalog/pins/{pin['id']}/retire",
        {"reason": "superseded"},
        headers=back,
        expect="success",
    )
    assert w.p.features.get(w.dana, "quant/px")["pins"][0]["state"] == "retired"
    r = dana.post("/catalog/features/quant/px/new-draft", expect="success")
    assert "/workbench/features/quant/px/edit" in str(r.url) and "Draft v2" in r.text
    dana.post("/catalog/features/quant/px/clone", {"new_name": "px_ext", "extend": "1"})
    ext = w.p.features.get(w.dana, "quant/px_ext")["versions"][0]["definition"]
    assert ext["extends"]["parent"].endswith("quant/px@v1")
    compare = dana.get("/catalog/features/quant/px/compare?v1=1&v2=2").text
    assert "v1" in compare and "v2" in compare
    assert "px" in page


def test_featureset_pages_transition_pin_and_new_draft(people):
    w, app, b = people
    mick, devi = b["mick"], b["devi"]
    assert "Attribute mapping" in devi.get("/catalog/featuresets/quant/panel").text
    r = mick.post(
        "/catalog/featuresets/quant/panel/pin",
        {"version_no": "1", "pin_name": "q3", "as_of": "2026-02-15", "cascade": "1"},
        expect="info",
    )
    assert "with cascade over its members" in r.text
    w.drain()
    r = devi.post("/catalog/featuresets/quant/panel/new-draft")
    assert "/workbench/featuresets/quant/panel/edit" in str(r.url)
    devi.post(
        "/catalog/featuresets/quant/panel/transition",
        {"version_no": "2", "transition": "submit"},
        expect="success",
    )
    mick.post(
        "/catalog/featuresets/quant/panel/transition",
        {"version_no": "2", "transition": "request_changes", "rationale": "rename x"},
        expect="success",
    )
    assert w.p.featuresets.get(w.devi, "quant/panel")["versions"][0]["state"] == "changes_requested"


def test_a_model_from_new_to_approved_through_forms(people):
    w, app, b = people
    mona, mgr, devi = b["mona"], b["mgr"], b["devi"]
    assert "Formula text" in mona.get("/models/new").text
    mona.post(
        "/models/new",
        {
            "namespace": "quant",
            "name": "bs",
            "kind": "formula",
            "authoring": "formula",
            "formula": "yhat = a*x",
            "roles": "a: parameter",
        },
        expect="success",
    )
    mona.post(
        "/models/quant/bs/formula",
        {
            "authoring": "python",
            "python_source": "def f(x, params):\n    return params['a'] * x + params['b']\n",
        },
        expect="success",
    )
    ir = w.p.models.get(w.mona, "quant/bs")["versions"][0]["formula_ir"]
    assert {i["name"]: i["role"] for i in ir["inputs"]} == {
        "a": "parameter",
        "b": "parameter",
        "x": "feature",
    }
    mona.post("/models/quant/bs/spec", {"spec_latex": complete_spec("bs")}, expect="success")
    r = mona.post("/models/quant/bs/render/1")
    assert "DRAFT RENDER" in r.text or "true LaTeX build" in r.text
    pdf = mona.get("/models/quant/bs/spec/1.pdf")
    assert pdf.content[:4] == b"%PDF"
    src = (
        "class Model:\n    def fit(self, X, y, ctx):\n        return {}\n\n"
        "    def predict(self, X, params, ctx):\n"
        "        return [params['a'] * v + params['b'] for v in X['x']]\n"
    )
    r = mona.post("/models/quant/bs/artifact", {"source": src}, expect="info")
    assert "validation ladder is running" in r.text
    w.drain()
    report = w.p.models.get(w.mona, "quant/bs")["versions"][0]["artifact_report"]
    assert report["passed"], report
    r = mona.post("/models/quant/bs/conformance/1", {"n": "200"})
    assert "Sampled agreement is not proof" in r.text and "200 of 200" in r.text
    mona.post(
        "/models/quant/bs/transition", {"version_no": "1", "transition": "submit"}, expect="success"
    )
    mgr.post(
        "/models/quant/bs/transition",
        {"version_no": "1", "transition": "approve"},
        expect="success",
    )
    r = mona.post("/models/quant/bs/new-draft", expect="success")
    assert "Draft v2 opened" in r.text
    mona.post(
        "/models/quant/bs/formula",
        {"authoring": "formula", "formula": "yhat = a*x*x", "roles": "a: parameter"},
        expect="success",
    )
    diff = mona.get("/models/quant/bs/diff?v1=1&v2=2").text
    assert "v1" in diff and "v2" in diff
    assert "bs" in devi.get("/models").text


def test_review_queue_and_generic_transitions(people):
    w, app, b = people
    dana, mick = b["dana"], b["mick"]
    w.p.features.create(
        w.dana,
        namespace="quant",
        name="rv",
        definition=json.loads(
            json.dumps(w.p.features.get(w.dana, "quant/px")["versions"][0]["definition"])
        ),
    )
    w.p.features.ingest(w.dana, "quant/rv", price_csv(3), fmt="csv")
    w.p.features.transition(w.dana, "quant/rv", 1, "submit")
    vid = w.p.features.get(w.dana, "quant/rv")["versions"][0]["id"]
    assert "quant/rv" in mick.get("/workflow").text
    review = mick.get(f"/workflow/review/feature_version/{vid}").text
    assert "approve" in review and "request_changes" in review
    mick.post(
        f"/workflow/review/feature_version/{vid}/transition",
        {"transition": "approve"},
        expect="success",
    )
    assert w.p.features.get(w.dana, "quant/rv")["versions"][0]["state"] == "approved"
    r = dana.c.get(f"/workflow/review/feature_version/{'0' * 32}")
    assert r.status_code == 404


def test_campaigns_aging_and_break_glass_reports(people):
    w, app, b = people
    mick = b["mick"]
    refs = []
    for i in range(2):
        name = f"cmp{i}"
        w.p.features.create(
            w.dana,
            namespace="quant",
            name=name,
            definition=w.p.features.get(w.dana, "quant/px")["versions"][0]["definition"],
        )
        w.p.features.ingest(w.dana, f"quant/{name}", price_csv(3), fmt="csv")
        w.p.features.transition(w.dana, f"quant/{name}", 1, "submit")
        refs.append(w.p.features.get(w.dana, f"quant/{name}")["versions"][0]["id"])
    assert "campaign" in mick.get("/workflow/campaigns").text.lower()
    r = mick.c.post(
        "/workflow/campaigns",
        data={
            "csrf_token": mick.csrf(),
            "name": "month-end",
            "transition": "approve",
            "item": [f"feature_version|{v}" for v in refs] + ["feature_version|" + "0" * 32],
            "rationale": "reviewed together",
        },
    )
    assert (
        "Campaign &#39;month-end&#39;: 2 of 3 succeeded" in r.text
        or "Campaign 'month-end': 2 of 3 succeeded" in r.text
    )
    r = mick.post("/workflow/campaigns", {"transition": "approve"}, expect="danger")
    assert "Select at least one object" in r.text
    mick.get("/workflow/aging")
    assert "Break-glass" in mick.get("/workflow/break-glass?days=7").text


def test_delegations_through_forms(people):
    w, app, b = people
    mick = b["mick"]
    page = mick.get("/workflow/delegations").text
    options = re.findall(r"<option>([^<]+)</option>", page)
    assert "dana" in options and "mick" not in options  # cannot delegate to yourself
    today = dt.date.today().isoformat()
    mick.c.post(
        "/workflow/delegations",
        data={
            "csrf_token": mick.csrf(),
            "to": "dana",
            "starts_on": today,
            "ends_on": today,
            "object_types": ["feature_version"],
            "reason": "leave",
        },
    )
    rows = w.p.workflow_svc.delegations(w.mick)
    live = [d for d in rows if not d.get("revoked_at")]
    assert live and live[0]["object_types"] == ["feature_version"]
    mick.post(f"/workflow/delegations/{live[0]['id']}/revoke", expect="info")
    assert all(d.get("revoked_at") for d in w.p.workflow_svc.delegations(w.mick))


def test_policy_editor_import_and_activation_by_a_second_admin(people):
    w, app, b = people
    admin, admin2 = b["admin"], b["admin2"]
    rows = w.p.workflow_svc.policies()
    fv = next(r for r in rows if r["object_type"] == "feature_version" and r["state"] == "active")
    assert "transitions" in admin.get(f"/workflow/policies/{fv['id']}").text
    token = admin.csrf()
    ok = admin.c.post(
        "/workflow/policies/validate",
        json={"object_type": "feature_version", "policy": fv["policy"]},
        headers={"X-CSRF-Token": token},
    )
    assert ok.status_code == 200 and ok.json()["errors"] == []
    bad = admin.c.post(
        "/workflow/policies/validate",
        json={"object_type": "feature_version", "policy": {"states": ["draft"], "transitions": {}}},
        headers={"X-CSRF-Token": token},
    )
    assert bad.json()["errors"]
    from maya.workflow import policy as pol

    r = admin.post(
        "/workflow/policies/import",
        {"object_type": "feature_version", "yaml": pol.to_yaml(fv["policy"])},
        expect="success",
    )
    draft_id = re.search(r"/workflow/policies/([0-9a-f-]{32,36})", str(r.url)).group(1)
    r = admin.post(f"/workflow/policies/{draft_id}/activate", expect="danger")
    assert "second" in r.text.lower() or "another" in r.text.lower()
    admin2.post(f"/workflow/policies/{draft_id}/activate", expect="success")
    r = admin.post(
        "/workflow/policies/import",
        {"object_type": "feature_version", "yaml": " "},
        expect="danger",
    )
    assert "Paste a policy in YAML" in r.text


def test_api_keys_and_two_factor_through_the_account_pages(people):
    w, app, b = people
    devi = b["devi"]
    r = devi.post("/account/keys", {"name": "notebook", "days": "30"})
    found = re.search(r"maya_[a-z]+_[0-9a-f]+_[A-Za-z0-9_-]+", r.text)
    assert found, (str(r.url), re.findall(r"alert-(\w+)[^>]*>([^<]*)", r.text))
    key = found.group(0)
    from maya.sdk import Client

    assert Client(app=app, api_key=key).auth.me()["username"] == "devi"
    key_id = key.split("_")[2]
    devi.post(f"/account/keys/{key_id}/revoke", expect="success")
    with pytest.raises(Exception):
        Client(app=app, api_key=key).auth.me()
    page = devi.c.post("/account/mfa/enroll", data={"csrf_token": devi.csrf("/account/mfa")}).text
    secret = re.search(r"secret=([A-Z2-7]+)", page).group(1)
    assert "secret=" not in devi.get("/account/mfa").text  # shown once
    r = devi.c.post(
        "/account/mfa/confirm", data={"csrf_token": devi.csrf("/account/mfa"), "code": "000000"}
    )
    assert "danger" in r.text
    code = totp.code_at(secret, totp.current_step())
    r = devi.c.post(
        "/account/mfa/confirm", data={"csrf_token": devi.csrf("/account/mfa"), "code": code}
    )
    assert "Two-factor authentication is on" in r.text
    # the next sign-in asks for a code, and a wrong one ends the attempt
    fresh = app
    from starlette.testclient import TestClient

    c = TestClient(fresh)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    r = c.post(
        "/login",
        data={"username": "devi", "password": PASSWORD + "-2", "csrf_token": tok},
        follow_redirects=False,
    )
    assert r.headers["location"] == "/mfa"
    tok = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/mfa").text).group(1)
    r = c.post("/mfa", data={"code": "123456", "csrf_token": tok})
    assert r.status_code == 401
    r = devi.post("/logout")
    # Out to the landing page: somebody who has just signed out is a visitor, not a
    # half-finished arrival, and what they should meet is what MAYA is for.
    assert str(r.url).endswith("/")
    assert "MAYA keeps the answer" in r.text


def test_governance_pages_raise_move_declare_and_review(people):
    w, app, b = people
    devi, mona, admin = b["devi"], b["mona"], b["admin"]
    assert "quant/linear" in devi.get("/governance").text
    devi.post(
        "/governance/findings",
        {"model": "quant/linear", "title": "Residuals drift", "severity": "high"},
        expect="success",
    )
    fid = w.p.governance.findings(w.devi, "quant/linear")[0]["id"]
    page = mona.get(f"/governance/findings/{fid}").text
    assert "Residuals drift" in page and "Mark remediated" in page
    mona.post(f"/governance/findings/{fid}/move", {"action": "remediated"}, expect="success")
    devi.post(
        f"/governance/findings/{fid}/move", {"action": "close", "note": "checked"}, expect="success"
    )
    assert w.p.governance.finding(w.devi, fid)["state"] == "closed"
    mona.post(
        "/governance/models/quant/linear/profile",
        {"use": "business_decision", "exposure": "20000000"},
        expect="success",
    )
    model_page = mona.get("/governance/models/quant/linear").text
    assert "Tier 2" in model_page and "Record a periodic review" in model_page
    devi.post(
        "/governance/models/quant/linear/review",
        {"outcome": "satisfactory", "note": "annual look"},
        expect="success",
    )
    admin.post("/governance/sweep", expect="info")
    assert "Governance" in mona.get("/models/quant/linear").text
