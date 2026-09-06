"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Featuresets: a named, versioned presentation of X.

A model is ``f : P × X → D(Y)``. Until now X existed only as a list buried inside
one model version's feature contract — unnameable, unshareable, and impossible to
compare across models. A featureset makes it an object.

The load-bearing idea is the separation of schema from constituents.

**A featureset declares a schema**: named slots, each with a type. That schema is
what a kernel is defined over.

**A version fills the schema**: each slot names a feature *and* the feature view
version supplying its values.

So ``inflation@v1`` may bind ``daily_index`` to DAILY_INFLATION and ``@v2`` bind
it to EUHICP, and a model reading ``daily_index`` does not change. And a version
that *cannot* fill the schema is refused — it is not a new version of this set,
it is a different set, or it is a model change, and MAYA decides which rather
than leaving somebody to remember.

Every binding pins the view version. A set that named views without pinning them
would resolve to different bytes next month with its digest unchanged — which is
adversarial finding C-2 exactly, one level out from the view.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.domain.schemas import Field, Schema
from core.evidence import EvidenceEngine
from core.features.common import INGEST_TIME, VALID_TIME, FeatureError
from core.features.composition import Resolver
from core.features.lifecycle import Lifecycle
from core.features import policy
from core.log import get_logger
from db import FeaturesetRepository, FeaturesetVersionRepository
from db.database import digest as canonical_digest

logger = get_logger(__name__)

# The point-in-time rule every featureset asserts. Stated once, here, rather than
# re-declared in every warrant that reads one.
# The rule an execution engine is handed, and it must be the rule MAYA's own
# assembly applies. It said `ingest_ts <= as_of`, which is the rule from BEFORE
# the `min` was added — so an engine implementing the published string admitted
# rows MAYA itself refuses, and the disagreement would have surfaced as a
# reproducibility failure nobody could locate.
#
# The bound is `min(label_ts, as_of)` because the two clocks refuse different
# things: `label_ts` is what the model could have known when the decision was
# made, and `as_of` is what the platform could have known when the set was
# built. Taking the earlier of the two is what makes a read at any `as_of` at or
# after the label give the same answer (L-10).
PIT_RULE = (f"{VALID_TIME} <= label_ts AND "
            f"{INGEST_TIME} <= min(label_ts, as_of)")


class FeaturesetRegistry:
    """Declares featuresets, publishes versions, and resolves them to bytes."""

    def __init__(self, sets: FeaturesetRepository,
                 versions: FeaturesetVersionRepository,
                 catalogue, views, derived, evidence: EvidenceEngine):
        self.sets, self.versions = sets, versions
        self.catalogue, self.views = catalogue, views
        self.derived, self.evidence = derived, evidence
        self.lifecycle = Lifecycle(evidence, "featureset")
        # The same fold as a feature's components, over slots instead. Sharing
        # it is what keeps "a combination of featuresets is a featureset" and
        # "a combination of features is a feature" the same statement.
        self.resolver = Resolver(lambda n, v: self.sets.one(name=n),
                                 lambda row: row.get("slots") or {},
                                 what="slot", noun="featureset")

    # ----------------------------------------------------------------- define
    def define(self, name: str, entity: str, owner: str, slots: Dict[str, Any],
               label_slot: Optional[str] = None, outcome_window_days: int = 0,
               grain: str = "", description: str = "",
               composes: Optional[Sequence[Any]] = None,
               operations: Optional[Sequence[Dict[str, Any]]] = None,
               ephemeral: bool = False, ttl_days: Optional[float] = None,
               defaults: Optional[Dict[str, Any]] = None,
               actor: str = "system") -> Dict[str, Any]:
        """Declare the schema. Constituents come later, with a version.

        A featureset composed from others inherits their slots by the same
        left-to-right fold a feature's components use, so it may declare none of
        its own and still have a schema.
        """
        if self.sets.one(name=name):
            raise FeatureError(f"featureset '{name}' already exists")
        if not slots and not composes:
            raise FeatureError(
                f"'{name}' declares no slots; a featureset is a schema, and a "
                f"schema with nothing in it is not one")
        normalised = {k: self._slot(k, v) for k, v in (slots or {}).items()}
        if outcome_window_days < 0:
            raise FeatureError("an outcome window cannot be negative")
        row = {"name": name, "entity": entity, "owner": owner,
               "description": description, "slots": normalised,
               "label_slot": label_slot,
               "outcome_window_days": outcome_window_days,
               "grain": grain or f"one row per {entity}",
               "composes": self._stamp(composes),
               "definition_version": 1,
               "operations": list(operations or []),
               "defaults": policy.check(defaults),
               "ephemeral": int(ephemeral),
               "expires_at": (self.lifecycle.expiry(ttl_days) if ephemeral
                              else None),
               "created_by": actor, "created_at": time.time()}
        # Resolved once here, so a composition that cannot resolve is refused at
        # declaration rather than the first time somebody publishes against it.
        resolved = self.resolver.resolve(row) if (composes or operations) else normalised
        if label_slot and label_slot not in resolved:
            raise FeatureError(
                f"the label slot '{label_slot}' is not one of the slots this "
                f"featureset resolves to")
        self.sets.add(row)
        self.evidence.append("featureset_defined", "featureset", row["id"],
                             {"name": name, "entity": entity,
                              "slots": sorted(normalised), "label": label_slot},
                             actor=actor)
        return self.sets.one(id=row["id"])

    # -------------------------------------------------------------- composition
    def _stamp(self, composes: Optional[Sequence[Any]]) -> List[Dict[str, Any]]:
        """Record which DEFINITION of each parent this was composed against.

        Deliberately the same construction as a feature's, because "a
        combination of featuresets is a featureset" has to mean the same thing
        one level up or it means nothing. Without the stamp a parent whose
        policy is changed silently changes every child that inherits from it --
        a stable identifier over moving contents, which is adversarial finding
        C-2 wearing its fourth costume.
        """
        out = []
        for parent in composes or []:
            spec = {"name": parent} if isinstance(parent, str) else dict(parent)
            row = self.sets.one(name=spec.get("name"))
            if row is None:
                raise FeatureError(
                    f"cannot compose from '{spec.get('name')}': no such featureset")
            spec.setdefault("definition_version",
                            row.get("definition_version") or 1)
            out.append(spec)
        return out

    def drift(self, row: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parents whose definition has moved since this featureset composed them.

        Reported rather than raised, for the same reason as a feature's: a child
        whose parent has moved is a thing to be told about. Refusing the read
        would take the schema away from whoever most needs to look at it.
        """
        moved = []
        for parent in row.get("composes") or []:
            spec = {"name": parent} if isinstance(parent, str) else parent
            current = self.sets.one(name=spec.get("name"))
            if current is None:
                continue
            was = spec.get("definition_version")
            now = current.get("definition_version") or 1
            if was is not None and now != was:
                moved.append({"parent": spec["name"], "composed_against": was,
                              "now_at": now,
                              "sealed": bool(current.get("sealed_at"))})
        return moved

    def preview(self, slots: Optional[Dict[str, Any]] = None,
                composes: Optional[Sequence[Any]] = None,
                operations: Optional[Sequence[Dict[str, Any]]] = None,
                defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """What this featureset WOULD resolve to, without declaring anything.

        Composition, inheritance and overrides are the part of this design
        people get wrong, and they get it wrong for a good reason: the answer is
        not what you typed, it is what your parents plus your operations say.
        Making somebody declare a featureset to find that out means the register
        fills with attempts.

        So this is the same fold `define` runs, with nothing written. It refuses
        exactly what `define` would refuse -- an unknown parent, an operation
        that is a no-op, a cycle, a depth past the limit -- because a preview
        that accepted more than the real thing would be worse than none.
        """
        row = {"name": "(preview)", "slots": {k: self._slot(k, v)
                                              for k, v in (slots or {}).items()},
               "composes": self._stamp(composes),
               "operations": list(operations or []),
               "defaults": policy.check(defaults)}
        resolved = self.resolver.resolve(row)
        own = set(row["slots"]) | {
            op.get("name") for op in row["operations"]
            if op.get("op") in ("add", "override") and op.get("name")}
        parents = self._parents(row)
        return {
            "slots": resolved,
            "declared_slots": sorted(own & set(resolved)),
            "inherited_slots": sorted(set(resolved) - own),
            "lineage": self.resolver.lineage(row),
            "provenance": self.resolver.explain(row) if row["composes"] else {},
            "policy": policy.explain(row, parents),
            "detail": self._preview_detail(resolved, own),
        }

    @staticmethod
    def _preview_detail(resolved: Dict[str, Any], own: set) -> str:
        inherited = len(set(resolved) - own)
        if not resolved:
            return "this resolves to no slots at all, which is not a schema"
        return (f"{len(resolved)} slot(s): {len(set(resolved) & own)} declared here"
                + (f", {inherited} inherited" if inherited else "")
                + ". the order is the fold: leftmost parent first, rightmost "
                  "wins, then this set's own slots, then its operations")

    @staticmethod
    def _slot(name: str, spec: Any) -> Dict[str, Any]:
        """A slot is a type and a nullability. Given a bare string, it is a type."""
        if isinstance(spec, str):
            spec = {"dtype": spec}
        if "dtype" not in spec:
            raise FeatureError(f"slot '{name}' does not say what type it holds")
        return {"dtype": spec["dtype"], "nullable": bool(spec.get("nullable", False))}

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self.sets.one(name=name)

    # -------------------------------------------------------------- resolution
    def slots_of(self, name: str) -> Dict[str, Any]:
        """The slots this featureset actually has, parents included.

        What a caller is told is not what the row says; it is what the row plus
        its parents plus its own operations say. Working that out is MAYA's job.
        """
        return self.resolver.resolve(self.require(name))

    def _parents(self, row: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = []
        for parent in row.get("composes") or []:
            spec = {"name": parent} if isinstance(parent, str) else parent
            found = self.sets.one(name=spec.get("name"))
            if found:
                out.append(found)
        return out

    def resolved(self, name: str,
                 request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Everything a caller needs to know about this featureset as it stands."""
        row = self.require(name)
        members = self.resolver.resolve(row)
        # A slot this featureset added through its own operation is its own,
        # not something it inherited. Calling it inherited would credit a parent
        # with a decision it did not make.
        own = set(row.get("slots") or {}) | {
            op.get("name") for op in (row.get("operations") or [])
            if op.get("op") in ("add", "override") and op.get("name")}
        return {
            **row, "slots": members,
            "declared_slots": sorted(own & set(members)),
            "inherited_slots": sorted(set(members) - own),
            "lineage": self.resolver.lineage(row),
            "provenance": self.resolver.explain(row) if row.get("composes") else {},
            "ownership": self.lifecycle.provenance(row),
            "lifetime": self.lifecycle.remaining(row),
            "sealed": bool(row.get("sealed_at")),
            "policy": policy.explain(row, self._parents(row), request),
            "drift": self.drift(row),
        }

    # --------------------------------------------------------------- lifecycle
    def seal(self, name: str, actor: str, note: str = "") -> Dict[str, Any]:
        row = self.require(name)
        self.sets.set(self.lifecycle.seal(row, actor, note), id=row["id"])
        return self.sets.one(id=row["id"])

    def break_seal(self, name: str, actor: str, reason: str) -> Dict[str, Any]:
        row = self.require(name)
        self.sets.set(self.lifecycle.break_seal(row, actor, reason), id=row["id"])
        return self.sets.one(id=row["id"])

    def transfer(self, name: str, to: str, actor: str,
                 reason: str = "") -> Dict[str, Any]:
        row = self.require(name)
        self.sets.set(self.lifecycle.transfer(row, to, actor, reason), id=row["id"])
        return self.sets.one(id=row["id"])

    def set_policy(self, name: str, defaults: Dict[str, Any],
                   actor: str = "system") -> Dict[str, Any]:
        """Attach default retrieval behaviour, which a request may still override."""
        row = self.require(name)
        self.lifecycle.refuse_if_sealed(row, "have its policy changed")
        checked = policy.check(defaults)
        # This is a definition change, not a note in the margin: a child that
        # inherits from this featureset resolves its retrieval behaviour through
        # here, so the children stamped against the old definition have to be
        # able to find out.
        version = (row.get("definition_version") or 1) + 1
        self.sets.set({"defaults": checked, "definition_version": version},
                      id=row["id"])
        self.evidence.append("featureset_policy_set", "featureset", row["id"],
                             {"name": name, "policy": checked,
                              "definition_version": version}, actor=actor)
        return self.sets.one(id=row["id"])

    def destroy(self, name: str, why: str = "expired",
                actor: str = "system") -> Dict[str, Any]:
        """Remove an ephemeral featureset and its versions. The record stays."""
        row = self.require(name)
        if not row.get("ephemeral"):
            raise FeatureError(
                f"'{name}' is not ephemeral. a durable featureset that a contract "
                f"or a warrant pinned cannot simply stop existing")
        versions = self.versions.many(featureset_id=row["id"])
        self.lifecycle.record_destruction(
            row, why, {"versions": len(versions),
                       "digests": [v["digest"] for v in versions]}, actor)
        for version in versions:
            self.versions.remove(id=version["id"])
        self.sets.remove(id=row["id"])
        return {"name": name, "destroyed": True, "why": why,
                "versions_removed": len(versions)}

    def expired(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        from core.features.lifecycle import reap
        return reap(self.sets.many(), now)

    def require(self, name: str) -> Dict[str, Any]:
        row = self.get(name)
        if row is None:
            raise FeatureError(f"no featureset '{name}'")
        return row

    def list(self) -> List[Dict[str, Any]]:
        return self.sets.many()

    # ---------------------------------------------------------------- publish
    def publish(self, name: str, bindings: Dict[str, Any],
                label: Optional[Dict[str, Any]] = None, note: str = "",
                actor: str = "system") -> Dict[str, Any]:
        """Fill the schema with exact, pinned constituents."""
        featureset = self.require(name)
        self.lifecycle.refuse_if_sealed(featureset, "take another version")
        # The schema to fill is the RESOLVED one: a featureset composed from
        # others owes the slots it inherited as much as the ones it declared.
        slots = self.resolver.resolve(featureset)

        if missing := sorted(set(slots) - set(bindings)):
            raise FeatureError(
                f"these slots are unfilled: {', '.join(missing)}. a version that "
                f"cannot fill the schema is not a version of this featureset")
        if extra := sorted(set(bindings) - set(slots)):
            raise FeatureError(
                f"these bindings name no declared slot: {', '.join(extra)}. "
                f"adding a slot changes the schema, which changes X — publish it "
                f"as a different featureset, and expect the model to need a new "
                f"version")

        # Leakage is checked on what was ASKED FOR, before anything is resolved.
        # A slot computed from the label is refused whether or not its view
        # happens to be materialised, and "you cannot train on the answer" is a
        # better message than "no view supplies that".
        self._refuse_leakage(featureset, bindings, label)

        resolved = {slot: self._resolve(slot, slots[slot], bindings[slot])
                    for slot in slots}
        label_binding = self._resolve_label(featureset, label, resolved)

        number = self._next_version(featureset["id"])
        row = {"featureset_id": featureset["id"], "version": number,
               "bindings": resolved, "label_binding": label_binding,
               "digest": canonical_digest({"bindings": resolved,
                                           "label": label_binding}),
               "note": note, "created_by": actor, "created_at": time.time()}
        self.versions.add(row)
        self.evidence.append("featureset_version_published", "featureset",
                             featureset["id"],
                             {"name": name, "version": number,
                              "digest": row["digest"],
                              "features": sorted(b["feature"] for b in resolved.values())},
                             actor=actor)
        logger.info("published %s@v%d over %d slots", name, number, len(resolved))
        return self.versions.one(id=row["id"])

    def _next_version(self, featureset_id: str) -> int:
        latest = self.versions.latest(featureset_id)
        return (latest["version"] + 1) if latest else 1

    def _resolve(self, slot: str, spec: Dict[str, Any],
                 binding: Any) -> Dict[str, Any]:
        """Turn 'this slot holds that feature' into an exact Delta namespace."""
        if isinstance(binding, str):
            binding = {"feature": binding}
        feature_name = binding.get("feature")
        if not feature_name:
            raise FeatureError(f"slot '{slot}' does not say which feature fills it")

        feature = self.catalogue.require(feature_name)
        if feature["dtype"] != spec["dtype"]:
            raise FeatureError(
                f"slot '{slot}' holds {spec['dtype']} but '{feature_name}' is "
                f"{feature['dtype']}; a version must fill the schema it declares")

        view_name, view_version = self._locate(feature_name, binding)
        view = self.views.require(view_name)
        pin = self.views.pinned(view_name, view_version)
        return {"feature": feature_name, "slot": slot, "dtype": feature["dtype"],
                "view": view_name, "view_version": view_version,
                "feature_view_id": view["id"],
                "namespace": pin["namespace"],
                # The Delta version, not just the path. A path is mutable; this
                # is what makes "same featureset version -> same bytes" true
                # rather than true-until-somebody-writes-again.
                "delta_version": pin["delta_version"],
                "derived": self.derived.is_derived(feature_name),
                "definition_version": (self.derived.require(feature_name)["definition_version"]
                                       if self.derived.is_derived(feature_name) else None),
                # Asked of the derived feature's inputs rather than read off
                # its row. The row holds what the meet said when the feature was
                # defined; demote an input afterwards and the row goes on
                # claiming the old answer. A featureset version is exactly where
                # somebody checks what they are training on, so it is the last
                # place a stale certification should survive.
                "certification": (
                    self.derived.certification_now(feature_name)
                    if self.derived is not None
                    and self.derived.is_derived(feature_name)
                    else feature.get("certification", "experimental"))}

    def _certification_now(self, binding: Dict[str, Any]) -> str:
        """The slot's certification as it stands, not as it was published.

        For a derived feature this is the meet over its inputs, asked again —
        so demoting an input reaches every featureset version that reads it.
        """
        feature_name = binding.get("feature")
        if not feature_name:
            return binding.get("certification", "experimental")
        if self.derived is not None and self.derived.is_derived(feature_name):
            return self.derived.certification_now(feature_name)
        feature = self.catalogue.get(feature_name)
        return (feature or {}).get("certification",
                                   binding.get("certification", "experimental"))

    def _locate(self, feature_name: str, binding: Dict[str, Any]) -> Tuple[str, int]:
        """Which view version supplies this feature's values.

        Named explicitly where the caller knows; otherwise the newest version of
        the only view carrying it. Ambiguity is refused rather than guessed,
        because guessing here is how a set silently reads the wrong bytes.
        """
        if binding.get("view"):
            version = binding.get("view_version")
            if version is None:
                raise FeatureError(
                    f"'{feature_name}' names view '{binding['view']}' without a "
                    f"version; a featureset version pins exactly, or the same "
                    f"version would resolve to different bytes next month")
            return binding["view"], int(version)

        candidates = [(v["name"], vv["version"])
                      for v in self.views.views.many()
                      for vv in self.views.versions_of(v["name"])
                      if feature_name in (vv["features"] or [])]
        if not candidates:
            raise FeatureError(
                f"no materialised feature view supplies '{feature_name}'; "
                f"materialise it before a featureset can pin it")
        names = {c[0] for c in candidates}
        if len(names) > 1:
            raise FeatureError(
                f"'{feature_name}' is supplied by more than one view "
                f"({', '.join(sorted(names))}); name the view and version")
        return max(candidates, key=lambda c: c[1])

    def _resolve_label(self, featureset: Dict[str, Any],
                       label: Optional[Dict[str, Any]],
                       resolved: Dict[str, Any]) -> Dict[str, Any]:
        slot = featureset["label_slot"]
        if not slot:
            return {}
        if slot in resolved:
            return resolved[slot]
        if not label:
            raise FeatureError(
                f"'{featureset['name']}' declares label slot '{slot}' but this "
                f"version does not bind it; a supervised set without a label is "
                f"not one")
        return self._resolve(slot, featureset["slots"][slot], label)

    def _refuse_leakage(self, featureset: Dict[str, Any],
                        bindings: Dict[str, Any],
                        label: Optional[Dict[str, Any]]) -> None:
        """No slot may be computed from the label, however many hops away."""
        label_slot = featureset["label_slot"]
        if not label_slot:
            return
        label_feature = self._feature_named(bindings.get(label_slot) or label)
        if not label_feature:
            return
        for slot, binding in bindings.items():
            if slot == label_slot:
                continue
            named = self._feature_named(binding)
            if named:
                self.derived.refuse_if_reads(named, label_feature)

    @staticmethod
    def _feature_named(binding: Any) -> Optional[str]:
        """The feature a binding asks for, before anything is resolved."""
        if isinstance(binding, str):
            return binding
        if isinstance(binding, dict):
            return binding.get("feature")
        return None

    # --------------------------------------------------------------- resolve
    def version(self, name: str, number: int) -> Dict[str, Any]:
        featureset = self.require(name)
        row = self.versions.one(featureset_id=featureset["id"], version=number)
        if row is None:
            raise FeatureError(f"featureset '{name}' has no version {number}")
        return row

    def version_by_id(self, version_id: str) -> Optional[Dict[str, Any]]:
        """A filled version, resolved from its id, carrying its set's name.

        The register stores the id on everything that pins a featureset version
        — a parameter set, a warrant, a snapshot — because a name would go
        stale. Reading it back therefore needs the name attached, and doing that
        here rather than at each caller keeps one answer to *which set is this*.
        """
        row = self.versions.one(id=version_id)
        if row is None:
            return None
        featureset = self.sets.one(id=row["featureset_id"])
        return {**row, "featureset": (featureset or {}).get("name")}

    def versions_of(self, name: str) -> List[Dict[str, Any]]:
        return sorted(self.versions.many(featureset_id=self.require(name)["id"]),
                      key=lambda v: v["version"])

    def latest(self, name: str) -> Optional[Dict[str, Any]]:
        return self.versions.latest(self.require(name)["id"])

    def plan(self, name: str, number: int) -> Dict[str, Any]:
        """Everything an engine needs to assemble this set, in one document."""
        featureset, version = self.require(name), self.version(name, number)
        return {
            "featureset": name, "version": number, "entity": featureset["entity"],
            "grain": featureset["grain"], "digest": version["digest"],
            "pit_rule": PIT_RULE,
            "label": version["label_binding"] or None,
            "outcome_window_days": featureset["outcome_window_days"],
            # The pin is frozen and the judgement is not.
            #
            # `view_version` and `delta_version` are read out of the stored
            # binding exactly as published — that immutability is the whole
            # reproducibility guarantee, and refreshing it would break the one
            # property a featureset version exists to have.
            #
            # `certification` is different in kind. It is an opinion about the
            # feature rather than a fact about the data, and it moves: a feature
            # certified in March and deprecated in July is deprecated. A plan
            # that reported "certified" because that is what somebody thought in
            # March would be telling a reviewer the least useful true thing
            # available.
            "slots": [{"slot": s, **b,
                       "certification": self._certification_now(b)}
                      for s, b in sorted(version["bindings"].items())],
            "namespaces": sorted({b["namespace"] for b in version["bindings"].values()}),
            "pins": sorted({(b["namespace"], b.get("delta_version"))
                            for b in version["bindings"].values()}),
        }

    # ---------------------------------------------------------------- schemas
    def schema(self, name: str) -> Schema:
        """The **resolved** schema, as the domain's own object, so the variance
        rule that gates alias promotion applies to a featureset unchanged.

        Resolved, not declared, and the difference was not cosmetic. This read
        the row's own `slots` while `publish` fills what `resolver.resolve`
        produces — so a featureset composed from parents declared nothing of its
        own, reported an **empty** schema, and therefore satisfied no kernel at
        all. A fit warrant naming it was refused `schema_not_satisfied` listing
        slots the set demonstrably has and had just been published with.

        Composition is the whole point of the object: a set that inherits its
        slots is the ordinary case, not an exotic one, and it was the case that
        could never be fitted. The two readings of "what slots does this have"
        have to be one reading, and it has to be the one `publish` uses, because
        that is the one the data actually fills.
        """
        featureset = self.require(name)
        slots = self.resolver.resolve(featureset)
        return Schema(tuple(Field(slot, spec["dtype"], spec.get("nullable", False))
                            for slot, spec in sorted(slots.items())
                            if slot != featureset["label_slot"]))

    def satisfies(self, name: str, kernel_input: Schema) -> Tuple[bool, List[str]]:
        """Does this featureset provide what the kernel declares it reads?

        Contravariance in inputs (law L-12): the set must accept everything the
        kernel's schema does. A missing or mistyped slot is not a warning — the
        model would be fitted over a different X than the one it declares.

        This is `L-W10`, and it is now literally the same comparison `L-12`
        makes when a version replaces another — `core.domain.lattice.refines`,
        written once. They were one relation implemented twice, and two
        implementations of one order eventually disagree in the direction of
        permitting more.
        """
        from core.domain.lattice import refines
        outcome = refines(self.schema(name), kernel_input)
        return outcome.holds, list(outcome.missing + outcome.narrowed)

    def restatements(self, name: str, number: int) -> Dict[str, Any]:
        """Which of this version's namespaces have been written to since.

        A featureset version resolves to the same bytes by construction, because
        every binding pins a Delta version. This answers the neighbouring
        question: has anything *underneath* it changed, so that a reader who
        dropped the pin would now see something else. That is what a restatement
        looks like from here, and it is worth knowing before comparing two runs.
        """
        version = self.version(name, number)
        moved = []
        for slot, binding in sorted(version["bindings"].items()):
            state = self.views.restated(binding["view"], binding["view_version"])
            if state["restated"]:
                moved.append({"slot": slot, **state})
        return {"featureset": name, "version": number,
                "restated": bool(moved), "slots": moved,
                "detail": (f"{len(moved)} of this version's namespaces have been "
                           f"written to since it was published; the version still "
                           f"reads the bytes it pinned"
                           if moved else
                           "nothing underneath this version has moved")}

    # ------------------------------------------------------------ roll forward
    def roll_forward(self, name: str, actor: str = "system") -> Dict[str, Any]:
        """Mint a version re-resolved to the newest view versions, with a diff.

        Publishing a new view version deliberately changes nothing about an
        existing featureset version. This is how you take up the new data on
        purpose, and see exactly what moved in doing so.
        """
        current = self.latest(name)
        if current is None:
            raise FeatureError(f"'{name}' has no version to roll forward")
        featureset = self.require(name)
        fresh: Dict[str, Any] = {}
        for slot, binding in current["bindings"].items():
            newest = self.views.versions_of(binding["view"])[-1]["version"]
            fresh[slot] = {"feature": binding["feature"], "view": binding["view"],
                           "view_version": newest}
        label = current["label_binding"] or None
        if label and featureset["label_slot"] not in fresh:
            newest = self.views.versions_of(label["view"])[-1]["version"]
            label = {"feature": label["feature"], "view": label["view"],
                     "view_version": newest}
        published = self.publish(name, fresh, label,
                                 note=f"rolled forward from v{current['version']}",
                                 actor=actor)
        published["moved"] = self.diff(current, published)
        return published

    @staticmethod
    def diff(before: Dict[str, Any], after: Dict[str, Any]) -> List[Dict[str, Any]]:
        """What changed between two versions, slot by slot."""
        moved = []
        for slot, new in after["bindings"].items():
            old = (before["bindings"] or {}).get(slot)
            if old is None:
                moved.append({"slot": slot, "was": None, "now": new["namespace"]})
            elif old["namespace"] != new["namespace"] or old["feature"] != new["feature"]:
                moved.append({"slot": slot,
                              "was": f"{old['feature']} @ {old['namespace']}",
                              "now": f"{new['feature']} @ {new['namespace']}"})
        return moved

    # ------------------------------------------------------------- retirement
    def can_retire(self, view_name: str, version: int) -> Tuple[bool, List[str]]:
        """A view version pinned by any featureset version cannot be retired."""
        view = self.views.require(view_name)
        holders = self.versions.consumers_of_view(view["id"], version)
        return not holders, holders
