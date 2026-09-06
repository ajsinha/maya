"""
MAYA — the warrant grammar, published.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The grammar is the contract between MAYA and everything that runs a model, so it
is published rather than documented: the vocabulary an engine builds against,
the JSON Schema it validates with, and an endpoint that checks a document and
says exactly what is wrong with it.

A contract nobody can check is a convention.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import Request

from core.execution.grammar import json_schema, validate, vocabulary
from routes.base import Routes


def _fibre(fibre) -> Dict[str, Any]:
    """One fibre, as the API shape. The four facets `L-15` names, and the three
    sentences that say what each facet is *for* — carried because a validator
    reading "what may be monitored" needs to know why before the list means
    anything."""
    return {
        "trainability_class": fibre.trainability_class,
        "label": fibre.label,
        "evidence": list(fibre.evidence),
        "lifecycle": list(fibre.lifecycle),
        "metrics": list(fibre.metrics),
        "templates": list(fibre.templates),
        "soundness_rests_on": fibre.soundness,
        "outcomes_analysis_is": fibre.outcomes,
        "monitoring_answers": fibre.answers,
    }


class GrammarRoutes(Routes):
    def register(self) -> None:
        api = self.api

        @self.app.get(f"{api}/grammar", tags=["grammar"])
        def grammar(request: Request):
            """The four axes: how P is inhabited, how the kernel is realised,
            what is asked of it, and where its data comes from."""
            self.principal(request)
            return vocabulary()

        @self.app.get(f"{api}/grammar/schema", tags=["grammar"])
        def schema(request: Request):
            """JSON Schema, generated from the vocabulary rather than kept beside it."""
            self.principal(request)
            return json_schema()

        @self.app.get(f"{api}/fibres", tags=["grammar"])
        def fibres(request: Request):
            """The fibration: what each trainability class needs, may be asked,
            and compiles into.

            Read-only, and deliberately here rather than under `/models`: a
            fibre is a property of the *class*, not of any model, and putting it
            on a model page is how nine facts become one per model and start
            disagreeing.
            """
            self.principal(request)
            registry = self.ctx["fibres"]
            return {"base": registry.classes(),
                    "law": "L-15",
                    "total": not registry.totality(),
                    "fibres": [_fibre(registry.of(name))
                               for name in registry.classes()]}

        @self.app.get(f"{api}/fibres/{{trainability_class}}", tags=["grammar"])
        def fibre(request: Request, trainability_class: str):
            """One fibre. Refuses `no_fibre` rather than returning an empty
            shape, because an empty fibre is what `L-15` exists to forbid and
            returning one here would be the platform reporting its own
            violation as data."""
            self.principal(request)
            return self.guard(
                lambda: _fibre(self.ctx["fibres"].of(trainability_class)))

        @self.app.post(f"{api}/grammar/validate", tags=["grammar"])
        def check(request: Request, document: Dict[str, Any]):
            """Validate a warrant and report every problem, not just the first.

            Whoever is writing one by hand wants the whole list; fixing one error
            to be told about the next is the worst possible interface for a
            document with ten sections.
            """
            self.principal(request)
            return validate({k: v for k, v in document.items()
                             if not k.startswith("_")}).as_dict()
