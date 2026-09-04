"""
MAYA — compiled documentation.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Documents are compiled from the register and the evidence graph, so the useful
endpoints are not "upload" and "download" but **compile**, **check the citations**
and **ask whether it has gone stale**.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import Request
from fastapi.responses import PlainTextResponse

from core.docs import KINDS, TITLES
from core.docs.common import PURPOSE
from routes.base import Routes


class DocumentRoutes(Routes):
    def register(self) -> None:
        docs, registry = self.ctx["documents"], self.ctx["registry"]
        api = self.api

        @self.app.get(f"{api}/document-kinds", tags=["documents"])
        def kinds(request: Request):
            self.principal(request)
            return {"kinds": [{"kind": k, "title": TITLES[k], "purpose": PURPOSE[k]}
                              for k in KINDS]}

        @self.app.get(f"{api}/documents", tags=["documents"])
        def list_documents(request: Request, urn: str):
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "document:read", model=model)
            return {"model": urn, "documents": [
                {**d, "staleness": docs.staleness(d["id"])}
                for d in docs.for_model(model["id"])]}

        @self.app.post(f"{api}/documents", status_code=201, tags=["documents"])
        def compile_document(request: Request, urn: str, kind: str):
            model = self.guard(lambda: registry.require(urn))
            who = self.authorise(request, "document:compile", model=model)
            return self.guard(lambda: docs.compile(kind, urn, self.actor(who)))

        @self.app.get(f"{api}/documents/{{document_id}}", tags=["documents"])
        def get_document(request: Request, document_id: str):
            self.authorise(request, "document:read")
            doc = self.guard(lambda: docs.require(document_id))
            return {**doc, "staleness": docs.staleness(document_id),
                    "citations_verified": docs.verify_citations(document_id)}

        @self.app.get(f"{api}/documents/{{document_id}}/markdown",
                      response_class=PlainTextResponse, tags=["documents"])
        def markdown(request: Request, document_id: str):
            """The document as markdown — what a person reads, or exports."""
            self.authorise(request, "document:read")
            return docs.markdown(self.guard(lambda: docs.require(document_id)))
