"""
SSO (OIDC) against a fake identity provider, and TOTP MFA (§12).

The fake IdP is real in the parts that matter: an RSA key, a JWKS document, a
discovery document and a token endpoint issuing signed ID tokens. Every check an
ID token must pass is attacked with a token that fails exactly that check.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from maya.core import totp
from maya.core.errors import NotAuthenticated, ValidationFailed
from maya.sdk import Client
from tests.conftest import PASSWORD, World, build_platform

ISSUER = "https://idp.example.test"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


class FakeIdP:
    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.rogue = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.claims: dict = {}
        self.nonce = ""
        self.overrides: dict = {}
        self.sign_with = self.key
        self.alg = "RS256"

    def jwk(self) -> dict:
        n = self.key.public_key().public_numbers()
        return {"kty": "RSA", "kid": "k1", "alg": "RS256",
                "n": _b64(n.n.to_bytes((n.n.bit_length() + 7) // 8, "big")),
                "e": _b64(n.e.to_bytes(3, "big"))}

    def id_token(self) -> str:
        now = time.time()
        claims = {"iss": ISSUER, "aud": "maya", "sub": "sub-" + self.claims.get(
            "preferred_username", "x"), "iat": now, "exp": now + 300, "nonce": self.nonce,
            **self.claims, **self.overrides}
        header = {"alg": self.alg, "kid": "k1", "typ": "JWT"}
        signing = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(claims).encode())}"
        sig = b"" if self.alg == "none" else self.sign_with.sign(
            signing.encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{signing}.{_b64(sig)}"

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json={
                "issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token", "jwks_uri": f"{ISSUER}/jwks"})
        if path == "/jwks":
            return httpx.Response(200, json={"keys": [self.jwk()]})
        if path == "/token":
            form = parse_qs(request.content.decode())
            assert form["code_verifier"][0] and form["grant_type"] == ["authorization_code"]
            return httpx.Response(200, json={"id_token": self.id_token(),
                                             "token_type": "Bearer"})
        return httpx.Response(404)


@pytest.fixture(scope="module")
def sso():
    platform = build_platform([
        "--auth.mode=hybrid", f"--auth.sso.issuer={ISSUER}",
        "--auth.sso.group_role_map.quants=model_designer,feature_designer",
        "--auth.sso.group_role_map.risk=model_manager"])
    idp = FakeIdP()
    platform.sso.transport = httpx.MockTransport(idp.handler)
    from maya.api.app import create_api
    yield platform, idp, create_api(platform)
    platform.shutdown()


def _sign_in(app, idp, **claims):
    anon = Client(app=app)
    start = anon.auth.sso_start()
    query = parse_qs(urlparse(start["authorize_url"]).query)
    assert query["code_challenge_method"] == ["S256"] and query["state"] == [start["state"]]
    idp.nonce = start["nonce"]
    idp.claims = claims
    return anon.auth.sso_callback("auth-code", start["code_verifier"], start["nonce"])


def test_jit_provisioning_maps_groups_to_roles_and_remaps_each_login(sso):
    platform, idp, app = sso
    out = _sign_in(app, idp, preferred_username="quinn", email="q@x", groups=["quants"])
    me = Client(app=app, token=out["token"]).auth.me()
    assert me["auth_source"] == "sso" and me["roles"] == ["feature_designer", "model_designer"]
    out = _sign_in(app, idp, preferred_username="quinn", groups=["risk"])
    assert Client(app=app, token=out["token"]).auth.me()["roles"] == ["model_manager"], \
        "leaving the quants group must remove its roles at the next login"


def test_unmapped_groups_are_denied_and_audited(sso):
    platform, idp, app = sso
    with pytest.raises(NotAuthenticated, match="maps to a MAYA role"):
        _sign_in(app, idp, preferred_username="nobody", groups=["marketing"])
    admin = platform.access
    with platform.uow() as uow:
        assert uow.repo("audit_events").count(action="auth.sso_refused") >= 1
    assert admin.verify_audit()["ok"]


@pytest.mark.parametrize("attack, message", [
    ({"aud": "someone-else"}, "audience"),
    ({"iss": "https://evil.example"}, "issuer"),
    ({"exp": 1000}, "expired"),
    ({"nonce": "replayed"}, "nonce"),
])
def test_each_id_token_check_bites(sso, attack, message):
    platform, idp, app = sso
    idp.overrides = attack
    try:
        with pytest.raises(NotAuthenticated, match=message):
            _sign_in(app, idp, preferred_username="mallory", groups=["quants"])
    finally:
        idp.overrides = {}


def test_forged_signature_and_alg_none_are_refused(sso):
    platform, idp, app = sso
    idp.sign_with = idp.rogue
    try:
        with pytest.raises(NotAuthenticated, match="signature"):
            _sign_in(app, idp, preferred_username="mallory", groups=["quants"])
    finally:
        idp.sign_with = idp.key
    idp.alg = "none"
    try:
        with pytest.raises(NotAuthenticated, match="not accepted"):
            _sign_in(app, idp, preferred_username="mallory", groups=["quants"])
    finally:
        idp.alg = "RS256"


def test_sso_cannot_take_over_a_local_account(sso):
    platform, idp, app = sso
    with pytest.raises(NotAuthenticated, match="local password account"):
        _sign_in(app, idp, preferred_username="admin", groups=["quants"])


def test_hybrid_keeps_password_login_and_sso_mode_refuses_it(sso):
    platform, idp, app = sso
    assert Client(app=app).auth.login("admin", "maya-dev-admin")["token"]
    strict = build_platform(["--auth.mode=sso", f"--auth.sso.issuer={ISSUER}"])
    from maya.api.app import create_api
    with pytest.raises(NotAuthenticated, match="SSO only"):
        Client(app=create_api(strict)).auth.login("admin", "maya-dev-admin")
    strict.shutdown()


def test_startup_refusals_name_what_is_missing():
    # SAML's startup refusals live in tests/test_saml.py
    with pytest.raises(ValidationFailed, match="issuer"):
        build_platform(["--auth.mode=hybrid", "--auth.sso.issuer="])


# -- MFA ---------------------------------------------------------------------------------------
def test_enrolled_user_is_challenged_and_codes_cannot_be_replayed():
    platform = build_platform()
    World(platform)
    from maya.api.app import create_api
    app = create_api(platform)
    first = Client(app=app).auth.login("dana", PASSWORD)
    assert first["mfa"] == "ok"
    dana = Client(app=app, token=first["token"])
    enrolled = dana.auth.mfa_enroll()
    assert enrolled["otpauth_uri"].startswith("otpauth://totp/MAYA:dana")
    secret = enrolled["secret"]
    step = totp.current_step()
    dana.auth.mfa_confirm(totp.code_at(secret, step))
    with platform.uow() as uow:
        stored = uow.repo("users").find_one(username="dana")["mfa_secret"]
    assert secret not in stored, "the TOTP secret must be encrypted at rest"

    second = Client(app=app).auth.login("dana", PASSWORD)
    assert second["mfa"] == "challenge"
    gated = Client(app=app, token=second["token"])
    with pytest.raises(NotAuthenticated, match="second factor"):
        gated.features.list()
    with pytest.raises(NotAuthenticated, match="already used"):
        gated.auth.mfa_verify(totp.code_at(secret, step))       # the enrollment code: a replay
    third = Client(app=app, token=Client(app=app).auth.login("dana", PASSWORD)["token"])
    third.auth.mfa_verify(totp.code_at(secret, step + 1))
    assert isinstance(third.features.list(), list)
    platform.shutdown()


def test_role_requirement_forces_enrollment_when_enforced():
    platform = build_platform(["--auth.mfa.enforce=true"])
    from maya.api.app import create_api
    app = create_api(platform)
    login = Client(app=app).auth.login("admin", "maya-dev-admin")
    assert login["mfa"] == "enroll"
    admin = Client(app=app, token=login["token"])
    with pytest.raises(NotAuthenticated, match="enroll"):
        admin.admin.users()
    secret = admin.auth.mfa_enroll()["secret"]
    admin.auth.mfa_confirm(totp.code_at(secret, totp.current_step()))
    assert admin.admin.users()
    platform.shutdown()


def test_no_credential_field_ever_leaves_the_server():
    platform = build_platform()
    World(platform)
    from maya.api.app import create_api
    app = create_api(platform)
    admin = Client(app=app, token=Client(app=app).auth.login("admin", "maya-dev-admin")["token"])
    admin.auth.mfa_enroll()
    for payload in (admin.admin.users(), [admin.auth.me()]):
        for user in payload:
            assert not {"password_hash", "mfa_secret", "mfa_last_step"} & set(user)
    platform.shutdown()


def _csrf(html: str) -> str:
    import re
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def test_web_holds_an_mfa_pending_session_at_the_code_page():
    from starlette.testclient import TestClient
    from maya.server import build_app
    platform = build_platform()
    World(platform)
    app = build_app(platform)
    # enroll dana through the API first
    api = Client(app=app, token=Client(app=app).auth.login("dana", PASSWORD)["token"])
    secret = api.auth.mfa_enroll()["secret"]
    step = totp.current_step()
    api.auth.mfa_confirm(totp.code_at(secret, step))
    web = TestClient(app)
    page = web.get("/login")
    r = web.post("/login", data={"username": "dana", "password": PASSWORD,
                                 "csrf_token": _csrf(page.text)}, follow_redirects=False)
    assert r.headers["location"] == "/mfa"
    assert web.get("/catalog/features", follow_redirects=False).headers["location"] == "/mfa"
    code_page = web.get("/mfa")
    r = web.post("/mfa", data={"code": totp.code_at(secret, step + 1),
                               "csrf_token": _csrf(code_page.text)}, follow_redirects=False)
    # past the second factor; next stop is the password an administrator set
    assert r.status_code == 303 and r.headers["location"] == "/account/password"
    assert web.get("/account/password").status_code == 200
    platform.shutdown()


def test_login_page_offers_sso_when_enabled(sso):
    from starlette.testclient import TestClient
    from maya.server import build_app
    platform, idp, _ = sso
    web = TestClient(build_app(platform))
    html = web.get("/login").text
    assert "/auth/sso/login" in html and "single sign-on" in html
    r = web.get("/auth/sso/login", follow_redirects=False)
    assert r.headers["location"].startswith(f"{ISSUER}/authorize?")
    bad = web.get("/auth/sso/callback?code=x&state=forged")
    assert bad.status_code == 400
