"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Models, and the versions that are the thing which actually runs.

The split between the two is the one people coming from an experiment tracker
get wrong, so it is worth saying once here rather than in every docstring: a
**model** is a record with an owner, a purpose and a tier; a **version** is an
immutable kernel; a **parameter set** is a point of `P`. Refitting produces a new
parameter set and *not* a new version, because the kernel did not change — which
is what lets a daily recalibration be approved as a procedure rather than
pretending a committee meets every morning.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

PREFIX = "maya://model/"


def short(urn: str) -> str:
    """The path segment for a URN. `maya://model/x.y` and `x.y` both work.

    Accepting both is not sloppiness: a caller reads the full URN off a warrant
    or a document and the short name off a URL, and making them convert would
    produce a 404 whose cause is a string format rather than a missing model.
    """
    return urn[len(PREFIX):] if urn.startswith(PREFIX) else urn


class Models:
    """Register, read and move a model through its lifecycle."""

    def __init__(self, maya):
        self._maya = maya

    def register(self, *, urn: str, name: str, model_class: str, domain: str,
                 owner: str, legal_entity: str, purpose: str,
                 description: str = "", origin: str = "internal") -> Dict[str, Any]:
        return self._maya.call("POST", "/models", json={
            "urn": urn, "name": name, "model_class": model_class,
            "domain": domain, "owner": owner, "legal_entity": legal_entity,
            "purpose": purpose, "description": description, "origin": origin})

    def get(self, urn: str) -> Dict[str, Any]:
        """The model with its versions, aliases, findings and evidence."""
        return self._maya.call("GET", f"/models/{short(urn)}")

    def list(self, *, domain: Optional[str] = None, tier: Optional[int] = None,
             q: Optional[str] = None, limit: Optional[int] = None,
             offset: Optional[int] = None) -> Dict[str, Any]:
        """The inventory, filtered to what this principal may see.

        The filtering happens on the platform, not here. A count that does not
        add up is how an out-of-scope model becomes discoverable, so the SDK
        never post-filters a listing.
        """
        return self._maya.call("GET", "/models", params={
            "domain": domain, "tier": tier, "q": q,
            "limit": limit, "offset": offset})

    def assess(self, urn: str, *, exposure: float, purpose_class: str,
               feature_count: Optional[int] = None,
               uses_alternative_data: Optional[bool] = None,
               interpretable: Optional[bool] = None) -> Dict[str, Any]:
        """Assess the risk tier. Returns the derivation, not just a number.

        Worth reading rather than discarding: it names which facts were used,
        which bands they fell in, the control set that follows, and the ruleset
        version that decided. A tier without its derivation is an opinion.

        The three complexity facts are optional here and omitted from the
        request when you do not pass them, rather than sent at their low-risk
        default. That distinction is the point: this method used to send only
        exposure and purpose, and the server's schema filled in "under fifty
        features, no alternative data, interpretable" — three declarations
        nobody made, each of which lowers the tier. MAYA now refuses the
        assessment when the omission would change the answer, and tells you
        which fact to send.
        """
        facts: Dict[str, Any] = {"exposure": exposure,
                                 "purpose_class": purpose_class}
        if feature_count is not None:
            facts["feature_count"] = feature_count
        if uses_alternative_data is not None:
            facts["uses_alternative_data"] = uses_alternative_data
        if interpretable is not None:
            facts["interpretable"] = interpretable
        return self._maya.call("POST", f"/models/{short(urn)}/assess", json=facts)

    def submit(self, urn: str, *, note: str = "") -> Dict[str, Any]:
        return self._maya.call("POST", f"/models/{short(urn)}/submit",
                               json={"note": note})

    def approve(self, urn: str, *, note: str = "") -> Dict[str, Any]:
        return self._maya.call("POST", f"/models/{short(urn)}/approve",
                               json={"note": note})

    def attest(self, urn: str, *, role: str) -> Dict[str, Any]:
        """Sign the attestation quorum for one role you actually hold."""
        return self._maya.call("POST", f"/models/{short(urn)}/attest",
                               json={"role": role})

    def relate(self, *, from_urn: str, to_urn: str, kind: str,
               note: str = "") -> Dict[str, Any]:
        """Record a relation. `derives_from` and `input_to` do different work.

        `derives_from` says where a model came from and does **not** propagate;
        `input_to` says what breaks when it changes and does. Answering both with
        one edge makes both answers wrong.
        """
        return self._maya.call("POST", "/model-relations", json={
            "from_urn": from_urn, "to_urn": to_urn, "kind": kind, "note": note})

    def blast_radius(self, urn: str) -> Dict[str, Any]:
        """What breaks if this changes. Only propagating edges are followed."""
        return self._maya.call("POST", "/blast-radius", json={"urn": urn})

    def shared_dependencies(self, urns: List[str]) -> Dict[str, Any]:
        """What these models both rest on.

        Two models fed by the same curve are not two independent risks, which is
        why an aggregate figure cannot simply add up.
        """
        return self._maya.call("POST", "/shared-dependencies", json={"urns": urns})


class Versions:
    """Immutable kernels, and the alias that decides which one runs."""

    def __init__(self, maya):
        self._maya = maya

    def create(self, urn: str, *, semver: str, kernel: Dict[str, Any],
               contract: Optional[Dict[str, Any]] = None,
               artifact_digest: Optional[str] = None,
               artifact_uri: Optional[str] = None) -> Dict[str, Any]:
        """Create a version. It is immutable from this moment.

        `artifact_uri` may be left out when the digest names something MAYA
        holds: the store is the authority on its own contents and fills in the
        uri, the size and the format itself.

        The trainability class is **derived** from `parameter_kind` and
        `fit_procedure` in the kernel. Declaring it here would be declaring a
        conclusion, and the SDK has no business holding an opinion about it.
        """
        return self._maya.call("POST", f"/models/{short(urn)}/versions", json={
            "semver": semver, "kernel": kernel, "contract": contract or {},
            "artifact_digest": artifact_digest, "artifact_uri": artifact_uri})

    def list(self, urn: str) -> List[Dict[str, Any]]:
        return self._maya.call("GET", f"/models/{short(urn)}").get("versions", [])

    def approve(self, urn: str, semver: str, *, note: str = "") -> Dict[str, Any]:
        """Approve directly. A Tier 1 or 2 version needs a quorum instead."""
        return self._maya.call(
            "POST", f"/models/{short(urn)}/versions/{semver}/approve",
            json={"note": note})

    def open_quorum(self, *, urn: str, semver: str) -> Dict[str, Any]:
        """Open a version approval two people in two roles must sign."""
        return self._maya.call("POST", "/version-approvals",
                               json={"urn": urn, "semver": semver})

    def sign_quorum(self, approval_id: str, *, role: str,
                    statement: str = "") -> Dict[str, Any]:
        """Sign for one role. The same person may not sign twice under two hats.

        The rationale is `statement`, which is what the endpoint reads. This sent
        `note`, and the endpoint dropped it — the signature recorded, the reason
        for it vanished, and both sides reported success. A quorum signature with
        no reasoning is most of what a quorum is for.

        The keyword is renamed rather than aliased. Accepting `note` and quietly
        mapping it would keep working for the one caller who wrote it and stay
        wrong for everyone reading the signature afterwards; a TypeError is the
        loud version of the same news.
        """
        return self._maya.call("POST", f"/version-approvals/{approval_id}/sign",
                               json={"role": role, "statement": statement})

    def promote(self, urn: str, *, semver: str, environment: str = "prod",
                alias: str = "champion", justification: str = "") -> Dict[str, Any]:
        """Move an alias — the most dangerous operation here.

        It is a proof obligation rather than a write: the replacement's contract
        must refine the incumbent's (L-7) and its schemas must satisfy variance
        (L-12), or the move is refused naming the clause. Consumers hold the URN
        and are neither redeployed nor broken.
        """
        return self._maya.call("PUT", f"/models/{short(urn)}/aliases", json={
            "semver": semver, "environment": environment, "alias": alias,
            "justification": justification})


class Limitations:
    """What a version cannot do, stated where it can be counted.

    The register had no client surface at all, so every case study in this
    repository wrote its limitations into a free-text `diagnostics` blob on a
    parameter set — where nothing can count them, compare them between two
    versions, or answer the question the register exists for: *which of these
    are enforced, and which are only written down?*
    """

    def __init__(self, maya):
        self._maya = maya

    def kinds(self) -> Dict[str, Any]:
        """The four kinds and what each is for. Closed on purpose."""
        return self._maya.call("GET", "/limitation-kinds")

    def record(self, *, urn: str, semver: str, kind: str, statement: str,
               basis: str = "", bound_key: Optional[str] = None,
               owner: str = "", materiality: str = "moderate",
               mitigation: str = "",
               review_due: Optional[float] = None) -> Dict[str, Any]:
        """State one against a version.

        `bound_key` names the contract clause that enforces it, and is checked
        against that version's own contract rather than accepted — a limitation
        claiming an enforcement that does not exist reads as the safe case and
        is not.
        """
        return self._maya.call("POST", "/limitations", json={
            "urn": urn, "semver": semver, "kind": kind,
            "statement": statement, "basis": basis, "bound_key": bound_key})

    def for_version(self, urn: str, semver: str) -> Dict[str, Any]:
        return self._maya.call("GET", "/limitations",
                               params={"urn": urn, "semver": semver})

    def across_the_estate(self) -> Dict[str, Any]:
        """Every standing limitation on every model. No urn, on purpose: the
        question this register exists for is an estate question."""
        return self._maya.call("GET", "/limitations")

    def withdraw(self, limitation_id: str, *, reason: str) -> Dict[str, Any]:
        """Withdrawn, never deleted. The version is immutable, so what it was
        understood to be is part of the record."""
        return self._maya.call("POST", f"/limitations/{limitation_id}/withdraw",
                               json={"reason": reason})


class Assumptions:
    """What a version relies on being true — the sibling of `Limitations`.

    The distinction decides which register a statement belongs in, and it is
    not a matter of taste. A limitation is a boundary of competence and cannot
    stop being true. An assumption is a claim about the world the model reads
    and **can stop being true while the model runs** — which is why this
    register counts what is *monitored* rather than what is *enforced*.
    """

    def __init__(self, maya):
        self._maya = maya

    def kinds(self) -> Dict[str, Any]:
        """The five kinds and the four materialities."""
        return self._maya.call("GET", "/assumption-kinds")

    def record(self, *, urn: str, semver: str, kind: str, statement: str,
               basis: str = "", monitor_id: Optional[str] = None,
               owner: str = "", materiality: str = "moderate",
               mitigation: str = "", review_due: Optional[float] = None,
               finding_id: Optional[str] = None,
               overlay_id: Optional[str] = None) -> Dict[str, Any]:
        """State one against a version.

        Send `monitor_id` where something actually tests the assumption. It is
        checked against the monitors that exist AND against the model they are
        on: an assumption watched by another model's monitor is unwatched, and
        reads as watched.

        `materiality` and `mitigation` are what make the register sortable. A
        `material` assumption with no monitor and no mitigation is the row the
        estate screen puts at the top, and it is not a documentation gap — it
        is a decision nobody has taken.
        """
        return self._maya.call("POST", "/assumptions", json={
            "urn": urn, "semver": semver, "kind": kind,
            "statement": statement, "basis": basis, "monitor_id": monitor_id,
            "owner": owner, "materiality": materiality,
            "mitigation": mitigation, "review_due": review_due,
            "finding_id": finding_id, "overlay_id": overlay_id})

    def for_version(self, urn: str, semver: str) -> Dict[str, Any]:
        return self._maya.call("GET", "/assumptions",
                               params={"urn": urn, "semver": semver})

    def across_the_estate(self) -> Dict[str, Any]:
        """Every standing assumption on every model, worst read first."""
        return self._maya.call("GET", "/assumptions")

    def withdraw(self, assumption_id: str, *, reason: str) -> Dict[str, Any]:
        """Withdrawn, never deleted — *we used to believe the sector mix was
        stable* is exactly the sentence a post-mortem needs to find."""
        return self._maya.call("POST", f"/assumptions/{assumption_id}/withdraw",
                               json={"reason": reason})
