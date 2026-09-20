"""
Break-glass sign-in under ``auth.mode: sso`` (§13.3): the administrator's way in when
the identity provider is not there.

The promise §13.3 makes is that an unreachable IdP still leaves a path for
administrators. These tests hold MAYA to it, and to the other half of the bargain: the
door is one named account, it must really be an administrator's, its session is short,
and using it is loud.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import pytest

from maya.core.clock import utcnow
from maya.core.errors import NotAuthenticated
from tests.conftest import PASSWORD, World, build_platform

ISSUER = "https://idp.example.test"


@pytest.fixture(scope="module")
def sso_only():
    """SSO as the only way in — with one designated break-glass administrator."""
    platform = build_platform(
        [
            "--auth.mode=sso",
            f"--auth.sso.issuer={ISSUER}",
            "--auth.break_glass.users=admin2,dana",
            "--auth.break_glass.session_minutes=15",
        ]
    )
    w = World(platform)
    from maya.api.app import create_api

    yield w, create_api(platform)
    platform.shutdown()


def _audit(w: World, action: str) -> list[dict]:
    with w.p.uow() as uow:
        return uow.repo("audit_events").list(action=action, order_by=["-seq"])


def test_an_ordinary_account_still_cannot_use_a_password(sso_only):
    w, _ = sso_only
    with pytest.raises(NotAuthenticated, match="signs people in with SSO only"):
        w.p.auth.login("mick", PASSWORD)
    assert _audit(w, "auth.login_refused")[0]["detail"]["reason"] == "password login disabled (sso)"


def test_the_designated_administrator_gets_in_and_the_door_is_loud(sso_only):
    w, _ = sso_only
    out = w.p.auth.login("admin2", PASSWORD, ip="10.0.0.9")
    assert out["break_glass"] is True and out["token"]
    principal = w.p.auth.principal(out["token"])
    assert principal.username == "admin2" and "admin" in principal.roles

    entry = _audit(w, "auth.break_glass_login")[0]
    assert entry["object_ref"] == "user:admin2" and entry["detail"]["mode"] == "sso"
    assert entry["ip"] == "10.0.0.9"
    with w.p.uow() as uow:
        admin = uow.repo("users").find_one(username="admin")
        notices = uow.repo("notifications").list(user_id=admin["id"], kind="break_glass")
        sess = uow.repo("sessions").find_one(token_hash=w.p.auth.token_hash(out["token"]))
    assert notices and "Break-glass sign-in" in notices[0]["message"]
    # the session is the short one, not the ordinary twelve hours
    assert (sess["absolute_expires_at"] - utcnow()).total_seconds() <= 15 * 60 + 5


def test_the_break_glass_login_is_also_a_webhook_event(sso_only):
    """A subscriber cannot watch the audit table, so an emergency sign-in that is only an
    audit entry reaches nobody outside MAYA. It is in the event map, and the event carries
    the account it was used on."""
    from maya.observability.events import EVENT_ACTIONS, event_type

    w, _ = sso_only
    assert "auth.break_glass_login" in EVENT_ACTIONS
    assert event_type({"action": "auth.break_glass_login"}) == "auth.break_glass_login"
    w.p.auth.login("admin2", PASSWORD, ip="10.0.0.11")
    with w.p.uow() as uow:
        rows = uow.repo("events").list(type="auth.break_glass_login", order_by=["-seq"])
    assert rows and rows[0]["object_ref"] == "user:admin2"


def test_a_designated_account_that_is_not_an_administrator_is_refused(sso_only):
    """`dana` is designated but holds only feature_designer: a break-glass account that
    cannot administer anything is a password with no purpose, and the refusal says so
    rather than letting the misconfiguration be found during the outage."""
    w, _ = sso_only
    with pytest.raises(NotAuthenticated, match="does not hold the administrator role"):
        w.p.auth.login("dana", PASSWORD)
    assert _audit(w, "auth.break_glass_refused")[0]["object_ref"] == "user:dana"


def test_a_designated_service_account_is_refused(sso_only):
    """A service account has no interactive sign-in at all; naming one as break-glass is
    the same misconfiguration as naming a non-administrator."""
    w, _ = sso_only
    with w.p.uow() as uow:
        dana = uow.repo("users").find_one(username="dana")
        uow.repo("users").update(dana["id"], {"is_service": True})
    try:
        with pytest.raises(NotAuthenticated, match="Invalid username or password"):
            w.p.auth.login("dana", PASSWORD)
    finally:
        with w.p.uow() as uow:
            uow.repo("users").update(dana["id"], {"is_service": False})


def test_a_wrong_password_on_the_break_glass_account_says_nothing_extra(sso_only):
    w, _ = sso_only
    with pytest.raises(NotAuthenticated, match="Invalid username or password"):
        w.p.auth.login("admin2", "not-the-password")


def test_the_login_page_offers_the_password_form_only_when_asked(sso_only):
    w, _ = sso_only
    from starlette.testclient import TestClient

    from maya.server import build_app

    client = TestClient(build_app(w.p))
    plain = client.get("/login")
    assert 'action="/login"' not in plain.text  # SSO only: no password form
    glass = client.get("/login?break-glass=1")
    assert 'name="password"' in glass.text
    import re

    csrf = re.search(r'name="csrf_token" value="([^"]+)"', glass.text).group(1)
    r = client.post(
        "/login",
        data={"username": "admin2", "password": PASSWORD, "csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert len(_audit(w, "auth.break_glass_login")) >= 2
