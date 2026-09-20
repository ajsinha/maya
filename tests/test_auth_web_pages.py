"""
The credential pages in the browser: rotating a key, issuing a client credential and
a reset link, and the two pages someone who cannot sign in has to be able to reach
without a session.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re

import pytest
from starlette.testclient import TestClient

from tests.conftest import PASSWORD, World, build_platform

ADMIN_PW = "Web-admin-pass-1"
CSRF = re.compile(r'name="csrf_token" value="([^"]+)"')


@pytest.fixture(scope="module")
def web():
    platform = build_platform()
    w = World(platform)
    platform.access.create_user(
        w.admin, username="botty", password=None, roles=["feature_designer"], is_service=True
    )
    from maya.server import build_app

    client = TestClient(build_app(platform))
    csrf = CSRF.search(client.get("/login").text).group(1)
    client.post(
        "/login", data={"username": "admin", "password": "maya-dev-admin", "csrf_token": csrf}
    )
    client.post(
        "/account/password",
        data={
            "old_password": "maya-dev-admin",
            "new_password": ADMIN_PW,
            "confirm_password": ADMIN_PW,
            "csrf_token": _csrf(client, "/account/password"),  # signing in rotates the token
        },
    )
    yield w, client
    platform.shutdown()


def _csrf(client: TestClient, path: str) -> str:
    return CSRF.search(client.get(path).text).group(1)


def test_the_credentials_page_rotates_a_key_and_shows_the_successor_once(web):
    w, client = web
    with w.p.uow() as uow:
        admin = uow.repo("users").find_one(username="admin")
        principal = w.p.auth.build_principal(uow, admin["id"])
    key = w.p.auth.create_api_key(principal, name="page key", days=30)
    page = client.get("/account/credentials")
    assert page.status_code == 200 and key["key_id"] in page.text
    csrf = CSRF.search(page.text).group(1)
    r = client.post(
        f"/account/credentials/keys/{key['key_id']}/rotate",
        data={"csrf_token": csrf, "overlap_days": "2"},
        follow_redirects=True,
    )
    assert "copy it now" in r.text and f"maya_{w.p.settings.environment}_" in r.text
    assert "keeps working until" in r.text
    # shown once: the secret is not on the page a second time
    assert "copy it now" not in client.get("/account/credentials").text


def test_an_administrator_issues_a_client_credential_and_a_reset_link(web):
    w, client = web
    csrf = _csrf(client, "/account/credentials")
    r = client.post(
        "/account/credentials/clients",
        data={"csrf_token": csrf, "username": "botty", "name": "nightly", "days": "20"},
        follow_redirects=True,
    )
    assert "client_id=" in r.text and "client_secret=" in r.text
    assert "botty" in client.get("/account/credentials").text

    r = client.post(
        "/account/credentials/reset-token",
        data={"csrf_token": csrf, "username": "mick"},
        follow_redirects=True,
    )
    assert "/login/reset?token=" in r.text and "Single use" in r.text


def test_someone_locked_out_can_ask_for_a_reset_and_redeem_it_without_a_session(web):
    w, _ = web
    from maya.server import build_app

    anon = TestClient(build_app(w.p))
    page = anon.get("/login/forgot")
    assert page.status_code == 200
    r = anon.post(
        "/login/forgot",
        data={"username": "owen", "csrf_token": CSRF.search(page.text).group(1)},
    )
    assert "an administrator has been asked" in r.text

    with w.p.uow() as uow:
        admin = uow.repo("users").find_one(username="admin")
        principal = w.p.auth.build_principal(uow, admin["id"])
    issued = w.p.auth.issue_password_reset(principal, "owen")
    page = anon.get(f"/login/reset?token={issued['token']}")
    assert issued["token"] in page.text
    csrf = CSRF.search(page.text).group(1)
    r = anon.post(
        "/login/reset",
        data={
            "token": issued["token"],
            "new_password": "Owen-brand-new-1",
            "confirm_password": "Owen-brand-new-1",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert w.p.auth.login("owen", "Owen-brand-new-1")["token"]
    # and the link is spent
    csrf = _csrf(anon, "/login/reset")  # the successful reset cleared the session
    r = anon.post(
        "/login/reset",
        data={
            "token": issued["token"],
            "new_password": "Owen-second-try-2",
            "confirm_password": "Owen-second-try-2",
            "csrf_token": csrf,
        },
    )
    assert "already been used" in r.text


def test_the_reset_page_refuses_mismatched_passwords_before_spending_the_token(web):
    w, _ = web
    from maya.server import build_app

    anon = TestClient(build_app(w.p))
    with w.p.uow() as uow:
        admin = uow.repo("users").find_one(username="admin")
        principal = w.p.auth.build_principal(uow, admin["id"])
    issued = w.p.auth.issue_password_reset(principal, "tess")
    page = anon.get("/login/reset")
    csrf = CSRF.search(page.text).group(1)
    r = anon.post(
        "/login/reset",
        data={
            "token": issued["token"],
            "new_password": "Tess-password-11",
            "confirm_password": "Tess-password-12",
            "csrf_token": csrf,
        },
    )
    assert r.status_code == 400 and "two new passwords differ" in r.text
    w.p.auth.complete_password_reset(issued["token"], "Tess-password-11")
    assert w.p.auth.login("tess", "Tess-password-11")["token"]


def test_a_person_without_the_admin_role_sees_only_their_own_credentials(web):
    w, _ = web
    from maya.server import build_app

    other = TestClient(build_app(w.p))
    csrf = CSRF.search(other.get("/login").text).group(1)
    other.post("/login", data={"username": "mick", "password": PASSWORD, "csrf_token": csrf})
    other.post(
        "/account/password",
        data={
            "old_password": PASSWORD,
            "new_password": "Mick-own-password-1",
            "confirm_password": "Mick-own-password-1",
            "csrf_token": _csrf(other, "/account/password"),
        },
    )
    page = other.get("/account/credentials")
    assert page.status_code == 200
    assert "Issue a client credential" not in page.text and "Service accounts" not in page.text
