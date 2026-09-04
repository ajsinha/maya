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
