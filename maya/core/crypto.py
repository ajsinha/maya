"""
Signing seam (§13.4.2). Type C: substitutable, never downgraded.

MAYA signs warrant tokens, leakage certificates, execution manifests and
reproducibility bundles with Ed25519 through the ``cryptography`` package.
There is no pure-Python signer and there will not be one: when the backend
is missing every call here raises ``CapabilityRefused`` naming what it
wanted, rather than producing a signature nobody should trust.

The signing key lives under the storage root (``keys/signing.pem``), created
on first use, never in configuration.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any

from maya.core.backends import Backends


class Signer:
    """Ed25519 signer bound to one key file."""

    def __init__(self, key_dir: Path) -> None:
        Backends.require("crypto")
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key_dir.mkdir(parents=True, exist_ok=True)
        path = key_dir / "signing.pem"
        if path.exists():
            key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        else:
            key = Ed25519PrivateKey.generate()
            pem = key.private_bytes(serialization.Encoding.PEM,
                                    serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption())
            with open(path, "xb") as fh:
                fh.write(pem)
        self._key = key
        pub = key.public_key().public_bytes(serialization.Encoding.Raw,
                                            serialization.PublicFormat.Raw)
        self.public_key_b64 = base64.b64encode(pub).decode()
        self.key_id = hashlib.sha256(pub).hexdigest()[:16]

    def sign(self, payload: bytes) -> str:
        return base64.b64encode(self._key.sign(payload)).decode()

    def signature_block(self, payload: bytes) -> dict[str, Any]:
        return {"algorithm": "Ed25519", "key_id": self.key_id,
                "public_key": self.public_key_b64, "signature": self.sign(payload)}


def verify(public_key_b64: str, payload: bytes, signature_b64: str) -> bool:
    """Verify an Ed25519 signature. Refuses (does not return False) without a backend."""
    Backends.require("crypto")
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
    try:
        pub.verify(base64.b64decode(signature_b64), payload)
        return True
    except InvalidSignature:
        return False


class SecretBox:
    """Authenticated encryption at rest (Fernet: AES-128-CBC + HMAC-SHA256).

    Used for secrets MAYA must read back, such as TOTP seeds. The key lives beside
    the signing key under the storage root, never in configuration. Type C: without
    the backend this refuses rather than storing a secret in the clear.
    """

    def __init__(self, key_dir: Path) -> None:
        Backends.require("crypto")
        from cryptography.fernet import Fernet
        key_dir.mkdir(parents=True, exist_ok=True)
        path = key_dir / "secretbox.key"
        if not path.exists():
            with open(path, "xb") as fh:
                fh.write(Fernet.generate_key())
        self._fernet = Fernet(path.read_bytes().strip())

    def seal(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def open(self, token: str) -> str:
        return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")


JWT_ALGORITHMS = ("RS256", "RS384", "RS512", "PS256", "ES256", "ES384")


def _b64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def verify_jws(jwk: dict[str, Any], alg: str, signing_input: bytes, signature: bytes) -> bool:
    """Verify a JWS signature against one JSON Web Key (RFC 7515/7517/7518).

    Asymmetric algorithms only. ``none`` and the HMAC family are refused outright:
    an identity token MAYA accepts must be verifiable without a shared secret.
    """
    Backends.require("crypto")
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa, utils

    if alg not in JWT_ALGORITHMS:
        raise ValueError(f"JWT algorithm '{alg}' is not accepted")
    digest = {"256": hashes.SHA256(), "384": hashes.SHA384(), "512": hashes.SHA512()}[alg[2:]]
    try:
        if alg.startswith(("RS", "PS")):
            if jwk.get("kty") != "RSA":
                return False
            key = rsa.RSAPublicNumbers(int.from_bytes(_b64u(jwk["e"]), "big"),
                                       int.from_bytes(_b64u(jwk["n"]), "big")).public_key()
            pad = padding.PKCS1v15() if alg.startswith("RS") else \
                padding.PSS(padding.MGF1(digest), padding.PSS.DIGEST_LENGTH)
            key.verify(signature, signing_input, pad, digest)
            return True
        if jwk.get("kty") != "EC":
            return False
        curve = {"P-256": ec.SECP256R1(), "P-384": ec.SECP384R1()}[jwk["crv"]]
        key = ec.EllipticCurvePublicNumbers(int.from_bytes(_b64u(jwk["x"]), "big"),
                                            int.from_bytes(_b64u(jwk["y"]), "big"),
                                            curve).public_key()
        half = len(signature) // 2
        der = utils.encode_dss_signature(int.from_bytes(signature[:half], "big"),
                                         int.from_bytes(signature[half:], "big"))
        key.verify(der, signing_input, ec.ECDSA(digest))
        return True
    except (InvalidSignature, KeyError, ValueError):
        return False
