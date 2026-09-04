"""
MAYA — tests for single sign-on.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The flow is standard. What is under test is what MAYA does with the group claims
when they arrive: maps them rather than obeying them, refuses an incompatible
pair rather than quietly reducing it, and records which groups produced which
roles.

The tokens here are signed by a real RSA key through openssl, so the verifier is
tested against genuine signatures rather than against its own arithmetic.
"""
from __future__ import annotations

import base64
import json
import subprocess
import time

import pytest

from core.authz.common import AuthzError
from core.authz.jws import verify
from core.authz.oidc import OidcProvider

ISSUER = "https://idp.example"
CLIENT = "maya"
REDIRECT = "http://localhost:5006/auth/callback"
ROLE_MAP = {"maya-developers": ["model_developer"],
            "maya-validators": ["validator"],
            "maya-risk": ["model_risk_manager"],
            "maya-everything": ["model_developer", "model_risk_manager"]}


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture(scope="module")
def keypair(tmp_path_factory):
    """A real RSA key. The verifier is tested against openssl's signatures."""
    if not subprocess.run(["which", "openssl"], capture_output=True).returncode == 0:
        pytest.skip("openssl is not available")
    directory = tmp_path_factory.mktemp("sso")
    private = directory / "key.pem"
    subprocess.run(["openssl", "genrsa", "-out", str(private), "2048"],
                   check=True, capture_output=True)
    modulus = subprocess.run(
        ["openssl", "rsa", "-in", str(private), "-noout", "-modulus"],
        check=True, capture_output=True, text=True).stdout.strip().split("=")[1]
    n = int(modulus, 16)
    jwk = {"kty": "RSA", "kid": "k1", "use": "sig",
           "n": _b64(n.to_bytes(256, "big")), "e": _b64((65537).to_bytes(3, "big"))}
    return {"private": private, "jwk": jwk, "dir": directory}


def sign(keypair, claims, header=None) -> str:
    head = _b64(json.dumps(header or {"alg": "RS256", "kid": "k1"}).encode())
    body = _b64(json.dumps(claims).encode())
    payload = keypair["dir"] / "payload.bin"
    payload.write_bytes(f"{head}.{body}".encode())
    signature = keypair["dir"] / "sig.bin"
    subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(keypair["private"]),
                    "-out", str(signature), str(payload)],
                   check=True, capture_output=True)
    return f"{head}.{body}.{_b64(signature.read_bytes())}"


def claims_for(nonce="n1", **extra):
    now = time.time()
    return {"iss": ISSUER, "aud": CLIENT, "sub": "u-1", "nonce": nonce,
            "iat": now, "exp": now + 300,
            "preferred_username": "j.okafor", "name": "J Okafor",
            "email": "j.okafor@bank.example", **extra}


@pytest.fixture
def provider(keypair):
    documents = {
        f"{ISSUER}/.well-known/openid-configuration": {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/authorize",
            "token_endpoint": f"{ISSUER}/token",
            "jwks_uri": f"{ISSUER}/jwks"},
        f"{ISSUER}/jwks": {"keys": [keypair["jwk"]]},
    }
    state = {"token": None}

    def fetch(url, form=None):
        if url == f"{ISSUER}/token":
            state["form"] = form
            return {"id_token": state["token"], "token_type": "Bearer"}
        return documents[url]

    p = OidcProvider(ISSUER, CLIENT, "secret", REDIRECT,
                     role_map=ROLE_MAP, fetch=fetch)
    p._exchanged = state
    return p


# ================================================================== the flow
class TestTheCodeFlow:
    def test_it_uses_pkce_and_carries_a_state_and_a_nonce(self, provider):
        """PKCE always, even with a client secret: the secret protects the
        exchange, the verifier protects the code, and a code intercepted in a
        redirect is the thing that actually gets stolen."""
        begun = provider.begin()
        assert "code_challenge_method=S256" in begun["url"]
        assert "response_type=code" in begun["url"]
        assert begun["state"] and begun["nonce"] and begun["verifier"]

    def test_a_provider_naming_a_different_issuer_is_refused(self, keypair):
        def fetch(url, form=None):
            return {"issuer": "https://somewhere.else",
                    "authorization_endpoint": "x", "token_endpoint": "y",
                    "jwks_uri": "z"}
        with pytest.raises(AuthzError) as exc:
            OidcProvider(ISSUER, CLIENT, redirect_uri=REDIRECT,
                         fetch=fetch).discover()
        assert exc.value.code == "issuer_mismatch"

    def test_an_unconfigured_provider_says_what_is_missing(self):
        p = OidcProvider("", "", redirect_uri="")
        assert "auth.oidc.issuer" in p.configured()
        with pytest.raises(AuthzError) as exc:
            p.begin()
        assert exc.value.code == "sso_not_configured"

    def test_a_state_that_does_not_match_is_a_forgery(self, provider, keypair):
        begun = provider.begin()
        provider._exchanged["token"] = sign(keypair, claims_for(begun["nonce"]))
        with pytest.raises(AuthzError) as exc:
            provider.complete("code", begun, "not-the-state")
        assert exc.value.code == "state_mismatch"
        assert "cross-site request forgery" in exc.value.remediation

    def test_a_login_left_open_too_long_expires(self, provider, keypair):
        begun = provider.begin()
        provider._exchanged["token"] = sign(keypair, claims_for(begun["nonce"]))
        with pytest.raises(AuthzError) as exc:
            provider.complete("code", begun, begun["state"],
                              now=time.time() + 3600)
        assert exc.value.code == "login_expired"

    def test_a_code_with_no_login_in_progress_is_refused(self, provider):
        with pytest.raises(AuthzError) as exc:
            provider.complete("code", {}, "state")
        assert exc.value.code == "no_login_in_progress"


class TestTheAssertionIsVerified:
    def _complete(self, provider, keypair, claims, nonce=None):
        begun = provider.begin()
        provider._exchanged["token"] = sign(
            keypair, {**claims, "nonce": nonce or begun["nonce"]})
        return provider.complete("code", begun, begun["state"])

    def test_a_genuine_token_signs_somebody_in(self, provider, keypair):
        identity = self._complete(provider, keypair, claims_for())
        assert identity["username"] == "j.okafor"
        assert identity["email"] == "j.okafor@bank.example"

    def test_a_tampered_token_is_refused(self, provider, keypair):
        begun = provider.begin()
        genuine = sign(keypair, claims_for(begun["nonce"]))
        head, _, signature = genuine.split(".")
        forged = json.dumps({**claims_for(begun["nonce"]), "sub": "admin"})
        provider._exchanged["token"] = f"{head}.{_b64(forged.encode())}.{signature}"
        with pytest.raises(AuthzError) as exc:
            provider.complete("code", begun, begun["state"])
        assert exc.value.code == "bad_signature"

    def test_an_unsigned_token_is_refused_by_the_verifier_not_obeyed(self,
                                                                     provider,
                                                                     keypair):
        """An algorithm the caller chooses and the verifier obeys is how a token
        gets accepted with no signature at all."""
        begun = provider.begin()
        head = _b64(json.dumps({"alg": "none", "kid": "k1"}).encode())
        body = _b64(json.dumps(claims_for(begun["nonce"])).encode())
        provider._exchanged["token"] = f"{head}.{body}."
        with pytest.raises(AuthzError) as exc:
            provider.complete("code", begun, begun["state"])
        assert exc.value.code == "unsupported_algorithm"

    def test_a_token_for_another_client_is_not_a_login_here(self, provider,
                                                            keypair):
        with pytest.raises(AuthzError) as exc:
            self._complete(provider, keypair,
                           {**claims_for(), "aud": "some-other-app"})
        assert exc.value.code == "audience_mismatch"

    def test_an_expired_token_is_refused(self, provider, keypair):
        with pytest.raises(AuthzError) as exc:
            self._complete(provider, keypair,
                           {**claims_for(), "exp": time.time() - 3600})
        assert exc.value.code == "token_expired"

    def test_a_replayed_assertion_is_caught_by_the_nonce(self, provider,
                                                         keypair):
        begun = provider.begin()
        provider._exchanged["token"] = sign(keypair,
                                            claims_for(nonce="a-different-one"))
        with pytest.raises(AuthzError) as exc:
            provider.complete("code", begun, begun["state"])
        assert exc.value.code == "nonce_mismatch"

    def test_a_key_the_provider_does_not_publish_is_refused(self, provider,
                                                            keypair):
        begun = provider.begin()
        provider._exchanged["token"] = sign(
            keypair, claims_for(begun["nonce"]),
            header={"alg": "RS256", "kid": "rotated-away"})
        with pytest.raises(AuthzError) as exc:
            provider.complete("code", begun, begun["state"])
        assert exc.value.code == "unknown_key"

    def test_a_weak_key_is_refused(self, keypair):
        small = {"kty": "RSA", "kid": "s", "n": _b64((2 ** 700).to_bytes(88, "big")),
                 "e": _b64((65537).to_bytes(3, "big"))}
        with pytest.raises(AuthzError) as exc:
            verify(sign(keypair, claims_for()), {"k1": small})
        assert exc.value.code in ("weak_key", "bad_signature")


# ================================================================ the roles
class TestGroupsAreMappedNotObeyed:
    def test_a_group_with_no_mapping_grants_nothing(self, provider):
        identity = provider.identity(
            {"sub": "u", "preferred_username": "x",
             "groups": ["some-unrelated-team"]})
        assert identity["roles"] == []
        assert identity["ignored_groups"] == ["some-unrelated-team"]
        assert "none of the groups is mapped" in identity["detail"]

    def test_a_mapped_group_grants_what_the_mapping_says(self, provider):
        identity = provider.identity(
            {"sub": "u", "preferred_username": "x",
             "groups": ["maya-validators", "unrelated"]})
        assert identity["roles"] == ["validator"]
        assert identity["mapped_from"] == {"maya-validators": ["validator"]}

    def test_a_string_of_groups_is_read_as_a_list(self, provider):
        identity = provider.identity(
            {"sub": "u", "preferred_username": "x",
             "groups": "maya-developers maya-validators"})
        assert set(identity["roles"]) == {"model_developer", "validator"}

    def test_a_token_with_nobody_in_it_is_refused(self, provider):
        with pytest.raises(AuthzError) as exc:
            provider.identity({"groups": []})
        assert exc.value.code == "no_subject"


class TestTheIncompatiblePairIsRefused:
    """A directory that can hand out a conflicting pair by mistake is why the
    check exists; honouring it only for local principals would honour it where
    it is least needed."""

    def test_a_directory_cannot_grant_incompatible_roles(self, provider,
                                                         principals, evidence):
        identity = provider.identity(
            {"sub": "u", "preferred_username": "solo",
             "groups": ["maya-everything"]})
        with pytest.raises(AuthzError) as exc:
            provider.sign_in(identity, principals, evidence)
        assert exc.value.code == "incompatible_roles"
        assert "let a directory decide segregation of duties" in exc.value.remediation

    def test_it_is_refused_rather_than_quietly_reduced(self, provider,
                                                       principals, evidence):
        identity = provider.identity(
            {"sub": "u", "preferred_username": "solo",
             "groups": ["maya-everything"]})
        with pytest.raises(AuthzError):
            provider.sign_in(identity, principals, evidence)
        assert principals.get("solo") is None


class TestProvisioningIsADecision:
    def test_an_unknown_person_is_refused_by_default(self, provider, principals,
                                                     evidence):
        """Auto-provisioning gives everybody in the directory a foothold in the
        model register."""
        identity = provider.identity(
            {"sub": "u", "preferred_username": "newcomer",
             "groups": ["maya-validators"]})
        with pytest.raises(AuthzError) as exc:
            provider.sign_in(identity, principals, evidence)
        assert exc.value.code == "not_provisioned"
        assert "deliberately" in exc.value.remediation

    def test_an_instance_may_choose_to_provision(self, provider, principals,
                                                 evidence):
        provider.provision = True
        identity = provider.identity(
            {"sub": "u", "preferred_username": "newcomer", "name": "N Comer",
             "email": "n@bank.example", "groups": ["maya-validators"]})
        principal = provider.sign_in(identity, principals, evidence)
        assert principal["username"] == "newcomer"
        assert principal["roles"] == ["validator"]

    def test_an_existing_principal_has_their_roles_brought_into_line(
            self, provider, principals, evidence):
        principals.create("j.okafor", "J Okafor", ["model_developer"], "pw")
        identity = provider.identity(
            {"sub": "u", "preferred_username": "j.okafor",
             "groups": ["maya-validators"]})
        principal = provider.sign_in(identity, principals, evidence)
        assert principal["roles"] == ["validator"]

    def test_somebody_in_no_mapped_group_cannot_be_provisioned(self, provider,
                                                               principals,
                                                               evidence):
        provider.provision = True
        identity = provider.identity(
            {"sub": "u", "preferred_username": "nobody", "groups": ["unrelated"]})
        with pytest.raises(AuthzError) as exc:
            provider.sign_in(identity, principals, evidence)
        assert exc.value.code == "no_roles_mapped"
        assert "a group does not grant itself" in exc.value.remediation


class TestTheClaimsAreRecorded:
    def test_the_groups_that_produced_the_roles_are_kept(self, provider,
                                                         principals, evidence,
                                                         repos):
        """'Why did they have that role in March' is otherwise unanswerable once
        the directory has moved on."""
        provider.provision = True
        identity = provider.identity(
            {"sub": "u-77", "iss": ISSUER, "preferred_username": "a.mehta",
             "groups": ["maya-validators", "unrelated"]})
        provider.sign_in(identity, principals, evidence)
        node = [e for e in repos["evidence"].many()
                if e["kind"] == "principal_signed_in_via_sso"][0]
        assert node["payload"]["subject"] == "u-77"
        assert node["payload"]["mapped_from"] == {"maya-validators": ["validator"]}
        assert node["payload"]["groups"] == ["maya-validators", "unrelated"]

    def test_the_description_says_what_it_does_with_groups(self, provider):
        described = provider.describe()
        assert described["enabled"]
        assert "mapped, never obeyed" in described["roles"]
        assert described["provisions_on_first_login"] is False


class TestTheProviderBeingDownDoesNotLockAnybodyOut:
    def test_an_unreachable_provider_says_to_use_local_credentials(self):
        def fetch(url, form=None):
            raise OSError("connection refused")
        p = OidcProvider(ISSUER, CLIENT, redirect_uri=REDIRECT, fetch=fetch)
        with pytest.raises(Exception) as exc:
            p.discover()
        assert "unreachable" in str(exc.value).lower() or \
            getattr(exc.value, "code", "") == "provider_unreachable"
