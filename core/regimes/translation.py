"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Translations, and the condition that makes them trustworthy.

A translation maps a regime's vocabulary onto MAYA's core terms: SS1/23's
"materiality" onto `is_material`, the EU AI Act's "high-risk deployment" onto a
combination of tier and purpose. Writing one is easy. Writing one that is *right*
is not, and a wrong translation produces exactly the class of bug that cannot be
defended to an examiner — a scope determination that is confidently incorrect.

The institution framework gives a check for this, and it is worth stating
plainly because it is the whole reason for the machinery:

    M ⊨_Σ' σ(φ)   ⟺   Mod(σ)(M) ⊨_Σ φ

**Truth is invariant under change of notation.** Evaluating a translated
obligation against the core state must give the same answer as translating the
state into the regime's vocabulary and evaluating the original obligation there.
If those disagree, the translation is wrong.

MAYA checks this rather than assuming it. A translation is tested against real
inventory states, and one that fails is refused — so a regime whose encoding is
inconsistent cannot be activated and quietly produce determinations nobody can
defend.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Sequence

from core.log import get_logger
from core.regimes.sentences import Sentence
from core.regimes.signature import CORE, Interpretation, Signature

logger = get_logger(__name__)


@dataclass(frozen=True)
class Translation:
    """A signature morphism: regime terms expressed as core terms.

    Each entry is a function from the core state to the regime's term. That is
    the direction that makes the satisfaction condition checkable: given a core
    state, both sides of the equivalence can be computed.
    """
    regime: Signature
    mapping: Mapping[str, Callable[[Mapping[str, Any]], Any]]

    def missing(self) -> List[str]:
        """Regime terms with no translation. Each is a term nothing can decide."""
        return sorted(t for t in self.regime.terms if t not in self.mapping)

    def interpret(self, core_state: Mapping[str, Any]) -> Interpretation:
        """`Mod(σ)` — the core state, read through the regime's vocabulary."""
        return Interpretation(self.regime,
                              {term: fn(core_state)
                               for term, fn in self.mapping.items()})


def satisfaction_condition(translation: Translation,
                           sentences: Sequence[Sentence],
                           core_states: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Check that truth survives translation, over a set of real states.

    The two sides:

      **direct** — read the core state through the regime's vocabulary, then
      evaluate the regime's own sentence there.

      **translated** — evaluate the same sentence against an interpretation built
      only from the terms the sentence actually uses, taken from the core state.

    They must agree for every sentence and every state. Where they do not, the
    translation assigns a regime term a meaning that does not survive the round
    trip, and the report names the sentence, the state and the term.
    """
    failures: List[Dict[str, Any]] = []
    checked = 0
    for index, state in enumerate(core_states):
        full = translation.interpret(state)
        for sentence in sentences:
            missing = [t for t in sentence.uses if t not in translation.mapping]
            if missing:
                failures.append({
                    "sentence": sentence.key, "state": index,
                    "reason": f"no translation for {', '.join(missing)}",
                    "terms": missing})
                continue
            narrowed = Interpretation(
                translation.regime,
                {t: translation.mapping[t](state) for t in sentence.uses})
            direct = sentence.holds(full)
            translated = sentence.holds(narrowed)
            checked += 1
            if direct == translated:
                continue
            # Distinguish the two ways this fails. A sentence that reads a term
            # it did not declare is an encoding error with a one-line fix; a
            # genuine change of truth is a wrong translation. Reporting them
            # alike would send someone looking in the wrong place.
            undeclared = sorted(t for t in translation.regime.terms
                                if t not in sentence.uses
                                and sentence.holds(Interpretation(
                                    translation.regime,
                                    {**narrowed.values,
                                     t: translation.mapping[t](state)})) == direct)
            failures.append({
                "sentence": sentence.key, "state": index,
                "reason": ("the sentence reads a term it did not declare"
                           if undeclared else "truth changed under translation"),
                "direct": direct, "translated": translated,
                "terms": list(sentence.uses),
                "undeclared": undeclared})
    holds = not failures
    if not holds:
        logger.warning("satisfaction condition failed for %s: %d discrepancies",
                       translation.regime.name, len(failures))
    return {
        "regime": translation.regime.name, "holds": holds,
        "checked": checked, "states": len(core_states),
        "untranslated_terms": translation.missing(),
        "failures": failures,
        "detail": (f"truth is invariant under translation across {checked} "
                   f"sentence-state pairs" if holds else
                   f"{len(failures)} discrepancy(ies): the translation assigns a "
                   "meaning that does not survive the round trip"),
    }
