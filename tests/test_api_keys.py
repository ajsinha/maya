"""How a service authenticates without a password.

A service principal signing in over HTTP Basic has three problems a key does
not. The password is a shared secret somebody typed and can retype elsewhere; it
carries **every** permission the principal holds, for as long as the account
exists; and rotating it means changing it in the register and in whatever holds
it at the same instant, or something stops working.
"""
from __future__ import annotations

import time

import pytest

from core.apikeys import MAX_LIFETIME_DAYS, PREFIX


def _with_key(client, secret, header="X-API-Key"):
    """A request carrying ONLY the key.

    The `client` fixture sends admin Basic credentials on every request, and
    `principal()` tries a session, then Basic, then a key — so a test that adds
    a key header to that client is testing the admin, and would pass with the
    key mechanism removed entirely.
    """
    return {header: secret, "Authorization": ""} if header != "Authorization" \
        else {"Authorization": f"Bearer {secret}"}


def _age(client, key_id, expires_at):
    """Move a key's expiry, through the app's own database.

    The `db` fixture is an in-memory database and the application's is
    file-backed: two databases, and writing to the first would leave the second
    exactly as it was — which is a test that passes while checking nothing.
    """
    client.app.state.ctx["api_keys"].repo.set({"expires_at": expires_at},
                                              id=key_id)


def _issue(client, username="svc.batch", name="nightly-scoring", **kw):
    body = {"username": username, "name": name, **kw}
    return client.post("/api/v1/api-keys", json=body)


@pytest.fixture
def keyed(client):
    """The same application, reached without the fixture's admin credentials."""
    from starlette.testclient import TestClient

    with TestClient(client.app) as bare:
        yield bare


@pytest.fixture
def service(client):
    client.post("/api/v1/principals", json={
        "username": "svc.batch", "display_name": "Nightly batch",
        "kind": "service", "roles": ["service"]})
    return "svc.batch"


class TestTheSecretIsShownOnce:

    def test_it_comes_back_at_creation_and_never_again(self, client, service):
        made = _issue(client)
        assert made.status_code == 201, made.text
        secret = made.json()["secret"]
        assert secret.startswith(PREFIX)
        listed = client.get("/api/v1/api-keys",
                            params={"username": service}).json()["keys"]
        assert listed and "secret" not in listed[0]
        assert listed[0]["prefix"].endswith("…")
        assert secret not in str(listed)

    def test_the_evidence_records_the_issue_and_not_the_secret(self, client,
                                                               service):
        secret = _issue(client).json()["secret"]
        nodes = client.app.state.ctx["evidence"].repo.many()
        issued = [n for n in nodes if n["kind"] == "api_key_issued"]
        assert issued, "the issue is on the chain"
        assert secret not in str(nodes), \
            "and the secret is not, anywhere on it"

    def test_a_prefix_is_enough_to_match_a_leaked_string(self, client, service):
        """Without holding either: it is the first characters, in clear."""
        secret = _issue(client).json()["secret"]
        listed = client.get("/api/v1/api-keys",
                            params={"username": service}).json()["keys"][0]
        assert secret.startswith(listed["prefix"].rstrip("…"))
        assert len(listed["prefix"]) < len(secret) / 2


class TestItAuthenticates:

    def test_as_a_bearer_token(self, client, keyed, service):
        secret = _issue(client).json()["secret"]
        r = keyed.get("/api/v1/me",
                      headers={"Authorization": f"Bearer {secret}"})
        assert r.status_code == 200 and r.json()["username"] == service

    def test_and_as_x_api_key(self, client, keyed, service):
        """Both, because both are what people actually send: `Bearer` is what a
        client library defaults to and `X-API-Key` is what a curl line looks
        like. Accepting one and not the other buys nothing."""
        secret = _issue(client).json()["secret"]
        r = keyed.get("/api/v1/me", headers={"X-API-Key": secret})
        assert r.status_code == 200

    def test_a_wrong_key_is_refused(self, client, keyed, service):
        r = keyed.get("/api/v1/me",
                      headers={"X-API-Key": PREFIX + "not-a-real-key"})
        assert r.status_code == 401

    def test_a_revoked_key_stops_working(self, client, keyed, service):
        made = _issue(client).json()
        secret = made["secret"]
        assert keyed.get("/api/v1/me",
                         headers={"X-API-Key": secret}).status_code == 200
        client.post(f"/api/v1/api-keys/{made['id']}/revoke",
                    json={"reason": "rotated"})
        assert keyed.get("/api/v1/me",
                         headers={"X-API-Key": secret}).status_code == 401

    def test_suspending_the_principal_stops_every_key_it_issued(
            self, client, keyed, service):
        """Checked at USE, against what the principal holds now — so a
        suspension reaches every key without anybody remembering to revoke
        them."""
        secret = _issue(client).json()["secret"]
        client.post(f"/api/v1/principals/{service}/suspend")
        assert keyed.get("/api/v1/me",
                         headers={"X-API-Key": secret}).status_code == 401

    def test_use_is_recorded_so_an_unused_key_is_visible(self, client, keyed,
                                                         service):
        made = _issue(client).json()
        keyed.get("/api/v1/me", headers={"X-API-Key": made["secret"]})
        row = client.get("/api/v1/api-keys",
                         params={"username": service}).json()["keys"][0]
        assert row["use_count"] >= 1 and row["last_used_at"]
        assert not row["never_used"]


class TestAKeyNarrowsAndNeverWidens:

    def test_a_scoped_key_is_refused_outside_its_scope(self, client, keyed,
                                                       people):
        client.post("/api/v1/principals", json={
            "username": "svc.reader", "display_name": "Reader",
            "kind": "service", "roles": ["operator"]})
        made = _issue(client, username="svc.reader", name="read-only",
                      scopes=["model:read"]).json()
        headers = {"X-API-Key": made["secret"]}
        assert keyed.get("/api/v1/models", headers=headers).status_code == 200
        # An act needing no subject, so the refusal is about the key's scope
        # rather than about a monitor that does not exist: `svc.reader` holds
        # `evidence:read` and this key does not.
        r = keyed.get("/api/v1/evidence/chain", headers=headers)
        assert r.status_code == 403
        assert r.json()["error"] == "outside_key_scope"
        assert "svc.reader" in r.json()["detail"], \
            "say that the principal holds it and the key does not"

    def test_a_key_may_not_carry_what_its_principal_lacks(self, client, service):
        r = _issue(client, name="too-wide", scopes=["principal:manage"])
        assert r.status_code == 422
        assert r.json()["error"] == "scope_exceeds_principal"
        assert "decision about accountability" in r.json()["remediation"]

    def test_an_unscoped_key_carries_what_the_principal_holds(self, client,
                                                             service):
        made = _issue(client).json()
        assert made["scopes"] == []
        assert made["scope_detail"] == "everything the principal holds"


class TestEveryKeyExpires:

    def test_a_lifetime_beyond_the_maximum_is_refused(self, client, service):
        r = _issue(client, name="forever", lifetime_days=MAX_LIFETIME_DAYS + 1)
        assert r.status_code == 422
        assert "credential nobody ever reviews" in r.json()["detail"]

    def test_an_expired_key_stops_working(self, client, keyed, service):
        made = _issue(client).json()
        _age(client, made["id"], time.time() - 1)
        assert keyed.get("/api/v1/me",
                         headers={"X-API-Key": made["secret"]}).status_code == 401

    def test_the_report_names_what_needs_looking_at(self, client, service):
        made = _issue(client).json()
        _age(client, made["id"], time.time() + 5 * 86400)
        report = client.get("/api/v1/api-keys").json()
        assert report["active"] == 1
        assert [k["name"] for k in report["expiring_soon"]] == ["nightly-scoring"]
        assert [k["name"] for k in report["never_used"]] == ["nightly-scoring"]


class TestIssuingAndRevoking:

    def test_a_key_needs_a_name_saying_what_holds_it(self, client, service):
        r = _issue(client, name="  ")
        assert r.status_code == 422
        assert "list nobody can safely revoke from" in r.json()["detail"]

    def test_two_keys_may_not_share_a_name(self, client, service):
        _issue(client)
        assert _issue(client).status_code == 409

    def test_rotation_is_two_keys_briefly(self, client, keyed, service):
        """There is no swap: issue the new one, move the caller, revoke the
        old. A rotation that is one atomic act has a window in which nothing
        works."""
        old = _issue(client, name="v1").json()
        new = _issue(client, name="v2").json()
        headers = {"X-API-Key": old["secret"]}
        assert keyed.get("/api/v1/me", headers=headers).status_code == 200
        client.post(f"/api/v1/api-keys/{old['id']}/revoke",
                    json={"reason": "rotated to v2"})
        assert keyed.get("/api/v1/me", headers=headers).status_code == 401
        assert keyed.get("/api/v1/me",
                         headers={"X-API-Key": new["secret"]}).status_code == 200

    def test_revoking_needs_a_reason(self, client, service):
        made = _issue(client).json()
        r = client.post(f"/api/v1/api-keys/{made['id']}/revoke",
                        json={"reason": " "})
        assert r.status_code == 422
        assert "indistinguishable from one during a tidy-up" in r.json()["detail"]

    def test_a_revoked_key_stays_on_the_list(self, client, service):
        """The row is what says the key existed, who issued it and when it
        stopped."""
        made = _issue(client).json()
        client.post(f"/api/v1/api-keys/{made['id']}/revoke",
                    json={"reason": "leaked in a ticket"})
        rows = client.get("/api/v1/api-keys",
                          params={"username": service}).json()["keys"]
        assert len(rows) == 1 and rows[0]["state"] == "revoked"
        assert rows[0]["revoke_reason"] == "leaked in a ticket"

    def test_a_key_for_a_suspended_principal_is_refused_at_issue(self, client,
                                                                 service):
        client.post(f"/api/v1/principals/{service}/suspend")
        r = _issue(client, name="sneaky")
        assert r.status_code == 409
        assert "way around the suspension" in r.json()["detail"]

    def test_issuing_needs_principal_manage(self, client, service, people):
        r = client.post("/api/v1/api-keys", auth=people["a.mehta"],
                        json={"username": service, "name": "mine"})
        assert r.status_code == 403


class TestTheHashing:

    def test_the_stored_value_is_not_the_key(self, client, service):
        secret = _issue(client).json()["secret"]
        rows = client.app.state.ctx["api_keys"].repo.db.query(
            "SELECT key_hash FROM api_key")
        assert rows and rows[0]["key_hash"] != secret
        assert len(rows[0]["key_hash"]) == 64, "a sha256 hex digest"

    def test_the_entropy_is_where_the_strength_is(self):
        """A fast hash is right here and wrong for a password. The key is 256
        bits from `secrets.token_urlsafe`, so there is no dictionary to attack;
        a password is something a person chose, and `principals.py` uses PBKDF2
        for exactly that reason."""
        from core.apikeys.register import ENTROPY_BYTES

        assert ENTROPY_BYTES >= 32
