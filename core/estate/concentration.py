"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What several models depend on at once, and why the answer is not a number.

Supervisors ask about ``interactions and dependencies among models; reliance on
common assumptions, data, or methodologies''. The register already answers the
first clause: `shared_dependencies` finds models two or more others read from.
The rest of the sentence --- the *data*, the *vendor*, the *methodology* --- was
not computed, and those are the ones a firm is least likely to know.

**This is the obstruction made findable, and deliberately not made additive.**
A network that *copies* a dependency is not the same as one that duplicates it,
and no aggregate risk figure computed from component ratings can tell them
apart. So what is produced here is the set of shared things and what rides on
each, and **no composite score anywhere**. The join over a tier lattice is
available and is order-theoretic; a magnitude is not available and would be a
number nobody could decompose in the meeting where it mattered.

**A concentration is not a count.** Twelve models reading one feature view is a
number. Twelve *tier 1* models reading one view, none of whose owners is the
view's owner, is a finding. So every shared thing carries the worst tier that
rides on it and how much of the estate that is --- and the sort is by what is
at stake rather than by how many.

**Five kinds, and the last two are the ones nobody has.**

  * **upstream models** --- already computed; a change there propagates.
  * **feature views** --- two models reading one view share its outage, its
    schema change and its restatement.
  * **datasets** --- two models fitted from one snapshot share whatever was
    wrong with it, and share it silently, because a snapshot is pinned and
    therefore invisible in ordinary operation.
  * **vendors** --- the one nobody computes, because the vendor's name is on an
    *assessment* and not on the model. A firm with four models from one bureau
    has one commercial relationship and four risk positions, and when that
    bureau reversion its score the four move together.
  * **methodologies** --- shared model class. The weakest signal here and the
    one worth having anyway: a methodology that turns out to be wrong is wrong
    everywhere it was used, and the 2007 correlation models were a
    methodological concentration long before anybody called them one.

**A single point of failure is stated as a question rather than asserted.** A
view that eleven models read is a single point of failure if it can fail. MAYA
knows what depends on it and does not know its operational resilience, so the
report names the dependency and says the second half is not a fact it holds.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.log import get_logger

logger = get_logger(__name__)

UPSTREAM, VIEW, DATASET, VENDOR, METHODOLOGY = (
    "upstream_model", "feature_view", "dataset", "vendor", "methodology")

KINDS: Dict[str, str] = {
    UPSTREAM: "a model whose output another model reads. A change there "
              "propagates, and the blast radius already follows it",
    VIEW: "a materialised feature view two or more models read. They share its "
          "outage, its schema change and its restatement",
    DATASET: "a pinned snapshot two or more parameter sets were fitted from. "
             "They share whatever was wrong with it, and share it silently — a "
             "pin is invisible in ordinary operation",
    VENDOR: "a third party two or more models come from. One commercial "
            "relationship and several risk positions, which move together when "
            "the vendor reversions",
    METHODOLOGY: "a model class two or more models share. The weakest signal "
                 "here and worth having: a methodology that is wrong is wrong "
                 "everywhere it was used",
}

#: How many dependents make something worth reporting at all. Two, because a
#: dependency with one dependent is not shared — it is just a dependency.
MINIMUM = 2

#: Above this share of the in-scope estate, a shared thing is reported as
#: reaching most of it. Not a threshold anything refuses on: it is the sentence
#: that makes a count legible.
BROAD = 0.30


class Concentration:
    """What several models depend on at once. Produces sets, never a score."""

    def __init__(self, registry, composition, features=None, parameters=None,
                 vendor=None):
        self.registry, self.composition = registry, composition
        self.features, self.parameters = features, parameters
        self.vendor = vendor

    # ------------------------------------------------------------------ scan
    def across_the_estate(self, urns: Optional[Sequence[str]] = None,
                          now: Optional[float] = None) -> Dict[str, Any]:
        """Every shared dependency, worst tier at stake first."""
        moment = now if now is not None else time.time()
        models = [self.registry.require(u) for u in urns] if urns \
            else self.registry.list()
        by_urn = {m["urn"]: m for m in models}
        shared: List[Dict[str, Any]] = []
        shared += self._upstream(by_urn)
        shared += self._views(by_urn)
        shared += self._datasets(by_urn)
        shared += self._vendors(by_urn)
        shared += self._methodologies(by_urn)

        for row in shared:
            tiers = [by_urn[u].get("tier") for u in row["relied_on_by"]
                     if by_urn.get(u) and by_urn[u].get("tier") is not None]
            row["worst_tier"] = min(tiers) if tiers else None
            row["share_of_estate"] = (round(len(row["relied_on_by"])
                                            / len(by_urn), 3)
                                      if by_urn else 0.0)
            row["broad"] = row["share_of_estate"] >= BROAD
        shared.sort(key=lambda r: (r["worst_tier"] if r["worst_tier"]
                                   is not None else 9,
                                   -len(r["relied_on_by"]), r["kind"]))
        by_kind: Dict[str, int] = {}
        for row in shared:
            by_kind[row["kind"]] = by_kind.get(row["kind"], 0) + 1
        return {
            "models": len(by_urn), "shared": shared, "count": len(shared),
            "by_kind": by_kind,
            "reaching_tier_1": [r["what"] for r in shared
                                if r["worst_tier"] == 1],
            "broad": [r["what"] for r in shared if r["broad"]],
            "kinds": [{"kind": k, "means": v} for k, v in KINDS.items()],
            # Stated on every answer, because the absence is the point.
            "aggregate_score": None,
            "scanned_at": moment,
            "detail": self._detail(by_urn, shared, by_kind),
        }

    def _detail(self, by_urn, shared, by_kind) -> str:
        if not shared:
            return (f"nothing is shared by two or more of {len(by_urn)} "
                    f"model(s). Worth checking against the recorded edges, "
                    f"views and assessments rather than believing: a "
                    f"dependency nobody entered is a concentration nothing "
                    f"here can see")
        tier_one = [r for r in shared if r["worst_tier"] == 1]
        out = (f"{len(shared)} shared dependenc(ies) across {len(by_urn)} "
               f"model(s): "
               + ", ".join(f"{n} {k.replace('_', ' ')}"
                           for k, n in sorted(by_kind.items())))
        if tier_one:
            out += (f". {len(tier_one)} carry a tier 1 model, which is the "
                    f"read that matters: a concentration is not a count, and "
                    f"twelve tier 4 models on one view is a different sentence "
                    f"from one tier 1 model on it")
        out += (". **There is no aggregate score here and there will not be "
                "one.** A network that copies a dependency and one that "
                "duplicates it produce identical component ratings, so any "
                "figure computed from those ratings is blind to exactly the "
                "thing this report exists to find. What composes is the order "
                "— the worst tier at stake — and not a magnitude")
        return out

    # ---------------------------------------------------------------- kinds
    def _upstream(self, by_urn: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self.composition is None:
            return []
        found = self.composition.shared_dependencies(list(by_urn))
        return [{"kind": UPSTREAM, "what": row.get("urn"),
                 "label": row.get("name") or row.get("urn"),
                 "relied_on_by": row.get("relied_on_by") or [],
                 "why": KINDS[UPSTREAM]}
                for row in found.get("shared", [])]

    def _views(self, by_urn: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Which views each model reads, through its parameter sets' bindings."""
        if self.parameters is None \
                or getattr(self.features, "sets", None) is None:
            return []
        readers: Dict[str, set] = {}
        for urn, model in by_urn.items():
            for view in self._views_of(model):
                readers.setdefault(view, set()).add(urn)
        return [{"kind": VIEW, "what": view, "label": view,
                 "relied_on_by": sorted(urns), "why": KINDS[VIEW]}
                for view, urns in readers.items() if len(urns) >= MINIMUM]

    def _views_of(self, model: Dict[str, Any]) -> set:
        out: set = set()
        for row in self.parameters.parameters.many(model_id=model["id"]):
            version_id = row.get("featureset_version_id")
            if not version_id:
                continue
            fsv = self.features.sets.versions.one(id=version_id)
            for binding in ((fsv or {}).get("bindings") or {}).values():
                if isinstance(binding, dict) and binding.get("view"):
                    out.add(binding["view"])
        return out

    def _datasets(self, by_urn: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Snapshots two or more parameter sets were fitted from."""
        if self.parameters is None:
            return []
        readers: Dict[str, set] = {}
        for urn, model in by_urn.items():
            for row in self.parameters.parameters.many(model_id=model["id"]):
                if row.get("snapshot_id"):
                    readers.setdefault(row["snapshot_id"], set()).add(urn)
        return [{"kind": DATASET, "what": snapshot, "label": snapshot,
                 "relied_on_by": sorted(urns), "why": KINDS[DATASET]}
                for snapshot, urns in readers.items() if len(urns) >= MINIMUM]

    def _vendors(self, by_urn: Dict[str, Any]) -> List[Dict[str, Any]]:
        """The one nobody computes: the vendor is on the ASSESSMENT.

        A firm with four models from one bureau has one commercial relationship
        and four risk positions, and nothing in an ordinary register joins them
        — because the vendor's name was typed on a due-diligence record rather
        than on the model.
        """
        if self.vendor is None:
            return []
        readers: Dict[str, set] = {}
        for urn in by_urn:
            for assessment in self.vendor.for_model(urn):
                name = (assessment.get("vendor") or "").strip()
                if name:
                    readers.setdefault(name, set()).add(urn)
        return [{"kind": VENDOR, "what": vendor, "label": vendor,
                 "relied_on_by": sorted(urns), "why": KINDS[VENDOR]}
                for vendor, urns in readers.items() if len(urns) >= MINIMUM]

    @staticmethod
    def _methodologies(by_urn: Dict[str, Any]) -> List[Dict[str, Any]]:
        readers: Dict[str, set] = {}
        for urn, model in by_urn.items():
            klass = (model.get("model_class") or "").strip()
            if klass:
                readers.setdefault(klass, set()).add(urn)
        return [{"kind": METHODOLOGY, "what": klass, "label": klass,
                 "relied_on_by": sorted(urns), "why": KINDS[METHODOLOGY]}
                for klass, urns in readers.items() if len(urns) >= MINIMUM]

    # --------------------------------------------------- single point of failure
    def single_points_of_failure(self,
                                 now: Optional[float] = None) -> Dict[str, Any]:
        """What the estate would lose if one thing stopped working.

        Named as a **dependency** and not asserted as a failure point, because
        the second half of that judgement is operational resilience and MAYA
        does not hold it. A view eleven models read is a single point of failure
        *if it can fail*, and whether it can is a fact about a pipeline, a
        cluster and an on-call rota that live somewhere else.
        """
        scan = self.across_the_estate(now=now)
        candidates = [r for r in scan["shared"]
                      if r["kind"] in (VIEW, DATASET, VENDOR, UPSTREAM)
                      and (r["worst_tier"] in (1, 2) or r["broad"])]
        return {
            "candidates": candidates, "count": len(candidates),
            "resilience_is_known": False,
            "detail": (
                f"{len(candidates)} shared dependenc(ies) either carry a tier 1 "
                f"or 2 model or reach {BROAD:.0%} of the estate. Each is named "
                f"as a **dependency** rather than asserted as a point of "
                f"failure: whether it can fail is a fact about a pipeline, a "
                f"cluster and an on-call rota, and MAYA does not hold any of "
                f"the three. Half of that judgement is here and the register "
                f"says which half"
                if candidates else
                "nothing shared reaches a tier 1 or 2 model or a broad share of "
                "the estate. That is the honest reading of the recorded "
                "dependencies and not a statement about the estate's "
                "resilience"),
        }

    # ------------------------------------------------------------------ one
    def of_model(self, urn: str,
                 now: Optional[float] = None) -> Dict[str, Any]:
        """What this model shares with anything else, and with what."""
        model = self.registry.require(urn)
        scan = self.across_the_estate(now=now)
        mine = [r for r in scan["shared"] if urn in r["relied_on_by"]]
        with_whom = sorted({u for r in mine for u in r["relied_on_by"]
                            if u != urn})
        return {
            "urn": urn, "tier": model.get("tier"),
            "shares": mine, "count": len(mine),
            "with": with_whom,
            "detail": (
                f"this model shares {len(mine)} dependenc(ies) with "
                f"{len(with_whom)} other model(s). A change to any of them "
                f"reaches here, and the reverse — which is the reading a blast "
                f"radius gives in one direction and this gives in the other"
                if mine else
                "this model shares nothing recorded with any other. Read it "
                "against what is entered rather than as isolation"),
        }
