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
from typing import Any, Callable, Dict, List, Sequence, Tuple

from core.regimes.signature import Interpretation


#: A sentence's deontic MODE, which is what makes L-16 checkable at all.
#: `holds` is an opaque predicate, so consistency cannot be decided over
#: arbitrary sentences — but almost every supervisory obligation has one of three
#: shapes, and for those the modality is structural. A sentence built by hand
#: from a lambda is `custom`, and the consistency check says so rather than
#: pretending to have proved something about it.
OBLIGES, FORBIDS, CONDITIONAL, CUSTOM = "obliges", "forbids", "conditional", "custom"


@dataclass(frozen=True)
class Sentence:
    """One obligation, in one regime's vocabulary."""
    key: str
    text: str
    uses: Tuple[str, ...]
    holds: Callable[[Interpretation], bool]
    citation: str = ""
    mode: str = CUSTOM
    #: Terms this sentence requires to be true, and terms it requires to be
    #: false. Empty for a `custom` sentence, which is the honest answer.
    obliged: Tuple[str, ...] = ()
    forbidden: Tuple[str, ...] = ()

    def evaluate(self, interp: Interpretation) -> Dict[str, Any]:
        satisfied = bool(self.holds(interp))
        read = {t: interp.get(t) for t in self.uses}
        # WHY it is not satisfied, which is two different answers.
        #
        # A term MAYA holds and that is false is a finding about the model. A
        # term MAYA does not hold at all is a finding about the platform's
        # coverage, and reporting them alike sends somebody to fix the wrong
        # thing. This matters more here than anywhere: four obligations in one
        # regime used to be satisfied for every model by a Python default, and
        # nothing on the answer distinguished a fact from a fabrication.
        unknown = sorted(t for t, v in read.items() if v is None)
        return {"sentence": self.key, "text": self.text, "satisfied": satisfied,
                "citation": self.citation, "read": read,
                "not_recorded": unknown,
                "detail": ("satisfied" if satisfied
                           else f"not satisfied: {self.text}"
                                + (f" — and MAYA holds no value for "
                                   f"{', '.join(unknown)}, so this is a gap in "
                                   f"what has been recorded rather than a "
                                   f"judgement about the model" if unknown else ""))}


def requires(key: str, text: str, *terms: str, citation: str = "") -> Sentence:
    """Declare a sentence whose obligation is that every named term is truthy.

    Most supervisory obligations have this shape — "there must be independent
    validation", "the model must have an identified owner" — so writing them out
    as predicates would be noise around a conjunction.
    """
    def holds(interp: Interpretation) -> bool:
        return all(interp.truthy(t) for t in terms)
    return Sentence(key, text, tuple(terms), holds, citation,
                    mode=OBLIGES, obliged=tuple(terms))


def forbids(key: str, text: str, term: str, citation: str = "") -> Sentence:
    """A sentence satisfied exactly when the named term is *not* truthy."""
    return Sentence(key, text, (term,), lambda i: not i.truthy(term), citation,
                    mode=FORBIDS, forbidden=(term,))


def implies(key: str, text: str, antecedent: str, consequent: str,
            citation: str = "") -> Sentence:
    """If the antecedent holds, the consequent must. Vacuously true otherwise.

    This is the shape almost every scoped obligation takes, and writing it
    explicitly keeps the vacuous case visible: a regime that does not apply is
    not a regime that is satisfied by accident.
    """
    # The consequent is obliged only where the antecedent holds, so it is
    # recorded as a CONDITIONAL obligation. Treating it as unconditional would
    # report a contradiction between two regimes that never both apply.
    return Sentence(key, text, (antecedent, consequent),
                    lambda i: (not i.truthy(antecedent)) or i.truthy(consequent),
                    citation, mode=CONDITIONAL, obliged=(consequent,))


def deontic_conflicts(sentences: Sequence[Sentence]) -> List[Dict[str, Any]]:
    """Terms one sentence obliges and another forbids — `O φ ∧ F φ`.

    This is L-16, and it is decidable exactly as far as the sentences declare
    their shape. `holds` is an opaque predicate, so consistency cannot be proved
    over arbitrary sentences; what can be decided is the case that actually
    occurs, which is two obligations written in the same vocabulary pulling a
    term in opposite directions.

    A **conditional** obligation is not counted against an unconditional
    prohibition. `if it is high-risk then it must have human oversight` and
    `it must not run unattended` do not contradict — they may simply never both
    apply — and reporting them as a contradiction would train somebody to ignore
    the check. Two conditionals are likewise left alone: deciding whether their
    antecedents can hold together is the satisfaction condition's job, over
    states, and this one reasons only about shape.
    """
    obliged: Dict[str, List[str]] = {}
    forbidden: Dict[str, List[str]] = {}
    for sentence in sentences:
        if sentence.mode == OBLIGES:
            for term in sentence.obliged:
                obliged.setdefault(term, []).append(sentence.key)
        elif sentence.mode == FORBIDS:
            for term in sentence.forbidden:
                forbidden.setdefault(term, []).append(sentence.key)

    return [{"term": term,
             "obliged_by": sorted(obliged[term]),
             "forbidden_by": sorted(forbidden[term]),
             "detail": f"'{term}' is required by {', '.join(sorted(obliged[term]))} "
                       f"and forbidden by {', '.join(sorted(forbidden[term]))}; "
                       f"no state satisfies both, so every determination this "
                       f"regime makes is unsatisfiable"}
            for term in sorted(set(obliged) & set(forbidden))]


def undecidable(sentences: Sequence[Sentence]) -> List[str]:
    """Sentences whose shape the consistency check cannot see.

    Reported rather than assumed consistent: a check that quietly ignores what
    it cannot read is a check that reports success for the cases it was least
    able to judge.
    """
    return sorted(s.key for s in sentences if s.mode == CUSTOM)
