"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Asking in English, and the boundary that makes it safe.

"Ask your data a question" is the demo every vendor gives and the feature every
model risk function is right to distrust, because in the usual construction the
language model sees the rows and produces the answer — which means a number on a
committee slide was written by something that cannot be asked where it got it.

The construction here inverts that. **The model produces a query and never a
number.** What it is given is the semantic layer's published catalogue —
entities, fields, operators — and what it hands back is a structured object. The
rows come from the register, computed by the same code the screens use, under
the reader's own scope. Nothing the model emits reaches a database, because the
proposal is *validated against the catalogue* before it runs and refused by name
if it names a field that does not exist.

**The query is always shown, alongside any rows.** Not behind a disclosure
triangle, not on request. An interface that shows only the answer is one where
nobody can tell a misread question from a wrong number — and the misread
question is far commoner. Somebody asking *how many models are unmonitored* and
being handed 4 has no way to know the query counted retired models unless the
query is in front of them.

**A refused proposal is reported, not retried into something else.** When the
translation names a field the layer does not have, the answer is the proposal
and the refusal. Quietly falling back to a query that *does* parse would answer
a different question than the one asked, in a form indistinguishable from
answering the right one.

**Where no provider is wired, MAYA translates by matching the published
vocabulary** — deterministic, explainable, and honest about it: the answer says
which of the two produced the query, because how much a reader should trust the
translation depends entirely on that. The matcher also reports the words it did
*not* use, since a translator that silently drops half a question is the failure
mode this whole design is arranged against.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

from core.assist.common import AssistError
from core.log import get_logger
from core.reporting.semantics import (ADMISSIBLE, ENTITIES, OPERATORS,
                                      QueryError)

logger = get_logger(__name__)

PROVIDER, VOCABULARY = "provider", "vocabulary_match"

#: Phrases that name an operator, longest first so "at least" is not read as
#: "least". Held as data because the vocabulary is the interface: a phrase list
#: buried in a chain of conditionals is one nobody can publish.
PHRASES: Tuple[Tuple[str, str], ...] = (
    ("greater than or equal to", "gte"), ("less than or equal to", "lte"),
    ("at least", "gte"), ("at most", "lte"),
    ("no more than", "lte"), ("no fewer than", "gte"),
    ("more than", "gt"), ("greater than", "gt"),
    ("fewer than", "lt"), ("less than", "lt"),
    ("is not", "ne"), ("not equal to", "ne"), ("other than", "ne"),
    ("contains", "contains"), ("containing", "contains"),
    ("mentions", "contains"),
    ("is missing", "is_null"), ("has no", "is_null"), ("without", "is_null"),
    ("has a", "not_null"), ("with a", "not_null"),
    ("one of", "in"), ("any of", "in"),
    ("equals", "eq"), ("is", "eq"), ("of", "eq"),
)

#: Words that carry no meaning for a query and are not reported as ignored. A
#: list of "ignored words" full of `the` and `me` is one nobody reads.
NOISE = frozenset((
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for",
    "from", "get", "give", "has", "have", "how", "i", "in", "list", "many",
    "me", "much", "of", "on", "or", "please", "show", "that", "the", "their",
    "them", "there", "this", "to", "us", "want", "was", "were", "what",
    "which", "who", "with", "you", "all", "any", "every", "its", "is", "it",
    "tell", "find", "count", "each"))

TRUE_WORDS = frozenset(("true", "yes", "y"))
FALSE_WORDS = frozenset(("false", "no", "n"))


class NaturalLanguageQuery:
    """Translates a question into a structured query, and shows it either way."""

    def __init__(self, semantics, provider=None, capabilities=None,
                 capability_key: str = "", generations=None):
        self.semantics = semantics
        # Optional. Without one, translation is the published-vocabulary match
        # and the answer says so — which is a weaker translator and an honest
        # one, rather than a better translator nobody can account for.
        self.provider = provider
        self.capabilities, self.capability_key = capabilities, capability_key
        self.generations = generations

    # -------------------------------------------------------------- translate
    def translate(self, question: str) -> Dict[str, Any]:
        """A structured query, or a refusal — and always the proposal."""
        if not (question or "").strip():
            raise AssistError(
                "question_required",
                "there is no question here to translate",
                "ask something about the register — "
                f"it holds {', '.join(sorted(ENTITIES))}")
        proposed, by, notes = self._propose(question)
        checked = self._validate(proposed)
        return {
            "question": question, "proposed": proposed,
            "translated_by": by, "understood": checked is None,
            "refusal": checked,
            **notes,
            "detail": self._detail(question, proposed, by, checked, notes),
        }

    def _propose(self, question: str) -> Tuple[Dict[str, Any], str, Dict]:
        if self.provider is not None and hasattr(self.provider, "propose_query"):
            proposal = self.provider.propose_query(
                question, catalogue=self.semantics.describe())
            logger.info("provider %s proposed a query for %r",
                        getattr(self.provider, "key", "?"), question[:60])
            return dict(proposal or {}), PROVIDER, {"used": [], "ignored": []}
        proposal, notes = _match(question)
        return proposal, VOCABULARY, notes

    def _validate(self, proposed: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Run it against the catalogue for one row. Nothing else validates it."""
        entity = proposed.get("entity") or ""
        try:
            self.semantics.query(
                entity, select=proposed.get("select"),
                where=proposed.get("where") or [], limit=1)
        except QueryError as refused:
            logger.info("proposed query on %r was refused: %s", entity,
                        refused.code)
            return refused.as_problem()
        return None

    @staticmethod
    def _detail(question, proposed, by, refusal, notes) -> str:
        if refusal:
            return (f"this reads as a query over '{proposed.get('entity') or 'nothing'}' "
                    f"and the register refuses it: {refusal['detail']}. The "
                    f"proposal is shown rather than retried into something that "
                    f"parses, because a query that answered a different "
                    f"question would be indistinguishable from one that "
                    f"answered this one")
        out = (f"read as {_render(proposed)}"
               + (", matched against the published vocabulary rather than by a "
                  "language model" if by == VOCABULARY else
                  ", proposed by the wired provider and then checked against "
                  "the published catalogue before anything ran"))
        if notes.get("ignored"):
            out += (f". {len(notes['ignored'])} word(s) were not used — "
                    f"{', '.join(notes['ignored'][:6])} — and that is said here "
                    f"because a translator that silently drops half a question "
                    f"is the failure this is arranged against")
        return out

    # -------------------------------------------------------------------- ask
    def ask(self, question: str, scope=None, limit: int = 100,
            actor: str = "system",
            now: Optional[float] = None) -> Dict[str, Any]:
        """Translate, show the query, and run it if it stands.

        The rows come from the register under the caller's own scope. Nothing
        the translator produced is in them, and no number here was written by a
        model.
        """
        translation = self.translate(question)
        moment = now if now is not None else time.time()
        if not translation["understood"]:
            return {**translation, "result": None, "asked_at": moment,
                    "asked_by": actor}
        proposed = translation["proposed"]
        result = self.semantics.query(
            proposed["entity"], select=proposed.get("select"),
            where=proposed.get("where") or [],
            order_by=proposed.get("order_by") or "",
            descending=bool(proposed.get("descending")),
            limit=limit, scope=scope, now=moment)
        logger.info("%s asked %r and got %d row(s)", actor, question[:60],
                    result["returned"])
        return {**translation, "result": result, "asked_at": moment,
                "asked_by": actor,
                "detail": (translation["detail"] + ". The rows are the "
                           "register's, computed under your own scope — the "
                           "translation produced a query and never a number")}

    # -------------------------------------------------------------- catalogue
    def vocabulary(self) -> Dict[str, Any]:
        """What a question may be built from, published before anybody asks."""
        return {
            "entities": [{"entity": e.name, "describes": e.describes,
                          "fields": [f.name for f in e.fields]}
                         for e in ENTITIES.values()],
            "phrases": [{"phrase": p, "operator": op} for p, op in PHRASES],
            "translated_by": (PROVIDER if self.provider is not None
                              and hasattr(self.provider, "propose_query")
                              else VOCABULARY),
            "detail": ("a question is matched against these names. Where a "
                       "provider is wired it proposes instead — and either way "
                       "the proposal is checked against this catalogue before "
                       "anything runs, so nothing a model emits reaches the "
                       "register unvalidated"),
        }


# ------------------------------------------------------------ the matcher
def _match(question: str) -> Tuple[Dict[str, Any], Dict[str, List[str]]]:
    """MAYA's own translation: match the published names, and report the rest."""
    original = question.strip().rstrip("?")
    text = original.lower()
    used: List[str] = []

    entity, ambiguous = _entity_in(text, used)
    spec = ENTITIES[entity]
    where, order_by, descending = [], "", False

    field, operator, value = _comparison(text, original, spec, used)
    if field is not None:
        where.append({"field": field, "operator": operator, "value": value})

    for word in ("oldest", "newest", "latest", "recent"):
        if word in text:
            order_by, descending = _time_field(spec), word != "oldest"
            used.append(word)
            break

    words = [w for w in re.findall(r"[a-z_]+", text)
             if w not in NOISE and not any(w in u for u in used)]
    return ({"entity": entity, "where": where, "order_by": order_by,
             "descending": descending},
            {"used": used, "ignored": sorted(set(words)),
             "also_named": ambiguous})


def _entity_in(text: str, used: List[str]) -> Tuple[str, List[str]]:
    """Which entity a question is about — the FIRST one it names.

    Leftmost rather than longest, and it matters. "how many models have more
    than two open findings" names both, and the thing being counted is the one
    the question opens with. Longest-first would answer about findings, which
    is a different number and looks exactly as authoritative.

    Every other entity named is returned too, so an ambiguous question is
    reported as ambiguous rather than silently resolved.
    """
    found: List[Tuple[int, str, str]] = []
    for name in ENTITIES:
        spoken = name.replace("_", " ")
        for form in (spoken + "s", spoken):
            match = re.search(rf"\b{re.escape(form)}\b", text)
            if match:
                found.append((match.start(), name, form))
                break
    if not found:
        # Nothing named. 'model' is the entity every other one hangs off, and
        # the ignored-words list will show nothing in the question chose it.
        return "model", []
    found.sort()
    used.append(found[0][2])
    return found[0][1], [name for _, name, _ in found[1:]]


def _comparison(text: str, original: str, spec, used: List[str]):
    """The first field name in the question, and what is being asked of it."""
    for field in sorted(spec.fields, key=lambda f: len(f.name), reverse=True):
        spoken = field.name.replace("_", " ")
        match = re.search(rf"\b{re.escape(spoken)}\b", text)
        if not match:
            continue
        used.append(spoken)
        tail, head = text[match.end():], text[:match.start()]
        raw_tail, raw_head = original[match.end():], original[:match.start()]
        # Both sides, again: "more than two open findings" puts the phrase
        # BEFORE the field, and reading only forwards turns a 'greater than'
        # into an 'equals' — a query that runs, returns a plausible number and
        # answers a question nobody asked.
        operator = _operator_in(tail, field.type, used) or \
            _operator_in(head, field.type, used) or _default_operator(field.type)
        if operator in ("is_null", "not_null"):
            return field.name, operator, None
        value = _value_in(tail, raw_tail, field.type)
        if value is None:
            # English puts the value on either side: "tier is 1" and "the
            # credit domain" are the same request, and a matcher that only
            # looked forwards would answer the second with no filter at all.
            value = _value_in(head, raw_head, field.type, last=True)
        if value is None:
            # A field named with nothing asked of it is not a filter. Reporting
            # it as one would invent a comparison the question did not make.
            return None, "", None
        used.append(str(value).lower())
        return field.name, operator, value
    return None, "", None


def _operator_in(span: str, type_: str, used: List[str]) -> str:
    for phrase, operator in PHRASES:
        if phrase in span and operator in ADMISSIBLE[type_]:
            used.append(phrase)
            return operator
    return ""


def _default_operator(type_: str) -> str:
    return "eq" if "eq" in ADMISSIBLE[type_] else ADMISSIBLE[type_][0]


def _value_in(lowered: str, original: str, type_: str, last: bool = False):
    """The value beside a field name. Quoted text keeps its case.

    `raw` is the same span before lowering, because 'Critical' is a value in
    the register and 'critical' is not — a matcher that lower-cased what
    somebody put in quotes would produce a query that parses and matches
    nothing, which reads on screen as an answer of zero.
    """
    quoted = re.search(r"['\"]([^'\"]+)['\"]", original)
    if quoted:
        return _coerce(quoted.group(1), type_)
    if type_ == "number":
        numbers = re.findall(r"-?\d+(?:\.\d+)?", lowered)
        return float(numbers[-1 if last else 0]) if numbers else None
    if type_ == "boolean":
        for word in re.findall(r"[a-z]+", lowered):
            if word in TRUE_WORDS:
                return True
            if word in FALSE_WORDS:
                return False
        return None
    words = [w for w in re.findall(r"[a-z0-9_.:-]+", lowered) if w not in NOISE
             and not any(w in phrase for phrase, _ in PHRASES)]
    if not words:
        return None
    chosen = words[-1] if last else words[0]
    # Give back the original casing of the word that was chosen.
    restored = re.search(rf"\b{re.escape(chosen)}\b", original, re.IGNORECASE)
    return restored.group(0) if restored else chosen


def _coerce(raw: str, type_: str):
    if type_ == "number":
        # Tested, not caught. Somebody putting a word in quotes against a
        # numeric field is an ordinary way to phrase a question wrongly, and a
        # handler here would log once per malformed question — which is noise
        # about the asker rather than about the platform.
        text = raw.strip()
        digits = text[1:] if text.startswith("-") else text
        return float(text) if digits.replace(".", "", 1).isdigit() else raw
    if type_ == "boolean":
        return raw.strip().lower() in TRUE_WORDS
    return raw


def _time_field(spec) -> str:
    """Which field 'latest' means for this entity, or nothing at all."""
    for field in spec.fields:
        if field.type == "timestamp":
            return field.name
    return ""


def _render(proposed: Dict[str, Any]) -> str:
    """The proposal in one sentence, for somebody who will not read JSON."""
    entity = proposed.get("entity") or "nothing"
    where = proposed.get("where") or []
    out = f"every {entity}"
    if where:
        clause = where[0]
        out += (f" whose {clause['field']} "
                f"{OPERATORS.get(clause['operator'], clause['operator'])}"
                + (f" {clause['value']}" if clause.get("value") is not None
                   else ""))
    if proposed.get("order_by"):
        out += (f", ordered by {proposed['order_by']}"
                + (" descending" if proposed.get("descending") else ""))
    return out


def catalogue_prompt(describe: Dict[str, Any]) -> str:
    """The catalogue as a provider sees it.

    Separate and public so that what a language model is told about this
    register is inspectable. A prompt nobody can read is a place where an
    instruction can live unexamined.
    """
    lines = ["Entities and fields you may use. Use nothing else."]
    for entity in describe.get("entities", []):
        fields = ", ".join(f"{f['name']}:{f['type']}"
                           for f in entity.get("fields", []))
        lines.append(f"- {entity['entity']} ({fields})")
    lines.append("Operators: " + ", ".join(
        o["operator"] for o in describe.get("operators", [])))
    lines.append("Return an object: entity, select, where "
                 "[{field, operator, value}], order_by, descending.")
    lines.append("Return no rows, no counts and no prose. You are producing a "
                 "query; the register produces the numbers.")
    return "\n".join(lines)
