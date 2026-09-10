"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Turning a supervisory statement into an encoding, and stopping short of it.

A regime in MAYA is a signature, a set of sentences and a translation into the
core vocabulary — and writing one is expert work: forty pages of open-textured
prose become a dozen obligations that a firm's counsel has to stand behind.
`L-8` already checks that an encoding is *sound* once written. Nothing proposed
one, so every regime after the three shipped ones started from a blank file.

This proposes. It does not encode, and the distinction is the whole module.

**No predicate is ever generated.** A sentence carries an executable predicate,
and a language model emitting Python that decides what a regulation obliges is
the point at which a governance platform starts making up the law. So a proposal
names a **form** — `requires`, `forbids`, `implies` — and the terms it applies
to, and *MAYA* constructs the sentence from its own constructors. What crosses
the boundary is a form name and some term names, never code.

**Every proposed sentence carries the span it came from.** A sentence with no
citation is one nobody can check against the regulation, which makes the whole
proposal unauditable in exactly the way the encoding it is proposing must not
be.

**The proposal is checked before anybody reads it, and a failing proposal is
shown rather than withheld.** The existing machinery runs unchanged — untranslated
terms, deontic conflicts (`L-16`), the satisfaction condition (`L-8`) — and where
it fails, the failure is the most informative thing about the proposal: it says
precisely which sentence cannot be defended and against which state.

**Nothing here activates anything.** The output is a candidate a person reads,
argues with and writes into the library themselves. A regime that entered force
because a machine proposed it and a check passed would mean the institution's
obligations were set by something with no standing to set them — and the check
passing says the encoding is *self-consistent*, which is a much weaker claim than
that it is *right*.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.assist.common import AssistError
from core.log import get_logger
from core.regimes.common import RegimeError
from core.regimes.engine import PROBE_STATES
from core.regimes.sentences import Sentence, deontic_conflicts, forbids, implies, requires
from core.regimes.signature import CORE_TERMS, Signature
from core.regimes.translation import Translation, satisfaction_condition

logger = get_logger(__name__)

REQUIRES, FORBIDS, IMPLIES = "requires", "forbids", "implies"

#: The only shapes a proposal may take. MAYA builds the sentence; the proposal
#: names one of these and the terms. There is deliberately no form that carries
#: an expression, because the moment one exists, code crosses the boundary.
FORMS: Dict[str, str] = {
    REQUIRES: "every named term must be true",
    FORBIDS: "the named term must not be true",
    IMPLIES: "if the first term holds, the second must",
}

#: Modal phrases that mark an obligation, and which form they suggest. This is
#: how a lawyer reads a statute for duties, and it is the whole of MAYA's own
#: extraction where no provider is wired. Longest first.
MODALS: Tuple[Tuple[str, str], ...] = (
    ("must not", FORBIDS), ("shall not", FORBIDS), ("may not", FORBIDS),
    ("is prohibited from", FORBIDS), ("are prohibited from", FORBIDS),
    ("shall refrain from", FORBIDS),
    ("is required to", REQUIRES), ("are required to", REQUIRES),
    ("shall ensure", REQUIRES), ("must ensure", REQUIRES),
    ("shall", REQUIRES), ("must", REQUIRES),
)

#: Words in a regulation that name something MAYA already evaluates. Held as
#: data so the mapping can be published: a term that maps by a rule nobody can
#: read is one nobody can dispute.
CUES: Dict[str, Tuple[str, ...]] = {
    "has_owner": ("owner", "accountable individual", "senior manager",
                  "responsible person"),
    "has_validation": ("validation", "validated", "effective challenge"),
    "validation_independent": ("independent", "independence", "separate from "
                               "development"),
    "has_monitoring": ("monitoring", "monitored", "ongoing performance"),
    "has_documentation": ("documentation", "documented", "technical file",
                          "record keeping"),
    "has_operating_contract": ("limitations", "intended purpose",
                               "conditions of use", "operating"),
    "has_version": ("version", "in use", "in production", "deployed"),
    "has_artifact_digest": ("integrity", "traceability", "logging"),
    "is_material": ("material", "materiality", "significant"),
    "has_declared_purpose": ("purpose", "intended use", "use case"),
    "is_generative": ("general-purpose", "generative", "foundation model"),
    "is_adaptive": ("continues to learn", "adaptive", "self-learning"),
    "is_opaque": ("black box", "opaque", "not interpretable"),
    "has_warrants": ("authorisation", "authorised use", "permission"),
}

#: Sentences shorter than this are headings, cross-references and numbering.
MIN_SENTENCE = 30

#: Constructions a modal match reads badly, and what each one signals. Reported
#: on the candidate rather than corrected, because a reading MAYA is unsure of
#: and says so is worth more to an adjudicator than a confident wrong one — and
#: correcting it silently would be the platform interpreting the regulation.
AMBIGUOUS: Tuple[Tuple[str, str], ...] = (
    ("without", "'must not ... without ...' is a conditional obligation and "
                "not a prohibition; read as a prohibition it forbids the thing "
                "the regulation actually requires"),
    ("unless", "'unless' introduces an exception, which this reading drops "
               "entirely — the encoding would apply the duty in the case the "
               "regulation exempts"),
    ("other than", "an exclusion this reading does not carry"),
    ("except", "an exception this reading does not carry"),
    ("where appropriate", "a proportionality qualifier: encoded flat, the duty "
                          "binds in cases the regulation leaves to judgement"),
    ("as appropriate", "a proportionality qualifier this reading drops"),
    ("reasonable", "an open-textured standard no term can decide; whatever is "
                   "encoded here will be narrower than what was written"),
)


class RegimeEncodingAssistant:
    """Proposes an encoding from regulatory text, and checks it before anybody reads it."""

    def __init__(self, provider=None):
        # Optional. Without one, obligations are found by modal-verb matching —
        # weaker, deterministic, and the proposal says which produced it,
        # because how far to trust a reading depends entirely on that.
        self.provider = provider

    # ---------------------------------------------------------------- propose
    def propose(self, name: str, text: str,
                citation: str = "") -> Dict[str, Any]:
        """Read regulatory prose and propose a signature, sentences and a
        translation — then check the result and report the check."""
        if not (name or "").strip():
            raise AssistError("name_required",
                              "a proposed regime needs a key to be argued about",
                              "give it one, like 'ss1-23' or 'mas-fead'")
        if len((text or "").strip()) < MIN_SENTENCE:
            raise AssistError(
                "text_too_short",
                "there is not enough text here to read obligations out of",
                "paste the section of the statement that carries the duties; a "
                "heading is not an obligation")

        candidates, unread = self._extract(text, citation)
        terms = sorted({t for c in candidates for t in c["terms"]})
        untranslatable = [t for t in terms if t not in CORE_TERMS]
        proposal = {
            "regime": name.strip(),
            "signature": terms,
            "sentences": candidates,
            "translation": {t: _translation_for(t) for t in terms
                            if t in CORE_TERMS},
            "untranslatable": untranslatable,
            "read_by": ("provider" if self._has_provider() else "modal_match"),
        }
        checked = self.check(proposal)
        return {**proposal, "check": checked,
                "unread_sentences": unread,
                "activatable": False,
                "detail": self._detail(proposal, checked, unread)}

    @staticmethod
    def _detail(proposal: Dict[str, Any], checked: Dict[str, Any],
                unread: Sequence[str]) -> str:
        out = (f"{len(proposal['sentences'])} obligation(s) read out of the "
               f"text by "
               + ("the wired provider, whose form and terms were kept and "
                  "whose everything else was discarded"
                  if proposal["read_by"] == "provider" else
                  "matching modal verbs — weaker than a language model and "
                  "entirely explainable, which for a first pass over a statute "
                  "is arguably the better trade")
               + f". {checked['detail']}")
        uncertain = [c for c in proposal["sentences"] if c.get("uncertain")]
        dropped = [c for c in proposal["sentences"] if c.get("terms_dropped")]
        if uncertain:
            out += (f". {len(uncertain)} reading(s) are flagged uncertain and "
                    f"the reason is on each: a construction like 'must not ... "
                    f"without ...' is a conditional obligation, and read as a "
                    f"prohibition it forbids the thing the regulation requires. "
                    f"They are named rather than corrected, because correcting "
                    f"one would be the platform interpreting the regulation")
        if dropped:
            out += (f". {len(dropped)} obligation(s) named more terms than the "
                    f"form carries and the surplus is listed on each, since a "
                    f"proposal that silently dropped half an obligation would "
                    f"be the failure this module warns about everywhere else")
        if proposal["untranslatable"]:
            out += (f". {len(proposal['untranslatable'])} term(s) — "
                    f"{', '.join(proposal['untranslatable'])} — are outside the "
                    f"core vocabulary, so nothing in the platform can decide "
                    f"them; no translation is invented for them, because "
                    f"deciding that a regulation's word means one of MAYA's is "
                    f"the expert judgement this must not make")
        if unread:
            out += (f". {len(unread)} passage(s) were not turned into anything: "
                    f"either they carry no modal verb, or they carry a duty "
                    f"about something the platform holds no term for — and the "
                    f"second is the most important line in a gap analysis")
        out += (". Nothing here is activated. This is a candidate for somebody "
                "to read, argue with and write into the library themselves")
        return out

    def _has_provider(self) -> bool:
        return self.provider is not None and hasattr(self.provider,
                                                     "propose_encoding")

    def _extract(self, text: str,
                 citation: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        if self._has_provider():
            proposed = self.provider.propose_encoding(
                text, forms=dict(FORMS), core_terms=sorted(CORE_TERMS))
            logger.info("provider proposed %d sentence(s) from %d characters",
                        len(proposed or []), len(text))
            return [self._sanitise(p, citation) for p in (proposed or [])], []
        return _by_modal(text, citation)

    @staticmethod
    def _sanitise(proposed: Dict[str, Any], citation: str) -> Dict[str, Any]:
        """Keep the form and the terms. Discard everything else.

        A proposal arriving with an `expression`, a `predicate` or a `lambda`
        loses them here rather than at the constructor, because the interesting
        failure is not that the code would not run — it is that something tried
        to send code, and the record should show what was kept.
        """
        form = str(proposed.get("form") or "")
        return {
            "key": re.sub(r"[^a-z0-9_]", "_", str(proposed.get("key") or "")
                          .lower()).strip("_") or "unnamed",
            "form": form if form in FORMS else "",
            "text": str(proposed.get("text") or "").strip(),
            "terms": [str(t) for t in (proposed.get("terms") or [])],
            "terms_dropped": [],
            "uncertain": _ambiguity(
                str(proposed.get("source_span") or "").lower()),
            "citation": str(proposed.get("citation") or citation),
            "source_span": str(proposed.get("source_span") or ""),
            "discarded": sorted(set(proposed) - {"key", "form", "text", "terms",
                                                 "citation", "source_span"}),
        }

    # ------------------------------------------------------------------ check
    def check(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        """Run `L-8` and `L-16` over a proposal, unchanged.

        The same machinery `activate` uses. A proposal that fails is reported
        with its failure rather than withheld: the failure names the sentence
        that cannot be defended and the state it fails against, which is the
        most useful thing anybody could be told about a draft encoding.
        """
        buildable: List[Sentence] = []
        unbuildable: List[Dict[str, Any]] = []
        for candidate in proposal.get("sentences") or []:
            sentence = _build(candidate)
            if sentence is None:
                unbuildable.append(candidate)
            else:
                buildable.append(sentence)
        if not buildable:
            return {"holds": False, "checked": 0, "failures": [],
                    "conflicts": [], "unbuildable": _keys(unbuildable),
                    "detail": ("no sentence in this proposal could be built "
                               "from a published form, so there is nothing to "
                               "check. That is a proposal, not an encoding")}
        signature = Signature.of(proposal["regime"],
                                 set(proposal["signature"]) & CORE_TERMS)
        translation = Translation(
            signature, {t: _CORE_READS[t] for t in signature.terms})
        checkable = [s for s in buildable
                     if all(t in signature.terms for t in s.uses)]
        conflicts = deontic_conflicts(checkable)
        report = satisfaction_condition(translation, checkable, PROBE_STATES) \
            if checkable else {"holds": False, "checked": 0, "failures": [],
                               "detail": "no sentence uses only terms the "
                                         "platform can evaluate"}
        return {
            "holds": bool(report["holds"]) and not conflicts,
            "checked": report["checked"],
            "failures": report.get("failures", []),
            "conflicts": conflicts,
            "unbuildable": _keys(unbuildable),
            "not_checkable": [s.key for s in buildable if s not in checkable],
            "detail": _check_detail(report, conflicts, unbuildable, buildable,
                                    checkable),
        }

    # ------------------------------------------------------------------- what
    @staticmethod
    def describe() -> Dict[str, Any]:
        """The forms, the cues and the boundary — published before anything runs."""
        return {
            "forms": [{"form": f, "means": m} for f, m in FORMS.items()],
            "modals": [{"phrase": p, "suggests": f} for p, f in MODALS],
            "cues": {term: list(words) for term, words in CUES.items()},
            "core_terms": sorted(CORE_TERMS),
            "activates": False,
            "detail": (
                "a proposal names a form and some terms; MAYA builds the "
                "sentence from its own constructors, so no predicate ever "
                "crosses the boundary. Nothing here activates a regime: the "
                "output is a candidate a person reads, argues with and writes "
                "into the library themselves. A regime that entered force "
                "because a machine proposed it and a check passed would mean "
                "the institution's obligations were set by something with no "
                "standing to set them — and the check passing says the "
                "encoding is self-consistent, which is a far weaker claim than "
                "that it is right"),
        }


# ----------------------------------------------------------------- extraction
def _by_modal(text: str, citation: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """MAYA's own reading: find the duties by their modal verbs.

    Weaker than a language model and entirely explainable — which for a first
    pass over a statute is arguably the better trade: an obligation this misses
    is one a person adds, and an obligation it invents is one they would have to
    find and remove.
    """
    candidates, unread = [], []
    for index, span in enumerate(_sentences(text)):
        # Whitespace collapsed before matching. Regulatory text arrives pasted
        # out of a PDF, and a cue like "black box" or "conditions of use" is
        # split across a line break in about half of it — a matcher that missed
        # those would report the duty as unreadable and look like a limit of
        # the vocabulary rather than of the paste.
        lowered = re.sub(r"\s+", " ", span.lower())
        form = next((f for phrase, f in MODALS if phrase in lowered), "")
        if not form:
            unread.append(span)
            continue
        terms = _terms_in(lowered)
        if not terms:
            # A duty MAYA can see and cannot express. Reported as unread rather
            # than dropped: an obligation the platform cannot evaluate is the
            # most important thing in a gap analysis.
            unread.append(span)
            continue
        ordered = _ordered(form, terms)
        candidates.append({
            "key": _key_for(terms, index),
            "form": _form_for(form, terms),
            "text": _statement(form, terms),
            "terms": ordered,
            # An obligation naming four things becomes a two-term implication,
            # and the two that did not fit are named. A proposal that silently
            # dropped half an obligation would be the exact failure this module
            # warns about everywhere else.
            "terms_dropped": [t for t in terms if t not in ordered],
            "uncertain": _ambiguity(lowered),
            "citation": citation,
            "source_span": span.strip(),
            "discarded": [],
        })
    return candidates, unread


def _ambiguity(lowered: str) -> List[str]:
    """Why this reading may be wrong. Named, never corrected."""
    return [why for word, why in AMBIGUOUS if word in lowered]


def _sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.;])\s+|\n{2,}", text)
    return [re.sub(r"\s+", " ", p).strip() for p in parts
            if len(p.strip()) >= MIN_SENTENCE]


def _terms_in(lowered: str) -> List[str]:
    found = []
    for term, cues in CUES.items():
        if any(cue in lowered for cue in cues):
            found.append(term)
    return found


def _form_for(form: str, terms: Sequence[str]) -> str:
    """Two terms and an obligation is nearly always a scoped one.

    "an in-scope model must have an owner" is an implication and not a bare
    requirement, and encoding it as the latter obliges every model in the
    estate — including the ones the regulation does not reach.
    """
    if form == REQUIRES and len(terms) >= 2:
        return IMPLIES
    return form


def _ordered(form: str, terms: List[str]) -> List[str]:
    if _form_for(form, terms) == IMPLIES:
        # Antecedent first, and scope-ish terms make the better antecedent.
        scope = [t for t in terms if t in ("has_version", "is_material",
                                           "has_declared_purpose",
                                           "is_generative")]
        rest = [t for t in terms if t not in scope]
        pair = (scope + rest)[:2]
        return pair if len(pair) == 2 else terms[:2]
    if form == FORBIDS:
        return terms[:1]
    return terms


def _key_for(terms: Sequence[str], index: int) -> str:
    return f"{terms[0]}_{index}" if terms else f"sentence_{index}"


def _statement(form: str, terms: Sequence[str]) -> str:
    ordered = _ordered(form, list(terms))
    if _form_for(form, terms) == IMPLIES:
        return f"where {ordered[0]} holds, {ordered[1]} must hold"
    if form == FORBIDS:
        return f"{ordered[0]} must not hold"
    return f"{', '.join(ordered)} must hold"


# ------------------------------------------------------------------ building
def _build(candidate: Dict[str, Any]) -> Optional[Sentence]:
    """Construct a sentence from a form and terms — MAYA's constructors only."""
    form, terms = candidate.get("form"), list(candidate.get("terms") or [])
    key, text = candidate.get("key") or "unnamed", candidate.get("text") or ""
    citation = candidate.get("citation") or ""
    try:
        if form == REQUIRES and terms:
            return requires(key, text, *terms, citation=citation)
        if form == FORBIDS and len(terms) == 1:
            return forbids(key, text, terms[0], citation=citation)
        if form == IMPLIES and len(terms) == 2:
            return implies(key, text, terms[0], terms[1], citation=citation)
    except RegimeError as refused:
        logger.info("proposed sentence %s could not be built: %s", key,
                    refused.code)
        return None
    return None


def _keys(rows: Sequence[Any]) -> List[str]:
    return [r.get("key", "unnamed") if isinstance(r, dict) else r.key
            for r in rows]


def _translation_for(term: str) -> str:
    """How a core term would be read. Published as prose, never as code."""
    return f"truthy({term}) on the model's core state"


#: Every core term reads as itself. A regime whose vocabulary IS the core
#: vocabulary translates by identity, which is the only translation a machine
#: may propose: inventing a mapping — 'their `oversight` means our
#: `has_validation`' — is precisely the expert judgement this must not make.
_CORE_READS = {term: (lambda s, t=term: bool(s.get(t))) for term in CORE_TERMS}


def _check_detail(report, conflicts, unbuildable, buildable, checkable) -> str:
    out = (f"{len(buildable)} sentence(s) built from published forms, "
           f"{len(checkable)} of them checkable against the core vocabulary")
    if unbuildable:
        out += (f". {len(unbuildable)} named no form MAYA constructs and were "
                f"dropped rather than interpreted")
    if conflicts:
        out += (". The encoding obliges and forbids the same term(s): "
                + "; ".join(c["detail"] for c in conflicts)
                + " — no state satisfies both, so every determination would be "
                  "unsatisfiable")
    if not report["holds"]:
        out += (f". The satisfaction condition fails: {report['detail']}. That "
                f"is the most useful thing about this draft — it names the "
                f"sentence that could not be defended to an examiner, before "
                f"anybody has written it into the library")
    else:
        out += (". The satisfaction condition holds over the probe states, "
                "which says this draft is self-consistent — a far weaker claim "
                "than that it reads the regulation correctly, and the reason "
                "nothing here activates anything")
    return out
