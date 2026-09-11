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
from core.http import conventions
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

        # ------------------------------------------- how this interface ages
        @self.app.get(f"{api}/conventions", tags=["grammar"])
        def conventions_(request: Request):
            """What this API promises about paging, projection and retirement.

            Published from the code rather than from a copy of it, for the same
            reason the grammar is: a client holding its own idea of how a
            cursor works is a second implementation that drifts, and it drifts
            silently because a wrong cursor still returns rows.
            """
            self.principal(request)
            return {
                "paging": {
                    "parameter": "cursor",
                    "ttl_seconds": conventions.CURSOR_TTL,
                    "max_page": conventions.MAX_PAGE,
                    "why_not_offset": (
                        "LIMIT/OFFSET is correct only over a table nobody is "
                        "writing to. A caller walking pages of the findings "
                        "while somebody raises one SKIPS a row — the insert "
                        "shifts everything down and page 2 starts one past "
                        "where page 1 ended. Nothing errors; the caller "
                        "receives a complete-looking list with a hole in it"),
                    "opaque": (
                        "a cursor names the last row you saw, carries the "
                        "ordering it was issued under, and is not meant to be "
                        "constructed. A hand-built one is a client depending "
                        "on an internal ordering, which is then an ordering "
                        "that can never change"),
                },
                "projection": {
                    "parameter": conventions.FIELDS,
                    "always_kept": sorted(conventions.ALWAYS_KEPT),
                    "why": (
                        "these fields are how an answer says it is "
                        "incomplete, and they survive every projection. A "
                        "response that looked complete because somebody "
                        "projected away the sentence saying it was not is the "
                        "failure this platform spends most of its effort "
                        "avoiding"),
                },
                "preconditions": {
                    "read": "ETag / If-None-Match on any JSON GET",
                    "write": (
                        "If-Match on a mutating request. A path with no GET "
                        "to evaluate against REFUSES rather than ignoring the "
                        "header — silently dropping a precondition is worse "
                        "than not supporting one, because the client believes "
                        "it has optimistic concurrency and has none"),
                },
                "retry": {
                    "header": "Idempotency-Key",
                    "why": (
                        "a POST is never safe to retry blindly: a create that "
                        "timed out may have succeeded. A key makes the retry "
                        "safe, and the same key over a DIFFERENT body is "
                        "refused rather than replayed"),
                },
            }

        @self.app.get(f"{api}/deprecations", tags=["grammar"])
        def deprecations_(request: Request):
            """Every endpoint on its way out, with its date and successor.

            Askable rather than only announced. A client should not have to
            wait to receive a `Sunset` header from an endpoint they happen to
            still be calling — the integration nobody has touched in two years
            is exactly the one that will break, and exactly the one nobody is
            looking at.

            Empty is the ordinary answer and not an oversight. Nothing here has
            been retired yet; the mechanism ships first on purpose, because
            adding it at the moment something is retired means the first
            endpoint to go is the one with no warning.
            """
            self.principal(request)
            rows = conventions.deprecations()
            return {
                "deprecations": rows, "count": len(rows),
                "detail": (
                    f"{len(rows)} endpoint(s) are on their way out"
                    if rows else
                    "nothing in this API is deprecated. The mechanism is "
                    "here before the first retirement on purpose: adding it "
                    "when something is being retired means the first endpoint "
                    "to go is the one nobody was warned about"),
            }
