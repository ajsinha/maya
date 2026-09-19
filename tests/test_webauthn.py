"""
Security keys (WebAuthn) as a second factor, against a software authenticator (§12).

Registration → a later password login is challenged → the key answers it. Then
each thing that must refuse: another origin, another relying party, a replayed
or expired challenge, a counter that fails to rise (a cloned key), a key that
is not yours — and a session still owing its second factor trying to add a key
or replace its TOTP authenticator (which would bypass the challenge entirely).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pytest

from maya.core import totp
from maya.core.errors import NotAuthenticated, PermissionDenied, ValidationFailed
from maya.sdk import Client
from tests.conftest import PASSWORD, World, build_platform
from tests.webauthn_authenticator import SoftKey


@pytest.fixture(scope="module")
def env():
    platform = build_platform()
    World(platform)
    from maya.api.app import create_api

    yield platform, create_api(platform)
    platform.shutdown()


def _login(app, username: str) -> tuple[Client, dict]:
    out = Client(app=app).auth.login(username, PASSWORD)
    return Client(app=app, token=out["token"]), out


def _register(app, username: str, key: SoftKey, name: str = "yubikey") -> dict:
    me, out = _login(app, username)
    assert out["mfa"] == "ok"
    options = me.auth.security_key_register_options()["options"]
    assert options["rp"]["id"] == "localhost" and options["attestation"] == "none"
    return me.auth.register_security_key(key.create(options), name=name)


def _answer(app, username: str, key: SoftKey, **kw) -> Client:
    me, out = _login(app, username)
    assert out["mfa"] == "challenge"
    options = me.auth.security_key_options()["options"]
    me.auth.security_key_verify(key.get(options, **kw))
    return me


def test_register_then_answer_the_challenge_with_the_key(env):
    platform, app = env
    key = SoftKey()
    row = _register(app, "dana", key)
    assert row["name"] == "yubikey" and row["transports"] == ["usb"]
    me, out = _login(app, "dana")
    assert out["mfa"] == "challenge"
    with pytest.raises(NotAuthenticated, match="second factor"):
        me.features.list()
    options = me.auth.security_key_options()["options"]
    assert [c["id"] for c in options["allowCredentials"]] == [row["credential_id"]]
    assert me.auth.security_key_verify(key.get(options)) == {"mfa": "ok"}
    assert isinstance(me.features.list(), list)
    status = me.auth.mfa_status()
    assert status["enrolled"] and status["security_keys"] == 1 and not status["totp"]
    with platform.uow() as uow:
        stored = uow.repo("webauthn_credentials").find_one(credential_id=row["credential_id"])
        assert stored["sign_count"] == 1 and stored["last_used_at"] is not None
        assert uow.repo("audit_events").list(action="auth.webauthn_registered")


def test_a_replayed_or_expired_challenge_is_refused(env):
    platform, app = env
    key = SoftKey()
    _register(app, "mick", key)
    me, _ = _login(app, "mick")
    answer = key.get(me.auth.security_key_options()["options"])
    me.auth.security_key_verify(answer)
    again, _ = _login(app, "mick")
    again.auth.security_key_options()
    with pytest.raises(NotAuthenticated, match="another sign-in|already used"):
        again.auth.security_key_verify(answer)  # the old challenge, replayed
    late, _ = _login(app, "mick")
    options = late.auth.security_key_options()["options"]
    with platform.uow() as uow:
        row = uow.repo("auth_challenges").find_one(
            kind="webauthn_login", handle=options["challenge"]
        )
        uow.repo("auth_challenges").update(
            row["id"], {"expires_at": dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)}
        )
    with pytest.raises(NotAuthenticated, match="expired"):
        late.auth.security_key_verify(key.get(options))
    with platform.uow() as uow:
        refused = uow.repo("audit_events").list(action="auth.webauthn_refused")
    assert {"the challenge has expired"} <= {a["detail"].get("reason") for a in refused}


def test_wrong_origin_or_relying_party_is_refused(env):
    _, app = env
    me, _ = _login(app, "mona")
    with pytest.raises(ValidationFailed, match="did not verify"):
        me.auth.register_security_key(
            SoftKey(origin="https://evil.example.test").create(
                me.auth.security_key_register_options()["options"]
            )
        )
    with pytest.raises(ValidationFailed, match="did not verify"):
        me.auth.register_security_key(
            SoftKey(rp_id="evil.example.test").create(
                me.auth.security_key_register_options()["options"]
            )
        )
    key = SoftKey()
    _register(app, "mona", key)
    key.origin = "https://evil.example.test"
    with pytest.raises(NotAuthenticated, match="did not verify"):
        _answer(app, "mona", key)
    key.origin = "http://localhost:8600"
    _answer(app, "mona", key)  # the real origin still works


def test_a_counter_that_does_not_rise_is_refused_and_ends_the_attempt(env):
    platform, app = env
    key = SoftKey()
    _register(app, "devi", key)
    _answer(app, "devi", key)  # counter now 1
    me, _ = _login(app, "devi")
    with pytest.raises(NotAuthenticated, match="sign count"):
        me.auth.security_key_verify(
            key.get(me.auth.security_key_options()["options"], bump=0)
        )  # a cloned key repeats the count
    with pytest.raises(NotAuthenticated):
        me.auth.me()  # that sign-in attempt is over
    with platform.uow() as uow:
        assert uow.repo("users").find_one(username="devi")["failed_attempts"] >= 1


def test_someone_elses_key_does_not_answer_your_challenge(env):
    _, app = env
    theirs = SoftKey()
    _register(app, "mgr", theirs)
    mine = SoftKey()
    _register(app, "owen", mine)
    me, _ = _login(app, "owen")
    with pytest.raises(NotAuthenticated, match="not registered to you"):
        me.auth.security_key_verify(theirs.get(me.auth.security_key_options()["options"]))


def test_a_session_owing_its_second_factor_cannot_add_or_replace_one(env):
    """Without this guard a stolen password alone could enroll a new factor and pass."""
    _, app = env
    key = SoftKey()
    _register(app, "tess", key)
    attacker, out = _login(app, "tess")
    assert out["mfa"] == "challenge"
    with pytest.raises(PermissionDenied, match="challenge"):
        attacker.auth.security_key_register_options()
    with pytest.raises(PermissionDenied, match="challenge"):
        attacker.auth.mfa_enroll()
    with pytest.raises(PermissionDenied, match="challenge"):
        attacker.auth.mfa_confirm("123456")
    with pytest.raises(NotAuthenticated, match="second factor"):
        attacker.features.list()


def test_keys_are_listed_removed_and_cleared_by_an_admin_reset(env):
    platform, app = env
    key = SoftKey()
    row = _register(app, "admin2", key, name="laptop")
    me = _answer(app, "admin2", key)
    assert [k["name"] for k in me.auth.security_keys()] == ["laptop"]
    second = _register_extra(app, me, SoftKey(), "phone")
    me.auth.remove_security_key(second["id"])
    assert [k["id"] for k in me.auth.security_keys()] == [row["id"]]
    admin = Client(app=app, token=Client(app=app).auth.login("admin", "maya-dev-admin")["token"])
    admin.admin.reset_mfa("admin2")
    _, out = _login(app, "admin2")
    assert out["mfa"] == "ok"
    with platform.uow() as uow:
        user = uow.repo("users").find_one(username="admin2")
        assert uow.repo("webauthn_credentials").count(user_id=user["id"]) == 0
        reset = uow.repo("audit_events").list(action="auth.mfa_reset")[-1]
    assert reset["detail"]["security_keys_removed"] == 1


def _register_extra(app, me: Client, key: SoftKey, name: str) -> dict:
    return me.auth.register_security_key(
        key.create(me.auth.security_key_register_options()["options"]), name=name
    )


def test_enrolling_a_key_satisfies_a_forced_enrollment():
    platform = build_platform(["--auth.mfa.enforce=true"])
    from maya.api.app import create_api

    app = create_api(platform)
    login = Client(app=app).auth.login("admin", "maya-dev-admin")
    assert login["mfa"] == "enroll"
    admin = Client(app=app, token=login["token"])
    key = SoftKey()
    out = admin.auth.register_security_key(
        key.create(admin.auth.security_key_register_options()["options"])
    )
    assert out["mfa"] == "ok" and admin.admin.users()
    platform.shutdown()


def test_with_totp_and_a_key_either_answers_the_challenge():
    platform = build_platform()
    World(platform)
    from maya.api.app import create_api

    app = create_api(platform)
    me, _ = _login(app, "dana")
    secret = me.auth.mfa_enroll()["secret"]
    step = totp.current_step()
    me.auth.mfa_confirm(totp.code_at(secret, step))
    key = SoftKey()
    me.auth.register_security_key(key.create(me.auth.security_key_register_options()["options"]))
    by_code, out = _login(app, "dana")
    assert out["mfa"] == "challenge"
    by_code.auth.mfa_verify(totp.code_at(secret, step + 1))
    assert isinstance(by_code.features.list(), list)
    by_key = _answer(app, "dana", key)
    assert isinstance(by_key.features.list(), list)
    assert by_key.auth.mfa_status()["totp"] and by_key.auth.mfa_status()["security_keys"] == 1
    platform.shutdown()


def test_the_web_flow_registers_a_key_and_answers_the_challenge_with_it():
    import re
    from starlette.testclient import TestClient
    from maya.server import build_app

    platform = build_platform()
    World(platform)
    web = TestClient(build_app(platform))

    def csrf(path: str) -> str:
        return re.search(r'name="csrf_token" value="([^"]+)"', web.get(path).text).group(1)

    def sign_in() -> None:
        web.post(
            "/login",
            data={"username": "dana", "password": PASSWORD, "csrf_token": csrf("/login")},
            follow_redirects=False,
        )

    sign_in()
    page = web.get("/account/mfa")
    assert page.status_code == 200 and 'data-webauthn="register"' in page.text
    headers = {"X-CSRF-Token": re.search(r'data-csrf="([^"]+)"', page.text).group(1)}
    assert web.post("/account/security-keys/options", json={}).status_code == 403  # no CSRF
    key = SoftKey()
    options = web.post("/account/security-keys/options", json={}, headers=headers).json()
    r = web.post(
        "/account/security-keys",
        headers=headers,
        json={"name": "desk key", "credential": key.create(options["options"])},
    )
    assert r.status_code == 200 and r.json()["next"] == "/account/mfa"
    assert "desk key" in web.get("/account/mfa").text
    web.post("/logout", data={"csrf_token": csrf("/")})

    sign_in()
    assert web.get("/catalog/features", follow_redirects=False).headers["location"] == "/mfa"
    challenge = web.get("/mfa")
    assert 'data-webauthn="authenticate"' in challenge.text and 'name="code"' not in challenge.text
    headers = {"X-CSRF-Token": re.search(r'data-csrf="([^"]+)"', challenge.text).group(1)}
    options = web.post("/mfa/key/options", json={}, headers=headers).json()
    r = web.post("/mfa/key", headers=headers, json={"credential": key.get(options["options"])})
    assert r.status_code == 200, r.text
    assert web.get("/catalog/features").status_code == 200
    platform.shutdown()
