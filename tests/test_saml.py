"""
SAML 2.0 single sign-on against a test IdP whose assertions are really signed (§12).

Every check a Response must pass is attacked with a Response that fails exactly
that check: signature, audience, issuer, recipient/destination, expiry,
InResponseTo (unsolicited, unknown, replayed), and a replayed assertion. The
happy path goes all the way to a session whose roles came from the IdP's groups.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
from urllib.parse import parse_qs, urlparse

import pytest

from maya.core.errors import CapabilityRefused, NotAuthenticated, ValidationFailed
from maya.sdk import Client
from tests.conftest import build_platform
from tests.saml_idp import ACS, SP, SamlIdP


@pytest.fixture(scope="module")
def saml():
    idp = SamlIdP()
    platform = build_platform(idp.argv())
    from maya.api.app import create_api
    yield platform, idp, create_api(platform)
    platform.shutdown()


def _start(app) -> str:
    return Client(app=app).auth.saml_start()["request_id"]


def _refusals(platform, reason: str) -> list:
    with platform.uow() as uow:
        return [a for a in uow.repo("audit_events").list(action="auth.sso_refused")
                if reason in a["detail"].get("reason", "")]


def test_signed_response_opens_a_session_with_mapped_roles(saml):
    platform, idp, app = saml
    anon = Client(app=app)
    start = anon.auth.saml_start(relay_state="/models")
    url = urlparse(start["redirect_url"])
    assert url.netloc == "idp.example.test" and "SAMLRequest" in parse_qs(url.query)
    assert parse_qs(url.query)["RelayState"] == ["/models"]
    out = anon.auth.saml_acs(idp.response(start["request_id"], "sara"))
    me = Client(app=app, token=out["token"]).auth.me()
    assert me["username"] == "sara" and "admin" in me["roles"]
    with platform.uow() as uow:
        user = uow.repo("users").find_one(username="sara")
        assert user["auth_source"] == "sso" and user["email"] == "sara@example.test"
        assert uow.repo("audit_events").list(action="auth.sso_login")



def test_repeated_attribute_elements_are_merged_not_refused(saml):
    """Keycloak sends one ``Role`` Attribute element per role by default, and a groups
    mapper without "single attribute" one ``groups`` element per group. python3-saml
    refuses such a Response unless told otherwise; MAYA merges the values (found
    against Keycloak 26.4)."""
    platform, idp, app = saml
    rid = _start(app)
    out = Client(app=app).auth.saml_acs(idp.response(
        rid, "kira", groups=("unmapped-team", "maya-admins"), repeat_attributes=True))
    me = Client(app=app, token=out["token"]).auth.me()
    assert me["username"] == "kira" and "admin" in me["roles"]
    with platform.uow() as uow:
        login = [a for a in uow.repo("audit_events").list(action="auth.sso_login")
                 if a["object_ref"] == "user:kira"]
        assert login and login[0]["detail"]["groups"] == ["unmapped-team", "maya-admins"]

def test_the_sp_metadata_names_entity_and_acs(saml):
    _, _, app = saml
    raw = Client(app=app).auth.saml_metadata()
    xml = raw["data"].decode() if isinstance(raw, dict) else raw.decode()
    assert f'entityID="{SP}"' in xml and ACS in xml


@pytest.mark.parametrize("change, reason", [
    ({"rogue": True}, "Signature validation failed"),
    ({"unsigned": True}, "signed"),
    ({"audience": "https://someone-else.example.test"}, "audience"),
    ({"issuer": "https://evil.example.test"}, "ssuer"),
    ({"destination": "https://evil.example.test/acs"}, "received at .* instead of"),
    ({"recipient": "https://evil.example.test/acs"}, "SubjectConfirmation|recipient"),
])
def test_each_assertion_check_refuses_on_its_own(saml, change, reason):
    platform, idp, app = saml
    rid = _start(app)
    with pytest.raises(NotAuthenticated, match=f"(?i){reason}"):
        Client(app=app).auth.saml_acs(idp.response(rid, "mallory", **change))
    assert _refusals(platform, "invalid"), "a refusal is audited durably"


def test_an_expired_assertion_is_refused(saml):
    _, idp, app = saml
    rid = _start(app)
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=30)
    with pytest.raises(NotAuthenticated, match="(?i)expired|NotOnOrAfter|no longer valid"):
        Client(app=app).auth.saml_acs(idp.response(rid, "sara", not_on_or_after=old))


def test_unsolicited_unknown_and_replayed_responses_are_refused(saml):
    platform, idp, app = saml
    anon = Client(app=app)
    with pytest.raises(NotAuthenticated, match="(?i)unsolicited"):
        anon.auth.saml_acs(idp.response(None, "sara"))
    with pytest.raises(NotAuthenticated, match="did not make"):
        anon.auth.saml_acs(idp.response("ONELOGIN_forged", "sara"))
    rid = _start(app)
    good = idp.response(rid, "sara")
    assert anon.auth.saml_acs(good)["token"]
    with pytest.raises(NotAuthenticated, match="already answered"):
        anon.auth.saml_acs(good)                      # the same Response again
    with pytest.raises(NotAuthenticated, match="already answered"):
        anon.auth.saml_acs(idp.response(rid, "sara"))  # a new Response to the used request
    assert _refusals(platform, "unsolicited") and _refusals(platform, "replay")


def test_a_replayed_assertion_is_refused_even_for_a_fresh_request(saml):
    _, idp, app = saml
    anon = Client(app=app)
    anon.auth.saml_acs(idp.response(_start(app), "sara", assertion_id="_fixed-assertion"))
    with pytest.raises(NotAuthenticated, match="assertion was already used"):
        anon.auth.saml_acs(idp.response(_start(app), "sara", assertion_id="_fixed-assertion"))


def test_an_expired_request_cannot_be_answered(saml):
    platform, idp, app = saml
    rid = _start(app)
    with platform.uow() as uow:
        row = uow.repo("auth_challenges").find_one(kind="saml_request", handle=rid)
        uow.repo("auth_challenges").update(row["id"], {
            "expires_at": dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)})
    with pytest.raises(NotAuthenticated, match="expired"):
        Client(app=app).auth.saml_acs(idp.response(rid, "sara"))


def test_no_mapped_group_is_refused(saml):
    _, idp, app = saml
    with pytest.raises(NotAuthenticated, match="maps to a MAYA role"):
        Client(app=app).auth.saml_acs(idp.response(_start(app), "nobody", groups=("x",)))


def test_startup_refuses_incomplete_or_unavailable_saml(monkeypatch):
    with pytest.raises(ValidationFailed, match="auth.sso.saml.sp_entity_id"):
        build_platform(["--auth.mode=sso", "--auth.sso.protocol=saml2"])
    with pytest.raises(CapabilityRefused, match="must be 'oidc' or 'saml2'"):
        build_platform(["--auth.mode=sso", "--auth.sso.protocol=ws-fed"])
    from maya.security import saml
    monkeypatch.setattr(saml, "available", lambda: False)
    with pytest.raises(CapabilityRefused, match="python3-saml"):
        build_platform(SamlIdP().argv())


def test_web_login_redirects_to_the_idp_and_the_acs_signs_in():
    from starlette.testclient import TestClient
    from maya.server import build_app
    idp = SamlIdP()
    platform = build_platform(idp.argv())
    web = TestClient(build_app(platform))
    r = web.get("/auth/sso/login?next=/models", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("https://idp.example.test")
    rid = parse_qs(urlparse(r.headers["location"]).query)
    with platform.uow() as uow:
        pending = uow.repo("auth_challenges").list(kind="saml_request", consumed_at=None)
    assert pending and "SAMLRequest" in rid
    # the IdP posts back cross-site: no session cookie comes with it
    fresh = TestClient(build_app(platform))
    r = fresh.post("/auth/sso/saml/acs", data={
        "SAMLResponse": idp.response(pending[-1]["handle"], "sara"), "RelayState": "/models"},
        follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/models"
    assert fresh.get("/", follow_redirects=False).status_code == 200
    bad = fresh.post("/auth/sso/saml/acs", data={"SAMLResponse": idp.response(None, "sara")})
    assert bad.status_code == 401 and "nsolicited" in bad.text
    platform.shutdown()
