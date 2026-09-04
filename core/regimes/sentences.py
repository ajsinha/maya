"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Sentences: a regulatory obligation, written in one regime's vocabulary.

A sentence is a predicate over an interpretation, plus the terms it uses. The
terms are declared rather than inferred, and checked against the signature when
the regime is built — so a sentence that reaches for a word its regime does not
define is refused at construction, not at evaluation against some unlucky model.

Sentences are deliberately small. A supervisory statement is forty pages of
open-textured prose, and turning it into obligations is expert work that this
package does not pretend to automate; what it does is hold the result in a form
that can be evaluated, translated, and checked for consistency.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Sequence, Tuple

from core.regimes.signature import Interpretation


@dataclass(frozen=True)
class Sentence:
    """One obligation, in one regime's vocabulary."""
    key: str
    text: str
    uses: Tuple[str, ...]
    holds: Callable[[Interpretation], bool]
    citation: str = ""

    def evaluate(self, interp: Interpretation) -> Dict[str, Any]:
        satisfied = bool(self.holds(interp))
        return {"sentence": self.key, "text": self.text, "satisfied": satisfied,
                "citation": self.citation,
                "read": {t: interp.get(t) for t in self.uses},
                "detail": (f"satisfied" if satisfied
                           else f"not satisfied: {self.text}")}


def requires(key: str, text: str, *terms: str, citation: str = "") -> Callable:
    """Declare a sentence whose obligation is that every named term is truthy.

    Most supervisory obligations have this shape — "there must be independent
    validation", "the model must have an identified owner" — so writing them out
    as predicates would be noise around a conjunction.
    """
    def holds(interp: Interpretation) -> bool:
        return all(interp.truthy(t) for t in terms)
    return Sentence(key, text, tuple(terms), holds, citation)


def forbids(key: str, text: str, term: str, citation: str = "") -> Sentence:
    """A sentence satisfied exactly when the named term is *not* truthy."""
    return Sentence(key, text, (term,), lambda i: not i.truthy(term), citation)


def implies(key: str, text: str, antecedent: str, consequent: str,
            citation: str = "") -> Sentence:
    """If the antecedent holds, the consequent must. Vacuously true otherwise.

    This is the shape almost every scoped obligation takes, and writing it
    explicitly keeps the vacuous case visible: a regime that does not apply is
    not a regime that is satisfied by accident.
    """
    return Sentence(key, text, (antecedent, consequent),
                    lambda i: (not i.truthy(antecedent)) or i.truthy(consequent),
                    citation)
