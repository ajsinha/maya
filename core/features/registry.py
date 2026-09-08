"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The feature platform's aggregate root.

Four collaborators do the work — the catalogue defines features, the view
manager materialises and namespaces them, the binder pins contracts, the builder
assembles training sets. This class is the seam they are wired through, and the
single object the application context holds.

It is deliberately thin. Anything with a decision in it belongs in one of the
four; if a method here grows a branch, that branch is in the wrong file.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.evidence import EvidenceEngine
from core.features.assembly import Column, TrainingSetBuilder
from core.features.catalogue import FeatureCatalogue
from core.features.common import FeatureError
from core.features.contracts import ContractBinder
from core.features.derived import DerivedFeatures
from core.features.sets import FeaturesetRegistry
from core.features.sources import SourceRegistry
from core.features.transfer import FeatureTransfer
from core.features.views import ViewManager
from db import (ContractRepository, DeltaStore, DerivedFeatureRepository,
                FeatureRepository, FeatureViewRepository,
                FeatureViewVersionRepository, FeaturesetRepository,
                FeaturesetVersionRepository, SnapshotRepository)


class FeatureRegistry:
    """Features, views, materialisation, contracts and PIT assembly."""

    def __init__(self, features: FeatureRepository, views: FeatureViewRepository,
                 view_versions: FeatureViewVersionRepository, contracts: ContractRepository,
                 snapshots: SnapshotRepository, delta: DeltaStore, evidence: EvidenceEngine,
                 derived: Optional[DerivedFeatureRepository] = None,
                 sets: Optional[FeaturesetRepository] = None,
                 set_versions: Optional[FeaturesetVersionRepository] = None,
                 sources=None, credentials=None):
        self.catalogue = FeatureCatalogue(features, evidence)
        self.views = ViewManager(views, view_versions, self.catalogue, delta, evidence)
        self.contracts = ContractBinder(contracts, view_versions, self.views, evidence)
        # Derived features and featuresets sit above the view layer: one computes
        # values from values, the other names a selection of them. Both are
        # optional so a caller that only wants the catalogue is not made to
        # construct them.
        self.derived = DerivedFeatures(derived, features, self.catalogue,
                                       evidence) if derived is not None else None
        self.sets = (FeaturesetRegistry(sets, set_versions, self.catalogue,
                                        self.views, self.derived, evidence)
                     if sets is not None and set_versions is not None else None)
        self.assembly = TrainingSetBuilder(self.views, snapshots, delta, evidence)
        # The Delta store and the snapshot register are the platform's own
        # persistence, not a collaborator's; reading them back is part of this
        # object's surface rather than something callers reach through it for.
        self.delta, self.snapshots = delta, snapshots
        # Feature VALUES are the one thing here that is not small, so they move
        # through a layer that never materialises a dataset whole.
        self.transfer = FeatureTransfer(delta, self.views, self.sets)
        # Where values come from when they are not uploaded. Optional so a
        # caller that only wants the catalogue is not made to supply one, and
        # so a deployment that forbids outbound connections can leave it off
        # entirely rather than configure it into uselessness.
        self.sources = (SourceRegistry(sources, self.views, evidence, credentials)
                        if sources is not None else None)

    # -------------------------------------------------------------- catalogue
    def define(self, *a, **kw) -> Dict[str, Any]:
        return self.catalogue.define(*a, **kw)

    def feature(self, name: str) -> Optional[Dict[str, Any]]:
        return self.catalogue.get(name)

    def list_features(self, **filters) -> List[Dict[str, Any]]:
        return self.catalogue.list(**filters)

    def similar(self, name: str, description: str, limit: int = 3) -> List[Dict[str, Any]]:
        return self.catalogue.similar(name, description, limit)

    def certify(self, name: str, level: str = "certified") -> Dict[str, Any]:
        return self.catalogue.certify(name, level)

    # ------------------------------------------------------------------ views
    def create_view(self, *a, **kw) -> Dict[str, Any]:
        return self.views.create(*a, **kw)

    def materialise(self, *a, **kw) -> Dict[str, Any]:
        return self.views.materialise(*a, **kw)

    def namespace(self, view_name: str, version: int) -> str:
        return self.views.namespace(view_name, version)

    def view_versions_of(self, view_name: str) -> List[Dict[str, Any]]:
        return self.views.versions_of(view_name)

    # -------------------------------------------------------------- contracts
    def bind_contract(self, *a, **kw) -> Dict[str, Any]:
        return self.contracts.bind(*a, **kw)

    def contract_for(self, model_version_id: str) -> Optional[Dict[str, Any]]:
        return self.contracts.for_version(model_version_id)

    def serving_namespaces(self, model_version_id: str) -> Dict[str, str]:
        return self.contracts.serving_namespaces(model_version_id)

    def can_retire(self, view_name: str, version: int) -> Tuple[bool, List[str]]:
        return self.contracts.can_retire(view_name, version)

    # --------------------------------------------------------- derived features
    def define_derived(self, *a, **kw) -> Dict[str, Any]:
        return self._derived().define(*a, **kw)

    def resolved_feature(self, name: str) -> Dict[str, Any]:
        """A feature as it actually stands: composition, shape, policy, lifetime."""
        return self.catalogue.resolved(name)

    def resolved_featureset(self, name: str,
                            request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._sets().resolved(name, request)

    def seal_feature(self, name: str, actor: str, note: str = "") -> Dict[str, Any]:
        return self.catalogue.seal(name, actor, note)

    def seal_featureset(self, name: str, actor: str, note: str = "") -> Dict[str, Any]:
        return self._sets().seal(name, actor, note)

    def derived_feature(self, name: str) -> Optional[Dict[str, Any]]:
        return self._derived().get(name)

    def lineage(self, name: str) -> List[str]:
        """Every feature this one rests on, transitively."""
        return sorted(self._derived().lineage(name))

    def dependants_of(self, name: str) -> List[str]:
        return self._derived().dependants_of(name)

    def compute_derived(self, name: str, rows: List[Dict[str, Any]]):
        return self._derived().compute(name, rows)

    # ------------------------------------------------------------- featuresets
    def preview_featureset(self, *a, **kw) -> Dict[str, Any]:
        """What a featureset would resolve to, declaring nothing."""
        return self.sets.preview(*a, **kw)

    def define_featureset(self, *a, **kw) -> Dict[str, Any]:
        return self._sets().define(*a, **kw)

    def publish_featureset(self, *a, **kw) -> Dict[str, Any]:
        return self._sets().publish(*a, **kw)

    def featureset(self, name: str) -> Optional[Dict[str, Any]]:
        return self._sets().get(name)

    def featureset_plan(self, name: str, version: int) -> Dict[str, Any]:
        return self._sets().plan(name, version)

    def featureset_satisfies(self, name: str, kernel_input) -> Tuple[bool, List[str]]:
        return self._sets().satisfies(name, kernel_input)

    def roll_forward(self, name: str, actor: str = "system") -> Dict[str, Any]:
        return self._sets().roll_forward(name, actor)

    def restatements(self, name: str, version: int) -> Dict[str, Any]:
        return self._sets().restatements(name, version)

    def pinned(self, view_name: str, version: int) -> Dict[str, Any]:
        """The namespace and the Delta version a view version was pinned at."""
        return self.views.pinned(view_name, version)

    def restated(self, view_name: str, version: int) -> Dict[str, Any]:
        return self.views.restated(view_name, version)

    def _derived(self) -> DerivedFeatures:
        if self.derived is None:
            raise FeatureError("this registry was built without derived features")
        return self.derived

    def _sets(self) -> FeaturesetRegistry:
        if self.sets is None:
            raise FeatureError("this registry was built without featuresets")
        return self.sets

    # --------------------------------------------------------------- assembly
    def build_training_set(self, *a, **kw) -> Dict[str, Any]:
        return self.assembly.build(*a, **kw)

    def build_from_featureset(self, name: str, version: int,
                              spine: List[Dict[str, Any]], as_of: float,
                              snapshot_name: Optional[str] = None,
                              actor: str = "system") -> Dict[str, Any]:
        """Assemble a PIT-correct training set from a pinned featureset version.

        The set supplies the columns and the namespaces; the caller supplies the
        spine and the as_of, which is the division the whole design rests on. The
        resulting snapshot names the featureset version, so a fit warrant may
        pin the snapshot instead and recompute nothing.
        """
        plan = self._sets().plan(name, version)
        # The BINDINGS, not a set of the views they happen to mention.
        #
        # This reduced the plan to `{(view, view_version)}` and handed that to
        # the assembler, which then name-joined every column of every view. The
        # slot-to-feature mapping — the entire content of a featureset version,
        # published, digested and signed into the fit warrant — was discarded
        # one call before it was used, so a set pinning `turnover` to one view
        # was fitted on whichever view supplied a column of that name last.
        columns = [Column(b["slot"], b["feature"], b["view"], b["view_version"])
                   for b in plan["slots"]]
        label_slot = None
        if plan["label"]:
            label = plan["label"]
            columns.append(Column(label["slot"], label["feature"],
                                  label["view"], label["view_version"]))
            # The screen needs the slot the label OCCUPIES in the frame, not the
            # word "label". Without it `detect_leakage` looked for a column that
            # a featureset-assembled snapshot never has.
            label_slot = label["slot"]
        views = [{"view": v, "version": n}
                 for v, n in sorted({c.source for c in columns})]
        snapshot = self.assembly.build(
            snapshot_name or f"{name}-v{version}",
            spine, views, as_of, columns=columns, label_slot=label_slot,
            actor=actor, featureset=name, featureset_version=version)
        return {**snapshot, "featureset": name, "featureset_version": version,
                "featureset_digest": plan["digest"]}

    def snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        return self.snapshots.one(id=snapshot_id)
