"""
The screens of batch 2, through the real app: the faceted catalog, the review
experience, the pin preview, controls disabled with their reason and a way to
ask for access, and following an object.

Every page here goes through the same stack a browser would use — session,
CSRF, the web tier as an SDK client — so a route that stopped calling the SDK,
or a template that stopped rendering what the payload carries, fails here.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import copy
import datetime as dt
import os
import re
import sys
import tempfile

import pytest

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
PASSWORD = "Web-pass-12345"


@pytest.fixture(scope="module")
def site():
    """A platform, the app, a logged-in manager and a small governed estate."""
    old_argv, old_home = sys.argv, os.environ.get("MAYA_HOME")
    sys.argv = ["pytest"]
    os.environ["MAYA_HOME"] = tempfile.mkdtemp(prefix="maya-rev-")
    from starlette.testclient import TestClient

    from maya.server import build_app
    from tests.conftest import build_platform, price_csv

    platform = build_platform()
    admin = _principal(platform, "admin")  # the bootstrap admin, who cannot log in yet
    for name, roles in (
        ("mick", ["feature_manager"]),
        ("dana", ["feature_designer"]),
        ("mona", ["model_designer"]),
        ("root", ["admin"]),
    ):
        platform.access.create_user(admin, username=name, password=PASSWORD, roles=roles)
    with platform.uow() as uow:
        for name in ("mick", "dana", "mona", "root"):
            user = uow.repo("users").find_one(username=name)
            uow.repo("users").update(user["id"], {"must_change_password": False})
    platform.access.create_namespace(admin, name="wr", preset="regulated")
    platform.access.create_namespace(
        admin, name="wr_shut", default_visibility="private", preset="regulated"
    )
    dana, mick = _principal(platform, "dana"), _principal(platform, "mick")
    definition = {
        "index": ["date", "symbol"],
        "index_types": {"date": "date", "symbol": "string"},
        "schema": [{"name": "close", "type": "float64"}],
        "source": {"type": "csv"},
        "resolution": {"grid": "as_is", "rules": {"close": "forward_fill(limit=3)"}},
        "transform": [],
        "quality": [{"check": "not_null", "attr": "close"}],
    }
    platform.features.create(
        dana, namespace="wr", name="wr_px", definition=definition, tags=["eod", "prices"]
    )
    platform.features.ingest(dana, "wr/wr_px", price_csv(), fmt="csv")
    platform.features.transition(dana, "wr/wr_px", 1, "submit")
    platform.features.transition(mick, "wr/wr_px", 1, "approve")
    platform.featuresets.create(
        dana,
        namespace="wr",
        name="wr_panel",
        definition={
            "index": ["date", "symbol"],
            "index_types": {"date": "date", "symbol": "string"},
            "members": [
                {"attr": "close", "ref": "maya://feature/wr/wr_px", "source_attr": "close"}
            ],
            "alignment": {"mode": "inner"},
        },
    )
    platform.featuresets.transition(dana, "wr/wr_panel", 1, "submit")
    platform.featuresets.transition(mick, "wr/wr_panel", 1, "approve")
    # v2 of the feature, in review, with a real semantic change to diff
    changed = copy.deepcopy(definition)
    changed["resolution"]["rules"]["close"] = "last_known_as_of(lag=1)"
    changed["schema"] = changed["schema"] + [{"name": "vol", "type": "float64"}]
    platform.features.new_draft(dana, "wr/wr_px")
    platform.features.update_draft(dana, "wr/wr_px", changed)
    platform.features.transition(dana, "wr/wr_px", 2, "submit")
    # something mona cannot read, so a control has a reason to be disabled
    platform.features.create(dana, namespace="wr_shut", name="wr_hidden", definition=definition)
    with platform.uow() as uow:
        f = uow.repo("features").find_one(name="wr_px")
        v2 = uow.repo("feature_versions").find_one(feature_id=f["id"], version_no=2)
    app = build_app(platform)
    client = TestClient(app)
    yield platform, client, v2["id"]
    platform.shutdown()
    sys.argv = old_argv
    if old_home is None:
        os.environ.pop("MAYA_HOME", None)
    else:
        os.environ["MAYA_HOME"] = old_home


def _principal(platform, username):
    with platform.uow() as uow:
        user = uow.repo("users").find_one(username=username)
        return platform.auth.build_principal(uow, user["id"])


def _login(client, username: str = "mick") -> None:
    token = CSRF_RE.search(client.get("/login").text).group(1)
    r = client.post(
        "/login",
        data={"username": username, "password": PASSWORD, "csrf_token": token},
        follow_redirects=True,
    )
    assert r.status_code == 200, r.text[:300]


def _csrf(client, path: str = "/") -> str:
    return CSRF_RE.search(client.get(path).text).group(1)


# -- the faceted catalog (§16.2) ----------------------------------------------------
def test_the_browse_page_offers_every_facet(site):
    _, client, _ = site
    _login(client)
    r = client.get("/catalog")
    assert r.status_code == 200
    for facet in ("f-type", "f-ns", "f-owner", "f-status", "f-tag", "f-fresh"):
        assert f'id="{facet}"' in r.text, facet
    assert "wr_px" in r.text
    assert 'value="featureset"' in r.text and 'value="model"' in r.text


def test_the_browse_page_narrows_on_a_facet(site):
    _, client, _ = site
    _login(client)
    assert "wr_px" in client.get("/catalog?tag=eod").text
    assert "wr_px" not in client.get("/catalog?tag=nothing_has_this").text
    sets = client.get("/catalog?type=featureset")
    assert "wr_panel" in sets.text and "wr_px" not in sets.text
    owned = client.get("/catalog?owner=dana&status=in_review")
    assert "wr_px" in owned.text


def test_the_browse_table_pages_from_the_server(site):
    _, client, _ = site
    _login(client)
    page = client.get("/ui/table/catalog?page_size=25&sort=name&total=1")
    assert page.status_code == 200
    body = page.json()
    assert body["total"] >= 1 and body["sort"] == "name"
    assert any("wr_px" in row for row in body["rows"])


# -- the review screen (§10.3, §10.6) ----------------------------------------------
def test_the_review_screen_shows_the_diff_the_impact_the_sod_and_what_is_outstanding(site):
    _, client, v2 = site
    _login(client)
    r = client.get(f"/workflow/review/feature_version/{v2}")
    assert r.status_code == 200, r.text[:400]
    assert "Semantic diff against v1" in r.text
    assert "forward_fill(limit=3)" in r.text and "last_known_as_of(lag=1)" in r.text
    assert "rule for close" in r.text
    assert "Impact: every dependent object and who owns it" in r.text
    assert "wr_panel" in r.text and "owned by" in r.text
    assert "Separation of duties in force" in r.text and "strict" in r.text
    assert "Approvals still outstanding" in r.text
    assert "feature_manager" in r.text
    assert "governed by policy v1 scoped to" in r.text


def test_the_review_screen_disables_approve_for_the_submitter_and_says_why(site):
    _, client, v2 = site
    _login(client, "dana")
    r = client.get(f"/workflow/review/feature_version/{v2}")
    assert r.status_code == 200
    assert "unavailable" in r.text
    assert "no &#39;A&#39; on feature" in r.text or "no 'A' on feature" in r.text
    assert (
        'value="approve" type="submit"\n              disabled' in r.text.replace("\r", "")
        or "disabled aria-disabled" in r.text
    )


# -- the pin preview (§16.4) -------------------------------------------------------
def test_the_pin_form_asks_for_a_preview_before_it_arms_the_button(site):
    _, client, _ = site
    _login(client)
    r = client.get("/catalog/features/wr/wr_px?tab=pins")
    assert 'data-pin-preview="/ui/pin-preview/wr/wr_px"' in r.text
    assert "data-pin-submit disabled" in r.text
    assert "data-pin-check" in r.text
    assert "/static/js/pin_preview.js" in r.text


def test_the_pin_preview_endpoint_reports_rows_fill_quality_and_storage(site):
    _, client, _ = site
    _login(client)
    token = _csrf(client, "/catalog/features/wr/wr_px")
    r = client.post(
        "/ui/pin-preview/wr/wr_px",
        json={"version_no": 1, "as_of": "2026-01-20", "pin_name": "eom"},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"] > 0
    assert "close" in body["columns"]
    assert body["storage"]["estimated_bytes"] > 0
    assert body["storage"]["sampled_rows"] > 0
    assert body["checks"] and all(c["passed"] for c in body["checks"])
    assert body["blockers"] == [] and body["may_pin"] is True


def test_the_preview_refuses_a_pin_that_would_be_refused(site):
    platform, client, _ = site
    _login(client)
    token = _csrf(client, "/catalog/features/wr/wr_px")
    platform.features.pin(
        _principal(platform, "mick"),
        "wr/wr_px",
        version_no=1,
        pin_name="taken",
        as_of=dt.date(2026, 1, 20),
    )
    r = client.post(
        "/ui/pin-preview/wr/wr_px",
        json={"version_no": 1, "as_of": "2026-01-20", "pin_name": "taken"},
        headers={"X-CSRF-Token": token},
    )
    body = r.json()
    assert body["may_pin"] is False
    assert any("never overwrites" in b for b in body["blockers"]), body["blockers"]
    draft = client.post(
        "/ui/pin-preview/wr/wr_px",
        json={"version_no": 2, "as_of": "2026-01-20", "pin_name": "fresh"},
        headers={"X-CSRF-Token": token},
    )
    assert any("only an approved version" in b for b in draft.json()["blockers"])


# -- disabled with the reason, and a way to ask (§16.4, §11.5) ----------------------
def test_a_control_the_reader_cannot_use_is_disabled_with_its_reason_and_offers_a_request(site):
    _, client, _ = site
    _login(client, "mona")
    r = client.get("/catalog/features/wr/wr_px?tab=pins")
    assert r.status_code == 200
    assert "Request access" in r.text
    assert "you may not request_pin this" in r.text or "you may not" in r.text
    assert 'action="/workflow/access-requests"' in r.text
    assert "disabled aria-disabled" in r.text


def test_asking_for_access_and_an_administrator_deciding_it(site):
    platform, client, _ = site
    _login(client, "mona")
    token = _csrf(client, "/catalog/features/wr/wr_px")
    r = client.post(
        "/workflow/access-requests",
        data={
            "csrf_token": token,
            "kind": "feature",
            "ref": "maya://feature/wr_shut/wr_hidden",
            "level": "read",
            "reason": "reviewing a challenger",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    mine = client.get("/workflow/access-requests")
    assert "wr_hidden" in mine.text and "reviewing a challenger" in mine.text
    assert "Withdraw" in mine.text

    _login(client, "root")
    queue = client.get("/workflow/access-requests")
    assert "Grant" in queue.text and "Refuse" in queue.text
    request_id = [
        r["id"]
        for r in platform.access_requests.list(_principal(platform, "root"))
        if "wr_hidden" in r["object_ref"]
    ][0]
    decide = client.post(
        f"/workflow/access-requests/{request_id}/decide",
        data={
            "csrf_token": _csrf(client, "/workflow/access-requests"),
            "decision": "approve",
            "note": "for the quarter",
            "days": "30",
        },
        follow_redirects=True,
    )
    assert decide.status_code == 200
    assert "Access granted, time-boxed and audited." in decide.text
    _login(client, "mona")
    assert client.get("/catalog/features/wr_shut/wr_hidden").status_code == 200


def test_the_login_of_an_administrator_shows_the_access_request_menu(site):
    _, client, _ = site
    _login(client, "root")
    assert "/workflow/access-requests" in client.get("/").text


# -- following an object (§5.7) -----------------------------------------------------
def test_following_and_unfollowing_a_feature_from_its_page(site):
    _, client, _ = site
    _login(client, "mona")
    token = _csrf(client, "/catalog/features/wr/wr_px")
    r = client.post(
        "/catalog/subscriptions",
        data={"csrf_token": token, "object_ref": "maya://feature/wr/wr_px"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    mine = client.get("/catalog/subscriptions")
    assert "maya://feature/wr/wr_px" in mine.text
    assert "Unfollow" in mine.text
    drop = client.post(
        "/catalog/subscriptions/remove",
        data={
            "csrf_token": _csrf(client, "/catalog/subscriptions"),
            "object_ref": "maya://feature/wr/wr_px",
        },
        follow_redirects=True,
    )
    assert "No longer following" in drop.text
    assert "maya://feature/wr/wr_px" not in client.get("/catalog/subscriptions").text


def test_the_dependents_panel_is_one_click_from_the_definition(site):
    _, client, _ = site
    _login(client)
    r = client.get("/catalog/features/wr/wr_px?tab=lineage")
    assert "What this would break" in r.text
    assert "wr_panel" in r.text
    assert "/catalog/featuresets/wr/wr_panel" in r.text


def test_every_new_page_renders_with_a_marked_table_and_no_traceback(site):
    _, client, v2 = site
    _login(client)
    paths = [
        "/catalog",
        "/catalog?type=featureset",
        "/catalog?type=model&freshness=30d",
        "/catalog/subscriptions",
        "/workflow/access-requests",
        "/workflow/access-requests?state=pending",
        f"/workflow/review/feature_version/{v2}",
    ]
    failures = []
    for path in paths:
        r = client.get(path)
        if r.status_code != 200 or "Traceback" in r.text or "<title>" not in r.text:
            failures.append((path, r.status_code, r.text[:300]))
            continue
        tables = len(re.findall(r"<table\b", r.text))
        marked = len(re.findall(r'<table class="maya-table"', r.text))
        if tables != marked:
            failures.append((path, "unmarked table", tables, marked))
    assert not failures, failures
