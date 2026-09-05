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
from core.execution.urn import model_urn as urn
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

        # ------------------------------------------------- the documentation graph
        @self.app.get(f"{self.api}/document-subjects", tags=["documents"])
        def subjects(request: Request):
            """What a document can be about, and which subjects are pinned."""
            self.principal(request)
            from core.docs.subjects import describe
            return describe()

        @self.app.get(f"{self.api}/dossiers/{{name:path}}", tags=["documents"])
        def dossier(request: Request, name: str):
            """Everything documented about a model, following the pins.

            A graph rather than a list: the training record for a parameter set
            hangs under the version that produced it, and the featureset
            documentation hangs under the featureset VERSION it was fitted from
            — not the set, which has since moved.
            """
            model = self.ctx["registry"].get(urn(name))
            if not model:
                raise self.not_found(f"no model {name}")
            self.authorise(request, "document:read", model=model)
            return self.guard(lambda: self.ctx["dossier"].of(model["urn"]))

        @self.app.post(f"{self.api}/training-records/{{parameter_set_id}}",
                       status_code=201, tags=["documents"])
        def training_record(request: Request, parameter_set_id: str):
            """Compile the record of one fit.

            Every other document is about a model or a version. This one is
            about a parameter set, which is the moment that had no document at
            all — two hundred and fifty calibrations a year, each a governed act
            with a warrant behind it and none of them readable.
            """
            who = self.authorise(request, "document:compile")
            return self.guard(lambda: self.ctx["training_records"].compile(
                parameter_set_id, actor=self.actor(who)))

        @self.app.get(f"{self.api}/training-records/{{parameter_set_id}}/preview",
                      tags=["documents"])
        def preview_training_record(request: Request, parameter_set_id: str):
            """What it would say, without authoring it."""
            self.authorise(request, "document:read")
            return self.guard(lambda: self.ctx["training_records"].render(
                parameter_set_id))
