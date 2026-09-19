"""
SAML signed requests and single logout (§12), against the test IdP.

MAYA signs its AuthnRequests and logout messages with its own key pair when
asked; signing out of MAYA sends a LogoutRequest to the IdP whose LogoutResponse
must answer it; and the IdP's own LogoutRequest — signed, from the configured
issuer, addressed to MAYA's SLS — ends every session of that sign-in and nothing
else. Each refusal is attacked on its own: unsigned, signed by the wrong key,
wrong issuer, wrong destination, an answer to no request, and a replayed answer.

These are protocol tests against a simulated IdP. The same flows against a real
one, Keycloak, are in tests/test_sso_keycloak.py (opt-in: MAYA_TEST_KEYCLOAK_URL).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import base64
import re
from urllib.parse import parse_qs, urlparse

import pytest

from maya.core.errors import NotAuthenticated, ValidationFailed
from maya.sdk import Client
from tests.conftest import build_platform
from tests.saml_idp import IDP_SLO, RSA_SHA256, SLS, SamlIdP, sp_key_pair


@pytest.fixture(scope="module")
def slo(tmp_path_factory):
    idp = SamlIdP()
    cert, key = sp_key_pair(tmp_path_factory.mktemp("sp-keys"))
    platform = build_platform(idp.argv(slo=True, sp_files=(cert, key)))
    from maya.api.app import create_api

    yield platform, idp, create_api(platform), cert
    platform.shutdown()


def _sign_in(app, idp: SamlIdP, username: str = "sara") -> str:
    request_id = Client(app=app).auth.saml_start()["request_id"]
    return Client(app=app).auth.saml_acs(idp.response(request_id, username))["token"]


def _alive(app, token: str) -> bool:
    try:
        Client(app=app, token=token).auth.me()
        return True
    except NotAuthenticated:
        return False


def _request_id(redirect_url: str) -> str:
    from onelogin.saml2.utils import OneLogin_Saml2_Utils

    raw = parse_qs(urlparse(redirect_url).query)["SAMLRequest"][0]
    xml = OneLogin_Saml2_Utils.decode_base64_and_inflate(raw)
    return re.search(r'ID="([^"]+)"', xml.decode() if isinstance(xml, bytes) else xml).group(1)


def _refused(platform, fragment: str) -> bool:
    with platform.uow() as uow:
        return any(
            fragment in a["detail"].get("reason", "")
            for a in uow.repo("audit_events").list(action="auth.sso_refused")
        )


def test_authn_requests_are_signed_with_the_sp_key_and_metadata_names_slo(slo):
    from onelogin.saml2.utils import OneLogin_Saml2_Utils

    platform, _, app, cert = slo
    url = Client(app=app).auth.saml_start()["redirect_url"]
    query = urlparse(url).query
    fields = parse_qs(query)
    assert fields["SigAlg"] == [RSA_SHA256]
    signed = "&".join(p for p in query.split("&") if not p.startswith("Signature="))
    assert OneLogin_Saml2_Utils.validate_binary_sign(
        signed, base64.b64decode(fields["Signature"][0]), open(cert).read(), RSA_SHA256
    )
    metadata = Client(app=app).auth.saml_metadata()
    text = metadata.decode() if isinstance(metadata, bytes) else str(metadata)
    assert "SingleLogoutService" in text and SLS in text and "KeyDescriptor" in text


def test_signing_out_of_maya_signs_out_at_the_idp(slo):
    platform, idp, app, _ = slo
    token = _sign_in(app, idp)
    out = Client(app=app, token=token).auth.logout()
    assert out["slo_redirect"].startswith(IDP_SLO) and "Signature=" in out["slo_redirect"]
    assert not _alive(app, token), "the MAYA session ends at once, whatever the IdP does"
    request_id = _request_id(out["slo_redirect"])
    answer = idp.logout_response(request_id)
    done = Client(app=app).auth.saml_sls(answer)
    assert done["outcome"] == "signed_out"
    with pytest.raises(NotAuthenticated, match="already answered"):
        Client(app=app).auth.saml_sls(answer)
    with pytest.raises(NotAuthenticated, match="did not make"):
        Client(app=app).auth.saml_sls(idp.logout_response("_not-a-request-maya-made"))


def test_a_password_session_signs_out_locally_only(slo):
    platform, _, app, _ = slo
    token = Client(app=app).auth.login("admin", "maya-dev-admin")["token"]
    assert Client(app=app, token=token).auth.logout()["slo_redirect"] is None


def test_the_idps_logout_request_ends_exactly_that_sign_in(slo):
    platform, idp, app, _ = slo
    first, second = _sign_in(app, idp, "sara"), _sign_in(app, idp, "sara")
    other = _sign_in(app, idp, "omar")
    out = Client(app=app).auth.saml_sls(idp.logout_request("sara"))
    assert out["outcome"] == "idp_logout" and out["sessions_ended"] == 2
    assert out["redirect_url"].startswith(IDP_SLO) and "SAMLResponse=" in out["redirect_url"]
    assert not _alive(app, first) and not _alive(app, second)
    assert _alive(app, other)
    with platform.uow() as uow:
        assert uow.repo("audit_events").find_one(action="auth.sso_logout", object_ref="saml:sara")


@pytest.mark.parametrize(
    "attack, reason",
    [
        ({"signed": False}, "Unsigned SAML LogoutRequest refused"),
        ({"rogue": True}, "Signature validation failed"),
        ({"issuer": "https://evil.example.test"}, "invalid"),
        ({"destination": "https://elsewhere.example.test/sls"}, "invalid"),
    ],
)
def test_logout_requests_the_idp_did_not_properly_send_end_nothing(slo, attack, reason):
    platform, idp, app, _ = slo
    token = _sign_in(app, idp, "sara")
    with pytest.raises(NotAuthenticated, match=reason):
        Client(app=app).auth.saml_sls(idp.logout_request("sara", **attack))
    assert _alive(app, token)
    assert _refused(platform, reason.split()[0])


def test_misconfiguration_is_refused_at_startup(tmp_path):
    idp = SamlIdP()
    argv = [a for a in idp.argv() if "sign_requests" not in a] + [
        "--auth.sso.saml.sign_requests=true"
    ]
    with pytest.raises(ValidationFailed, match="sp_cert, auth.sso.saml.sp_key"):
        build_platform(argv)


def test_without_slo_the_sls_is_refused_and_logout_stays_local(tmp_path):
    idp = SamlIdP()
    platform = build_platform(idp.argv())
    from maya.api.app import create_api

    app = create_api(platform)
    token = _sign_in(app, idp)
    assert Client(app=app, token=token).auth.logout()["slo_redirect"] is None
    with pytest.raises(ValidationFailed, match="not configured"):
        Client(app=app).auth.saml_sls(idp.logout_request("sara"))
    platform.shutdown()


def test_the_browser_follows_both_directions(slo):
    """Web: signing out redirects to the IdP; the IdP's signed request clears the
    browser session and is answered with a redirect back to the IdP."""
    from starlette.testclient import TestClient
    from maya.server import build_app

    platform, idp, _, _ = slo
    web = TestClient(build_app(platform), base_url="http://127.0.0.1:8600")
    to_idp = web.get("/auth/sso/login?next=/", follow_redirects=False).headers["location"]
    request_id = _request_id(to_idp)
    signed_in = web.post(
        "/auth/sso/saml/acs",
        data={"SAMLResponse": idp.response(request_id, "sara"), "RelayState": "/"},
        follow_redirects=False,
    )
    assert signed_in.status_code == 303
    home = web.get("/")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', home.text).group(1)
    out = web.post("/logout", data={"csrf_token": csrf}, follow_redirects=False)
    assert out.headers["location"].startswith(IDP_SLO)
    back = web.get("/auth/sso/saml/sls?" + idp.logout_request("sara"), follow_redirects=False)
    assert back.status_code == 303 and back.headers["location"].startswith(IDP_SLO)
