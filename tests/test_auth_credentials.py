"""
The §12 credential rules: password history and maximum age, a cap on concurrent
sessions, single-use password-reset tokens, per-key rate limits, key rotation, and
OAuth2 client credentials for service accounts.

Each test asserts the refusal's *reason*, not only that something was refused: a
policy a person cannot understand from the message is a policy they work around.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pytest

from maya.core.clock import utcnow
from maya.core.errors import (
    ConflictError,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    QuotaExceeded,
    ValidationFailed,
)
from maya.sdk import Client
from tests.conftest import PASSWORD, World, build_platform

NEW = "Rotated-password-9"


@pytest.fixture(scope="module")
def creds():
    """A platform with a short history, a tight session cap and a maximum age."""
    platform = build_platform(
        [
            "--auth.password.history=3",
            "--auth.password.max_age_days=30",
            "--auth.session.concurrent_sessions=2",
            "--auth.api_keys.rotation_overlap_days=3",
        ]
    )
    w = World(platform)
    platform.access.create_namespace(w.admin, name="eq", preset="standard")
    platform.access.create_user(
        w.admin, username="robot", password=None, roles=["feature_designer"], is_service=True
    )
    from maya.api.app import create_api

    yield w, create_api(platform)
    platform.shutdown()


def _user(w: World, username: str) -> dict:
    with w.p.uow() as uow:
        return uow.repo("users").find_one(username=username)


def _touch_user(w: World, username: str, changes: dict) -> None:
    with w.p.uow() as uow:
        user = uow.repo("users").find_one(username=username)
        uow.repo("users").update(user["id"], changes)


def _audit(w: World, action: str) -> list[dict]:
    with w.p.uow() as uow:
        return uow.repo("audit_events").list(action=action, order_by=["-seq"])


# -- password history and maximum age -------------------------------------------------
def test_a_password_may_not_go_back_to_one_of_the_last_n(creds):
    w, _ = creds
    dana = w.principal("dana")
    w.p.auth.change_password(dana, PASSWORD, NEW)
    with pytest.raises(ValidationFailed) as exc:
        w.p.auth.change_password(dana, NEW, PASSWORD)
    assert "used before" in exc.value.message and "last 3" in exc.value.message
    # three back is still remembered; four back is forgotten again
    w.p.auth.change_password(dana, NEW, "Second-choice-22")
    with pytest.raises(ValidationFailed):
        w.p.auth.change_password(dana, "Second-choice-22", NEW)
    w.p.auth.change_password(dana, "Second-choice-22", "Third-choice-33")
    w.p.auth.change_password(dana, "Third-choice-33", PASSWORD)  # the oldest has aged out


def test_the_history_length_is_configurable_and_zero_turns_it_off():
    platform = build_platform(["--auth.password.history=0"])
    try:
        w = World(platform)
        mona = w.principal("mona")
        platform.auth.change_password(mona, PASSWORD, NEW)
        platform.auth.change_password(mona, NEW, PASSWORD)  # no history: allowed
    finally:
        platform.shutdown()


def test_a_password_past_its_maximum_age_is_refused_with_the_reason(creds):
    w, _ = creds
    _touch_user(w, "tess", {"password_changed_at": utcnow() - dt.timedelta(days=45)})
    with pytest.raises(NotAuthenticated) as exc:
        w.p.auth.login("tess", PASSWORD)
    assert "30-day maximum age" in exc.value.message and "15 day" in exc.value.message
    assert _user(w, "tess")["must_change_password"] is True
    assert _audit(w, "auth.login_refused")[0]["detail"]["reason"] == "password expired"
    # and it is the age, not the password: fresh again, the same password works
    _touch_user(w, "tess", {"password_changed_at": utcnow()})
    assert w.p.auth.login("tess", PASSWORD)["token"]


def test_a_password_whose_age_is_unknown_never_expires(creds):
    """MAYA does not guess: an account whose password change was never recorded would
    otherwise be locked out the day a maximum age is configured."""
    w, _ = creds
    _touch_user(w, "devi", {"password_changed_at": None})
    assert w.p.auth.login("devi", PASSWORD)["token"]


def test_an_administrators_reset_obeys_the_history_and_starts_the_clock(creds):
    """A reset used to write the hash straight to the row: it could hand back a password
    the account had just stopped using, and left the age unrecorded, so the §12 maximum
    never expired it. It goes through the one password path now."""
    w, _ = creds
    w.p.access.create_user(w.admin, username="rusty", password=PASSWORD, roles=["feature_designer"])
    w.p.access.reset_password(w.admin, "rusty", NEW)
    with pytest.raises(ValidationFailed) as exc:
        w.p.access.reset_password(w.admin, "rusty", PASSWORD)
    assert "used before" in exc.value.message
    user = _user(w, "rusty")
    assert user["must_change_password"] is True
    assert user["password_changed_at"] is not None
    assert (utcnow() - user["password_changed_at"]).total_seconds() < 120
    # and the reset password works, so the new hash really was the one written
    assert w.p.auth.login("rusty", NEW)["token"]


def test_a_new_accounts_password_has_an_age_from_the_first_day(creds):
    """Without a recorded change time a password never ages, so a brand-new account would
    be exempt from the maximum age for as long as it existed."""
    w, _ = creds
    w.p.access.create_user(w.admin, username="fresh", password=PASSWORD, roles=[])
    assert _user(w, "fresh")["password_changed_at"] is not None
    _touch_user(w, "fresh", {"password_changed_at": utcnow() - dt.timedelta(days=45)})
    with pytest.raises(NotAuthenticated, match="30-day maximum age"):
        w.p.auth.login("fresh", PASSWORD)
    # a service account gets no password at all, and no clock to go with it
    assert _user(w, "robot")["password_changed_at"] is None


def test_the_class_requirement_is_configurable():
    platform = build_platform(["--auth.password.require_classes=4"])
    try:
        with pytest.raises(ValidationFailed) as exc:
            platform.auth.check_policy("nosymbolshere1A")
        assert "4 of" in exc.value.message
        platform.auth.check_policy("with-symbols-1A")
    finally:
        platform.shutdown()


# -- concurrent sessions ---------------------------------------------------------------
def test_a_third_session_ends_the_oldest_and_says_so(creds):
    w, _ = creds
    first = w.p.auth.login("mgr", PASSWORD)["token"]
    second = w.p.auth.login("mgr", PASSWORD)["token"]
    assert w.p.auth.principal(first).username == "mgr"
    third = w.p.auth.login("mgr", PASSWORD)["token"]
    with pytest.raises(NotAuthenticated, match="Session has ended"):
        w.p.auth.principal(first)
    assert w.p.auth.principal(second).username == "mgr"
    assert w.p.auth.principal(third).username == "mgr"
    evicted = _audit(w, "auth.session_evicted")
    assert evicted and evicted[0]["detail"]["reason"] == "over the 2-session cap"


def test_a_service_account_is_exempt_from_the_session_cap(creds):
    """A fleet of workers sharing one credential holds one token each by design."""
    w, app = creds
    admin = w.admin
    made = w.p.auth.create_client_credential(admin, username="robot", days=10)
    tokens = [
        Client(app=app).auth.client_credentials_token(made["client_id"], made["client_secret"])[
            "access_token"
        ]
        for _ in range(3)
    ]
    assert all(w.p.auth.principal(t).username == "robot" for t in tokens)


def test_an_idle_session_and_an_old_one_are_both_refused_and_revoked(creds):
    w, _ = creds
    token = w.p.auth.login("owen", PASSWORD)["token"]
    with w.p.uow() as uow:
        sess = uow.repo("sessions").find_one(token_hash=w.p.auth.token_hash(token))
        uow.repo("sessions").update(sess["id"], {"expires_at": utcnow() - dt.timedelta(minutes=1)})
    with pytest.raises(NotAuthenticated, match="Session expired"):
        w.p.auth.principal(token)
    with w.p.uow() as uow:
        assert uow.repo("sessions").require(sess["id"])["revoked_at"] is not None


def test_a_terminated_session_is_dead_at_once(creds):
    w, _ = creds
    token = w.p.auth.login("mick", PASSWORD)["token"]
    listed = [s for s in w.p.auth.list_sessions() if s["username"] == "mick"]
    assert listed and "token_hash" not in listed[0]
    w.p.auth.terminate_session(w.admin, listed[0]["id"])
    w.p.auth.forget_principals()
    with pytest.raises(NotAuthenticated, match="Session has ended"):
        w.p.auth.principal(token)


# -- password reset tokens --------------------------------------------------------------
def test_a_reset_token_works_once_and_ends_every_session(creds):
    w, _ = creds
    open_token = w.p.auth.login("mona", PASSWORD)["token"]
    issued = w.p.auth.issue_password_reset(w.admin, "mona")
    assert issued["shown_once"] and issued["expires_at"] > utcnow()
    w.p.auth.complete_password_reset(issued["token"], "Fresh-mona-pass-1")
    with pytest.raises(NotAuthenticated, match="Session has ended"):
        w.p.auth.principal(open_token)
    assert w.p.auth.login("mona", "Fresh-mona-pass-1")["token"]
    with pytest.raises(NotAuthenticated, match="already been used"):
        w.p.auth.complete_password_reset(issued["token"], "Another-mona-pass-2")


def test_an_expired_or_unknown_reset_token_is_refused(creds):
    w, _ = creds
    issued = w.p.auth.issue_password_reset(w.admin, "devi")
    with w.p.uow() as uow:
        row = uow.repo("auth_challenges").find_one(
            kind="password_reset", handle=w.p.auth.token_hash(issued["token"])
        )
        uow.repo("auth_challenges").update(
            row["id"], {"expires_at": utcnow() - dt.timedelta(minutes=1)}
        )
    with pytest.raises(NotAuthenticated, match="expired"):
        w.p.auth.complete_password_reset(issued["token"], "Devi-new-password-1")
    with pytest.raises(NotAuthenticated, match="not valid"):
        w.p.auth.complete_password_reset("no-such-token", "Devi-new-password-1")


def test_a_reset_honours_the_password_policy_and_history(creds):
    w, _ = creds
    issued = w.p.auth.issue_password_reset(w.admin, "devi")
    with pytest.raises(ValidationFailed, match="at least 12 characters"):
        w.p.auth.complete_password_reset(issued["token"], "short")
    with pytest.raises(ValidationFailed, match="used before"):
        w.p.auth.complete_password_reset(issued["token"], PASSWORD)
    w.p.auth.complete_password_reset(issued["token"], "Devi-new-password-1")


def test_only_a_user_administrator_issues_a_token_and_sso_users_have_none(creds):
    w, _ = creds
    with pytest.raises(PermissionDenied):
        w.p.auth.issue_password_reset(w.principal("dana"), "mona")
    with pytest.raises(NotFound):
        w.p.auth.issue_password_reset(w.admin, "nobody-here")
    _touch_user(w, "tess", {"auth_source": "sso"})
    try:
        with pytest.raises(ValidationFailed, match="identity provider"):
            w.p.auth.issue_password_reset(w.admin, "tess")
    finally:
        _touch_user(w, "tess", {"auth_source": "db"})


def test_asking_for_a_reset_tells_the_administrators_and_nothing_to_the_asker(creds):
    w, app = creds
    out = Client(app=app).auth.request_password_reset("mick")
    assert out["ok"] is True
    unknown = Client(app=app).auth.request_password_reset("no-such-person")
    assert unknown == out  # the same answer: the form is not a user directory
    Client(app=app).auth.request_password_reset("mick")  # asking again buries no inbox
    with w.p.uow() as uow:
        admin = uow.repo("users").find_one(username="admin")
        notices = uow.repo("notifications").list(user_id=admin["id"], kind="password_reset")
    assert len(notices) == 1
    assert "'mick' asked for a password reset" in notices[0]["message"]
    assert [a for a in _audit(w, "auth.password_reset_requested") if a["detail"]["known"] is False]


# -- API keys: budget, rotation and the report -------------------------------------------
def test_a_key_spends_its_own_budget_and_a_budgetless_key_does_not(creds):
    w, _ = creds
    dana = w.principal("dana")
    tight = w.p.auth.create_api_key(dana, name="tight", days=5, rate_per_minute=6)
    for _ in range(6):
        assert w.p.auth.principal(tight["api_key"]).username == "dana"
    with pytest.raises(QuotaExceeded) as exc:
        w.p.auth.principal(tight["api_key"])
    assert "6 requests a minute" in exc.value.message
    assert exc.value.context["key_id"] == tight["key_id"]
    loose = w.p.auth.create_api_key(dana, name="loose", days=5)
    for _ in range(20):
        assert w.p.auth.principal(loose["api_key"]).username == "dana"


def test_rotation_issues_a_successor_and_retires_the_old_key(creds):
    w, _ = creds
    mick = w.principal("mick")
    old = w.p.auth.create_api_key(mick, name="ci", days=60, namespaces=["eq"], roles=[])
    new = w.p.auth.rotate_api_key(mick, old["key_id"], overlap_days=3)
    assert new["retired"] == old["key_id"] and new["key_id"] != old["key_id"]
    assert new["retires_at"] < old["expires_at"]
    # both work during the overlap, and the successor carries the same scope
    assert w.p.auth.principal(old["api_key"]).username == "mick"
    assert w.p.auth.principal(new["api_key"]).key_namespaces == ["eq"]
    with pytest.raises(ConflictError, match="already rotated"):
        w.p.auth.rotate_api_key(mick, old["key_id"])


def test_a_zero_day_overlap_retires_the_old_key_immediately(creds):
    w, _ = creds
    mick = w.principal("mick")
    old = w.p.auth.create_api_key(mick, name="cutover", days=30)
    new = w.p.auth.rotate_api_key(mick, old["key_id"], overlap_days=0)
    with pytest.raises(NotAuthenticated, match="revoked or expired"):
        w.p.auth.principal(old["api_key"])
    assert w.p.auth.principal(new["api_key"]).username == "mick"


def test_the_report_names_keys_to_revoke_or_rotate(creds):
    w, _ = creds
    owen = w.principal("owen")
    stale = w.p.auth.create_api_key(owen, name="forgotten", days=200)
    soon = w.p.auth.create_api_key(owen, name="nearly over", days=200)
    with w.p.uow() as uow:
        row = uow.repo("api_keys").find_one(key_id=stale["key_id"])
        uow.repo("api_keys").update(
            row["id"],
            {
                "created_at": utcnow() - dt.timedelta(days=200),
                "last_used_at": utcnow() - dt.timedelta(days=120),
            },
        )
        row = uow.repo("api_keys").find_one(key_id=soon["key_id"])
        uow.repo("api_keys").update(row["id"], {"expires_at": utcnow() + dt.timedelta(days=3)})
    report = {r["key_id"]: r["reasons"] for r in w.p.auth.api_key_report(owen)}
    assert "unused for 120 days: revoke it" in report[stale["key_id"]]
    assert any("rotate it" in r for r in report[soon["key_id"]])
    assert all("secret_hash" not in r for r in w.p.auth.api_key_report(owen))


def test_the_report_also_names_expired_and_never_used_and_rotated_keys(creds):
    w, _ = creds
    tess = w.principal("tess")
    dead = w.p.auth.create_api_key(tess, name="long over", days=1)
    idle = w.p.auth.create_api_key(tess, name="never touched", days=200)
    rotated = w.p.auth.create_api_key(tess, name="superseded", days=100)
    w.p.auth.rotate_api_key(tess, rotated["key_id"], overlap_days=5)
    with w.p.uow() as uow:
        row = uow.repo("api_keys").find_one(key_id=dead["key_id"])
        uow.repo("api_keys").update(row["id"], {"expires_at": utcnow() - dt.timedelta(days=2)})
        row = uow.repo("api_keys").find_one(key_id=idle["key_id"])
        uow.repo("api_keys").update(row["id"], {"created_at": utcnow() - dt.timedelta(days=100)})
    report = {r["key_id"]: r["reasons"] for r in w.p.auth.api_key_report(tess)}
    assert "expired" in report[dead["key_id"]]
    assert "never used in 100 days: revoke it" in report[idle["key_id"]]
    assert any("replaces it" in r for r in report[rotated["key_id"]])
    # a revoked key is not reported: there is nothing left to do about it
    w.p.auth.revoke_api_key(tess, dead["key_id"])
    assert dead["key_id"] not in {r["key_id"] for r in w.p.auth.api_key_report(tess)}


def test_a_key_is_refused_from_an_address_outside_its_allowlist(creds):
    w, _ = creds
    dana = w.principal("dana")
    key = w.p.auth.create_api_key(dana, name="office only", days=5, cidrs=["10.1.0.0/16"])
    assert w.p.auth.principal(key["api_key"], ip="10.1.2.3").username == "dana"
    for outside in ("192.168.0.4", None):
        with pytest.raises(NotAuthenticated, match="not allowed from this address"):
            w.p.auth.principal(key["api_key"], ip=outside)


def test_a_namespace_may_cap_a_keys_life_below_the_global_maximum(creds):
    """The ceiling is set through the service, not by hand in the database: until
    ``update_namespace`` allowed the field, that was the only way to set it at all."""
    w, _ = creds
    assert (
        w.p.access.update_namespace(w.admin, "eq", {"api_key_max_days": 7})["api_key_max_days"] == 7
    )
    with pytest.raises(ValidationFailed, match="at least 1 day"):
        w.p.access.update_namespace(w.admin, "eq", {"api_key_max_days": 0})
    with pytest.raises(ValidationFailed, match="whole number of days"):
        w.p.access.update_namespace(w.admin, "eq", {"api_key_max_days": "a fortnight"})
    with w.p.uow() as uow:
        ns = uow.repo("namespaces").find_one(name="eq")
    assert ns["api_key_max_days"] == 7, "a refused change left the ceiling alone"
    try:
        with pytest.raises(ValidationFailed, match="1–7 days"):
            w.p.auth.create_api_key(
                w.principal("dana"), name="too long", days=30, namespaces=["eq"]
            )
        assert w.p.auth.create_api_key(
            w.principal("dana"), name="within", days=7, namespaces=["eq"]
        )["api_key"]
    finally:
        cleared = w.p.access.update_namespace(w.admin, "eq", {"api_key_max_days": ""})
    assert cleared["api_key_max_days"] is None, "an empty value means the global maximum"
    assert w.p.auth.create_api_key(
        w.principal("dana"), name="long again", days=30, namespaces=["eq"]
    )["api_key"]


# -- service accounts and client credentials ----------------------------------------------
def test_a_service_account_gets_a_credential_it_could_never_create_itself(creds):
    w, app = creds
    made = w.p.auth.create_client_credential(
        w.admin, username="robot", roles=["feature_designer"], namespaces=["eq"], days=30
    )
    assert made["client_id"] and made["client_secret"] and "secret_hash" not in made
    sdk = Client(app=app)
    granted = sdk.auth.client_credentials_token(made["client_id"], made["client_secret"])
    assert granted["token_type"] == "Bearer" and granted["expires_in"] <= 3600
    principal = w.p.auth.principal(granted["access_token"])
    assert principal.username == "robot" and principal.roles == ["feature_designer"]
    assert principal.key_namespaces == ["eq"] and principal.principal_type == "api_key"


def test_a_client_credential_is_not_a_bearer_key_and_a_wrong_secret_is_refused(creds):
    w, app = creds
    made = w.p.auth.create_client_credential(w.admin, username="robot", days=30)
    with pytest.raises(NotAuthenticated, match="exchange it for a token"):
        w.p.auth.principal(f"maya_{w.p.settings.environment}_{made['client_id']}_nonsense")
    with pytest.raises(NotAuthenticated, match="invalid_client"):
        Client(app=app).auth.client_credentials_token(made["client_id"], "wrong-secret")
    assert _audit(w, "auth.client_credentials_refused")


def test_revoking_a_credential_kills_the_tokens_it_issued(creds):
    w, app = creds
    made = w.p.auth.create_client_credential(w.admin, username="robot", days=30)
    token = Client(app=app).auth.client_credentials_token(made["client_id"], made["client_secret"])[
        "access_token"
    ]
    assert w.p.auth.principal(token).username == "robot"
    w.p.auth.revoke_api_key(w.admin, made["client_id"])
    with pytest.raises(NotAuthenticated, match="Session has ended"):
        w.p.auth.principal(token)
    # and a token issued in another process, whose session row nobody revoked, dies too:
    # the credential is checked on every use
    second = w.p.auth.create_client_credential(w.admin, username="robot", days=30)
    token = Client(app=app).auth.client_credentials_token(
        second["client_id"], second["client_secret"]
    )["access_token"]
    with w.p.uow() as uow:
        row = uow.repo("api_keys").find_one(key_id=second["client_id"])
        uow.repo("api_keys").update(row["id"], {"expires_at": utcnow() - dt.timedelta(minutes=1)})
    w.p.auth.forget_principals()
    with pytest.raises(NotAuthenticated, match="revoked or expired"):
        w.p.auth.principal(token)


def test_a_credential_never_widens_its_holder_or_its_issuer(creds):
    w, _ = creds
    with pytest.raises(PermissionDenied, match="no 'U' on users"):
        w.p.auth.create_client_credential(w.principal("mick"), username="robot", roles=["admin"])
    with pytest.raises(PermissionDenied, match="roles you do not hold"):
        w.p.auth.create_api_key(w.principal("mick"), name="wider", roles=["admin"])
    with pytest.raises(PermissionDenied, match="does not hold"):
        w.p.auth.create_client_credential(w.admin, username="robot", roles=["model_manager"])
    with pytest.raises(PermissionDenied, match="only they can create"):
        w.p.auth.create_api_key(w.admin, name="not yours", for_user="dana")
    with pytest.raises(ValidationFailed, match="use an API key for yourself"):
        w.p.auth.create_client_credential(w.admin, username="admin")


def test_the_token_endpoint_refuses_any_other_grant(creds):
    """RFC 6749 asks an unsupported grant to be named as such, not silently treated as the
    one grant MAYA does implement."""
    _, app = creds
    from starlette.testclient import TestClient

    r = TestClient(app).post(
        "/api/v1/auth/token",
        data={"grant_type": "password", "client_id": "x", "client_secret": "y"},
    )
    assert r.status_code == 422 and "unsupported_grant_type" in r.json()["detail"]


def test_an_administrator_can_issue_a_key_for_a_service_account(creds):
    w, _ = creds
    key = w.p.auth.create_api_key(
        w.admin, name="robot key", for_user="robot", roles=["feature_designer"], days=30
    )
    principal = w.p.auth.principal(key["api_key"])
    assert principal.username == "robot" and principal.roles == ["feature_designer"]
    with pytest.raises(PermissionDenied):
        w.p.auth.create_api_key(w.principal("dana"), name="sneaky", for_user="robot")


def test_the_shipped_admin_password_is_recognised_until_it_is_changed():
    """What the non-dev startup refusal is built on (§12): MAYA can tell that `admin` still
    has the password it ships with. The refusal itself lives in the platform's startup
    checks, behind the sandbox check, and is not exercised here."""
    platform = build_platform()
    try:
        assert platform.auth.default_admin_password_active() is True
        w = World(platform)
        platform.access.reset_password(w.admin, "admin", "A-real-password-1")
        assert platform.auth.default_admin_password_active() is False
    finally:
        platform.shutdown()
