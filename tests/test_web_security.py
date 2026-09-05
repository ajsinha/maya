"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The two things a browser-facing surface gets wrong, and did.

**The open redirect was live.** `POST /login` honoured whatever `next` carried,
so `/login?next=https://evil.example/phish` sent the browser there immediately
after somebody typed real credentials into the real form on the real domain.
That is the whole of a credential-phishing attack, and the redirect is the part
that makes the link look legitimate. The same door was open a second time on the
single sign-on path, where the target survived a round trip through the identity
provider before being followed.

**CSRF had one defence, implemented by somebody else.** The session cookie is
`SameSite=Strict`, which is real and is enforced by the browser — a client that
does not implement it, or an intermediary that strips the attribute, takes the
control away and its removal is invisible from here. These tests fix the
boundary the token applies to, which is the part worth getting right: ambient
cookie authority, and nothing else.
"""
from __future__ import annotations

import re

import pytest

from core.authz import csrf
from routes.base import local_path

TOKEN = re.compile(r'name="csrf-token" content="([^"]+)"')

MODEL = {"urn": "maya://model/probe.one", "name": "Probe",
         "model_class": "credit.pd.scorecard", "domain": "credit",
         "owner": "person/admin", "legal_entity": "LE-1", "purpose": "p"}


@pytest.fixture
def browser(client):
    """A client authenticated the way a browser is: a session cookie, no header."""
    client.post("/login", data={"username": "admin", "password": "admin123"},
                follow_redirects=False)
    client.headers.pop("Authorization", None)
    return client


def token_of(browser) -> str:
    return TOKEN.search(browser.get("/dashboard").text).group(1)


class TestARedirectTargetIsAPathOrNothing:
    @pytest.mark.parametrize("hostile", [
        "https://evil.example/phish",
        "http://evil.example",
        "//evil.example",                      # protocol-relative
        "/\\evil.example",                     # backslash, normalised by browsers
        "\\\\evil.example",
        "javascript:alert(1)",
        "  https://evil.example",              # leading space, stripped by browsers
        "/\tevil.example" .replace("evil", "//evil"),
        "",
    ])
    def test_a_foreign_target_becomes_the_fallback(self, hostile):
        assert local_path(hostile) == "/dashboard"

    @pytest.mark.parametrize("ours", [
        "/dashboard", "/model/credit.pd.smallbiz", "/features?page=2",
        "/help/warrants#the-four-axes",
    ])
    def test_our_own_paths_are_kept_exactly(self, ours):
        assert local_path(ours) == ours

    def test_it_is_replaced_rather_than_repaired(self):
        """A target somebody had to sanitise is a target nobody understands."""
        assert local_path("https://evil.example/dashboard") == "/dashboard"

    def test_the_login_form_no_longer_redirects_off_site(self, client):
        r = client.post("/login", follow_redirects=False,
                        data={"username": "admin", "password": "admin123",
                              "next": "https://evil.example/phish"})
        assert r.status_code == 303
        assert r.headers["location"] == "/dashboard"

    def test_a_local_next_still_works(self, client):
        r = client.post("/login", follow_redirects=False,
                        data={"username": "admin", "password": "admin123",
                              "next": "/features"})
        assert r.headers["location"] == "/features"


class TestTheTokenAppliesToAmbientAuthorityOnly:
    """The boundary is the design. Everything else here is ordinary."""

    def test_a_cookie_authenticated_mutation_without_a_token_is_refused(self, browser):
        r = browser.post("/api/v1/models", json=MODEL)
        assert r.status_code == 403
        assert r.json()["error"] == "csrf_token_invalid"
        assert "HTTP Basic" in r.json()["remediation"]

    def test_the_same_call_with_the_page_token_succeeds(self, browser):
        r = browser.post("/api/v1/models", json=MODEL,
                         headers={csrf.HEADER: token_of(browser)})
        assert r.status_code == 201, r.text

    def test_a_wrong_token_is_refused(self, browser):
        r = browser.post("/api/v1/models", json=MODEL,
                         headers={csrf.HEADER: "not-the-token"})
        assert r.status_code == 403

    def test_basic_credentials_need_no_token(self, client):
        """A caller who can set an Authorization header already holds the
        credential; asking for a token as well protects nothing and breaks every
        engine and script — which is how a control ends up switched off."""
        r = client.post("/api/v1/models", json=MODEL)
        assert r.status_code == 201, r.text

    def test_reading_needs_no_token(self, browser):
        assert browser.get("/api/v1/models").status_code == 200

    def test_signing_in_needs_no_token(self, client):
        """A sign-in form has no session to carry a token from, so requiring one
        would fail the first request of every visit."""
        r = client.post("/login", follow_redirects=False,
                        data={"username": "admin", "password": "admin123"})
        assert r.status_code == 303


class TestTheTokenReachesThePages:
    def test_every_page_carries_it(self, browser):
        for path in ("/dashboard", "/models/new", "/features", "/policies"):
            page = browser.get(path)
            assert page.status_code == 200, path
            assert TOKEN.search(page.text), f"{path} has no csrf-token meta tag"

    def test_it_is_stable_within_a_session(self, browser):
        """Rotating per form would break the back button, two tabs, and every
        page here that posts more than once — and a control people route around
        is worse than one they never had, because it also reports success."""
        assert token_of(browser) == token_of(browser)

    def test_the_hook_is_vendored_and_loaded(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parent.parent
        assert (root / "web" / "static" / "js" / "csrf.js").exists()
        assert "csrf.js" in (root / "web" / "templates" / "base.html").read_text()


class TestTheComparison:
    def test_it_is_constant_time(self):
        """A byte-by-byte comparison on a secret leaks its prefix through
        timing. Thin over HTTP, free to close, and this is the one place the
        codebase compares a secret."""
        import inspect
        assert "compare_digest" in inspect.getsource(csrf.matches)

    def test_an_absent_token_never_matches(self):
        assert not csrf.matches(None, "x")
        assert not csrf.matches("x", None)
        assert not csrf.matches("", "")

    def test_exemptions_are_exact_paths_rather_than_prefixes(self):
        """A prefix exemption grows silently as routes are added beneath it."""
        assert all(not p.endswith("*") for p in csrf.EXEMPT_PATHS)
        assert "/api/v1" not in csrf.EXEMPT_PATHS
