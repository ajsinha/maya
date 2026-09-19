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
