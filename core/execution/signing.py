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

from core.log import get_logger
from db.database import digest as canonical_digest

logger = get_logger(__name__)

MAX_JITTER_PCT = 50


# Secrets that are public knowledge because they ship in this repository. A
# deployment running on one of these is a deployment anybody can forge warrants
# for, so it is named at start-up rather than discovered.
KNOWN_WEAK_KEYS = frozenset({"maya-dev-key", "changeme", "secret", ""})


class WarrantSigner:
    """Signs, verifies and ages warrants.

    **The secret and its name are two different strings.** They were once one:
    the signing key was used as the HMAC secret *and* written into every
    descriptor as `signature.key_id`, which published the secret to every holder
    of a warrant -- and `warrant:read` is held by every role, the auditor
    included. Anyone with one descriptor could mint a warrant for any model,
    any principal, any use, with the operating boundary emptied and an expiry a
    century out, and MAYA's own verify() would accept it.

    The key id is now DERIVED from the secret by a one-way digest. It still
    identifies which key signed a warrant -- which is what a key id is for, and
    what makes rotation legible -- and it cannot be turned back into the secret.
    A caller may override the label; it is never allowed to become the secret.
    """

    ALGORITHM = "HMAC-SHA256"

    def __init__(self, signing_key: str = "maya-dev-key",
                 key_id: Optional[str] = None, jitter_pct: int = 20):
        self._key = signing_key.encode()
        self.key_id = key_id or self.label_for(signing_key)
        self.jitter = max(0, min(jitter_pct, MAX_JITTER_PCT))
        if signing_key in KNOWN_WEAK_KEYS:
            # Loud, and at construction rather than at first use: a warrant
            # signed with a published secret is a warrant anybody can forge, and
            # the failure is silent in every other respect.
            logger.warning(
                "warrants are being signed with a PUBLISHED default key. Anyone "
                "with a copy of this repository can forge a warrant that MAYA "
                "will verify. Set warrants.signing_key before any environment "
                "that matters.")

    @staticmethod
    def label_for(signing_key: str) -> str:
        """A name for the key that is not the key.

        One-way, so publishing it in every descriptor tells a reader which key
        signed and nothing about how to sign. Rotating the secret changes the
        label by itself, so two warrants signed under different keys are
        distinguishable without anybody maintaining a mapping.
        """
        return "k-" + sha256(signing_key.encode()).hexdigest()[:16]

    @property
    def uses_a_published_key(self) -> bool:
        """Whether this signer can be forged by anybody with the source."""
        return self._key.decode() in KNOWN_WEAK_KEYS

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
