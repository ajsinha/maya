"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Warrants: the whole contract between MAYA and anything that runs a model.

The SDK deliberately does **not** validate a warrant. The platform validates
every one against the grammar before it signs it — a signature over a
non-conforming document would assure that it is authentic and not that it is
usable — so a second check here could only ever disagree with the first, and it
would disagree on a stale copy of the vocabulary.

What the SDK does is make it hard to hold a warrant carelessly. `resolve` returns
the descriptor; `execute` sends the inputs and never sees the descriptor at all;
and the expiry is on the document where a caller can read it, because a warrant
is short-lived on purpose and a client that caches one has quietly turned a
revocable authorisation into a permanent one.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class Warrants:
    """Entitlements, warrants, and the two things you can do with one."""

    def __init__(self, maya):
        self._maya = maya

    # ------------------------------------------------------------ standing
    def grant(self, *, urn: str, principal: str, declared_use: str,
              environment: str = "prod",
              flavour: str = "descriptor_only") -> Dict[str, Any]:
        """The standing entitlement a warrant is minted against.

        A grant and a warrant are different things and the difference matters: a
        grant says *this principal may ask*, a warrant is one signed, expiring
        answer to one asking. Revoking the grant stops the next warrant rather
        than reaching into the last one, which is why the revocation floor is
        measured in seconds and not in hope.
        """
        return self._maya.call("POST", "/warrants", json={
            "urn": urn, "principal": principal, "declared_use": declared_use,
            "environment": environment, "flavour": flavour})

    def revoke(self, *, urn: str, reason: str) -> Dict[str, Any]:
        return self._maya.call("POST", "/warrants/revoke",
                               json={"urn": urn, "reason": reason})

    # ------------------------------------------------------------- minting
    def resolve(self, *, urn: str, principal: str, declared_use: str,
                environment: str = "prod",
                verb: Optional[str] = None) -> Dict[str, Any]:
        """A signed descriptor for one operation on one version.

        You may only resolve **for yourself** unless you hold `warrant:issue`.
        Otherwise anybody could obtain a credential in a service account's name,
        and a credential that does not name who is acting is not a credential.

        The descriptor names the approved parameter set by id and digest. An
        engine re-derives that digest from the values before running — it does
        not compare the stored digest against the warrant's copy, because those
        are two copies of one claim and would agree happily over values somebody
        had edited underneath them.
        """
        return self._maya.call("POST", "/resolve", params={"verb": verb}, json={
            "urn": urn, "principal": principal, "declared_use": declared_use,
            "environment": environment})

    def for_fitting(self, *, urn: str, principal: str, featureset: str,
                    featureset_version: int, window: Dict[str, float],
                    as_of: float, environment: str = "lab",
                    declared_use: str = "model_development") -> Dict[str, Any]:
        """A warrant to fit this version from that featureset version.

        Three laws are checked before it is signed: training data must come from
        a source readable as-of (L-W3), the read must be bounded in **both**
        clocks (L-W9), and the featureset must provide what the kernel declares
        it reads (L-W10) — because adding a regressor is a model change, not a
        data change.

        What comes back is self-describing: the slots, their types, which feature
        and view version fills each, the entity, the grain, the label binding and
        the outcome window. Names and types, never values — a signed credential
        is not a wire format for a dataset.
        """
        return self._maya.call("POST", "/fit-warrants", json={
            "urn": urn, "environment": environment, "principal": principal,
            "declared_use": declared_use, "featureset": featureset,
            "featureset_version": featureset_version,
            "window": window, "as_of": as_of})

    # ------------------------------------------------------------- running
    def execute(self, *, urn: str, principal: str, declared_use: str,
                inputs: Dict[str, Any],
                environment: str = "prod") -> Dict[str, Any]:
        """Run it through the captive engine.

        A convenience, and honest about being one: MAYA does not execute models
        as a rule, and this engine is a consumer of the same public warrant
        contract anything else would use. A `no_runtime` refusal here means this
        instance has no engine for that runtime — not that the warrant is wrong.
        """
        return self._maya.call("POST", "/execute", json={
            "urn": urn, "principal": principal, "declared_use": declared_use,
            "environment": environment, "inputs": inputs})

    # -------------------------------------------------------------- shapes
    def grammar(self) -> Dict[str, Any]:
        """The four vocabularies, published rather than documented."""
        return self._maya.call("GET", "/grammar")

    def schema(self) -> Dict[str, Any]:
        """The JSON Schema, so an engine in any language can check a warrant
        before acting on it. A contract nobody can check is a convention."""
        return self._maya.call("GET", "/grammar/schema")

    def validate(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Ask the platform whether a document conforms. Every problem at once,
        because fixing one to be told about the next is the worst possible
        interface for a document with ten sections."""
        return self._maya.call("POST", "/grammar/validate", json=document)

    # ------------------------------------------------------------ profiles
    def profiles(self) -> Dict[str, Any]:
        """The live request-default profiles, least specific first."""
        return self._maya.call("GET", "/warrant-profiles")

    def preview_profiles(self, *, urn: str, environment: str = "prod",
                         semver: Optional[str] = None,
                         request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """What a profile would fill in here, and which profile said so."""
        return self._maya.call("POST", "/warrant-profiles/preview", json={
            "urn": urn, "environment": environment, "semver": semver,
            "request": request or {}})
