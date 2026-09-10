"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The feature catalogue: definitions, duplicate detection, certification.

Feature sprawl is what makes a large store unusable — the fourth
``customer_income_v2_final`` is not a data problem, it is a discovery problem.
So near-duplicates surface at the moment of creation, when renaming is still
cheap, rather than in an audit two years later.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.evidence import EvidenceEngine
from core.features import shapes
from core.features.assertions import validate as validate_assertions
from core.features.common import FeatureError
from core.features.composition import Resolver
from core.features.lifecycle import Lifecycle
from core.classification import common as classification
from core.log import get_logger
from core.features import policy
from db import FeatureRepository

logger = get_logger(__name__)


LEVELS = ("experimental", "certified", "deprecated")
SIMILARITY_FLOOR = 0.25


class FeatureCatalogue:
    """Feature definitions and their certification state."""

    def __init__(self, features: FeatureRepository, evidence: EvidenceEngine):
        self.features, self.evidence = features, evidence
        self.lifecycle = Lifecycle(evidence, "feature")
        # Components fold the same way a featureset's slots do, so the machinery
        # is shared and the two cannot drift apart in behaviour.
        self.resolver = Resolver(self._load, self._own_components,
                                 what="component", noun="feature")

    def define(self, name: str, entity: str, dtype: str, description: str, owner: str,
               business_definition: str = "", source_system: str = "",
               sensitivity: str = "internal", pii: bool = False,
               protected_basis: bool = False, proxy_risk: str = "none",
               shape: Any = None, components: Optional[Sequence[str]] = None,
               composes: Optional[Sequence[Any]] = None,
               operations: Optional[Sequence[Dict[str, Any]]] = None,
               ephemeral: bool = False, ttl_days: Optional[float] = None,
               defaults: Optional[Dict[str, Any]] = None,
               assertions: Optional[List[Dict[str, Any]]] = None,
               actor: str = "system") -> Dict[str, Any]:
        if self.features.one(name=name):
            raise FeatureError(f"feature '{name}' is already defined")
        # Closed here rather than anywhere downstream. `sensitivity` was free
        # text, displayed on one screen and read by nothing — and a lattice
        # over free text is a lattice over nothing, because 'Confidential',
        # 'confidential' and 'CONF' are three classes to a computer and one to
        # a person. Nothing can propagate a class until the class is a value.
        try:
            sensitivity = classification.normalise(sensitivity)
        except classification.ClassificationError as refused:
            # Translated rather than propagated: a caller defining a feature
            # should meet a FeatureError, not a refusal type from a subsystem
            # it has never heard of. Logged because the translation loses the
            # original code, and a refusal is a governance decision.
            logger.warning("feature '%s' refused: %s", name, refused.code)
            raise FeatureError(refused.detail) from refused
        dims = shapes.parse(shape)
        named = shapes.check_components(dims, components)
        row = {"name": name, "entity": entity, "dtype": dtype, "description": description,
               "business_definition": business_definition, "owner": owner,
               "created_by": actor,
               "source_system": source_system, "sensitivity": sensitivity,
               "pii": int(pii), "protected_basis": int(protected_basis),
               "proxy_risk": proxy_risk, "certification": "experimental",
               "shape": list(dims), "components": named,
               "composes": self._stamp(composes),
               "operations": list(operations or []),
               "definition_version": 1,
               "defaults": policy.check(defaults),
               # Validated rather than stored as given: an assertion the
               # platform silently dropped would be one somebody believes is
               # running on every load.
               "assertions": validate_assertions(assertions),
               "ephemeral": int(ephemeral),
               "expires_at": (self.lifecycle.expiry(ttl_days) if ephemeral
                              else None),
               "created_at": time.time()}
        self.features.add(row)
        stored = self.features.one(id=row["id"])
        if row["composes"] or row["operations"]:
            # Resolved once here so a composition that cannot resolve is refused
            # now rather than the first time somebody reads it — but NOT written
            # back. The row holds what this feature declares; resolution is a
            # read-time act, and storing its result would apply the operations
            # a second time on the next read.
            self.resolve(stored)
        self.evidence.append("feature_defined", "feature", row["id"],
                             {"name": name, "entity": entity,
                              "shape": list(dims),
                              "composes": [c if isinstance(c, str) else c.get("name")
                                           for c in row["composes"]],
                              "ephemeral": ephemeral}, actor=actor)
        return stored

    # -------------------------------------------------------------- composition
    def _stamp(self, composes: Optional[Sequence[Any]]) -> List[Dict[str, Any]]:
        """Record which DEFINITION of each parent this was composed against.

        A feature's definition is amendable, and an amendment advances its
        definition version. Without recording which one a child resolved
        against, amending a parent would silently change every child — a stable
        identifier over moving contents, which is adversarial finding C-2 in a
        third costume. The version is stamped here so drift can be reported.
        """
        out = []
        for parent in composes or []:
            spec = {"name": parent} if isinstance(parent, str) else dict(parent)
            row = self.features.one(name=spec.get("name"))
            if row is None:
                raise FeatureError(
                    f"cannot compose from '{spec.get('name')}': no such feature")
            spec.setdefault("definition_version",
                            row.get("definition_version") or 1)
            out.append(spec)
        return out

    def _load(self, name: str, version: Optional[int]) -> Optional[Dict[str, Any]]:
        """The parent as it stands. Drift against the stamped version is
        reported by ``resolved`` rather than raised here: a child whose parent
        has moved is a thing to be told about, not a read that should fail."""
        return self.features.one(name=name)

    def drift(self, row: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parents whose definition has moved since this feature composed them."""
        moved = []
        for parent in row.get("composes") or []:
            spec = {"name": parent} if isinstance(parent, str) else parent
            current = self.features.one(name=spec.get("name"))
            if current is None:
                continue
            was = spec.get("definition_version")
            now = current.get("definition_version") or 1
            if was is not None and now != was:
                moved.append({"parent": spec["name"], "composed_against": was,
                              "now_at": now,
                              "sealed": bool(current.get("sealed_at"))})
        return moved

    @staticmethod
    def _own_components(row: Dict[str, Any]) -> Dict[str, Any]:
        """A feature's own contribution: its named components, as a keyed map."""
        return {c: {"dtype": row.get("dtype"), "from": row.get("name")}
                for c in (row.get("components") or [])}

    def _parents(self, row: Dict[str, Any]) -> List[Dict[str, Any]]:
        """The parent rows, in fold order, for explaining where a policy came from."""
        out = []
        for parent in row.get("composes") or []:
            spec = {"name": parent} if isinstance(parent, str) else parent
            found = self.features.one(name=spec.get("name"))
            if found:
                out.append(found)
        return out

    def resolve(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """The components this feature actually has, parents included."""
        return self.resolver.resolve(row)

    def resolved(self, name: str) -> Dict[str, Any]:
        """What a caller asking for this feature should be told it is.

        The whole point of composition is that the answer is not what the row
        says; it is what the row plus its parents plus its own operations say.
        Working that out is MAYA's job and not the caller's.
        """
        row = self.require(name)
        members = self.resolve(row)
        declared = shapes.parse(row.get("shape") or [])
        # The first axis follows the components: composing a tenor onto a curve
        # makes it longer, and a shape that disagreed would be the stale half.
        effective = ((len(members),) + tuple(declared[1:])) if members else declared
        return {
            # Insertion order, never sorted. For a vector the component order IS
            # the axis order — a curve whose tenors came back alphabetically
            # would be a different curve, and one nobody would notice was wrong.
            **row, "components": list(members),
            "shape": list(effective),
            "dimensionality": shapes.describe(effective, list(members)),
            "lineage": self.resolver.lineage(row),
            "provenance": self.resolver.explain(row) if row.get("composes") else {},
            "ownership": self.lifecycle.provenance(row),
            "policy": policy.explain(row, self._parents(row)),
            "lifetime": self.lifecycle.remaining(row),
            "sealed": bool(row.get("sealed_at")),
            "drift": self.drift(row),
        }

    def get(self, name: str) -> Dict[str, Any]:
        return self.features.one(name=name)

    def require(self, name: str) -> Dict[str, Any]:
        row = self.get(name)
        if not row:
            raise FeatureError(f"no feature '{name}'")
        return row

    def list(self, **filters) -> List[Dict[str, Any]]:
        return self.features.many(**filters)

    def missing(self, names: List[str]) -> List[str]:
        """Which of these features are not defined. Used before building a view."""
        return [n for n in names if not self.features.one(name=n)]

    def similar(self, name: str, description: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Cheap duplicate detection by token overlap.

        Deliberately not embeddings: the point is to be fast enough to run on
        every keystroke of a definition form, and explainable enough that a
        steward can see why two features were called alike.
        """
        words = self._tokens(name, description)
        scored = []
        for f in self.features.many():
            overlap = self._jaccard(words, self._tokens(f["name"], f["description"]))
            if overlap > SIMILARITY_FLOOR:
                scored.append((overlap, f))
        return [f for _, f in sorted(scored, key=lambda t: -t[0])[:limit]]

    @staticmethod
    def _tokens(name: str, description: str) -> set:
        return set(description.lower().split()) | set(name.lower().replace("_", " ").split())

    @staticmethod
    def _jaccard(a: set, b: set) -> float:
        return len(a & b) / max(len(a | b), 1)

    def certify(self, name: str, level: str = "certified") -> Dict[str, Any]:
        if level not in LEVELS:
            raise FeatureError(f"unknown certification level '{level}'; "
                               f"expected one of {', '.join(LEVELS)}")
        self.require(name)
        self.features.set({"certification": level}, name=name)
        return self.features.one(name=name)

    # ---------------------------------------------------------------- lifecycle
    def seal(self, name: str, actor: str, note: str = "") -> Dict[str, Any]:
        """Declare a feature final. It can still be composed from — that is why."""
        row = self.require(name)
        self.features.set(self.lifecycle.seal(row, actor, note), id=row["id"])
        return self.features.one(id=row["id"])

    def break_seal(self, name: str, actor: str, reason: str) -> Dict[str, Any]:
        row = self.require(name)
        self.features.set(self.lifecycle.break_seal(row, actor, reason),
                          id=row["id"])
        return self.features.one(id=row["id"])

    def transfer(self, name: str, to: str, actor: str,
                 reason: str = "") -> Dict[str, Any]:
        """Hand on the responsibility. The creator does not move; they are history."""
        row = self.require(name)
        self.features.set(self.lifecycle.transfer(row, to, actor, reason),
                          id=row["id"])
        return self.features.one(id=row["id"])

    def amend(self, name: str, fields: Dict[str, Any],
              actor: str = "system") -> Dict[str, Any]:
        """Change a feature's definition, which a sealed one refuses.

        Every amendment advances the definition version, because somebody may
        already have composed against the previous one and a composition pins.
        """
        row = self.require(name)
        self.lifecycle.refuse_if_sealed(row, "be amended")
        allowed = {"description", "business_definition", "source_system",
                   "sensitivity", "proxy_risk", "shape", "components",
                   "composes", "operations", "defaults"}
        if unknown := sorted(set(fields) - allowed):
            raise FeatureError(
                f"these fields are not amendable: {', '.join(unknown)}. a "
                f"feature's name, entity and type are what other things pinned "
                f"it by; changing them would be a new feature wearing an old name")
        patch = dict(fields)
        if "defaults" in patch:
            patch["defaults"] = policy.check(patch["defaults"])
        if "shape" in patch or "components" in patch:
            dims = shapes.parse(patch.get("shape", row.get("shape")))
            patch["shape"] = list(dims)
            patch["components"] = shapes.check_components(
                dims, patch.get("components", row.get("components")))
        patch["definition_version"] = (row.get("definition_version") or 1) + 1
        with self.evidence.recording():
            self.features.set(patch, id=row["id"])
            self.evidence.append("feature_amended", "feature", row["id"],
                                 {"name": name, "changed": sorted(fields),
                                  "definition_version": patch["definition_version"]},
                                 actor=actor)
        return self.features.one(id=row["id"])

    def retire(self, name: str, reason: str,
               actor: str = "system") -> Dict[str, Any]:
        """Take a durable feature out of use without erasing it.

        The act the refusals have named since they were written, and which
        nothing implemented. `destroy` on a durable feature says "it is not
        destroyed but retired" and there was no retire endpoint anywhere — so a
        feature created by mistake could never be removed, and the two refusals
        pointed at each other: delete the featureset and you are told to remove
        what refers to it; delete the feature and you are told to correct the
        view version.

        The row stays, because something composed from it and a definition that
        stops existing makes every historical reference unreadable. What
        changes is that it can no longer be composed from, and the catalogue
        says who retired it and why.
        """
        row = self.require(name)
        if row.get("retired_at"):
            raise FeatureError(
                f"'{name}' was already retired by {row.get('retired_by')}",
                remediation="define a new feature if this one is needed again")
        if not (reason or "").strip():
            raise FeatureError(
                f"retiring '{name}' needs a reason; a feature that leaves the "
                f"catalogue without one is a decision nobody can review",
                remediation="say why it is being retired")
        with self.evidence.recording():
            self.features.set({"retired_at": time.time(), "retired_by": actor,
                               "retire_reason": reason.strip()}, id=row["id"])
            self.evidence.append("feature_retired", "feature", row["id"],
                                 {"name": name, "reason": reason.strip()},
                                 actor=actor)
        return self.features.one(id=row["id"])

    def destroy(self, name: str, why: str = "expired",
                actor: str = "system") -> Dict[str, Any]:
        """Remove an ephemeral feature. The rows go; the record does not."""
        row = self.require(name)
        if not row.get("ephemeral"):
            raise FeatureError(
                f"'{name}' is not ephemeral, so it is not destroyed but retired; "
                f"a durable feature that something composed from cannot simply "
                f"stop existing. Retire it instead: "
                f"POST /api/v1/features/{name}/retire with a reason",
                remediation=f"POST /api/v1/features/{name}/retire")
        self.lifecycle.record_destruction(row, why, actor=actor)
        self.features.remove(id=row["id"])
        return {"name": name, "destroyed": True, "why": why}

    def expired(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """Ephemeral features that have outlived their declared lifetime."""
        from core.features.lifecycle import reap
        return reap(self.features.many(), now)
