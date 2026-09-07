"""Administering people, from the screen rather than from curl.

`/admin/principals` listed everybody — roles, scope, effective permissions,
incompatible pairs — and then named the five endpoints you had to run by hand.
Every other admin screen reads state a person does not create: a rulebook, a
batch, a hash chain, a fibre. Administering *people* is different. It is the one
thing an operations manager does daily, this platform's own persona for that job
is the administrator, and a governance platform whose administrator cannot
administer it from the interface is one where somebody keeps a shell script —
which is where the second account for a forgotten password comes from.

The screen decides nothing. Every act goes through the same API a script would,
with the same authorisation, the same incompatible-roles check and the same
evidence.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from tests.api_helpers import login as _login

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "web" / "templates" / "admin_principals.html"
SCRIPT = ROOT / "web" / "static" / "js" / "admin-principals.js"


class TestTheScreenCanActuallyDoIt:

    def test_an_administrator_is_offered_the_form(self, client):
        _login(client)
        body = client.get("/admin/principals").text
        assert 'id="new-principal"' in body
        for act in ("edit-roles", "set-password", "suspend"):
            assert act in body, act

    def test_somebody_without_the_permission_is_offered_none_of_it(self, client):
        client.post("/api/v1/principals", json={
            "username": "reader", "display_name": "Reader",
            "roles": ["auditor"], "password": "pw-long-enough-x"})
        _login(client, "reader", "pw-long-enough-x")
        body = client.get("/admin/principals").text
        assert 'id="new-principal"' not in body
        assert "edit-roles" not in body
        assert "needs <span class=\"mono\">principal:manage</span>" in body

    def test_the_page_loads_its_client(self, client):
        _login(client)
        assert "/static/js/admin-principals.js" in client.get(
            "/admin/principals").text
        assert client.get("/static/js/admin-principals.js").status_code == 200

    def test_the_scope_fields_offer_what_the_estate_contains(self, registered,
                                                             client):
        """A free-typed `LE-UK-2` beside an existing `LE-UK-02` is a scope that
        silently reaches nothing."""
        _login(client)
        body = registered.get("/admin/principals").text
        assert '<datalist id="entities-in-use">' in body
        assert "LE-US-01" in body and "credit" in body


class TestTheScreenDecidesNothing:
    """The whole argument for it being a client: a screen that re-implemented a
    governance check would be a second implementation, and it disagrees with the
    first eventually, in the direction of permitting more."""

    def test_it_holds_no_role_list_of_its_own(self):
        """The roles come from the register, so a role added to the platform
        appears here without anybody editing a template."""
        page = PAGE.read_text(encoding="utf-8")
        assert "{% for r in roles %}" in page
        # Prose may name a role — the page explains why a validator who may
        # also approve is not performing effective challenge. What it may not
        # do is carry the LIST, as a value or an option somebody typed.
        for invented in ("model_developer", "validator", "auditor",
                         "model_risk_manager"):
            for hard_coded in (f'value="{invented}"', f">{invented}<"):
                assert hard_coded not in page, \
                    f"'{hard_coded}' is written into the page rather than read"

    def test_the_role_list_comes_from_the_register(self, client):
        """Roles moved out of a Python dictionary so a bank could define one.
        A page that then rendered its own list would have undone that."""
        from tests.api_helpers import login

        # Defined BEFORE signing in: once a session cookie exists the CSRF
        # guard refuses a POST without a token, which is the guard working.
        made = client.post("/api/v1/roles", json={
            "name": "regional_mrm", "description": "MRM for one region",
            "permissions": ["model:read", "report:read"]})
        assert made.status_code == 201, made.text
        login(client)
        body = client.get("/admin/principals").text
        assert "regional_mrm" in body, \
            "a role defined through the API appears without editing a template"

    def test_a_built_in_role_is_offered_no_controls(self, client):
        from tests.api_helpers import login

        login(client)
        body = client.get("/admin/principals").text
        assert "built in" in body
        # `validator` ships; the remove control must not be offered for it.
        row = body.split(">validator<")[1][:600] if ">validator<" in body else ""
        assert "remove-role" not in row

    def test_the_client_holds_no_incompatible_pairs(self):
        """Comments may explain the check; code may not repeat it."""
        script = SCRIPT.read_text(encoding="utf-8")
        code = re.sub(r"/\*.*?\*/|//[^\n]*", "", script, flags=re.S)
        for role in ("model_developer", "model_risk_manager", "validator",
                     "auditor", "model_owner"):
            assert role not in code, f"'{role}' is named in the client's code"
        # It reads the server's refusal code rather than deciding for itself.
        assert 'r.code !== "incompatible_roles"' in script

    def test_every_act_goes_through_the_api(self):
        script = SCRIPT.read_text(encoding="utf-8")
        urls = set(re.findall(r'"(/api/v1/[^"]*)"', script))
        assert urls, "the client posts to nothing"
        # People and roles, which is what this screen is called and what it
        # administers. Anything else here would be a second screen wearing this
        # one's name.
        assert all(u.startswith(("/api/v1/principals", "/api/v1/roles"))
                   for u in urls), urls

    def test_it_reads_refusals_through_the_one_reader(self):
        """The `[object Object]` fix applies here too, and this is a new screen
        — which is exactly where a tenth copy would have appeared."""
        assert "MAYA.refusal.read" in SCRIPT.read_text(encoding="utf-8")


class TestTheApiStillRefusesWhatItRefused:
    """The screen being able to ask does not mean the platform has to answer."""

    def test_an_incompatible_pair_is_still_refused(self, client, people):
        r = client.post("/api/v1/principals", json={
            "username": "two.hats", "display_name": "Two Hats",
            "roles": ["model_developer", "validator"], "password": "pw-long-enough-x"})
        assert r.status_code == 409
        assert r.json()["error"] == "incompatible_roles"
        assert "effective challenge" in r.json()["detail"]

    def test_and_can_be_granted_as_a_recorded_exception(self, client):
        r = client.post("/api/v1/principals", json={
            "username": "two.hats", "display_name": "Two Hats",
            "roles": ["model_developer", "validator"], "password": "pw-long-enough-x",
            "allow_conflicts": True})
        assert r.status_code == 201, r.text

    def test_a_reader_may_not_create_anybody(self, client, people):
        r = client.post("/api/v1/principals", auth=people["a.mehta"], json={
            "username": "x", "display_name": "X", "roles": ["auditor"]})
        assert r.status_code == 403

    @pytest.mark.parametrize("path,method", [
        ("/api/v1/principals/j.okafor/roles", "put"),
        ("/api/v1/principals/j.okafor/suspend", "post"),
        ("/api/v1/principals/j.okafor/password", "post"),
    ])
    def test_every_act_the_screen_offers_needs_the_permission(
            self, client, people, path, method):
        body = {"roles": ["auditor"]} if path.endswith("roles") else \
            ({"password": "x" * 12} if path.endswith("password") else {})
        r = getattr(client, method)(path, auth=people["a.mehta"], json=body)
        assert r.status_code == 403, f"{path} -> {r.status_code}"
