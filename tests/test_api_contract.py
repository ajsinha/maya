"""
The API contract, endpoint by endpoint (§18.1): every route in the OpenAPI
document is exercised as an anonymous caller, as a signed-in user with no role,
and as an administrator — with a body that passes schema validation, with none,
and with bytes that are not JSON. The rules asserted:

* anonymous callers get 401 everywhere but the four sign-in routes;
* nothing answers 5xx, whoever calls and whatever they send;
* every error is an RFC 9457 problem document whose status matches the response;
* malformed JSON is 422, never a crash;
* a role-less user writes nothing but their own session, keys, MFA, inbox and
  workspaces, and is refused (403) by every administrative route;
* an unknown object is 404, not an empty success.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import pytest

from tests._contract import PREFIX, call, concrete, endpoints
from tests.conftest import PASSWORD, World, build_platform

# Sign-in is necessarily reachable before signing in.
PUBLIC = {("POST", "/auth/login"), ("GET", "/auth/sso/config"), ("POST", "/auth/sso/start"),
          ("POST", "/auth/sso/callback"),
          # SAML sign-in: the IdP's POST carries no session, and metadata is public by design
          ("POST", "/auth/sso/saml/start"), ("POST", "/auth/sso/saml/acs"),
          ("GET", "/auth/sso/saml/metadata")}
# A never-ending server-sent stream: covered by its own test below, not the sweep.
STREAMING = {("GET", "/events/stream")}
# Writes any signed-in person may make on their own behalf, or that change nothing shared.
SELF_SERVICE = {("POST", "/auth/api-keys"), ("POST", "/auth/logout"),
                ("POST", "/auth/mfa/webauthn/register/options"),
                ("POST", "/auth/mfa/webauthn/register"),
                ("DELETE", "/auth/mfa/webauthn/{key_id}"),
                ("POST", "/auth/mfa/enroll"), ("POST", "/features/infer"),
                ("POST", "/inbox/read"), ("POST", "/workspaces"),
                # a campaign authorizes each item's transition separately; with no
                # permission on anything, it records only failures
                ("POST", "/workflow/campaigns")}
ADMIN_ONLY = {
    ("GET", "/audit"), ("GET", "/auth/sessions"), ("DELETE", "/auth/sessions/{session_id}"),
    ("POST", "/custody/anchor"), ("GET", "/custody/anchors"), ("GET", "/custody/verify"),
    ("GET", "/events"), ("POST", "/groups"), ("POST", "/namespaces"),
    ("PATCH", "/namespaces/{name}"), ("POST", "/roles"), ("POST", "/sql-connections"),
    ("DELETE", "/sql-connections/{name}"), ("POST", "/sql-connections/{name}/test"),
    ("GET", "/system/config"), ("GET", "/system/estate"), ("POST", "/system/integrity"),
    ("POST", "/users"), ("PATCH", "/users/{username}"),
    ("POST", "/users/{username}/mfa-reset"), ("POST", "/users/{username}/password-reset"),
    ("PUT", "/users/{username}/roles"), ("GET", "/webhooks"), ("POST", "/webhooks"),
    ("DELETE", "/webhooks/{webhook_id}"), ("GET", "/webhooks/{webhook_id}/deliveries"),
    ("POST", "/webhooks/{webhook_id}/ping"), ("POST", "/workflow/policies"),
    ("POST", "/workflow/policies/{policy_id}/activate"),
}


@pytest.fixture(scope="module")
def api():
    from starlette.testclient import TestClient

    from maya.api.app import create_api
    platform = build_platform(["--observability.webhooks.allow_private=true"])
    w = World(platform)
    platform.access.create_user(w.admin, username="nobody", password=PASSWORD, roles=[])
    app = create_api(platform)
    client = TestClient(app, raise_server_exceptions=False)

    def login(username: str, password: str) -> dict[str, str]:
        r = client.post(f"{PREFIX}/auth/login", json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['token']}"}

    yield app, client, login
    platform.shutdown()


def _sweep(api):
    app, _, _ = api
    return [(m, p, op) for m, p, op in endpoints(app)
            if (m, p[len(PREFIX):]) not in STREAMING]


def _problem(r, who: str, method: str, path: str) -> None:
    assert r.status_code < 500, (who, method, path, r.status_code, r.text[:300])
    if r.status_code >= 400:
        doc = r.json()
        assert doc.get("status") == r.status_code and doc.get("type"), (who, method, path, doc)


def test_the_sweep_covers_every_endpoint(api):
    app, _, _ = api
    paths = {(m, p[len(PREFIX):]) for m, p, _ in endpoints(app)}
    assert len(paths) >= 150
    for name, table in (("PUBLIC", PUBLIC), ("SELF_SERVICE", SELF_SERVICE),
                        ("ADMIN_ONLY", ADMIN_ONLY), ("STREAMING", STREAMING)):
        assert table <= paths, (name, sorted(table - paths))


def test_anonymous_callers_are_refused_everywhere_but_sign_in(api):
    app, client, _ = api
    wrong = []
    for m, p, op in _sweep(api):
        r = call(client, app, m, p, op)
        _problem(r, "anonymous", m, p)
        if (m, p[len(PREFIX):]) not in PUBLIC and r.status_code != 401:
            wrong.append((m, p, r.status_code))
    assert not wrong, wrong
    stream = client.get(f"{PREFIX}/events/stream")
    assert stream.status_code == 401


def test_nothing_answers_5xx_and_errors_are_problem_documents(api):
    app, client, login = api
    for who, creds in (("nobody", ("nobody", PASSWORD)), ("admin", ("admin", "maya-dev-admin"))):
        for m, p, op in _sweep(api):
            headers = login(*creds)                  # fresh: a logout in the sweep ends it
            _problem(call(client, app, m, p, op, headers), who, m, p)
            _problem(call(client, app, m, p, op, headers, with_body=False), who + " (no body)", m, p)


def test_malformed_json_is_422_on_every_json_endpoint(api):
    app, client, login = api
    checked = 0
    for m, p, op in _sweep(api):
        if "application/json" not in (op.get("requestBody") or {}).get("content", {}):
            continue
        headers = {**login("admin", "maya-dev-admin"), "Content-Type": "application/json"}
        r = client.request(m, concrete(p), headers=headers, content=b"{not json")
        assert r.status_code == 422, (m, p, r.status_code, r.text[:200])
        checked += 1
    assert checked >= 50


def test_a_roleless_user_writes_only_on_their_own_behalf(api):
    app, client, login = api
    wrote = []
    for m, p, op in _sweep(api):
        if m == "GET" or (m, p[len(PREFIX):]) in SELF_SERVICE:
            continue
        r = call(client, app, m, p, op, login("nobody", PASSWORD))
        if r.status_code < 300:
            wrote.append((m, p, r.status_code))
    assert not wrote, wrote


def test_every_administrative_route_refuses_a_roleless_user(api):
    app, client, login = api
    ops = {(m, p[len(PREFIX):]): op for m, p, op in endpoints(app)}
    wrong = []
    for m, p in sorted(ADMIN_ONLY):
        r = call(client, app, m, PREFIX + p, ops[(m, p)], login("nobody", PASSWORD))
        if r.status_code != 403:
            wrong.append((m, p, r.status_code, r.text[:120]))
    assert not wrong, wrong


OBJECT_GETS = [
    "/features/{namespace}/{name}", "/featuresets/{namespace}/{name}",
    "/models/{namespace}/{name}", "/warrants/training/{warrant_id}",
    "/warrants/execution/{ew_id}", "/jobs/{job_id}", "/workspaces/{ws_id}",
    "/workspaces/{ws_id}/impact", "/webhooks/{webhook_id}/deliveries",
    "/workflow/policies/{policy_id}",
]


@pytest.mark.parametrize("path", OBJECT_GETS)
def test_an_unknown_object_is_404_not_an_empty_success(api, path):
    app, client, login = api
    ops = {(m, p[len(PREFIX):]): op for m, p, op in endpoints(app)}
    assert ("GET", path) in ops, path
    r = call(client, app, "GET", PREFIX + path, ops[("GET", path)],
             login("admin", "maya-dev-admin"))
    assert r.status_code == 404, (path, r.status_code, r.text[:200])
    assert r.json()["type"] == "not_found"


def test_unknown_workflow_object_types_are_refused_by_name(api):
    _, client, login = api
    h = login("admin", "maya-dev-admin")
    r = client.get(f"{PREFIX}/workflow/population/spaceship", headers=h)
    assert r.status_code == 422 and "feature_version" in r.text
    r = client.post(f"{PREFIX}/workflow/comments", headers=h,
                    json={"object_type": "spaceship", "object_id": "x", "body": "hello"})
    assert r.status_code == 422


def test_the_user_directory_hides_account_security_state_from_non_admins(api):
    _, client, login = api
    rows = client.get(f"{PREFIX}/users", headers=login("nobody", PASSWORD)).json()
    assert rows and all(set(r) == {"id", "username", "display_name", "status"} for r in rows)
    full = client.get(f"{PREFIX}/users", headers=login("admin", "maya-dev-admin")).json()
    admin = next(r for r in full if r["username"] == "admin")
    assert "failed_attempts" in admin and "roles" in admin
    assert not any("password_hash" in r or "mfa_secret" in r for r in full)
