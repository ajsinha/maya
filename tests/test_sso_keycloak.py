"""
Single sign-on against a real identity provider: Keycloak, OIDC and SAML 2.0 (§12).

Opt-in. Set ``MAYA_TEST_KEYCLOAK_URL`` to a running Keycloak whose master realm
admin is ``MAYA_TEST_KEYCLOAK_ADMIN`` / ``MAYA_TEST_KEYCLOAK_ADMIN_PASSWORD``
(default admin / admin), e.g. a throwaway dev-mode container::

    docker run -d --name maya-keycloak --network host \\
        -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \\
        quay.io/keycloak/keycloak:26.4 start-dev --http-port=58080

(``--network host`` so Keycloak can reach MAYA server to server for OIDC back-channel
logout; without it those two tests fail, the rest pass.)
    MAYA_TEST_KEYCLOAK_URL=http://localhost:58080 pytest tests/test_sso_keycloak.py

The module creates its own realm through the admin REST API (removed afterwards),
starts MAYA for real with ``run_maya_web.py`` on 127.0.0.1 — a different site from
Keycloak's ``localhost``, so the SAML POST and the logout redirects are cross-site
as in production — and drives headless Chrome through Keycloak's own login page.
The realm is configured exactly as the security guide's "Tested against Keycloak"
section describes. Needs Playwright and Chrome; skipped otherwise.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import os
import re
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator

import pytest

KEYCLOAK = os.environ.get("MAYA_TEST_KEYCLOAK_URL", "").rstrip("/")
pytestmark = pytest.mark.skipif(not KEYCLOAK, reason="MAYA_TEST_KEYCLOAK_URL is not set")
playwright_sync = pytest.importorskip("playwright.sync_api")
httpx = pytest.importorskip("httpx")

ROOT = Path(__file__).resolve().parents[1]
ALICE, ALICE_PW = "kc.alice", "Alice-Pass-123!"
BOB, BOB_PW = "kc.bob", "Bob-Pass-123456!"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Realm:
    """A throwaway Keycloak realm set up for one MAYA through the admin REST API."""

    def __init__(self, maya: str, sp_cert: str) -> None:
        self.name = f"maya-it-{secrets.token_hex(4)}"
        self.maya, self.sp_entity = maya, f"{maya}/saml"
        self.issuer = f"{KEYCLOAK}/realms/{self.name}"
        self.saml_url = f"{self.issuer}/protocol/saml"
        self.http = httpx.Client(base_url=KEYCLOAK, timeout=30)
        self._login()
        self.admin = f"/admin/realms/{self.name}"
        self._ok(self.http.post("/admin/realms", json={"realm": self.name, "enabled": True}))
        self.alice = self._user(ALICE, ALICE_PW, "maya-admins", "maya-risk")
        self._user(BOB, BOB_PW)  # in no mapped group
        self._oidc_client()
        self._saml_client(
            "".join(line for line in sp_cert.splitlines() if "CERTIFICATE" not in line)
        )
        descriptor = self.http.get(f"/realms/{self.name}/protocol/saml/descriptor").text
        self.idp_cert = re.search(
            r"<ds:X509Certificate>([^<]+)</ds:X509Certificate>", descriptor
        ).group(1)

    def _login(self) -> None:
        tok = self.http.post(
            "/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": os.environ.get("MAYA_TEST_KEYCLOAK_ADMIN", "admin"),
                "password": os.environ.get("MAYA_TEST_KEYCLOAK_ADMIN_PASSWORD", "admin"),
            },
        )
        self.http.headers["Authorization"] = f"Bearer {tok.json()['access_token']}"

    @staticmethod
    def _ok(r: Any) -> Any:
        assert r.status_code < 300, f"{r.request.method} {r.request.url}: {r.text}"
        return r

    def _user(self, username: str, password: str, *groups: str) -> str:
        first = username.split(".")[1].title()
        self._ok(
            self.http.post(
                f"{self.admin}/users",
                json={
                    "username": username,
                    "enabled": True,
                    "email": f"{first.lower()}@example.test",
                    "emailVerified": True,
                    "firstName": first,
                    "lastName": "Keycloak",
                    "credentials": [{"type": "password", "value": password, "temporary": False}],
                },
            )
        )
        uid = self.http.get(
            f"{self.admin}/users", params={"username": username, "exact": "true"}
        ).json()[0]["id"]
        for group in groups:
            self.http.post(f"{self.admin}/groups", json={"name": group})  # 409 if present
            gid = next(
                g["id"] for g in self.http.get(f"{self.admin}/groups").json() if g["name"] == group
            )
            self._ok(self.http.put(f"{self.admin}/users/{uid}/groups/{gid}"))
        return uid

    def _oidc_client(self) -> None:
        """Confidential, PKCE S256, groups claim (short names) from a ``groups`` client
        scope — Keycloak refuses a scope it does not know, and MAYA asks for ``groups``."""
        self._ok(
            self.http.post(
                f"{self.admin}/client-scopes",
                json={
                    "name": "groups",
                    "protocol": "openid-connect",
                    "attributes": {"include.in.token.scope": "true"},
                    "protocolMappers": [
                        {
                            "name": "groups",
                            "protocol": "openid-connect",
                            "protocolMapper": "oidc-group-membership-mapper",
                            "config": {
                                "claim.name": "groups",
                                "full.path": "false",
                                "id.token.claim": "true",
                                "access.token.claim": "true",
                                "userinfo.token.claim": "true",
                            },
                        }
                    ],
                },
            )
        )
        self._ok(
            self.http.post(
                f"{self.admin}/clients",
                json={
                    "clientId": "maya-oidc",
                    "protocol": "openid-connect",
                    "enabled": True,
                    "publicClient": False,
                    "secret": "maya-oidc-secret",
                    "standardFlowEnabled": True,
                    "directAccessGrantsEnabled": False,
                    "implicitFlowEnabled": False,
                    "redirectUris": [f"{self.maya}/auth/sso/callback"],
                    "attributes": {
                        "pkce.code.challenge.method": "S256",
                        "post.logout.redirect.uris": f"{self.maya}/login?signed_out=1",
                        "backchannel.logout.url": f"{self.maya}/api/v1/auth/sso/oidc/backchannel-logout",
                        "backchannel.logout.session.required": "true",
                    },
                },
            )
        )
        scope = next(
            c["id"]
            for c in self.http.get(f"{self.admin}/client-scopes").json()
            if c["name"] == "groups"
        )
        client = self.http.get(f"{self.admin}/clients", params={"clientId": "maya-oidc"}).json()[0][
            "id"
        ]
        self._ok(self.http.put(f"{self.admin}/clients/{client}/optional-client-scopes/{scope}"))

    def _saml_client(self, sp_cert_body: str) -> None:
        """Client id = MAYA's SP entity id; signed assertions and documents; MAYA's
        requests signed with its key; front-channel logout by redirect to MAYA's SLS;
        a ``groups`` attribute with one element per group (not "single")."""
        self._ok(
            self.http.post(
                f"{self.admin}/clients",
                json={
                    "clientId": self.sp_entity,
                    "protocol": "saml",
                    "enabled": True,
                    "frontchannelLogout": True,
                    "redirectUris": [f"{self.maya}/*"],
                    "attributes": {
                        "saml.assertion.signature": "true",
                        "saml.server.signature": "true",
                        "saml.signature.algorithm": "RSA_SHA256",
                        "saml.client.signature": "true",
                        "saml.signing.certificate": sp_cert_body,
                        "saml.encrypt": "false",
                        "saml.force.post.binding": "true",
                        "saml_force_name_id_format": "true",
                        "saml_name_id_format": "username",
                        "saml.authnstatement": "true",
                        "saml_assertion_consumer_url_post": f"{self.maya}/auth/sso/saml/acs",
                        "saml_single_logout_service_url_redirect": f"{self.maya}/auth/sso/saml/sls",
                    },
                    "protocolMappers": [
                        {
                            "name": "groups",
                            "protocol": "saml",
                            "protocolMapper": "saml-group-membership-mapper",
                            "config": {
                                "attribute.name": "groups",
                                "full.path": "false",
                                "single": "false",
                                "attribute.nameformat": "Basic",
                            },
                        },
                        {
                            "name": "email",
                            "protocol": "saml",
                            "protocolMapper": "saml-user-property-mapper",
                            "config": {
                                "user.attribute": "email",
                                "attribute.name": "email",
                                "attribute.nameformat": "Basic",
                            },
                        },
                    ],
                },
            )
        )

    def sessions(self, user_id: str) -> int:
        self._login()
        return len(self.http.get(f"{self.admin}/users/{user_id}/sessions").json())

    def admin_sign_out(self, user_id: str) -> None:
        """The admin console's "Sign out" for a user: Keycloak's back channel only."""
        self._login()
        self._ok(self.http.post(f"{self.admin}/users/{user_id}/logout"))

    def end_latest_session(self, user_id: str) -> None:
        """The admin console's "Sign out" on one session: the user's most recent."""
        self._login()
        latest = max(
            self.http.get(f"{self.admin}/users/{user_id}/sessions").json(), key=lambda s: s["start"]
        )
        self._ok(self.http.delete(f"{self.admin}/sessions/{latest['id']}"))

    def delete(self) -> None:
        self._login()
        self.http.delete(self.admin)


class Maya:
    """``python run_maya_web.py`` with a throwaway MAYA_HOME, in hybrid mode."""

    def __init__(self, home: Path, port: int, *argv: str) -> None:
        self.url = f"http://127.0.0.1:{port}"
        env = dict(os.environ, MAYA_HOME=str(home))
        env.pop("MAYA_CONFIG_FILE", None)
        self.log = open(home / "maya.log", "wb")
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "run_maya_web.py",
                f"--server.port={port}",
                "--server.host=127.0.0.1",
                "--auth.mode=hybrid",
                "--auth.sso.group_role_map.maya-risk=model_manager",
                *argv,
            ],
            cwd=ROOT,
            env=env,
            stdout=self.log,
            stderr=subprocess.STDOUT,
        )
        for _ in range(240):
            try:
                if httpx.get(f"{self.url}/login", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            if self.proc.poll() is not None:
                break
            time.sleep(0.5)
        self.stop()
        raise AssertionError(f"MAYA did not start; see {home / 'maya.log'}")

    def stop(self) -> None:
        if self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.log.close()


@pytest.fixture(scope="module")
def realm(tmp_path_factory) -> Iterator[tuple[Realm, int, tuple[str, str]]]:
    from tests.saml_idp import sp_key_pair

    port = _free_port()
    sp = sp_key_pair(tmp_path_factory.mktemp("sp-keys"))
    try:
        r = Realm(f"http://127.0.0.1:{port}", Path(sp[0]).read_text())
    except httpx.HTTPError as exc:
        pytest.skip(f"Keycloak at {KEYCLOAK} is unreachable: {exc}")
    yield r, port, sp
    r.delete()


@pytest.fixture(scope="module")
def browser():
    with playwright_sync.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception as exc:  # noqa: BLE001 - no Chrome here: nothing to drive
            pytest.skip(f"Chrome is not available to Playwright: {exc}")
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context()
    yield ctx.new_page()
    ctx.close()


@pytest.fixture(scope="module")
def oidc(realm, tmp_path_factory):
    r, port, _ = realm
    m = Maya(
        tmp_path_factory.mktemp("maya-oidc"),
        port,
        "--auth.sso.protocol=oidc",
        f"--auth.sso.issuer={r.issuer}",
        "--auth.sso.client_id=maya-oidc",
        "--auth.sso.client_secret=maya-oidc-secret",
        f"--auth.sso.redirect_uri=http://127.0.0.1:{port}/auth/sso/callback",
        f"--auth.sso.post_logout_redirect_uri=http://127.0.0.1:{port}/login?signed_out=1",
    )
    yield r, m
    m.stop()


@pytest.fixture(scope="module")
def saml(realm, tmp_path_factory, oidc):
    """After the OIDC tests (same port): MAYA again, now as a SAML service provider."""
    r, port, (sp_cert, sp_key) = realm
    oidc[1].stop()
    home = tmp_path_factory.mktemp("maya-saml")
    idp_cert = home / "idp.crt"
    idp_cert.write_text(f"-----BEGIN CERTIFICATE-----\n{r.idp_cert}\n-----END CERTIFICATE-----\n")
    m = Maya(
        home,
        port,
        "--auth.sso.protocol=saml2",
        f"--auth.sso.saml.sp_entity_id={r.sp_entity}",
        f"--auth.sso.saml.acs_url={r.maya}/auth/sso/saml/acs",
        f"--auth.sso.saml.idp_entity_id={r.issuer}",
        f"--auth.sso.saml.idp_sso_url={r.saml_url}",
        f"--auth.sso.saml.idp_cert_file={idp_cert}",
        f"--auth.sso.saml.idp_slo_url={r.saml_url}",
        f"--auth.sso.saml.sls_url={r.maya}/auth/sso/saml/sls",
        "--auth.sso.saml.sign_requests=true",
        f"--auth.sso.saml.sp_cert_file={sp_cert}",
        f"--auth.sso.saml.sp_key_file={sp_key}",
    )
    yield r, m
    m.stop()


def _sso_login(page, maya: Maya, username: str = ALICE, password: str = ALICE_PW) -> bool:
    """Start SSO from MAYA; sign in on Keycloak's page if it asks. True if it asked."""
    page.goto(f"{maya.url}/auth/sso/login?next=/")
    asked = page.locator("#username").count() > 0
    if asked:
        assert page.url.startswith(KEYCLOAK)
        page.fill("#username", username)
        page.fill("#password", password)
        page.click("#kc-login")
        page.wait_for_load_state("networkidle")
    return asked


def _signed_in_as(page, maya: Maya) -> tuple[str, list[str]] | None:
    """(username, roles) from MAYA's own navigation, or None when MAYA asks for login."""
    page.goto(f"{maya.url}/")
    if "/login" in page.url:
        return None
    menu = page.locator(".px-3.py-2").filter(has=page.locator(".fw-semibold")).first
    roles = (menu.locator(".small-muted").text_content() or "").strip()
    return (
        (menu.locator(".fw-semibold").text_content() or "").strip(),
        sorted(r.strip() for r in roles.split(",") if r.strip() and roles != "no roles"),
    )


def _sign_out_of_maya(page) -> None:
    """Submit the navigation's sign-out form; wait until the browser is back at MAYA's
    login page (by way of Keycloak when single logout is on)."""
    page.evaluate("document.querySelector(\"form[action='/logout']\").submit()")
    page.wait_for_url(re.compile(r"^http://127\.0\.0\.1:\d+/login"))
    page.wait_for_load_state("networkidle")


# -- OIDC -------------------------------------------------------------------------------
def test_oidc_sign_in_through_keycloak_maps_groups_to_roles(oidc, page):
    _, maya = oidc
    assert _sso_login(page, maya)
    assert page.url == f"{maya.url}/"
    assert _signed_in_as(page, maya) == (ALICE, ["admin", "model_manager"])


def test_oidc_person_in_no_mapped_group_is_refused(oidc, page):
    _, maya = oidc
    _sso_login(page, maya, BOB, BOB_PW)
    assert "None of your identity-provider groups maps to a MAYA role" in page.content()
    assert _signed_in_as(page, maya) is None


def test_oidc_sign_out_ends_the_keycloak_session_too(oidc, page):
    """RP-initiated logout: MAYA ends its session and sends the browser to Keycloak's
    end-session endpoint, which (asked to confirm, as Keycloak does without an ID token
    hint) ends its own and returns to MAYA; the next sign-in asks for the password."""
    r, maya = oidc
    _sso_login(page, maya)
    before = r.sessions(r.alice)  # earlier tests' browsers keep their own sessions
    page.evaluate("document.querySelector(\"form[action='/logout']\").submit()")
    page.wait_for_url(re.compile(re.escape(r.issuer)))
    page.click("#kc-logout")
    page.wait_for_url(re.compile(r"^http://127\.0\.0\.1:\d+/login"))
    assert _signed_in_as(page, maya) is None
    assert r.sessions(r.alice) == before - 1, "this browser's Keycloak session ended"
    assert _sso_login(page, maya), "Keycloak's session ended: it asks for the password"


def test_oidc_keycloak_admin_sign_out_reaches_maya_by_back_channel(oidc, page):
    """Ending this sign-in's session in Keycloak's admin console POSTs a signed logout
    token (naming the session's sid) to MAYA, server to server; the MAYA session ends
    with no browser involved. (Keycloak 26.4's "sign out all sessions" of a user sent a
    token for one of the user's sessions only; the security guide records that.)"""
    r, maya = oidc
    _sso_login(page, maya)
    assert _signed_in_as(page, maya)
    r.end_latest_session(r.alice)
    for _ in range(20):
        if _signed_in_as(page, maya) is None:
            break
        time.sleep(0.5)
    assert _signed_in_as(page, maya) is None


# -- SAML 2.0 ---------------------------------------------------------------------------
def test_saml_sign_in_with_signed_request_maps_repeated_group_attributes(saml, page):
    """Keycloak sends one ``groups`` element per group and one ``Role`` per role."""
    _, maya = saml
    assert _sso_login(page, maya)
    assert page.url == f"{maya.url}/"
    assert _signed_in_as(page, maya) == (ALICE, ["admin", "model_manager"])


def test_saml_sign_out_follows_single_logout_through_keycloak(saml, page):
    r, maya = saml
    _sso_login(page, maya)
    _sign_out_of_maya(page)
    assert page.url == f"{maya.url}/login?signed_out=1"
    assert "signed out of MAYA and of your identity provider" in page.content()
    assert _signed_in_as(page, maya) is None
    assert _sso_login(page, maya), "Keycloak's session ended too: it asks for the password"


def test_saml_keycloak_front_channel_logout_ends_the_maya_session(saml, page):
    """Ending the Keycloak session in the browser (its end-session page) sends the
    browser through MAYA's SLS with a signed LogoutRequest."""
    r, maya = saml
    _sso_login(page, maya)
    assert _signed_in_as(page, maya)
    page.goto(f"{r.issuer}/protocol/openid-connect/logout")
    page.click("#kc-logout")
    page.wait_for_url(re.compile(r"/protocol/saml\?SAMLResponse="))  # back from MAYA's SLS
    page.wait_for_load_state("networkidle")
    assert _signed_in_as(page, maya) is None


def test_saml_admin_sign_out_does_not_reach_maya(saml, page):
    """The admin console's "Sign out" is back-channel; MAYA's SLS is front-channel
    (redirect binding) only, so the MAYA session lasts until its own timeout or
    sign-out. Documented, not hidden."""
    r, maya = saml
    _sso_login(page, maya)
    r.admin_sign_out(r.alice)
    assert r.sessions(r.alice) == 0
    assert _signed_in_as(page, maya) == (ALICE, ["admin", "model_manager"])
    _sign_out_of_maya(page)  # Keycloak still answers MAYA's LogoutRequest
    assert page.url == f"{maya.url}/login?signed_out=1"
