"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Descriptor signing and time-to-live.

A descriptor is a bearer credential: whoever holds it can act on it, so it is
signed over its canonical form and it expires. Both properties are here rather
than spread through the service, because a signature computed two different ways
is a signature that verifies in one place and fails in another.

TTL carries jitter for a specific reason found in adversarial review as H-1.
A fleet issued descriptors at deploy time expires them in lockstep, and the
resulting thundering herd hits resolution at exactly the moment the platform is
least able to absorb it. Spreading expiry over a band turns a spike into a
trickle.
"""
from __future__ import annotations

import hmac
import random
from hashlib import sha256
from typing import Any, Dict, Optional

from db.database import digest as canonical_digest

MAX_JITTER_PCT = 50


class WarrantSigner:
    """Signs, verifies and ages warrants."""

    ALGORITHM = "HMAC-SHA256"

    def __init__(self, signing_key: str = "maya-dev-key", jitter_pct: int = 20):
        self._key = signing_key.encode()
        self.key_id = signing_key
        self.jitter = max(0, min(jitter_pct, MAX_JITTER_PCT))

    def sign(self, warrant: Dict[str, Any]) -> str:
        """HMAC over the canonical form, with the signature block excluded.

        The block is excluded whole rather than blanked, so a warrant signed
        before the block existed and one signed after produce the same digest
        over the same content.
        """
        body = {k: v for k, v in warrant.items() if k != "signature"}
        return hmac.new(self._key, canonical_digest(body).encode(), sha256).hexdigest()

    def verify(self, warrant: Dict[str, Any]) -> bool:
        claimed = (warrant.get("signature") or {}).get("value", "")
        return hmac.compare_digest(claimed, self.sign(warrant))

    def jittered(self, ttl: int) -> int:
        """+/- jitter so a fleet does not expire in lockstep and stampede."""
        if not self.jitter:
            return ttl
        delta = ttl * self.jitter / 100.0
        return max(1, int(ttl + random.uniform(-delta, delta)))

    @staticmethod
    def is_expired(warrant: Dict[str, Any], now: Optional[float] = None) -> bool:
        import time
        auth = warrant["authority"]
        return (now or time.time()) > auth["expires_at"] + auth.get("grace_seconds", 0)
