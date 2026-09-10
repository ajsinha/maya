"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The register as it stood on a date that has passed.

This is the question every examination opens with — *what did your inventory say
about this model in March* — and the one a register built out of mutable rows
cannot answer, because the rows have since been updated. Delta time travel gives
it for feature *data*; nothing gave it for the register itself, and `docs/03`
called that the largest single gap.

The answer was already in the building. The evidence chain is append-only,
hash-linked and records every act that changes the register, so the register at
a moment is a **fold of the chain up to that moment**. Nothing new has to be
stored, no history table has to be maintained in parallel, and — the part that
matters most — the answer carries the **chain hash at that sequence**, so it is
verifiable rather than merely asserted. A projection somebody could have
rewritten is not evidence, and the whole point of doing this from the chain
instead of from an audit table is that the chain cannot be rewritten without
every hash after the edit disagreeing.

**What it projects and what it will not.** It folds what the chain actually
carries: existence, owner, lifecycle status, tier, versions and their classes,
which versions were approved, and which version each environment's alias pointed
at. It does **not** invent the fields the chain does not carry — every projected
model names them under `not_projected`, because *we do not know what the purpose
field said in March* is an answer and a confidently wrong purpose is not.

That list is also a to-do list. Each entry in it is a payload that could carry
one more field, and the honest way to close it is one field at a time, at the
point of the act, rather than by adding a shadow copy of the register that
drifts from it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

#: How each lifecycle act moves the record. The chain records `from` and `to`
#: on every one of them, so the fold does not need this map to know the answer
#: — it needs it to know which kinds are lifecycle acts at all.
LIFECYCLE_KINDS: Tuple[str, ...] = (
    "model_submit", "model_approve", "model_attest", "model_amend",
    "model_retire", "model_send_back", "model_baseline",
)

#: What the chain does not carry, per model, and therefore what a projection
#: cannot honestly answer. Named in the answer rather than omitted from it.
NOT_PROJECTED: Tuple[str, ...] = (
    "purpose", "description", "model_class", "domain", "legal_entity",
    "designations", "attributes",
)


class AsAtProjection:
    """Folds the evidence chain into the register as it stood at a moment."""

    def __init__(self, evidence, registry=None):
        self.evidence, self.registry = evidence, registry

    # ------------------------------------------------------------------ fold
    def register(self, moment: float) -> Dict[str, Any]:
        """Every model as it stood, and the chain position that proves it."""
        # `repo.many()` returns the chain in sequence order, which is the
        # order it has to be folded in: two acts in the same second are still
        # ordered, and folding by timestamp would make that ordering the
        # database's business rather than the chain's.
        nodes = [n for n in self.evidence.repo.many()
                 if (n.get("recorded_at") or 0) <= moment]
        models: Dict[str, Dict[str, Any]] = {}
        versions_of: Dict[str, str] = {}      # version id -> model id

        for node in nodes:
            self._apply(node, models, versions_of)

        alive = [m for m in models.values() if not m["deleted"]]
        alive.sort(key=lambda m: m.get("urn") or "")
        seq, chain_hash = self._position(nodes)
        return {
            "as_at": moment, "models": alive, "count": len(alive),
            "chain_seq": seq, "chain_hash": chain_hash,
            "nodes_folded": len(nodes),
            "not_projected": list(NOT_PROJECTED),
            "detail": self._detail(alive, seq, chain_hash),
        }

    def model(self, urn: str, moment: float) -> Dict[str, Any]:
        """One model as it stood. The same fold, filtered."""
        whole = self.register(moment)
        found = next((m for m in whole["models"] if m.get("urn") == urn), None)
        if found is None:
            return {
                "as_at": moment, "urn": urn, "existed": False,
                "chain_seq": whole["chain_seq"],
                "chain_hash": whole["chain_hash"],
                "detail": (f"nothing in the chain up to this moment registers "
                           f"{urn}. Either it did not exist yet, or it was "
                           f"registered and deleted before it"),
            }
        return {"as_at": moment, "existed": True,
                "chain_seq": whole["chain_seq"],
                "chain_hash": whole["chain_hash"],
                "not_projected": list(NOT_PROJECTED), **found}

    # ---------------------------------------------------------------- events
    def _apply(self, node: Dict[str, Any], models: Dict[str, Dict[str, Any]],
               versions_of: Dict[str, str]) -> None:
        kind = node.get("kind")
        subject = node.get("subject_id") or ""
        payload = node.get("payload") or {}

        if kind == "model_registered":
            models[subject] = {
                "model_id": subject, "urn": payload.get("urn"),
                "owner": payload.get("owner"), "status": "draft",
                "tier": None, "versions": {}, "aliases": {},
                "deleted": False,
                "registered_at": node.get("recorded_at"),
            }
            return

        if kind == "model_deleted" and subject in models:
            models[subject]["deleted"] = True
            return

        if kind in LIFECYCLE_KINDS and subject in models:
            # The chain records `to` on every transition, so the fold reads the
            # act's own answer rather than re-deriving it from a state machine
            # that may since have changed.
            if payload.get("to"):
                models[subject]["status"] = payload["to"]
            return

        if kind == "tier_assigned" and subject in models:
            models[subject]["tier"] = payload.get("tier")
            return

        if kind == "alias_moved" and subject in models:
            environment = payload.get("environment") or "prod"
            models[subject]["aliases"][environment] = {
                "alias": payload.get("alias"), "semver": payload.get("to")}
            return

        if kind == "version_created":
            owner = self._owner_of_version(node, payload, models, versions_of)
            if owner:
                versions_of[subject] = owner
                models[owner]["versions"][payload.get("semver")] = {
                    "semver": payload.get("semver"),
                    "trainability_class": payload.get("trainability_class"),
                    "digest": payload.get("digest"),
                    "status": "draft",
                    "created_at": node.get("recorded_at"),
                }
            return

        if kind == "version_approved":
            owner = versions_of.get(subject)
            if owner and payload.get("semver") in models[owner]["versions"]:
                models[owner]["versions"][payload["semver"]]["status"] = "approved"
            return

    def _owner_of_version(self, node: Dict[str, Any], payload: Dict[str, Any],
                          models: Dict[str, Dict[str, Any]],
                          versions_of: Dict[str, str]) -> Optional[str]:
        """Which model a version node belongs to.

        The urn is on the payload, so this is a pure fold — which is the point:
        a fold cannot look anything up, and asking the register would mean a
        model deleted since silently lost its versions from its own history.

        Nodes recorded before the urn was carried fall back to asking the
        register, which is the honest hybrid rather than pretending an older
        chain says something it does not. Those are the nodes where a deletion
        does lose the link, and it is better to say so here than to have the
        projection quietly show a model that had no versions.
        """
        urn: Optional[str] = payload.get("urn")
        if urn:
            for model_id, model in models.items():
                if model.get("urn") == urn:
                    return model_id
            return None
        if self.registry is None:
            return None
        row = self.registry.version_by_id(node.get("subject_id") or "")
        if not row:
            return None
        found: Optional[str] = (
            self.registry.get(row.get("urn") or "") or {}).get("id")
        return found if found in models else None

    # --------------------------------------------------------------- shaping
    @staticmethod
    def _position(nodes: List[Dict[str, Any]]) -> Tuple[Optional[int], Optional[str]]:
        """The chain sequence and hash this projection is true at.

        The reason to answer from the chain rather than from an audit table.
        A projection somebody could have rewritten is not evidence; this one
        names the hash at its own end, and the chain cannot be rewritten without
        every hash after the edit disagreeing.
        """
        if not nodes:
            return None, None
        last = nodes[-1]
        return last.get("seq"), last.get("chain_hash")

    @staticmethod
    def _detail(models: List[Dict[str, Any]], seq: Optional[int],
                chain_hash: Optional[str]) -> str:
        if seq is None:
            return ("nothing had been recorded by this moment — the register "
                    "did not exist yet")
        attested = sum(1 for m in models if m["status"] == "attested")
        return (f"{len(models)} model(s), {attested} of them attested, as at "
                f"chain sequence {seq} (hash {str(chain_hash)[:16]}…). The hash "
                f"is what makes this evidence rather than an assertion: the "
                f"chain cannot be rewritten without every hash after the edit "
                f"disagreeing")
