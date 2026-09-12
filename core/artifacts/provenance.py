"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Who built this artifact, and can you check that they say so.

The register already verifies an artifact by **digest**: what resolves is what
was registered, and a substituted file is caught. A signature answers a different
question — *who produced it* — and the difference matters exactly when the answer
is *nobody here*.

**A digest establishes integrity; a signature establishes origin, and only one
of those tells you the artifact came from your own build.** A substituted file
fails the digest check. A file that was never substituted because the attacker
had access to the build is a file whose digest was correct from the first moment
anybody looked at it, and no amount of digest checking will ever say otherwise.
That is the whole of what SLSA is about and the whole reason this is a separate
control.

**MAYA verifies attestations; it does not mint them.** Signing happens in a build
system, with keys a build system holds. A governance platform that signed
artifacts would hold the key that could forge one — the same objection it makes
about its own warrant signing, which is why a warrant's key is derived from the
audience it is issued to rather than shared across the estate. So an attestation
arrives, and the register
checks it against a **trusted identity** the firm configured, records the answer,
and refuses at resolution if the firm asked it to.

**An unverifiable attestation is worse than none, and is refused as such.** A
signature nobody can check is a decoration, and a register displaying one would
be telling every reader that the provenance was established. The states here are
`verified`, `unverified` and `absent`, and they are three different facts.

**What this deliberately does not do is embed a cryptographic library.** The
verification port is defined; a firm wires in cosign, its own PKI, or a Sigstore
client. Shipping one would be shipping a trust-root decision — whose keys, whose
transparency log, whose revocation — that a bank's security function has already
made differently.
"""
from __future__ import annotations

import time

from typing import Any, Dict, List, Optional

from core.artifacts.common import ArtifactError
from core.log import get_logger

logger = get_logger(__name__)

VERIFIED, UNVERIFIED, ABSENT = "verified", "unverified", "absent"

#: What each state means, and why they are three rather than two. A register
#: that collapsed `unverified` into `absent` would let an attestation nobody
#: could check read as no attestation at all — which is nearly right and hides
#: the case where somebody thought they had signed it.
STATES: Dict[str, str] = {
    VERIFIED: "an attestation was presented and checked against an identity "
              "this firm trusts",
    UNVERIFIED: "an attestation was presented and could NOT be checked — a "
                "signature nobody can verify is a decoration, and a register "
                "displaying one would be telling every reader the provenance "
                "was established",
    ABSENT: "no attestation was presented. A different fact from one that "
            "failed: this artifact's origin was never claimed, and somebody "
            "may believe it was",
}

#: The provenance predicates a build system emits. Recorded as given: an
#: in-toto statement is the build system's words, and paraphrasing it into a
#: shape this platform prefers would lose whatever a verifier needs.
PREDICATES = ("https://slsa.dev/provenance/v1",
              "https://in-toto.io/attestation/release/v0.1")


class ArtifactProvenance:
    """Checks who built an artifact, against identities the firm trusts."""

    def __init__(self, verifier=None, trusted: Optional[List[str]] = None,
                 evidence=None, require_verified: bool = False, repo=None):
        # The verification port. `None` means nothing can be checked, which is
        # REPORTED — never treated as verified. Shipping a client would be
        # shipping a trust-root decision a bank's security function has already
        # made differently.
        self.verifier = verifier
        self.trusted = list(trusted or ())
        self.evidence = evidence
        # Whether an unverified artifact may resolve. Off by default: a firm
        # that has not wired a verifier in would otherwise find every model
        # refusing on the day this shipped.
        self.require_verified = require_verified
        # Where the verdict is kept, so that resolution has something to read.
        #
        # Without it `check_at_resolution` could only ever be handed `absent`,
        # which is why it had no caller: switching `require_verified` on would
        # have refused every model in the estate. Provenance was verified,
        # written to the evidence chain, and then forgotten.
        self.repo = repo

    # --------------------------------------------------------------- record
    def attest(self, *, artifact_digest: str, predicate: str,
               statement: Dict[str, Any], identity: str = "",
               actor: str = "system") -> Dict[str, Any]:
        """Take delivery of a build system's provenance statement."""
        if not (artifact_digest or "").strip():
            raise ArtifactError(
                "digest_required",
                "an attestation with no artifact digest is a statement about "
                "nothing in particular",
                "attest the digest the build produced")
        if predicate not in PREDICATES:
            raise ArtifactError(
                "unknown_predicate",
                f"'{predicate}' is not a provenance predicate this register "
                f"recognises",
                "one of " + ", ".join(PREDICATES))

        verdict = self.verify(artifact_digest, statement, identity)
        if self.evidence is not None:
            with self.evidence.recording():
                self.evidence.append(
                    "artifact_provenance_attested", "artifact",
                    artifact_digest,
                    {"predicate": predicate, "identity": identity,
                     "state": verdict["state"],
                     "builder": verdict.get("builder")}, actor=actor)
        self._remember(artifact_digest, predicate, verdict, actor)
        if verdict["state"] == UNVERIFIED:
            logger.warning("provenance for %s could not be verified: %s",
                           artifact_digest[:20], verdict["why"])
        return {**verdict, "artifact_digest": artifact_digest,
                "predicate": predicate}

    # --------------------------------------------------------------- verify
    def verify(self, artifact_digest: str, statement: Dict[str, Any],
               identity: str = "") -> Dict[str, Any]:
        """Check an attestation against an identity the firm trusts."""
        builder = ((statement or {}).get("predicate") or {}).get(
            "builder", {}).get("id") or identity or ""
        if self.verifier is None:
            return {
                "state": UNVERIFIED, "builder": builder or None,
                "why": ("no verifier is wired into this instance, so nothing "
                        "checked this signature. That is reported rather than "
                        "passed: an attestation nobody can check is a "
                        "decoration"),
                "means": STATES[UNVERIFIED],
            }
        if self.trusted and builder not in self.trusted:
            return {
                "state": UNVERIFIED, "builder": builder or None,
                "why": (f"the statement names builder '{builder}', which is "
                        f"not one of the identities this firm trusts. A "
                        f"correctly-signed artifact from the wrong builder is "
                        f"exactly the case a digest cannot catch"),
                "means": STATES[UNVERIFIED],
            }
        try:
            ok = bool(self.verifier(artifact_digest, statement))
        except Exception as failure:
            logger.warning("the provenance verifier raised for %s",
                           artifact_digest[:20], exc_info=True)
            return {"state": UNVERIFIED, "builder": builder or None,
                    "why": (f"the verifier did not complete ({failure}). An "
                            f"artifact nothing could check is not an artifact "
                            f"something checked and cleared"),
                    "means": STATES[UNVERIFIED]}
        if not ok:
            return {"state": UNVERIFIED, "builder": builder or None,
                    "why": "the signature did not verify",
                    "means": STATES[UNVERIFIED]}
        return {"state": VERIFIED, "builder": builder or None,
                "why": (f"checked against {builder or 'a trusted identity'}"),
                "means": STATES[VERIFIED]}

    def _remember(self, artifact_digest: str, predicate: str,
                  verdict: Dict[str, Any], actor: str) -> None:
        """Keep the verdict, replacing any earlier one for the same bytes.

        Replaced rather than appended: provenance is a fact about the bytes,
        and the current answer is the one resolution needs. The history is on
        the evidence chain, which is where a history belongs.
        """
        if self.repo is None:
            return
        row = {"artifact_digest": artifact_digest, "state": verdict["state"],
               "predicate": predicate, "builder": verdict.get("builder"),
               "why": verdict.get("why", ""), "recorded_by": actor,
               "recorded_at": time.time()}
        held = self.repo.one(artifact_digest=artifact_digest)
        if held is None:
            self.repo.add(row)
        else:
            self.repo.set(row, id=held["id"])

    def state_of(self, artifact_digest: str) -> str:
        """`verified`, `unverified`, or `absent` when nobody attested.

        `absent` is not stored and is not a failure — it is the answer for an
        artifact nobody made a statement about, and it is a different fact from
        one whose statement could not be checked.
        """
        if self.repo is None or not artifact_digest:
            return ABSENT
        held = self.repo.one(artifact_digest=artifact_digest)
        return (held or {}).get("state") or ABSENT

    # ------------------------------------------------------------ resolution
    def check_at_resolution(self, artifact_digest: str,
                            state: str = ABSENT) -> None:
        """Refuse a resolution if the firm asked for verified provenance.

        Off by default and deliberately: a firm that has not wired a verifier
        in would otherwise find every model refusing on the day this shipped,
        which is how a security control gets turned off permanently in its
        first week.
        """
        if not self.require_verified or state == VERIFIED:
            return
        raise ArtifactError(
            "provenance_not_verified",
            f"this instance requires verified provenance and this artifact's "
            f"is {state}. {STATES.get(state, '')}",
            "attest the build, or wire a verifier in — and note that a digest "
            "establishes integrity while a signature establishes ORIGIN: a "
            "file that was never substituted because the attacker had access "
            "to the build has a correct digest from the first moment anybody "
            "looked at it")

    # -------------------------------------------------------------- posture
    def posture(self) -> Dict[str, Any]:
        """What this instance can actually establish about an artifact's origin."""
        return {
            "verifier_wired": self.verifier is not None,
            "trusted_identities": list(self.trusted),
            "required_at_resolution": self.require_verified,
            "states": STATES, "predicates": list(PREDICATES),
            "detail": (
                "a verifier is wired in, so an attestation can be checked"
                if self.verifier is not None else
                "no verifier is wired into this instance, so every attestation "
                "reads as UNVERIFIED rather than as verified. MAYA does not "
                "mint signatures either: signing happens in a build system "
                "with keys a build system holds, and a governance platform "
                "that signed artifacts would hold the key that could forge one "
                "— the same objection it already makes about its own warrant "
                "signing")
            + ". A digest establishes integrity and a signature establishes "
              "origin, and only the second tells you the artifact came from "
              "your own build",
        }
