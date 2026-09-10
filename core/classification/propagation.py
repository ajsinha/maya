"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A model is at least as sensitive as the most sensitive thing it reads.

A feature has carried a `sensitivity` since the catalogue was written. It was
free text, it was displayed on one screen, and **nothing read it** — not the
model that consumed the feature, not the document compiled from that model, not
one control anywhere. A field that describes a legal obligation and reaches no
decision is a field that will be wrong, because nothing ever depends on it being
right.

**Propagation is a join in a lattice, which is why it is derived and never
declared.** The classes are totally ordered, so the join is a maximum, and a
maximum is the one rule about this that cannot be argued with: a thing built out
of parts is not less sensitive than its most sensitive part. Letting somebody
*declare* a model's class would let them declare it lower, which is the only
direction anybody ever wants to move it.

**Declaring it higher is allowed and declaring it lower is refused by name.** A
firm may decide a model is more sensitive than its inputs force — an output can
be more disclosive than any single input, which is most of what re-identification
is. The refusal for the other direction names the feature that forces the floor,
so somebody told *no* has somewhere to go.

**`pii` is not a level and is deliberately not folded into one.** A confidential
model built on personal data and a confidential model built on market data are
the same class and different legal objects, and collapsing them loses exactly
the distinction a data protection officer needs. It propagates as its own flag,
by the same rule: a model reading one personal feature is personal.

**Two paths to a model's inputs, and they are not equally good.** A parameter set
pins a featureset version whose bindings *name* the features — that is exact. A
version's declared `input_schema` names fields, which may or may not be features
in the catalogue — that is a match on name and is reported as such. A model with
inputs declared and never bound has a classification nobody can derive, and this
says so rather than returning the default, because returning `internal` for a
model nobody has traced is reporting an assumption as a finding.

**The surprising answer is the useful one.** A board pack compiled across the
estate inherits the join of every model in it, which is nearly always higher than
whoever asked for it expected. That is not a bug in the arithmetic; it is what
aggregation does, and it is the reason the classification of a summary document
is worth computing rather than assuming.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from core.classification.common import (BOTTOM, DEFAULT, ClassificationError,
                                        at_least, join, normalise)
from core.log import get_logger

logger = get_logger(__name__)


class Classification:
    """Derives what a model, and anything compiled from it, is classified as."""

    def __init__(self, registry, features, parameters=None):
        self.registry, self.features = registry, features
        # The parameter register, which is where a model's featureset version
        # is actually pinned. Optional: without it only the declared path is
        # available, and the answer says which path it came from.
        self.parameters = parameters

    # -------------------------------------------------------------- features
    def of_feature(self, name: str) -> Dict[str, Any]:
        """One feature's class, normalised."""
        row = self.features.catalogue.require(name)
        return {"feature": name,
                "classification": normalise(row.get("sensitivity") or ""),
                "pii": bool(row.get("pii")),
                "stated": bool((row.get("sensitivity") or "").strip())}

    # ---------------------------------------------------------------- models
    def of_model(self, urn: str) -> Dict[str, Any]:
        """What this model's inputs force, and what it declares.

        The derived floor is the join over every feature reachable from it. The
        declared class may sit above that floor and never below.
        """
        model = self.registry.require(urn)
        bound, declared_only, unresolved = self._inputs(urn)
        rows = [self.of_feature(name) for name in sorted(bound | declared_only)]

        derived = join(*[r["classification"] for r in rows]) if rows else BOTTOM
        pii = any(r["pii"] for r in rows)
        forcing = [r for r in rows if r["classification"] == derived
                   and derived != BOTTOM]

        stated = (model.get("attributes") or {}).get("classification")
        effective = join(derived, normalise(stated)) if stated else derived
        return {
            "urn": urn, "derived": derived, "declared": stated,
            "classification": effective, "pii": pii,
            "features": rows,
            "bound": sorted(bound), "declared_only": sorted(declared_only),
            "unresolved_inputs": sorted(unresolved),
            "forced_by": [r["feature"] for r in forcing],
            "traceable": bool(rows) or not unresolved,
            "detail": self._model_detail(urn, derived, effective, stated, rows,
                                         forcing, unresolved, pii),
        }

    def _inputs(self, urn: str):
        """Which features this model reads, and how sure we are.

        `bound` came from a featureset version's resolved bindings, which name
        the feature. `declared_only` came from matching a version's declared
        input field names against the catalogue, which is a guess. `unresolved`
        are declared inputs that match nothing, and they are the reason this
        method returns three sets rather than one.
        """
        bound: set = set()
        declared: set = set()
        unresolved: set = set()

        if self.parameters is not None:
            for row in self._parameter_sets(urn):
                bound |= self._features_of_binding(
                    row.get("featureset_version_id"))

        for version in self.registry.versions(urn):
            for field in version.get("input_schema") or []:
                name = field.get("name") if isinstance(field, dict) else field
                if not name or name in bound:
                    continue
                if self.features.catalogue.get(name):
                    declared.add(name)
                else:
                    unresolved.add(name)
        return bound, declared, unresolved

    def _parameter_sets(self, urn: str) -> List[Dict[str, Any]]:
        model = self.registry.require(urn)
        return list(self.parameters.parameters.many(model_id=model["id"]))

    def _features_of_binding(self, featureset_version_id: Optional[str]) -> set:
        if not featureset_version_id:
            return set()
        row = self.features.sets.versions.one(id=featureset_version_id)
        if not row:
            return set()
        out = set()
        for binding in (row.get("bindings") or {}).values():
            name = (binding.get("feature") if isinstance(binding, dict)
                    else binding)
            if name:
                out.add(name)
        return out

    @staticmethod
    def _model_detail(urn, derived, effective, stated, rows, forcing,
                      unresolved, pii) -> str:
        if not rows and unresolved:
            return (f"{len(unresolved)} declared input(s) match no feature in "
                    f"the catalogue and nothing is bound, so this model's "
                    f"classification cannot be derived. Reporting "
                    f"'{DEFAULT}' here would be reporting an assumption as a "
                    f"finding")
        if not rows:
            return ("this model reads no catalogued feature, so the join is "
                    "over the empty set and the answer is the bottom of the "
                    "lattice")
        out = (f"{len(rows)} feature(s) give a derived floor of {derived}"
               + (f", forced by {', '.join(r['feature'] for r in forcing)}"
                  if forcing else ""))
        if stated and not at_least(stated, derived):
            # NOT `effective != derived`: when the declaration is below the
            # floor the join returns the floor, so the two are equal and that
            # test silently reports the wrong branch.
            out += (f"; declared {stated}, which is below the floor, so the "
                    f"floor stands")
        elif stated:
            out += f"; declared {stated}, at or above it"
        if pii:
            out += ("; and it reads personal data, which is a separate fact "
                    "from the level and carries its own duties")
        if unresolved:
            out += (f". {len(unresolved)} declared input(s) match no catalogued "
                    f"feature and are not in the join")
        return out

    # ---------------------------------------------------------------- declare
    def declare(self, urn: str, classification: str,
                actor: str = "system") -> Dict[str, Any]:
        """State a model's class. Refused if it is below what its inputs force.

        Higher is allowed, because an output can be more disclosive than any
        single input — which is most of what re-identification is. Lower is
        refused, and the refusal names the feature that forces the floor.
        """
        wanted = normalise(classification)
        current = self.of_model(urn)
        if not at_least(wanted, current["derived"]):
            forcing = current["forced_by"]
            raise ClassificationError(
                "below_the_derived_floor",
                f"this model reads {', '.join(forcing) or 'features'} and is "
                f"therefore at least {current['derived']}; '{wanted}' is below "
                f"that. A thing built out of parts is not less sensitive than "
                f"its most sensitive part",
                f"declare {current['derived']} or higher, or reclassify "
                f"{forcing[0] if forcing else 'the feature'} — which is a "
                f"decision about the data rather than about this model")
        model = self.registry.require(urn)
        attributes = {**(model.get("attributes") or {}),
                      "classification": wanted}
        self.registry.update(urn, {"attributes": attributes}, actor)
        logger.info("model %s declared %s by %s", urn, wanted, actor)
        return self.of_model(urn)

    # ------------------------------------------------------------- documents
    def of_documents(self, urns: Sequence[str]) -> Dict[str, Any]:
        """What a document describing these models inherits.

        The one people get wrong. A board pack across the estate inherits the
        join of every model in it, which is nearly always higher than whoever
        asked for it expected — that is what aggregation does, and it is the
        reason this is worth computing rather than assuming.
        """
        rows = [self.of_model(urn) for urn in urns]
        inherited = join(*[r["classification"] for r in rows]) if rows else BOTTOM
        highest = [r["urn"] for r in rows
                   if r["classification"] == inherited and inherited != BOTTOM]
        pii = [r["urn"] for r in rows if r["pii"]]
        untraceable = [r["urn"] for r in rows if not r["traceable"]]
        return {
            "models": len(rows), "classification": inherited,
            "pii": bool(pii), "pii_models": pii,
            "inherited_from": highest,
            "untraceable": untraceable,
            "detail": (
                f"a document describing {len(rows)} model(s) is {inherited}, "
                f"inherited from {', '.join(highest[:3])}"
                + (f" and {len(highest) - 3} other(s)" if len(highest) > 3
                   else "")
                + (". It aggregates personal data, which is a separate duty "
                   "from the level" if pii else "")
                + (f". {len(untraceable)} of them could not be traced to any "
                   f"catalogued feature, so this floor may be too low"
                   if untraceable else "")
                if rows else
                "a document describing no model inherits nothing"),
        }

    # ---------------------------------------------------------------- estate
    def across_the_estate(self) -> Dict[str, Any]:
        """Every model's class, and where the scheme is not working."""
        rows = [self.of_model(m["urn"]) for m in self.registry.list()]
        rows.sort(key=lambda r: (-len(r["forced_by"]), r["urn"]))
        by_level: Dict[str, int] = {}
        for row in rows:
            by_level[row["classification"]] = by_level.get(
                row["classification"], 0) + 1
        untraceable = [r["urn"] for r in rows if not r["traceable"]]
        unstated = sum(1 for r in rows
                       for f in r["features"] if not f["stated"])
        return {
            "models": rows, "count": len(rows), "by_level": by_level,
            "pii": sum(1 for r in rows if r["pii"]),
            "untraceable": untraceable,
            "features_never_classified": unstated,
            "detail": (
                f"{len(rows)} model(s): "
                + ", ".join(f"{n} {level}" for level, n in
                            sorted(by_level.items()))
                + (f". {len(untraceable)} cannot be traced to any catalogued "
                   f"feature and their level is not derived from anything"
                   if untraceable else "")
                + (f". {unstated} feature reference(s) carry no stated class "
                   f"and are taking the default, which is a class nobody chose"
                   if unstated else "")),
        }
