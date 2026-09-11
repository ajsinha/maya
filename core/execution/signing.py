"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Descriptor signing and time-to-live.

A descriptor is a bearer credential: whoever holds it can act on it, so it is
signed over its canonical form and it expires. Both properties are here rather
than spread through the service, because a signature computed two different ways
is a signature that verifies in one place and fails in another.

## Why the key is derived per audience

A shared HMAC secret has one well-known defect, and it is the one every review
of this platform has raised: **an engine that can verify a warrant can mint
one.** For years the answer written down here was *asymmetric signing, not
built* — which deferred the whole problem to a key hierarchy nobody had, and
left the defect in place in the meantime.

The defect is smaller than the deferral suggested, because it has two halves
that were being treated as one.

*Who can forge* is the half that matters operationally. An engine compromised
today can mint a warrant for **any** model, any principal, any use — so the
blast radius of one compromised consumer is the whole estate.

*Who can prove authorship to a third party* is the half that needs public-key
cryptography, and it is a much rarer requirement: it is the ability to show
somebody who is **not** the bank that only MAYA could have issued a descriptor.

The first half does not need asymmetry at all. It needs the signing key to be
**derived from the audience**, so a compromised engine holds a key that signs
only its own warrants:

    k_audience = HMAC(root, "maya/warrant/v<gen>/" || audience)

MAYA holds the root and can derive every audience key; an engine is given its
own and can derive nothing. A stolen key now forges warrants for one principal
in one deployment, which is a containment property rather than a cryptographic
one — and containment is what the shared secret was actually costing.

What this deliberately does **not** claim is non-repudiation. A verifier holding
`k_audience` could still have minted the warrants it verifies, so a descriptor
proves authorship to **the bank** and not to a third party. `posture()` says so
in those words rather than letting *signed* be read as more than it is.

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

from core.execution.errors import WarrantError
from core.log import get_logger
from db.database import digest as canonical_digest

logger = get_logger(__name__)

MAX_JITTER_PCT = 50

#: The derivation label. It carries a version so that changing the construction
#: later is a visible break rather than two deployments silently disagreeing
#: about what a signature is over.
DERIVATION = "maya/warrant/v1/"

#: What an audience string falls back to when a warrant names no principal.
#: Signing such a warrant under the root would quietly restore the estate-wide
#: key the derivation exists to remove, so it gets an audience of its own that
#: no principal can ever hold.
NO_AUDIENCE = "\x00unattributed"


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
                 key_id: Optional[str] = None, jitter_pct: int = 20,
                 per_audience: bool = True, generation: int = 1):
        self._key = signing_key.encode()
        self.root_label = key_id or self.label_for(signing_key)
        # Kept for every caller that reads `signer.key_id` to stamp a
        # descriptor before the audience is known. It names the ROOT, which is
        # the generation a reader needs for rotation; the per-warrant label
        # adds the audience and is what actually lands in the document.
        self.key_id = self.root_label
        self.per_audience = per_audience
        self.generation = max(1, int(generation))
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

    # ------------------------------------------------------- the derivation
    @staticmethod
    def audience_of(warrant: Dict[str, Any]) -> str:
        """Who this warrant is for. The principal in its authority block.

        A descriptor with no principal is not a descriptor anybody can resolve,
        but it can still be handed to `sign` by a caller building one up. It is
        given an audience no principal can hold rather than falling back to the
        root, because the fallback would restore the estate-wide key silently
        and only for the malformed cases — which is the worst of both.
        """
        authority = warrant.get("authority") or {}
        return str(authority.get("principal") or "").strip() or NO_AUDIENCE

    def key_for(self, audience: str) -> bytes:
        """The key this audience's warrants are signed with.

        One HMAC step from the root. Not a full HKDF: there is no salt to
        contribute and no expansion to do, so the extra machinery would be
        ceremony rather than strength.
        """
        if not self.per_audience:
            return self._key
        info = f"{DERIVATION[:-3]}{self.generation}/{audience}".encode()
        return hmac.new(self._key, info, sha256).digest()

    def key_material_for(self, audience: str) -> str:
        """The derived key as hex, for handing to the engine that holds it.

        This is a secret and the only secret this class will ever return. It is
        deliberately a method rather than a property so that every call site
        reads as an act — `key_material_for` appears in exactly one route, which
        records it, checks the caller is the audience or an administrator, and
        says in its own docstring that MAYA cannot tell whether the engine
        stored it safely.
        """
        audience = (audience or "").strip()
        if not audience:
            raise WarrantError(
                "audience_required",
                "key material was asked for with no audience named",
                "name the principal whose key you want. A key with no "
                "audience is the estate-wide secret this derivation exists "
                "to remove, and handing one out under a blank name is how it "
                "would come back")
        return self.key_for(audience).hex()

    def label_for_audience(self, audience: str) -> str:
        """The `key_id` written into a warrant for this audience.

        `<root label>.<audience digest>`. The root half makes rotation legible —
        two warrants signed under different roots are distinguishable without a
        mapping — and the audience half makes it obvious at a glance that two
        engines are not sharing a key. Both halves are one-way.
        """
        if not self.per_audience:
            return self.root_label
        return (f"{self.root_label}.g{self.generation}."
                + sha256(audience.encode()).hexdigest()[:8])

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
        key = self.key_for(self.audience_of(warrant))
        return hmac.new(key, canonical_digest(body).encode(), sha256).hexdigest()

    def verify(self, warrant: Dict[str, Any]) -> bool:
        """Recompute and compare.

        The audience is read from the warrant being verified, which is the
        property that makes the derivation worth anything: an attacker who
        changes `authority.principal` to redirect a warrant changes the key it
        should have been signed under, so the substitution fails here rather
        than being caught — or not — by a separate check somebody remembered.
        """
        claimed = (warrant.get("signature") or {}).get("value", "")
        return hmac.compare_digest(claimed, self.sign(warrant))

    # ------------------------------------------------------------- posture
    def posture(self) -> Dict[str, Any]:
        """What a MAYA signature proves, and what it does not.

        Published rather than documented, for the same reason the timestamp
        posture is: *signed* is a word readers fill in generously, and the
        gap between what it means here and what they will assume is exactly
        where an assurance stops being true.
        """
        return {
            "alg": self.ALGORITHM,
            "per_audience": self.per_audience,
            "generation": self.generation,
            "root_key_id": self.root_label,
            "uses_a_published_key": self.uses_a_published_key,
            "proves": [
                "the descriptor has not been altered since MAYA sealed it",
                "it was sealed by a holder of this audience's key",
            ],
            "does_not_prove": [
                "authorship to a third party. A verifier holds the same key it "
                "verifies with, so it could have minted what it checks. A "
                "descriptor is evidence to the bank and not to somebody "
                "outside it",
            ],
            "containment": (
                "a compromised engine can forge warrants for ITSELF and for "
                "nobody else: its key is derived from its own principal, and "
                "the derivation is one-way"
                if self.per_audience else
                "NONE. Every audience shares one secret, so any holder can "
                "mint a warrant for any principal, any model and any use. "
                "Set warrants.per_audience_keys"),
            "rotation": (
                "raise warrants.key_generation to re-key every audience at "
                "once without touching the root, or change the root to "
                "re-key and re-label. Warrants already issued keep verifying "
                "only under the generation that signed them, which is why the "
                "generation is in the key id"),
        }

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
