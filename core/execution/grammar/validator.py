"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The grammar validator.

Two passes, and the order matters. **Shape** first — are the sections present,
are the vocabulary values recognised, does each runtime carry the entry keys it
needs. Then **admissibility** — given a well-formed document, do the four axes
make sense together.

Reporting every problem rather than stopping at the first is deliberate. Whoever
is writing a warrant by hand wants the whole list, and an engine rejecting one
wants to log the whole list. Fixing one error to be told about the next is the
worst possible interface for a document with ten sections.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.execution.grammar import rules
from core.execution.grammar.rules import Problem
from core.execution.grammar.vocabulary import (BINDING_KEYS, BINDINGS, REQUIRED_SECTIONS,
                                               RUNTIME_ENTRY, RUNTIMES, SINKS,
                                               VERBS, WARRANT_VERSION)


class GrammarReport:
    """The verdict on one warrant document."""

    def __init__(self, problems: List[Problem]):
        self.problems = problems

    @property
    def valid(self) -> bool:
        return not self.problems

    def as_dict(self) -> Dict[str, Any]:
        return {"valid": self.valid, "problem_count": len(self.problems),
                "problems": [p.as_dict() for p in self.problems],
                "detail": ("conforms to the MAYA warrant grammar "
                           f"v{WARRANT_VERSION}" if self.valid
                           else f"{len(self.problems)} problem(s): "
                                + "; ".join(p.detail for p in self.problems))}

    def __bool__(self) -> bool:
        return self.valid


class GrammarValidator:
    """Validates a warrant document against the grammar."""

    def validate(self, doc: Dict[str, Any]) -> GrammarReport:
        problems = self._shape(doc)
        if not problems:
            problems = self._admissibility(doc)
        return GrammarReport(problems)

    # ------------------------------------------------------------------ shape
    def _shape(self, doc: Dict[str, Any]) -> List[Problem]:
        problems: List[Problem] = []
        if doc.get("maya_warrant") != WARRANT_VERSION:
            problems.append(Problem(
                "L-W0", "maya_warrant",
                f"expected warrant grammar version '{WARRANT_VERSION}', got "
                f"{doc.get('maya_warrant')!r}",
                "issue the warrant from a current MAYA, or migrate the document"))
        for section in REQUIRED_SECTIONS:
            if section not in doc:
                problems.append(Problem(
                    "L-W0", section, f"the '{section}' section is missing",
                    "every warrant carries all ten sections; an absent one is not "
                    "an empty one"))
        if problems:
            return problems              # nothing below can be trusted yet

        problems += self._operation(doc["operation"])
        problems += self._realisation(doc["realisation"])
        problems += self._data(doc["data"])
        problems += self._required_for_verb(doc)
        return problems

    @staticmethod
    def _operation(operation: Dict[str, Any]) -> List[Problem]:
        verb = operation.get("verb")
        if verb not in VERBS:
            return [Problem("L-W0", "operation.verb",
                            f"'{verb}' is not a warrant verb",
                            f"use one of {', '.join(VERBS)}")]
        return []

    @staticmethod
    def _realisation(realisation: Dict[str, Any]) -> List[Problem]:
        runtime = realisation.get("runtime")
        if runtime not in RUNTIMES:
            return [Problem("L-W0", "realisation.runtime",
                            f"'{runtime}' is not a known runtime",
                            f"use one of {', '.join(RUNTIMES)}")]
        entry = realisation.get("entry") or {}
        missing = [k for k in RUNTIME_ENTRY[runtime] if k not in entry]
        return [Problem(
            "L-W0", "realisation.entry",
            f"the '{runtime}' runtime needs {', '.join(missing)} in its entry block",
            f"a '{runtime}' entry carries {', '.join(RUNTIME_ENTRY[runtime]) or 'nothing'}")
        ] if missing else []

    @staticmethod
    def _data(data: Dict[str, Any]) -> List[Problem]:
        problems: List[Problem] = []
        for i, binding in enumerate(data.get("inputs") or []):
            kind = binding.get("binding")
            if kind not in BINDINGS:
                problems.append(Problem(
                    "L-W0", f"data.inputs[{i}].binding",
                    f"'{kind}' is not a known data binding",
                    f"use one of {', '.join(BINDINGS)}"))
                continue
            missing = [k for k in BINDING_KEYS[kind] if k not in binding]
            if missing:
                problems.append(Problem(
                    "L-W0", f"data.inputs[{i}]",
                    f"a '{kind}' binding needs {', '.join(missing)}",
                    f"a '{kind}' binding carries "
                    f"{', '.join(BINDING_KEYS[kind]) or 'nothing'}"))
        for i, out in enumerate(data.get("outputs") or []):
            if out.get("sink") not in SINKS:
                problems.append(Problem(
                    "L-W0", f"data.outputs[{i}].sink",
                    f"'{out.get('sink')}' is not a known sink",
                    f"use one of {', '.join(SINKS)}"))
        return problems

    @staticmethod
    def _required_for_verb(doc: Dict[str, Any]) -> List[Problem]:
        verb = doc["operation"].get("verb")
        problems = []
        for path in rules.REQUIRED_FOR_VERB.get(verb, ()):
            section, _, key = path.partition(".")
            if not (doc.get(section) or {}).get(key):
                problems.append(Problem(
                    "L-W0", path, f"'{verb}' requires {path}",
                    f"{rules.__name__.split('.')[-1]}: a '{verb}' warrant must "
                    f"declare {path}"))
        return problems

    # ---------------------------------------------------------- admissibility
    @staticmethod
    def _admissibility(doc: Dict[str, Any]) -> List[Problem]:
        verb = doc["operation"]["verb"]
        runtime = doc["realisation"]["runtime"]
        klass = doc["subject"].get("trainability_class", "T0")
        inputs = doc["data"].get("inputs") or []
        outputs = doc["data"].get("outputs") or []

        found = [
            rules.check_descriptor_only(runtime, verb),
            rules.check_verb_against_class(verb, klass),
            rules.check_generative(verb, runtime),
            rules.check_fit_output(verb, outputs),
            rules.check_determinism(doc["operation"], runtime),
            rules.check_parameter_source(verb, doc.get("parameters") or {}),
            rules.check_outcomes(verb, inputs),
        ]
        problems = [p for p in found if p is not None]
        problems += rules.check_training_bindings(verb, inputs)
        problems += rules.check_featureset_bounds(verb, inputs)
        return problems


def validate(doc: Dict[str, Any]) -> GrammarReport:
    """Module-level convenience: one validator, no state to carry."""
    return GrammarValidator().validate(doc)
