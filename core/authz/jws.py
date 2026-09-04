"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

RS256 verification, in the standard library.

An identity provider's ID token is a JWT signed with RSA. Verifying it needs a
public-key operation and nothing else — no secrets, no key generation, no
signing. So it is here rather than in a dependency, for the same reason every
asset in this platform is vendored: a governance system that cannot be deployed
into an air-gapped network is a governance system somebody works around.

**Construct, never parse.** RSA PKCS#1 v1.5 verification has one famous failure
mode: an implementation that *parses* the recovered block and hunts for the
digest inside it can be fooled by a forged signature that puts a valid-looking
structure in the padding (Bleichenbacher, 2006). The safe implementation builds
the block the signature *should* have produced and compares the whole thing.
That is what this does, and it is why the code reads as a construction rather
than a search.

**Everything is compared in constant time**, not because a timing attack on a
public-key verification is plausible, but because the alternative is a habit.

What this deliberately does not do: sign anything, generate a key, verify any
algorithm but RS256, or accept ``alg: none``. An "algorithm" field that a caller
controls and the verifier obeys is the other famous JWT failure, and the fix is
to decide the algorithm here rather than read it from the token.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import hmac
import json
from typing import Any, Dict, Optional, Tuple

from core.authz.common import AuthzError
from core.log import get_logger, swallowed

logger = get_logger(__name__)

RS256 = "RS256"

# The DigestInfo prefix for SHA-256, from RFC 8017 §9.2 note 1. Prepended to the
# hash to form the block RSA is expected to have signed.
SHA256_DIGEST_INFO = bytes.fromhex(
    "3031300d060960864801650304020105000420")

MIN_MODULUS_BITS = 2048


def b64url_decode(value: str) -> bytes:
    """Base64url without padding, as every JWT field is encoded."""
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError) as exc:
        swallowed(logger, exc, "decoded a token segment",
                  "refused as malformed rather than read past", logging.INFO)
        raise AuthzError("malformed_token",
                         f"a token segment is not base64url: {exc}", "") from exc


def b64url_int(value: str) -> int:
    """A JWK's big-endian integer field."""
    return int.from_bytes(b64url_decode(value), "big")


def split(token: str) -> Tuple[Dict[str, Any], Dict[str, Any], bytes, bytes]:
    """Header, claims, the bytes that were signed, and the signature."""
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthzError(
            "malformed_token",
            f"a JWT has three segments; this has {len(parts)}",
            "the identity provider returned something that is not an ID token")
    header_b64, claims_b64, signature_b64 = parts
    try:
        header = json.loads(b64url_decode(header_b64))
        claims = json.loads(b64url_decode(claims_b64))
    except (ValueError, TypeError) as exc:
        swallowed(logger, exc, "parsed a token segment",
                  "refused as malformed rather than guessed at", logging.INFO)
        raise AuthzError("malformed_token",
                         f"a token segment is not JSON: {exc}", "") from exc
    if not isinstance(header, dict) or not isinstance(claims, dict):
        raise AuthzError("malformed_token",
                         "a token segment is not an object", "")
    signed = f"{header_b64}.{claims_b64}".encode()
    return header, claims, signed, b64url_decode(signature_b64)


def verify(token: str, keys: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Verify an RS256 JWT against a JWKS, returning its claims.

    The algorithm is decided here and not read from the token. A verifier that
    obeys the token's own ``alg`` field can be told ``none``, at which point the
    signature is whatever the sender says it is.
    """
    header, claims, signed, signature = split(token)
    if header.get("alg") != RS256:
        raise AuthzError(
            "unsupported_algorithm",
            f"this verifier accepts {RS256} and the token declares "
            f"'{header.get('alg')}'",
            "an algorithm the caller chooses and the verifier obeys is how a "
            "token gets accepted with no signature at all")
    kid = header.get("kid")
    key = _key_for(kid, keys)
    _verify_rsa(signed, signature, key)
    return claims


def _key_for(kid: Optional[str],
             keys: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    if not keys:
        raise AuthzError("no_signing_keys",
                         "no signing keys are available to verify against",
                         "the provider's JWKS could not be fetched")
    if kid is None:
        if len(keys) == 1:
            return next(iter(keys.values()))
        raise AuthzError(
            "ambiguous_key",
            "the token names no key and the provider publishes several",
            "trying each in turn would make a token valid if ANY key signed it")
    key = keys.get(kid)
    if key is None:
        raise AuthzError(
            "unknown_key",
            f"the token was signed with key '{kid}', which the provider does "
            f"not publish",
            "the provider may have rotated its keys; the set is refetched on "
            "the next login rather than trusted from cache indefinitely")
    return key


def _verify_rsa(signed: bytes, signature: bytes, key: Dict[str, Any]) -> None:
    """RSA PKCS#1 v1.5 with SHA-256. Constructed and compared, never parsed."""
    if key.get("kty") != "RSA":
        raise AuthzError("unsupported_key",
                         f"this verifier reads RSA keys and the provider "
                         f"published a '{key.get('kty')}'", "")
    modulus = b64url_int(key["n"])
    exponent = b64url_int(key["e"])
    size = (modulus.bit_length() + 7) // 8
    if modulus.bit_length() < MIN_MODULUS_BITS:
        raise AuthzError(
            "weak_key",
            f"the provider's key is {modulus.bit_length()} bits; this verifier "
            f"requires at least {MIN_MODULUS_BITS}",
            "a key short enough to factor makes every signature meaningless")
    if len(signature) != size:
        raise AuthzError("bad_signature",
                         "the signature is not the length of the modulus", "")

    recovered = pow(int.from_bytes(signature, "big"), exponent, modulus)
    recovered_bytes = recovered.to_bytes(size, "big")

    # Build what the block MUST be, and compare the whole of it:
    #   0x00 0x01 <0xFF padding> 0x00 <DigestInfo> <SHA-256 digest>
    digest = hashlib.sha256(signed).digest()
    suffix = SHA256_DIGEST_INFO + digest
    padding_length = size - len(suffix) - 3
    if padding_length < 8:
        raise AuthzError("weak_key",
                         "the modulus is too small to hold a padded SHA-256 "
                         "block", "")
    expected = b"\x00\x01" + b"\xff" * padding_length + b"\x00" + suffix

    if not hmac.compare_digest(expected, recovered_bytes):
        logger.warning("an ID token failed signature verification")
        raise AuthzError(
            "bad_signature",
            "the token's signature does not verify against the provider's key",
            "the token was not issued by that provider, or it has been altered "
            "in transit")


def jwks(document: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """A JWKS document as a map from key id to key, RSA signing keys only."""
    out: Dict[str, Dict[str, Any]] = {}
    for index, key in enumerate(document.get("keys") or []):
        if key.get("kty") != "RSA":
            continue
        if key.get("use") not in (None, "sig"):
            continue
        out[key.get("kid") or f"key-{index}"] = key
    if not out:
        raise AuthzError(
            "no_signing_keys",
            "the provider's key set contains no RSA signing keys",
            "this verifier reads RS256, which is what every mainstream "
            "provider issues; a provider using something else needs a "
            "verifier that reads it")
    return out
