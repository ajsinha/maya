"""
MAYA — attached documents.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Documents somebody wrote, filed against the version they describe. Multipart
upload, because that is how a file arrives; everything after it is the same
register discipline as the rest of the platform.
"""
from __future__ import annotations

from typing import Optional

from fastapi import File, Form, Request, UploadFile
from fastapi.responses import Response

from core.attachments import KIND_MEANING, KINDS
from routes.base import Body, Routes


class ReviewIn(Body):
    accept: bool
    note: str = ""


class AttachmentRoutes(Routes):
    def register(self) -> None:
        attachments, registry = self.ctx["attachments"], self.ctx["registry"]
        api = self.api

        @self.app.get(f"{api}/attachment-kinds", tags=["attachments"])
        def kinds(request: Request):
            self.principal(request)
            return {"kinds": [{"kind": k, "means": KIND_MEANING[k]} for k in KINDS]}

        @self.app.get(f"{api}/attachments", tags=["attachments"])
        def list_attachments(request: Request, urn: str, history: bool = False):
            """What documentation this model has on file."""
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "document:read", model=model)
            rows = (attachments.history(model["id"]) if history
                    else attachments.for_model(model["id"]))
            return {"model": urn, **attachments.status(model["id"]),
                    "attachments": rows}

        @self.app.post(f"{api}/attachments", status_code=201, tags=["attachments"])
        async def attach(request: Request, urn: str = Form(...),
                         kind: str = Form(...), title: str = Form(...),
                         semver: Optional[str] = Form(None),
                         note: str = Form(""),
                         supersedes: Optional[str] = Form(None),
                         model_level: bool = Form(False),
                         subject_type: Optional[str] = Form(None),
                         subject_id: Optional[str] = Form(None),
                         file: UploadFile = File(...)):
            """File a document against what it is ABOUT.

            Version-level by default, so a caller that says nothing files
            exactly what it filed before. `subject_type` and `subject_id` are
            for the documents that were previously unfilable: a convergence
            study about one parameter set, a data dictionary about one
            featureset version.
            """
            model = self.guard(lambda: registry.require(urn))
            who = self.authorise(request, "document:attach", model=model)
            data = await file.read()
            return self.guard(lambda: attachments.attach(
                urn, kind, title, file.filename or "document",
                data, file.content_type or "application/octet-stream",
                semver, note, supersedes, model_level,
                subject_type, subject_id, actor=self.actor(who)))

        @self.app.get(f"{api}/attachments/{{attachment_id}}", tags=["attachments"])
        def read(request: Request, attachment_id: str):
            self.authorise(request, "document:read")
            return self.guard(lambda: attachments.require(attachment_id))

        @self.app.get(f"{api}/attachments/{{attachment_id}}/content",
                      tags=["attachments"])
        def content(request: Request, attachment_id: str):
            """The bytes, verified against the digest that was reviewed."""
            self.authorise(request, "document:read")
            row = self.guard(lambda: attachments.require(attachment_id))
            data = self.guard(lambda: attachments.content(attachment_id))
            return Response(
                data, media_type=row["media_type"],
                headers={"Content-Disposition":
                         f'attachment; filename="{row["filename"]}"'})

        @self.app.post(f"{api}/attachments/{{attachment_id}}/review",
                       tags=["attachments"])
        def review(request: Request, attachment_id: str, body: ReviewIn):
            """Accept or reject. Never by whoever attached it."""
            who = self.authorise(request, "document:review")
            return self.guard(lambda: attachments.review(
                attachment_id, body.accept, self.actor(who), body.note))
