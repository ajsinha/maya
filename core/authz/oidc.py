"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Single sign-on, and the question it forces.

Connecting an identity provider is mostly mechanical: discovery, an
authorisation code, a token exchange, a signed assertion to verify. The
authorisation-code flow with PKCE, a state parameter, and a nonce — none of it
is novel and all of it is here.

What is not mechanical is what happens to **roles**. An identity provider that
grants MAYA roles is an identity provider that decides segregation of duties, and
the person administering it is very often the person whose duties are being
segregated. So:

**Group claims are mapped, not obeyed.** The mapping lives in MAYA's
configuration. A group with no mapping grants nothing; it does not grant itself.

**The incompatible-roles check still applies.** If the provider puts somebody in
both the developers' group and the approvers' group, the login is **refused** —
not silently accepted with both roles, and not silently reduced to one. A
directory that can hand out an incompatible pair by mistake is exactly why the
check exists, and honouring it only for locally-created principals would honour
it where it is least needed.

**Provisioning is a decision, not a default.** An instance can create principals
on first login, or refuse anybody it does not already know. The default is to
refuse, because auto-provisioning gives everybody in the directory a foothold in
the model register, and that is a decision somebody should make deliberately.

**The claims that produced the roles are recorded.** Not the whole token — it
carries more about a person than a governance record needs — but the issuer, the
subject and the groups that were mapped. *"Why did this person have that role in
March"* is otherwise unanswerable once the directory has moved on.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.authz.common import AuthzError
from core.authz.jws import b64url_decode, jwks, verify
from core.authz.roles import conflicts
from core.log import get_logger, swallowed

logger = get_logger(__name__)

DISCOVERY_PATH = "/.well-known/openid-configuration"
TIMEOUT_SECONDS = 10.0

# How long an unredeemed login attempt stays valid. Long enough for a person to
# authenticate; short enough that a state value left in a browser's history is
# not a credential.
STATE_TTL_SECONDS = 600.0

# Clock skew allowed on a token's own timestamps. Providers and hosts disagree
# by seconds; refusing over that would be theatre.
LEEWAY_SECONDS = 120.0

DEFAULT_SCOPES = ("openid", "profile", "email")


class OidcProvider:
    """One identity provider: discovery, the code flow, and claim mapping."""

    def __init__(self, issuer: str, client_id: str,
                 client_secret: Optional[str] = None,
                 redirect_uri: str = "", scopes: Sequence[str] = DEFAULT_SCOPES,
                 group_claim: str = "groups",
                 role_map: Optional[Dict[str, Sequence[str]]] = None,
                 provision: bool = False,
                 link_on_first_login: bool = False,
                 username_claim: str = "preferred_username",
                 fetch=None):
        self.issuer = (issuer or "").rstrip("/")
        self.client_id, self.client_secret = client_id, client_secret
        self.redirect_uri = redirect_uri
        self.scopes = tuple(scopes)
        self.group_claim = group_claim
        self.role_map = {k: tuple(v) for k, v in (role_map or {}).items()}
        self.provision = provision
        # Whether a directory login may claim an EXISTING local principal
        # that nobody has linked. Off by default: a principal that already
        # holds governance authority must be linked by an administrator,
        # not by whoever first presents a matching name.
        self.link_on_first_login = link_on_first_login
        self.username_claim = username_claim
        # Injected so the flow can be tested without a provider on the network,
        # and so an air-gapped deployment can supply its own transport. Wrapped,
        # because the refusal a caller sees should be the provider's regardless
        # of which transport failed to reach it.
        self._fetch = _guarded(fetch or _http)
        self._discovered: Optional[Dict[str, Any]] = None
        self._keys: Optional[Dict[str, Dict[str, Any]]] = None

    # ------------------------------------------------------------- discovery
    def configured(self) -> Optional[str]:
        """Why this provider cannot be used, or None."""
        if not self.issuer:
            return "no issuer is configured; set auth.oidc.issuer"
        if not self.client_id:
            return "no client id is configured; set auth.oidc.client_id"
        if not self.redirect_uri:
            return "no redirect uri is configured; set auth.oidc.redirect_uri"
        return None

    def discover(self, refresh: bool = False) -> Dict[str, Any]:
        if self._discovered is None or refresh:
            self._discovered = self._fetch(self.issuer + DISCOVERY_PATH)
            for required in ("authorization_endpoint", "token_endpoint",
                             "jwks_uri", "issuer"):
                if required not in self._discovered:
                    raise AuthzError(
                        "discovery_incomplete",
                        f"the provider's configuration has no "
                        f"'{required}'", "")
            if self._discovered["issuer"].rstrip("/") != self.issuer:
                raise AuthzError(
                    "issuer_mismatch",
                    f"the document at {self.issuer} declares itself to be "
                    f"{self._discovered['issuer']}",
                    "a provider that names a different issuer than the one "
                    "asked is either misconfigured or is not the one asked")
        return self._discovered

    def keys(self, refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        if self._keys is None or refresh:
            self._keys = jwks(self._fetch(self.discover()["jwks_uri"]))
        return self._keys

    # ------------------------------------------------------------------ start
    def begin(self, redirect_to: str = "/dashboard") -> Dict[str, Any]:
        """The URL to send somebody to, and the secrets to remember for later."""
        if (why := self.configured()):
            raise AuthzError("sso_not_configured", why,
                             "sign in with local credentials, or configure the "
                             "provider")
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        query = urllib.parse.urlencode({
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
            "state": state, "nonce": nonce,
            # PKCE always, even with a client secret. The secret protects the
            # exchange; the verifier protects the code, and a code intercepted
            # in a redirect is the thing that actually gets stolen.
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        return {
            "url": f"{self.discover()['authorization_endpoint']}?{query}",
            "state": state, "nonce": nonce, "verifier": verifier,
            "redirect_to": redirect_to, "created_at": time.time(),
        }

    # --------------------------------------------------------------- complete
    def complete(self, code: str, pending: Dict[str, Any], state: str,
                 now: Optional[float] = None) -> Dict[str, Any]:
        """Exchange the code, verify the assertion, and read the claims."""
        moment = now if now is not None else time.time()
        if not pending:
            raise AuthzError(
                "no_login_in_progress",
                "there is no login in progress for this browser",
                "start again from the sign-in page; a code arriving with no "
                "state to check it against is either stale or forged")
        if not secrets.compare_digest(str(pending.get("state", "")), str(state)):
            raise AuthzError(
                "state_mismatch",
                "the state does not match the one this login began with",
                "this is what a cross-site request forgery looks like from "
                "here; the login is refused rather than completed")
        if moment - (pending.get("created_at") or 0) > STATE_TTL_SECONDS:
            raise AuthzError(
                "login_expired",
                "this login attempt has been open too long",
                "start again; a state value left in a browser's history should "
                "not still be a credential")

        tokens = self._exchange(code, pending["verifier"])
        claims = self._assert(tokens, pending.get("nonce"), moment)
        return self.identity(claims)

    def _exchange(self, code: str, verifier: str) -> Dict[str, Any]:
        payload = {"grant_type": "authorization_code", "code": code,
                   "redirect_uri": self.redirect_uri,
                   "client_id": self.client_id, "code_verifier": verifier}
        if self.client_secret:
            payload["client_secret"] = self.client_secret
        response = self._fetch(self.discover()["token_endpoint"], payload)
        if "id_token" not in response:
            raise AuthzError(
                "no_id_token",
                "the provider returned no id_token",
                "MAYA authenticates on the signed assertion, not on an access "
                "token: an access token says what the bearer may do elsewhere, "
                "not who they are here")
        return response

    def _assert(self, tokens: Dict[str, Any], nonce: Optional[str],
                now: float) -> Dict[str, Any]:
        claims = verify(tokens["id_token"], self.keys())
        if claims.get("iss", "").rstrip("/") != self.issuer:
            raise AuthzError("issuer_mismatch",
                             f"the token was issued by "
                             f"{claims.get('iss')}, not by {self.issuer}", "")
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        if self.client_id not in audiences:
            raise AuthzError(
                "audience_mismatch",
                f"the token was issued for {audiences}, not for "
                f"{self.client_id}",
                "a token minted for another client is not a login here, however "
                "genuine its signature")
        if (expiry := claims.get("exp")) is not None and now > expiry + LEEWAY_SECONDS:
            raise AuthzError("token_expired", "the token has expired", "")
        if (issued := claims.get("iat")) is not None and issued > now + LEEWAY_SECONDS:
            raise AuthzError("token_from_the_future",
                             "the token was issued in the future", "")
        if nonce and claims.get("nonce") != nonce:
            raise AuthzError(
                "nonce_mismatch",
                "the token does not carry the nonce this login began with",
                "this is what a replayed assertion looks like from here")
        return claims

    # -------------------------------------------------------------- identity
    @staticmethod
    def _is_unbound(principal: Dict[str, Any]) -> bool:
        return not (principal.get("sso_issuer") or principal.get("sso_subject"))

    @staticmethod
    def _bound_principal(principals, identity: Dict[str, Any]):
        """The principal this (issuer, subject) pair names, if any.

        This -- not the username -- is what a directory login resolves to. The
        subject is the one claim an identity provider guarantees is stable and
        unique within its issuer; a username is a display convenience the
        directory may reuse.
        """
        return principals.by_directory(identity.get("issuer"),
                                       identity.get("subject"))

    @staticmethod
    def _bind(principals, principal: Dict[str, Any], identity: Dict[str, Any],
              evidence, actor: str) -> None:
        """Record the binding once, on the record, so it can be questioned."""
        principals.bind_directory(principal["username"], identity["issuer"],
                                  identity["subject"], actor=actor)
        evidence.append("principal_linked_to_directory", "principal",
                        principal["id"],
                        {"username": principal["username"],
                         "issuer": identity["issuer"],
                         "subject": identity["subject"]}, actor=actor)
        logger.info("bound principal %s to %s subject %s",
                    principal["username"], identity["issuer"],
                    identity["subject"])

    # ----------------------------------------------------------------- claims
    def identity(self, claims: Dict[str, Any]) -> Dict[str, Any]:
        """Who the provider says this is, and what MAYA makes of it."""
        username = (claims.get(self.username_claim)
                    or claims.get("email") or claims.get("sub"))
        if not username:
            raise AuthzError(
                "no_subject",
                f"the token carries no '{self.username_claim}', email or "
                f"subject to identify anybody by", "")
        groups = claims.get(self.group_claim) or []
        if isinstance(groups, str):
            groups = [g for g in groups.replace(",", " ").split() if g]
        roles, mapped, ignored = self.roles_for(groups)
        return {
            "username": str(username),
            "display_name": claims.get("name") or str(username),
            "email": claims.get("email"),
            "subject": claims.get("sub"),
            # The issuer MAYA is configured to trust, not the one the token
            # claims to come from. `_assert` has already refused a token whose
            # `iss` disagrees, so these are the same string on any accepted
            # login -- and binding to the configured one means the durable
            # identity is anchored to a decision somebody made here.
            "issuer": self.issuer,
            "groups": list(groups), "roles": roles,
            "mapped_from": mapped, "ignored_groups": ignored,
            "detail": self._detail(roles, mapped, ignored),
        }

    def roles_for(self, groups: Sequence[str]
                  ) -> Tuple[List[str], Dict[str, List[str]], List[str]]:
        """Map group claims onto roles. A group with no mapping grants nothing."""
        roles: List[str] = []
        mapped: Dict[str, List[str]] = {}
        ignored: List[str] = []
        for group in groups:
            granted = self.role_map.get(group)
            if not granted:
                ignored.append(group)
                continue
            mapped[group] = list(granted)
            for role in granted:
                if role not in roles:
                    roles.append(role)
        return roles, mapped, ignored

    @staticmethod
    def _detail(roles, mapped, ignored) -> str:
        parts = [f"{len(roles)} role(s) from {len(mapped)} mapped group(s)"
                 if roles else "no roles: none of the groups is mapped"]
        if ignored:
            parts.append(f"{len(ignored)} group(s) grant nothing here")
        return "; ".join(parts)

    # ------------------------------------------------------------ the login
    def sign_in(self, identity: Dict[str, Any], principals,
                evidence, actor: str = "sso") -> Dict[str, Any]:
        """Turn a verified identity into a principal, or refuse to.

        The incompatible-roles check applies here exactly as it does to a
        locally-created principal. A directory that can hand out a conflicting
        pair by mistake is the reason the check exists, and honouring it only
        for locally-created principals would honour it where it is least needed.
        """
        username = identity["username"]
        # The DURABLE identity first. A username is not one: a directory user
        # submitting preferred_username 'admin' was previously signed in as the
        # local admin, in no mapped group, because the username was what carried
        # the roles and nothing checked that this was the same human.
        bound = self._bound_principal(principals, identity)
        if bound is not None:
            # The binding wins over the claim. A directory may rename somebody;
            # the subject is what it guarantees, so a renamed person keeps their
            # account here rather than acquiring a second one.
            username = bound["username"]
        existing = bound or principals.get(username)
        if bound is None and existing is not None and not self._is_unbound(existing):
            raise AuthzError(
                "identity_not_linked",
                f"{username} exists here and is bound to a different directory "
                f"identity, so this login is a different person with the same "
                f"name -- or the same person from a directory nobody linked",
                "link the principal to this issuer and subject deliberately; "
                "resolving a directory login onto a local account by username "
                "is how somebody signs in as an administrator by claiming to "
                "be called one")
        if bound is None and existing is not None:
            # Known here, never linked. Linking is the deliberate act, and it is
            # recorded, but it is refused for anybody holding governance
            # authority: those accounts have to be linked by an administrator
            # rather than by whoever first presents a matching name.
            if not self.link_on_first_login:
                raise AuthzError(
                    "identity_not_linked",
                    f"{username} exists here but is not linked to any directory "
                    f"identity",
                    "an administrator must link the principal to this issuer and "
                    "subject, or enable auth.oidc.link_on_first_login for a "
                    "directory you control end to end")

        # The mapping is checked FIRST, before whether this person is known here.
        # An incompatible pair is a statement about the directory's
        # configuration and is worth surfacing either way; telling somebody they
        # are not provisioned would hide the more serious problem behind the
        # lesser one.
        if (found := conflicts(identity["roles"])):
            raise AuthzError(
                "incompatible_roles",
                f"the directory places {username} in groups that map to "
                f"incompatible roles: {'; '.join(found)}",
                "fix the group membership, or the mapping; accepting both would "
                "let a directory decide segregation of duties, and refusing "
                "quietly would hide that it had")
        if existing is None and not self.provision:
            raise AuthzError(
                "not_provisioned",
                f"{username} authenticated successfully and has no principal here",
                "create the principal first, or enable auth.oidc.provision — "
                "which gives everybody in the directory a foothold in the model "
                "register, and is a decision somebody should make deliberately")
        if not identity["roles"] and existing is None:
            raise AuthzError(
                "no_roles_mapped",
                f"{username} is in {len(identity['groups'])} group(s), none of "
                f"which is mapped to a role here",
                "map a group in auth.oidc.roles; a group does not grant itself")

        if existing is None:
            principal = principals.create(
                username, identity["display_name"], identity["roles"],
                password=None, kind="person", email=identity.get("email"),
                actor=actor)
            self._bind(principals, principal, identity, evidence, actor)
        else:
            principal = existing
            if bound is None:
                self._bind(principals, principal, identity, evidence, actor)
            if identity["roles"] and set(identity["roles"]) != set(existing["roles"]):
                principal = principals.set_roles(username, identity["roles"],
                                                 actor=actor)
        # The claims that produced the roles, and not the whole token: it
        # carries more about a person than a governance record needs. Without
        # this, "why did they have that role in March" is unanswerable once the
        # directory has moved on.
        evidence.append("principal_signed_in_via_sso", "principal",
                        principal.get("id", username),
                        {"username": username, "issuer": identity["issuer"],
                         "subject": identity["subject"],
                         "groups": identity["groups"],
                         "mapped_from": identity["mapped_from"],
                         "roles": identity["roles"],
                         "provisioned": existing is None}, actor=actor)
        logger.info("sso sign-in for %s from %s (%s)",
                    username, identity["issuer"], identity["detail"])
        return principals.get(username) or principal

    # -------------------------------------------------------------- describe
    def describe(self) -> Dict[str, Any]:
        return {
            "enabled": self.configured() is None,
            "unavailable_because": self.configured(),
            "issuer": self.issuer, "client_id": self.client_id,
            "scopes": list(self.scopes),
            "group_claim": self.group_claim,
            "mapped_groups": {g: list(r) for g, r in sorted(self.role_map.items())},
            "provisions_on_first_login": self.provision,
            "flow": "authorisation code with PKCE; a state parameter and a nonce "
                    "are required and checked",
            "roles": "group claims are mapped, never obeyed. a group with no "
                     "mapping grants nothing, and a mapping that would produce "
                     "an incompatible pair refuses the login rather than "
                     "quietly reducing it",
        }


def _guarded(fetch):
    """Any transport failure becomes one refusal with one remediation."""
    def call(url: str, form: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            return fetch(url, form) if form is not None else fetch(url)
        except Exception as exc:                      # noqa: BLE001 — translated
            if isinstance(exc, AuthzError):
                # Already ours, and already logged where it was raised. Tested
                # here rather than in its own clause so there is one handler and
                # one place that records what was recovered from.
                raise
            swallowed(logger, exc, f"reached the identity provider at {url}",
                      "the login is refused with the reason rather than hanging",
                      level=30)
            raise AuthzError(
                "provider_unreachable",
                f"the identity provider did not answer: {exc}",
                "sign in with local credentials while it is unavailable; SSO "
                "being down should not lock everybody out of the register"
            ) from exc
    return call


def _http(url: str, form: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """A JSON GET, or a form POST. The standard library, as everywhere here."""
    data = urllib.parse.urlencode(form).encode() if form else None
    request = urllib.request.Request(
        url, data=data,
        headers={"Accept": "application/json"} if not form else
        {"Accept": "application/json",
         "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # Re-raised for _guarded to translate: one refusal, one remediation,
        # whichever transport is in use.
        swallowed(logger, exc, f"reached the identity provider at {url}",
                  "translated into a single refusal by the caller", level=20)
        raise


PREFIX = "auth.oidc.roles."


def role_map(config) -> Dict[str, List[str]]:
    """Group-to-role mappings, read by prefix from the flat configuration.

    ``auth.oidc.roles.maya-validators: validator, model_risk_manager`` maps one
    directory group onto the roles it grants HERE. The group name is the key
    because that is what the directory controls; the roles are the value
    because that is what MAYA controls, and the direction of that arrow is the
    whole point.
    """
    out: Dict[str, List[str]] = {}
    for key, value in (config.as_dict() if hasattr(config, "as_dict") else {}).items():
        if not key.startswith(PREFIX):
            continue
        group = key[len(PREFIX):]
        roles = [r.strip() for r in str(value).split(",") if r.strip()]
        if group and roles:
            out[group] = roles
    return out


def build(config, fetch=None) -> Optional[OidcProvider]:
    """The provider this instance is configured with, if any."""
    if config is None or not config.get("auth.oidc.issuer"):
        return None
    return OidcProvider(
        config.get("auth.oidc.issuer", ""),
        config.get("auth.oidc.client_id", ""),
        config.get("auth.oidc.client_secret") or None,
        config.get("auth.oidc.redirect_uri", ""),
        config.get_list("auth.oidc.scopes", list(DEFAULT_SCOPES)),
        config.get("auth.oidc.group_claim", "groups"),
        role_map(config),
        config.get_bool("auth.oidc.provision", False),
        config.get("auth.oidc.username_claim", "preferred_username"),
        fetch)
