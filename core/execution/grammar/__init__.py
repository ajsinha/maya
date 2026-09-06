"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The warrant grammar.

Four independent vocabularies whose product covers every model a bank runs:
how the parameter object is inhabited, how the kernel is realised, what is
being asked of it, and where its data comes from. Plus the admissibility laws
that say which combinations mean anything, and a JSON Schema generated from the
vocabulary so an engine in any language can check a warrant before acting.
"""
from core.execution.grammar.rules import Problem, admissible_verbs
from core.execution.grammar.schema import json_schema, vocabulary
from core.execution.grammar.validator import GrammarReport, GrammarValidator, validate
from core.execution.grammar.vocabulary import (BINDINGS, RUNTIME_ENTRY, RUNTIMES,
                                               SECTIONS, SINKS, VERB_MEANING, VERBS,
                                               WARRANT_VERSION)

__all__ = [
                                               "BINDINGS",
                                               "RUNTIMES",
                                               "RUNTIME_ENTRY",
                                               "SECTIONS",
                                               "SINKS",
                                               "VERBS",
                                               "VERB_MEANING",
                                               "WARRANT_VERSION",
                                               "GrammarReport",
                                               "GrammarValidator",
                                               "Problem",
                                               "admissible_verbs",
                                               "json_schema",
                                               "validate",
                                               "vocabulary",
]
