"""
OpenID Connect: authorization code flow with PKCE (§12).

OIDC is the SSO floor: pure-Python HTTP plus JWT verification through the
crypto seam, available on every platform. This module is the protocol only —
discovery, the authorization URL, the code exchange and ID-token validation.
Turning verified claims into a MAYA principal lives in ``maya.services.sso``.

What an ID token must satisfy before MAYA believes a word of it: a signature
by a key the issuer publishes (asymmetric only — ``none`` and HMAC refused),
``iss`` equal to the configured issuer, ``aud`` containing our client id,
``exp`` in the future and ``iat`` not in it (with a small skew), and the
``nonce`` MAYA sent.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from maya.core import crypto
from maya.core.errors import NotAuthenticated, ValidationFailed

CLOCK_SKEW = 120
JWKS_TTL = 3600


def _b64u_json(part: str) -> dict[str, Any]:
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def pkce_pair() -> tuple[str, str]:
    """(code_verifier, S256 code_challenge) per RFC 7636."""
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge.decode().rstrip("=")


@dataclass
class OIDCSettings:
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: str = "openid profile email groups"


class OIDCClient:
    """One relying party against one issuer."""

    def __init__(self, cfg: OIDCSettings, *, transport: httpx.BaseTransport | None = None,
                 timeout: float = 10.0) -> None:
        self.cfg = cfg
        self._http = httpx.Client(transport=transport, timeout=timeout)
        self._meta: dict[str, Any] | None = None
        self._jwks: tuple[float, list[dict[str, Any]]] | None = None

    # -- discovery ------------------------------------------------------------------
    def metadata(self) -> dict[str, Any]:
        if self._meta is None:
            url = self.cfg.issuer.rstrip("/") + "/.well-known/openid-configuration"
            meta = self._get_json(url)
            if meta.get("issuer", "").rstrip("/") != self.cfg.issuer.rstrip("/"):
                raise NotAuthenticated("The identity provider's discovery document names a "
                                       "different issuer than MAYA is configured with")
            self._meta = meta
        return self._meta

    def _get_json(self, url: str) -> dict[str, Any]:
        try:
            r = self._http.get(url)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise NotAuthenticated(f"The identity provider is unreachable: {exc}") from exc

    def _keys(self, refresh: bool = False) -> list[dict[str, Any]]:
        if refresh or self._jwks is None or time.time() - self._jwks[0] > JWKS_TTL:
            self._jwks = (time.time(), self._get_json(self.metadata()["jwks_uri"])["keys"])
        return self._jwks[1]

    # -- the flow -----------------------------------------------------------------------
    def begin(self) -> dict[str, str]:
        """State, nonce and PKCE verifier to keep, and the URL to send the browser to."""
        state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        verifier, challenge = pkce_pair()
        query = urlencode({"response_type": "code", "client_id": self.cfg.client_id,
                           "redirect_uri": self.cfg.redirect_uri, "scope": self.cfg.scopes,
                           "state": state, "nonce": nonce, "code_challenge": challenge,
                           "code_challenge_method": "S256"})
        return {"authorize_url": f"{self.metadata()['authorization_endpoint']}?{query}",
                "state": state, "nonce": nonce, "code_verifier": verifier}

    def finish(self, code: str, code_verifier: str, nonce: str) -> dict[str, Any]:
        """Exchange the code and return the validated ID-token claims."""
        form = {"grant_type": "authorization_code", "code": code,
                "redirect_uri": self.cfg.redirect_uri, "client_id": self.cfg.client_id,
                "code_verifier": code_verifier}
        if self.cfg.client_secret:
            form["client_secret"] = self.cfg.client_secret
        try:
            r = self._http.post(self.metadata()["token_endpoint"], data=form)
        except httpx.HTTPError as exc:
            raise NotAuthenticated(f"The identity provider is unreachable: {exc}") from exc
        if r.status_code != 200:
            raise NotAuthenticated("The identity provider refused the authorization code")
        id_token = r.json().get("id_token")
        if not id_token:
            raise NotAuthenticated("The identity provider returned no ID token")
        return self.validate(id_token, nonce)

    def validate(self, id_token: str, nonce: str, *, now: float | None = None) -> dict[str, Any]:
        try:
            header_b64, payload_b64, sig_b64 = id_token.split(".")
            header, claims = _b64u_json(header_b64), _b64u_json(payload_b64)
            signature = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
        except (ValueError, json.JSONDecodeError) as exc:
            raise NotAuthenticated("The ID token is malformed") from exc
        alg = header.get("alg", "")
        if alg not in crypto.JWT_ALGORITHMS:
            raise NotAuthenticated(f"ID token algorithm '{alg}' is not accepted")
        signing_input = f"{header_b64}.{payload_b64}".encode()
        if not self._signature_ok(header, alg, signing_input, signature):
            raise NotAuthenticated("The ID token signature does not verify")
        self._check_claims(claims, nonce, time.time() if now is None else now)
        return claims

    def _signature_ok(self, header: dict[str, Any], alg: str, signing_input: bytes,
                      signature: bytes) -> bool:
        for refresh in (False, True):   # a rotated key: refetch the JWKS once
            candidates = [k for k in self._keys(refresh)
                          if not header.get("kid") or k.get("kid") == header["kid"]]
            if any(crypto.verify_jws(k, alg, signing_input, signature) for k in candidates):
                return True
        return False

    def _check_claims(self, claims: dict[str, Any], nonce: str, now: float) -> None:
        if str(claims.get("iss", "")).rstrip("/") != self.cfg.issuer.rstrip("/"):
            raise NotAuthenticated("ID token issuer mismatch")
        aud = claims.get("aud")
        audiences = aud if isinstance(aud, list) else [aud]
        if self.cfg.client_id not in audiences:
            raise NotAuthenticated("ID token audience does not include this client")
        if float(claims.get("exp", 0)) < now - CLOCK_SKEW:
            raise NotAuthenticated("ID token has expired")
        if float(claims.get("iat", now)) > now + CLOCK_SKEW:
            raise NotAuthenticated("ID token is issued in the future")
        if not nonce or not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise NotAuthenticated("ID token nonce mismatch (possible replay)")


def settings_from(props: Any) -> OIDCSettings:
    """OIDC settings from configuration — no silent defaults for issuer or client."""
    issuer = (props.get("auth.sso.issuer") or "").strip()
    client_id = (props.get("auth.sso.client_id") or "").strip()
    if not issuer or not client_id:
        raise ValidationFailed("auth.sso.issuer and auth.sso.client_id must be set for SSO")
    return OIDCSettings(issuer=issuer, client_id=client_id,
                        client_secret=props.get("auth.sso.client_secret") or "",
                        redirect_uri=props.get("auth.sso.redirect_uri") or "",
                        scopes=props.get("auth.sso.scopes") or "openid profile email groups")
