"""
A software WebAuthn authenticator for tests: an ES256 (P-256) key pair, 'none'
attestation, a signature counter, and the exact byte layouts a browser and a
security key produce — client data JSON, authenticator data, a COSE public key
in CBOR, an ECDSA signature over authData ‖ SHA-256(clientDataJSON). Nothing is
mocked on the verifying side: py_webauthn checks these like any other key.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

UP, UV, AT = 0x01, 0x04, 0x40


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class SoftKey:
    def __init__(self, origin: str = "http://localhost:8600", rp_id: str = "localhost") -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.origin, self.rp_id = origin, rp_id
        self.counter = 0
        self.user_handle = b""

    def _cose(self) -> bytes:
        from webauthn.helpers import encode_cbor

        nums = self.key.public_key().public_numbers()
        return encode_cbor(
            {1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")}
        )

    def _client_data(self, kind: str, challenge: str) -> bytes:
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": self.origin, "crossOrigin": False}
        ).encode()

    def _auth_data(self, flags: int, extra: bytes = b"") -> bytes:
        rp_hash = hashlib.sha256(self.rp_id.encode()).digest()
        return rp_hash + bytes([flags]) + struct.pack(">I", self.counter) + extra

    def create(self, options: dict[str, Any]) -> dict[str, Any]:
        """navigator.credentials.create(): a registration response to MAYA's options."""
        from webauthn.helpers import encode_cbor

        self.user_handle = unb64u(options["user"]["id"])
        attested = (
            bytes(16)
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + self._cose()
        )
        auth_data = self._auth_data(UP | UV | AT, attested)
        attestation = encode_cbor({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": b64u(self.credential_id),
            "rawId": b64u(self.credential_id),
            "type": "public-key",
            "clientExtensionResults": {},
            "authenticatorAttachment": "cross-platform",
            "response": {
                "clientDataJSON": b64u(self._client_data("webauthn.create", options["challenge"])),
                "attestationObject": b64u(attestation),
                "transports": ["usb"],
            },
        }

    def get(self, options: dict[str, Any], *, bump: int = 1) -> dict[str, Any]:
        """navigator.credentials.get(): an assertion answering MAYA's challenge."""
        self.counter += bump
        client_data = self._client_data("webauthn.get", options["challenge"])
        auth_data = self._auth_data(UP | UV)
        signature = self.key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": b64u(self.credential_id),
            "rawId": b64u(self.credential_id),
            "type": "public-key",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": b64u(client_data),
                "authenticatorData": b64u(auth_data),
                "signature": b64u(signature),
                "userHandle": b64u(self.user_handle),
            },
        }
