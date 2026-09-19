"""
OIDC logout, both directions (§12): RP-initiated logout at the IdP's end-session
endpoint, and back-channel logout tokens the IdP POSTs server to server.

A logout token is verified like an ID token and then some. Every check is attacked
with a token that fails exactly that one: signature, issuer, audience, freshness,
the logout event, a nonce, a missing sub/sid, a missing jti, and a replayed jti.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
import time
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from maya.core.errors import NotAuthenticated
from maya.sdk import Client
from tests.conftest import build_platform
from tests.test_sso_mfa import ISSUER, FakeIdP, _b64, _sign_in

EVENT = "http://schemas.openid.net/event/backchannel-logout"
AFTER = "http://127.0.0.1:8600/login?signed_out=1"


class LogoutIdP(FakeIdP):
    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json={
                "issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token", "jwks_uri": f"{ISSUER}/jwks",
                "end_session_endpoint": f"{ISSUER}/logout"})
        return super().handler(request)

    def id_token(self) -> str:
        self.overrides.setdefault("sid", "sid-" + self.claims.get("preferred_username", "x"))
        return super().id_token()

    def logout_token(self, *, drop: tuple[str, ...] = (), rogue: bool = False,
                     **claims) -> str:
        now = time.time()
        body = {"iss": ISSUER, "aud": "maya", "iat": now, "jti": uuid.uuid4().hex,
                "events": {EVENT: {}}, "sub": "sub-oona", "sid": "sid-oona", **claims}
        for key in drop:
            body.pop(key, None)
        header = {"alg": "RS256", "kid": "k1", "typ": "logout+jwt"}
        signing = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(body).encode())}"
        key = self.rogue if rogue else self.key
        sig = key.sign(signing.encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{signing}.{_b64(sig)}"


@pytest.fixture(scope="module")
def oidc():
    platform = build_platform([
        "--auth.mode=hybrid", f"--auth.sso.issuer={ISSUER}",
        f"--auth.sso.post_logout_redirect_uri={AFTER}",
        "--auth.sso.group_role_map.quants=model_designer"])
    idp = LogoutIdP()
    platform.sso.transport = httpx.MockTransport(idp.handler)
    from maya.api.app import create_api
    yield platform, idp, create_api(platform)
    platform.shutdown()


def _alive(app, token: str) -> bool:
    try:
        Client(app=app, token=token).auth.me()
        return True
    except NotAuthenticated:
        return False


def test_signing_out_of_maya_signs_out_at_the_idp(oidc):
    platform, idp, app = oidc
    token = _sign_in(app, idp, preferred_username="olga", groups=["quants"])["token"]
    out = Client(app=app, token=token).auth.logout()
    url = urlparse(out["slo_redirect"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == f"{ISSUER}/logout"
    assert parse_qs(url.query) == {"client_id": ["maya"], "post_logout_redirect_uri": [AFTER]}
    assert not _alive(app, token)


def test_a_logout_token_ends_that_sign_in_and_nothing_else(oidc):
    platform, idp, app = oidc
    idp.overrides = {}
    mine = _sign_in(app, idp, preferred_username="oona", groups=["quants"])["token"]
    idp.overrides = {}
    other = _sign_in(app, idp, preferred_username="otto", groups=["quants"])["token"]
    token = idp.logout_token()
    assert Client(app=app).auth.oidc_backchannel_logout(token)["sessions_ended"] == 1
    assert not _alive(app, mine) and _alive(app, other)
    with platform.uow() as uow:
        entry = uow.repo("audit_events").find_one(action="auth.sso_logout",
                                                  object_ref="oidc:sub-oona")
        assert entry and entry["detail"]["channel"] == "back"


def test_a_token_naming_only_a_sid_ends_that_session(oidc):
    platform, idp, app = oidc
    idp.overrides = {"sid": "sid-only-this"}
    token = _sign_in(app, idp, preferred_username="omar", groups=["quants"])["token"]
    out = Client(app=app).auth.oidc_backchannel_logout(
        idp.logout_token(drop=("sub",), sid="sid-only-this"))
    assert out["sessions_ended"] == 1 and not _alive(app, token)


@pytest.mark.parametrize("change, reason", [
    ({"rogue": True}, "signature does not verify"),
    ({"iss": "https://evil.example.test"}, "issuer mismatch"),
    ({"aud": "someone-else"}, "audience"),
    ({"iat": time.time() - 3600}, "not fresh"),
    ({"events": {}}, "no logout event"),
    ({"nonce": "n"}, "must not carry a nonce"),
    ({"drop": ("sub", "sid")}, "sub or a sid"),
    ({"drop": ("jti",)}, "jti"),
])
def test_each_logout_token_check_refuses_on_its_own(oidc, change, reason):
    platform, idp, app = oidc
    idp.overrides = {}
    token = _sign_in(app, idp, preferred_username="oona", groups=["quants"])["token"]
    from starlette.testclient import TestClient
    web = TestClient(app)
    resp = web.post("/api/v1/auth/sso/oidc/backchannel-logout",
                    data={"logout_token": idp.logout_token(**change)})
    assert resp.status_code == 400 and reason in resp.json()["detail"], resp.text
    assert resp.headers["cache-control"] == "no-store"
    assert _alive(app, token), "a refused token ends nothing"


def test_a_logout_token_is_single_use(oidc):
    platform, idp, app = oidc
    token = idp.logout_token()
    Client(app=app).auth.oidc_backchannel_logout(token)
    with pytest.raises(NotAuthenticated, match="already used"):
        Client(app=app).auth.oidc_backchannel_logout(token)
