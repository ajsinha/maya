"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Derived features: Z = f(X, Y).

A derived feature is one whose values are computed from other features rather
than supplied. Log transforms, ratios, interaction terms — the ordinary
furniture of a regression, and the ordinary place where a training set quietly
becomes wrong.

Four rules govern them, and each exists because the alternative fails silently.

**Lineage is recorded**, so a primitive cannot be retired while something derives
from it. That is the retirement guard feature views already have, one hop out.

**The ingest clock is inherited as a maximum**: ``ingest_ts(Z) = max(ingest_ts(X),
ingest_ts(Y))``. You did not know Z before you knew both its inputs. Taking the
minimum — or stamping the moment of computation — would make a derived feature
appear knowable earlier than it was, and every point-in-time assembly built on it
would be subtly, invisibly early. This is the easiest way to leak the future into
a training set, and it is arithmetic, so it is computed rather than trusted.

**A derived feature may not read a label.** ``price_per_sqft = sale_price /
living_area_sqft`` is leakage with a division sign in front of it. The check
walks the whole lineage, not just the immediate inputs, because a derivation of a
derivation of the label is still the label.

**Certification is the meet of its inputs.** Deriving from an uncertified feature
does not launder it.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Set

from core.evidence import EvidenceEngine
from core.features.common import INGEST_TIME, FeatureError
from core.features.expressions import Expression
from core.log import get_logger
from db import DerivedFeatureRepository, FeatureRepository
from db.database import digest as canonical_digest

logger = get_logger(__name__)

INTERNAL, EXTERNAL = "internal", "external"
EVALUATORS = (INTERNAL, EXTERNAL)

# What to record when the arithmetic has no answer for a row.
ON_ERROR = ("null", "refuse")

# Certification is a chain, weakest first; a derived feature sits at the meet.
CERTIFICATION_ORDER = ("experimental", "reviewed", "certified", "gold")


# A derivation deeper than this is a modelling problem rather than a depth
# problem, and the refusal says so instead of exhausting the stack.
MAX_DEPTH = 12


class DerivedFeatures:
    """Defines derived features, keeps their lineage, and evaluates them."""

    def __init__(self, derived: DerivedFeatureRepository,
                 features: FeatureRepository, catalogue, evidence: EvidenceEngine):
        self.derived, self.features = derived, features
        self.catalogue, self.evidence = catalogue, evidence

    # ----------------------------------------------------------------- define
    def define(self, name: str, expression: str, dtype: str, description: str,
               owner: str, evaluator: str = INTERNAL, on_error: str = "null",
               note: str = "", actor: str = "system") -> Dict[str, Any]:
        """Declare a feature computed from others. Definitions are versioned."""
        if evaluator not in EVALUATORS:
            raise FeatureError(f"evaluator must be one of {', '.join(EVALUATORS)}")
        if on_error not in ON_ERROR:
            raise FeatureError(f"on_error must be one of {', '.join(ON_ERROR)}")

        parsed = Expression(expression)
        inputs = parsed.feature_names()
        if not inputs and not parsed.reads_clock():
            raise FeatureError(
                f"'{name}' reads no features, so it is a constant rather than a "
                f"derived feature")
        if name in inputs:
            raise FeatureError(f"'{name}' is defined in terms of itself")
        if missing := self.catalogue.missing(inputs):
            raise FeatureError(
                f"undefined inputs: {', '.join(missing)}; a derived feature can "
                f"only read features the catalogue knows about")
        self._refuse_cycle(name, inputs)

        row = self.features.one(name=name)
        if row is None:
            entity = self._entity_of(inputs)
            row = {"name": name, "entity": entity, "dtype": dtype,
                   "description": description, "owner": owner,
                   "certification": self.certification_of(inputs),
                   "created_at": time.time()}
            self.features.add(row)
        version = len(self.derived.many(name=name)) + 1
        definition = {
            "feature_id": row["id"], "name": name, "expression": parsed.source,
            "inputs": inputs, "evaluator": evaluator, "on_error": on_error,
            "definition_version": version, "note": note,
            "digest": canonical_digest({"expression": parsed.source, "inputs": inputs}),
            "created_by": actor, "created_at": time.time()}
        self.derived.add(definition)
        self.evidence.append("derived_feature_defined", "feature", row["id"],
                             {"name": name, "expression": parsed.source,
                              "inputs": inputs, "definition_version": version,
                              "evaluator": evaluator}, actor=actor)
        logger.info("defined derived feature %s@v%d over %s", name, version, inputs)
        return self.derived.one(id=definition["id"])

    def _entity_of(self, inputs: Sequence[str]) -> str:
        """A derived feature lives at the grain of its inputs, and they must
        agree — a ratio of a per-customer to a per-account number is not one
        number, and stored as one it would be silently wrong."""
        entities = {self.catalogue.require(n)["entity"] for n in inputs}
        if len(entities) > 1:
            raise FeatureError(
                f"inputs span more than one entity ({', '.join(sorted(entities))}); "
                f"a derived feature has one grain, so combine them in a view first")
        return entities.pop() if entities else "unknown"

    def _refuse_cycle(self, name: str, inputs: Sequence[str]) -> None:
        for start in inputs:
            if name in self.lineage(start):
                raise FeatureError(
                    f"'{name}' would depend on itself through '{start}'")

    # ---------------------------------------------------------------- lineage
    def lineage(self, name: str, seen: Optional[Set[str]] = None) -> Set[str]:
        """Every feature this one rests on, transitively.

        The closure and not just the immediate inputs, because a derivation of a
        derivation of the label is still the label.
        """
        seen = seen if seen is not None else set()
        definition = self.derived.current(name)
        if definition is None:
            return seen
        for parent in definition["inputs"]:
            if parent not in seen:
                seen.add(parent)
                self.lineage(parent, seen)
        return seen

    def depends_on(self, name: str, candidate: str) -> bool:
        return candidate in self.lineage(name)

    # ------------------------------------------------------------ provenance
    def provenance(self, name: str,
                   depth: int = 0) -> Dict[Any, int]:
        """This feature as a polynomial over the base features it rests on.

        The same `ℕ[X]` the evidence chain uses (`L-9`), applied one layer
        across. A derivation is a term; annotating each base feature with its
        own variable and evaluating the term in the free commutative semiring
        gives the object every other question about the feature is a
        *homomorphism out of*:

        | Question | The homomorphism |
        |---|---|
        | what does this rest on? | the variables of the polynomial |
        | when did it become knowable? | pushforward into (max, max) |
        | does it touch the label? | membership of the label's variable |
        | how much do we trust it? | pushforward into the trust semiring |

        The ingest clock in particular stops being a rule somebody could forget
        to apply. It is a homomorphism, and homomorphisms do not have
        exceptions — which is the strongest form the platform's "arithmetic, not
        policy" claim can take.
        """
        from core.evidence.semirings import (POLYNOMIAL, poly_variable)
        if depth > MAX_DEPTH:
            raise FeatureError(
                f"'{name}' derives through more than {MAX_DEPTH} levels; that is "
                f"a modelling problem rather than a depth problem")
        definition = self.derived.current(name)
        if definition is None:
            return poly_variable(name)              # a base feature IS a variable
        total = POLYNOMIAL.zero
        term = POLYNOMIAL.one
        for parent in definition["inputs"]:
            term = POLYNOMIAL.times(term, self.provenance(parent, depth + 1))
        return POLYNOMIAL.plus(total, term)

    def rests_on(self, name: str) -> Set[str]:
        """The variables of the polynomial — lineage, read off the algebra.

        Agrees with `lineage()` on every derivation, which is asserted rather
        than assumed: two routes to one answer are worth having only while they
        agree, and worth testing for exactly that reason.
        """
        return {variable
                for monomial in self.provenance(name)
                for variable, _ in monomial}

    def dependants_of(self, feature_name: str) -> List[str]:
        """What would break if this feature were retired."""
        return sorted({d["name"] for d in self.derived.many()
                       if feature_name in self.lineage(d["name"])})

    def certification_of(self, inputs: Sequence[str]) -> str:
        """The meet: as certified as the least-certified input, never more."""
        levels = [self.catalogue.require(n).get("certification", "experimental")
                  for n in inputs]
        ranks = [CERTIFICATION_ORDER.index(l) if l in CERTIFICATION_ORDER else 0
                 for l in levels]
        return CERTIFICATION_ORDER[min(ranks)] if ranks else "experimental"

    # ---------------------------------------------------------------- leakage
    def refuse_if_reads(self, name: str, label: str) -> None:
        """A feature derived from the label leaks the answer into the set."""
        if name == label or self.depends_on(name, label):
            raise FeatureError(
                f"'{name}' is computed from '{label}', which this featureset "
                f"declares as its label — a feature derived from the label leaks "
                f"the answer into the training set. derive it from a value known "
                f"before the outcome, or declare it an output rather than a feature")

    # --------------------------------------------------------------- evaluate
    def compute(self, name: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add the derived column to each row, with its inherited ingest clock.

        The rows come back with ``ingest_ts`` advanced to the latest of the
        inputs the value rests on, because that is when the value became
        knowable.
        """
        definition = self.require(name)
        if definition["evaluator"] == EXTERNAL:
            raise FeatureError(
                f"'{name}' is declared external, so MAYA does not compute it; "
                f"materialise its values like any primitive — the definition is "
                f"still kept, so lineage and the leakage check still apply")
        parsed = Expression(definition["expression"])
        out = []
        for row in rows:
            value = parsed.evaluate(row)
            if value is None and definition["on_error"] == "refuse":
                raise FeatureError(
                    f"'{name}' has no value for entity {row.get('entity_id')} and "
                    f"its definition says to refuse rather than record a null")
            out.append({**row, name: value,
                        INGEST_TIME: self.knowable_at(row, definition["inputs"])})
        return out

    @staticmethod
    def knowable_at(row: Dict[str, Any], inputs: Sequence[str]) -> float:
        """ingest_ts(Z) = max over the inputs. You did not know Z before them.

        Rows carry one ingest stamp rather than one per column, so the row's own
        stamp is the floor; per-input stamps refine it upward where a caller has
        them. Downward would be a lie about when the value could have been used.
        """
        stamps = [row.get(f"{i}__{INGEST_TIME}") for i in inputs]
        known = [s for s in stamps if s is not None] + [row.get(INGEST_TIME, 0.0)]
        return max(known)

    # ------------------------------------------------------------------ query
    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self.derived.current(name)

    def require(self, name: str) -> Dict[str, Any]:
        definition = self.get(name)
        if definition is None:
            raise FeatureError(f"'{name}' is not a derived feature")
        return definition

    def is_derived(self, name: str) -> bool:
        return self.derived.current(name) is not None

    def list(self) -> List[Dict[str, Any]]:
        """The current definition of each derived feature, newest version only."""
        names = sorted({d["name"] for d in self.derived.many()})
        return [self.derived.current(n) for n in names]

    def history(self, name: str) -> List[Dict[str, Any]]:
        """Every definition of a name. A correction is a new version, because
        somebody may already have trained against the old one."""
        return sorted(self.derived.many(name=name), key=lambda d: d["definition_version"])
