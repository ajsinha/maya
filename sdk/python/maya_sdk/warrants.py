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

    # -------------------------------------------------------------- limits
    def limits(self) -> Dict[str, Any]:
        """Every live grant, and how close it is to its limits.

        Read `unlimited` first: a grant with no limit of any kind is a decision
        nobody has taken rather than one they have.
        """
        return self._maya.call("GET", "/grant-limits")

    def limits_of(self, warrant_id: str) -> Dict[str, Any]:
        """One grant's limits, what it has spent, and what is left."""
        return self._maya.call("GET", f"/grant-limits/{warrant_id}")

    def set_limits(self, warrant_id: str, *, rate: Optional[int] = None,
                   quota: Optional[int] = None,
                   cost: Optional[float] = None,
                   window_hours: Optional[float] = None) -> Dict[str, Any]:
        """Declare what this grant may spend.

        Three limits, and they are not three sizes of the same thing. `rate`
        bounds calls per minute and protects the downstream system from a loop.
        `quota` bounds calls per window and protects the *authorisation* from
        being used more than anybody intended — which no rate limit would
        notice, because none of it is fast. `cost` is the only one whose unit is
        not calls, and is therefore the one that matters for a token-metered
        model, where ten calls can cost more than ten thousand.

        On the grant rather than the principal: a service account holding four
        grants should not have one runaway use exhaust the other three.

        Exceeding one gives `429` with `rate_limit_reached`,
        `quota_limit_reached` or `cost_limit_reached`. The refusal is recorded
        and does not itself count against the limit, so a retry loop cannot keep
        a grant exhausted.
        """
        return self._maya.call("PUT", f"/grant-limits/{warrant_id}",
                               json={"rate": rate, "quota": quota,
                                     "cost": cost,
                                     "window_hours": window_hours})

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


class Composites:
    """One call over a chain of models, and the refusal that makes it worth having.

    A discount curve feeds a valuation feeds a provision. The caller wants one
    authorisation; the register holds three models, three approvals and three
    tiers.

    **A chain is as governed as its least governed link.** A composite resolves
    only if every node resolves — one blocked finding anywhere, one revoked
    grant, one unapproved version, and the whole thing is refused, naming
    *every* failing node rather than the first. A caller told only about the
    first fixes it, retries, and discovers the second; a chain with three
    problems then takes three round trips and each looks like a new failure.

    **The composite's tier is the join of its nodes'.** A chain is at least as
    risky as its riskiest part, derived and not declarable, because the only
    direction anybody ever wants to move it is down.

    **There is no composite descriptor.** `composite_descriptor` is always None
    and that is the design: signing one would be MAYA asserting the chain as a
    whole is authorised, and nothing established that — three people approved
    three models for three purposes and none of them approved the composition.
    What you get back is the nodes in call order, each with its own descriptor
    and its own limitations.
    """

    def __init__(self, maya):
        self._maya = maya

    def list(self) -> Dict[str, Any]:
        """Every model that reads another model's output.

        `tier_raised_by_the_chain` is the number a feeder graph exists to
        produce: models that are riskier as part of a chain than the register
        records them individually.
        """
        return self._maya.call("GET", "/composites")

    def chain(self, terminal: str) -> Dict[str, Any]:
        """The models feeding a terminal, in the order they must be called."""
        return self._maya.call("GET", "/composites", params={"urn": terminal})

    def resolve(self, terminal: str, *, environment: str, declared_use: str,
                principal: str = "", verb: str = "score") -> Dict[str, Any]:
        """Resolve every node, or refuse the whole chain."""
        return self._maya.call("POST", "/composites/resolve", json={
            "terminal": terminal, "environment": environment,
            "declared_use": declared_use, "principal": principal,
            "verb": verb})

    def check(self, terminal: str, *, environment: str, declared_use: str,
              principal: str = "") -> Dict[str, Any]:
        """Would this chain resolve? Without minting anything.

        Its own call because *can this chain run* is asked far more often than
        the chain is run, and answering by resolving would mint descriptors
        nobody intends to use.
        """
        return self._maya.call("POST", "/composites/check", json={
            "terminal": terminal, "environment": environment,
            "declared_use": declared_use, "principal": principal})


class Shadow:
    """An answer that must not be used, and what a register can do about it.

    **MAYA is not in the serving path.** It does not mirror traffic, does not
    sample, and cannot observe the share — a platform claiming to enforce a
    canary percentage by *watching* would be claiming something it has no way
    to check. The `share` you declare is an attestation, and it is labelled one.

    Three things it does do, and each is a real control. It authorises the
    mirror as **advisory**, so every answer under it is non-authoritative and
    every invocation is recorded as such — a firm that never marked its shadow
    traffic has a challenger's answers in the same log as its champion's, and
    *did this number reach a decision* becomes unanswerable a year later.

    It **refuses a shadow grant whose `declared_use` is an approved production
    use**. That is exactly how a shadow answer reaches a decision: not by
    somebody deciding to use it, but by a grant nothing can tell apart from a
    production one at the point of use.

    And it notices a shadow that never ends. Shadow mode exists to decide
    something; one running past ninety days is a second production model nobody
    approved, on production traffic, with no owner and no monitoring plan.
    """

    def __init__(self, maya):
        self._maya = maya

    def posture(self) -> Dict[str, Any]:
        """What MAYA does and does not do about mirrored traffic."""
        return self._maya.call("GET", "/shadow/posture")

    def list(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        """Every advisory grant in the estate.

        An empty answer is ambiguous and says so: either the firm does no
        shadow testing, or it does it unmarked, and the register cannot tell
        the two apart.
        """
        return self._maya.call("GET", "/shadow", params={"now": now})

    def status(self, urn: str, *, environment: str = "",
               now: Optional[float] = None) -> Dict[str, Any]:
        """Advisory grants on one model, and whether any has outstayed itself."""
        return self._maya.call("GET", "/shadow",
                               params={"urn": urn,
                                       "environment": environment,
                                       "now": now})

    def authorise(self, urn: str, *, environment: str, principal: str,
                  declared_use: str, mirrors: str, share: float,
                  until: Optional[float] = None) -> Dict[str, Any]:
        """Issue an advisory grant for a challenger beside a champion.

        `declared_use` must be the shadow's own and not a production one.
        `mirrors` names the production use whose traffic is being copied, so
        something can tell whether this is shadowing anything at all.
        """
        return self._maya.call("POST", "/shadow", json={
            "urn": urn, "environment": environment, "principal": principal,
            "declared_use": declared_use, "mirrors": mirrors, "share": share,
            "until": until})
