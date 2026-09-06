"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Signatures: the vocabulary a supervisory regime talks in.

Regimes do not disagree only about requirements. They disagree about **what
words mean**. SR 26-2 reasons about complexity, exposure and whether something
applies statistical, economic or financial theory. The EU AI Act reasons about
intended purpose, deployers, natural persons and Annex III categories. SS1/23
reasons about materiality and proportionality. These are different vocabularies
describing overlapping realities, and flattening them into one set of fields is
how a scope determination becomes indefensible.

So each regime carries its own **signature** — the terms it may use — and a
**translation** into MAYA's own vocabulary. Adding a regulator is then adding a
signature and a translation, and nothing in the schema, the API or the interface
moves.

The translation is the interesting part, and it is checked. See translation.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, FrozenSet, Iterable, Mapping


@dataclass(frozen=True)
class Signature:
    """The terms a regime may use, and nothing else."""
    name: str
    terms: FrozenSet[str]

    @classmethod
    def of(cls, name: str, terms: Iterable[str]) -> "Signature":
        return cls(name, frozenset(terms))

    def contains(self, term: str) -> bool:
        return term in self.terms

    def missing(self, used: Iterable[str]) -> list:
        """Terms a sentence used that this signature does not define."""
        return sorted(t for t in used if t not in self.terms)


# MAYA's own vocabulary: the terms the platform can actually evaluate against a
# model's state. Every regime translates into this, and a term outside it is a
# term nothing can decide.
CORE_TERMS: FrozenSet[str] = frozenset({
    # identity and ownership
    "has_owner", "has_declared_purpose", "legal_entity", "domain",
    # what kind of thing it is
    "trainability_class", "parameter_kind", "is_opaque", "is_adaptive",
    "is_generative", "output_kind",
    # materiality
    "tier", "exposure", "purpose_class", "is_material",
    # evidence
    "has_version", "has_artifact_digest", "has_operating_contract",
    "has_feature_contract", "has_validation", "validation_independent",
    "has_monitoring", "has_documentation", "is_attested",
    "open_blocking_findings", "has_overlays", "overlay_persistent",
    # use
    "environments", "has_warrants", "human_in_the_loop",
})

CORE = Signature.of("maya.core", CORE_TERMS)


@dataclass(frozen=True)
class Interpretation:
    """A regime's state, read through its own vocabulary.

    This is `Mod(Σ)` — an inventory state as that regime sees it. Producing one
    is exactly the act of translating, and doing it explicitly is what lets the
    satisfaction condition be checked rather than assumed.
    """
    signature: Signature
    values: Mapping[str, Any] = field(default_factory=dict)

    def get(self, term: str, default: Any = None) -> Any:
        if not self.signature.contains(term):
            raise KeyError(
                f"'{term}' is not in the {self.signature.name} signature; a regime "
                "may only reason in its own vocabulary")
        return self.values.get(term, default)

    def truthy(self, term: str) -> bool:
        value = self.get(term)
        return bool(value) if not isinstance(value, (int, float)) else value > 0
