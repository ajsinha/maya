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
from typing import Any, Dict, List, Optional, Tuple

from core.domain.schemas import Field, Schema
from core.evidence import EvidenceEngine
from core.features.common import ENTITY, INGEST_TIME, VALID_TIME, FeatureError
from core.log import get_logger
from db import FeaturesetRepository, FeaturesetVersionRepository
from db.database import digest as canonical_digest

logger = get_logger(__name__)

# The point-in-time rule every featureset asserts. Stated once, here, rather than
# re-declared in every warrant that reads one.
PIT_RULE = f"{VALID_TIME} <= label_ts AND {INGEST_TIME} <= as_of"


class FeaturesetRegistry:
    """Declares featuresets, publishes versions, and resolves them to bytes."""

    def __init__(self, sets: FeaturesetRepository,
                 versions: FeaturesetVersionRepository,
                 catalogue, views, derived, evidence: EvidenceEngine):
        self.sets, self.versions = sets, versions
        self.catalogue, self.views = catalogue, views
        self.derived, self.evidence = derived, evidence

    # ----------------------------------------------------------------- define
    def define(self, name: str, entity: str, owner: str, slots: Dict[str, Any],
               label_slot: Optional[str] = None, outcome_window_days: int = 0,
               grain: str = "", description: str = "",
               actor: str = "system") -> Dict[str, Any]:
        """Declare the schema. Constituents come later, with a version."""
        if self.sets.one(name=name):
            raise FeatureError(f"featureset '{name}' already exists")
        if not slots:
            raise FeatureError(
                f"'{name}' declares no slots; a featureset is a schema, and a "
                f"schema with nothing in it is not one")
        normalised = {k: self._slot(k, v) for k, v in slots.items()}
        if label_slot and label_slot not in normalised:
            raise FeatureError(
                f"the label slot '{label_slot}' is not one of the declared slots")
        if outcome_window_days < 0:
            raise FeatureError("an outcome window cannot be negative")
        row = {"name": name, "entity": entity, "owner": owner,
               "description": description, "slots": normalised,
               "label_slot": label_slot,
               "outcome_window_days": outcome_window_days,
               "grain": grain or f"one row per {entity}",
               "created_by": actor, "created_at": time.time()}
        self.sets.add(row)
        self.evidence.append("featureset_defined", "featureset", row["id"],
                             {"name": name, "entity": entity,
                              "slots": sorted(normalised), "label": label_slot},
                             actor=actor)
        return self.sets.one(id=row["id"])

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
        slots = featureset["slots"]

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
                "certification": feature.get("certification", "experimental")}

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
            "slots": [{"slot": s, **b} for s, b in sorted(version["bindings"].items())],
            "namespaces": sorted({b["namespace"] for b in version["bindings"].values()}),
            "pins": sorted({(b["namespace"], b.get("delta_version"))
                            for b in version["bindings"].values()}),
        }

    # ---------------------------------------------------------------- schemas
    def schema(self, name: str) -> Schema:
        """The declared schema, as the domain's own object, so the variance rule
        that gates alias promotion can be applied to a featureset unchanged."""
        featureset = self.require(name)
        return Schema(tuple(Field(slot, spec["dtype"], spec.get("nullable", False))
                            for slot, spec in sorted(featureset["slots"].items())
                            if slot != featureset["label_slot"]))

    def satisfies(self, name: str, kernel_input: Schema) -> Tuple[bool, List[str]]:
        """Does this featureset provide what the kernel declares it reads?

        Contravariance in inputs (law L-12): the set must accept everything the
        kernel's schema does. A missing or mistyped slot is not a warning — the
        model would be fitted over a different X than the one it declares.
        """
        missing = self.schema(name).accepts_superset_of(kernel_input)
        return not missing, missing

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
