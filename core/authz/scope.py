"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Scope: which models a principal's permissions actually reach.

A permission says what someone may do. A scope says what they may do it **to**.
Both are needed, and conflating them is how a validator in the UK entity ends up
able to approve a US model because they hold the right role globally.

Two dimensions, because these are the two a bank actually organises around:

  * **Legal entity** — model risk aggregates by entity, not by org chart, and
    entities answer to different supervisors.
  * **Domain** — credit, market, financial crime, operations. How second-line
    specialisms are divided.

An empty list means unrestricted on that dimension. That default is deliberate:
the alternative, enumerating every entity for every principal, is the design
that makes people grant a wildcard to get on with their day, and a wildcard
granted in haste is indistinguishable from no control at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence, Tuple


@dataclass(frozen=True)
class Scope:
    """The set of models a principal may act on."""
    legal_entities: Tuple[str, ...] = ()
    domains: Tuple[str, ...] = ()

    @classmethod
    def of(cls, principal: Dict[str, Any]) -> "Scope":
        return cls(tuple(principal.get("legal_entities") or ()),
                   tuple(principal.get("domains") or ()))

    @property
    def unrestricted(self) -> bool:
        return not self.legal_entities and not self.domains

    def permits(self, model: Dict[str, Any]) -> bool:
        """Whether this scope reaches a model."""
        if self.legal_entities and model.get("legal_entity") not in self.legal_entities:
            return False
        if self.domains and model.get("domain") not in self.domains:
            return False
        return True

    def refusal(self, model: Dict[str, Any]) -> str:
        """Why it did not reach — naming the dimension that excluded it."""
        if self.legal_entities and model.get("legal_entity") not in self.legal_entities:
            return (f"model belongs to legal entity {model.get('legal_entity')}, "
                    f"outside your scope ({', '.join(self.legal_entities)})")
        if self.domains and model.get("domain") not in self.domains:
            return (f"model is in the {model.get('domain')} domain, "
                    f"outside your scope ({', '.join(self.domains)})")
        return "outside your scope"

    def filter(self, models: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Row-level filtering for listings.

        Applied to the inventory rather than to each detail page alone, so a
        model outside scope is not merely unopenable — it is not visible, and
        its existence is not disclosed by a count that does not add up.
        """
        return [m for m in models if self.permits(m)]

    def describe(self) -> str:
        if self.unrestricted:
            return "all entities, all domains"
        parts = []
        parts.append(", ".join(self.legal_entities) if self.legal_entities else "all entities")
        parts.append(", ".join(self.domains) if self.domains else "all domains")
        return " / ".join(parts)
