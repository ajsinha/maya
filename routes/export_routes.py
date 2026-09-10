"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Export packs over HTTP.

The pack is produced for somebody who will not be given a login, but it is
*requested* by somebody who has one — and scope applies to the request exactly
as it does to the model page. A pack is the most complete thing this platform
produces about a model, so an export of a model the caller may not read would be
the largest scope leak available.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import Request
from fastapi.responses import Response

from core.docs import KINDS
from core.execution.urn import model_urn as urn
from core.export import CONTENTS, DEFAULT_DOCUMENTS, PACK_VERSION
from routes.base import Body, Routes


class ShareIn(Body):
    """A link to one sealed pack, for one recipient, until one date.

    `content_digest` is required and there is no field for a path. A share
    pointing at a location would serve whatever is at that location later,
    which is how a document a firm handed over becomes one nobody can
    reproduce.
    """
    urn: str
    recipient: str
    purpose: str
    content_digest: str
    pack_digest: str = ""
    filename: str = ""
    days: float = 30.0
    max_reads: Optional[int] = None


class ExportRoutes(Routes):
    def register(self) -> None:
        api = self.api

        @self.app.get(f"{api}/export-packs", tags=["documents"])
        def describe(request: Request):
            """What a pack contains, and what each part answers."""
            self.principal(request)
            return {"pack_version": PACK_VERSION, "contents": CONTENTS,
                    "documents": list(DEFAULT_DOCUMENTS),
                    "document_kinds": list(KINDS),
                    "detail": "a self-contained, digested record of one model; "
                              "read gaps.md first"}

        @self.app.post(f"{api}/export-packs/{{name:path}}", tags=["documents"])
        def build(request: Request, name: str,
                  documents: Optional[str] = None,
                  attachments: bool = True):
            """Cut a pack and return the zip.

            `documents` narrows which are compiled, comma-separated. Everything
            else is always included: a pack assembled to a caller's taste is a
            pack the next reader has to ask for again.
            """
            model = self.ctx["registry"].get(urn(name))
            if not model:
                raise self.not_found(f"no model {name}")
            who = self.authorise(request, "document:read", model=model)
            kinds: List[str] = ([k.strip() for k in documents.split(",") if k.strip()]
                                if documents else list(DEFAULT_DOCUMENTS))
            pack = self.guard(lambda: self.ctx["export"].build(
                model["urn"], documents=kinds, include_attachments=attachments,
                actor=self.actor(who)))
            # Recorded, because cutting a complete record of a model and handing
            # it to somebody outside is itself a governance act — and the thing
            # an auditor asks about later is who took a copy and when.
            self.ctx["evidence"].append(
                "export_pack_cut", "export_pack",
                pack["manifest"]["content_digest"],
                {"urn": model["urn"], "model_id": model["id"],
                 "pack_digest": pack["digest"],
                 # The archive's member count, which is what a
                 # recipient sees. The manifest's own `files` list
                 # is one shorter and always will be: it cannot
                 # carry its own digest.
                 "files": pack["manifest"]["members_in_archive"],
                 "digested": len(pack["manifest"]["files"]),
                 "gaps": pack["manifest"]["gaps"],
                 "documents": kinds}, actor=self.actor(who))
            return Response(
                pack["bytes"], media_type="application/zip",
                headers={"Content-Disposition":
                         f'attachment; filename="{pack["filename"]}"',
                         "X-Pack-Digest": pack["digest"],
                         "X-Pack-Content-Digest":
                             pack["manifest"]["content_digest"]})

        @self.app.get(f"{api}/export-packs/{{name:path}}/manifest", tags=["documents"])
        def manifest(request: Request, name: str,
                     documents: Optional[str] = None,
                     attachments: bool = True):
            """The manifest without the bytes.

            Worth its own endpoint: comparing the content digest against the
            last pack answers *has anything changed* without moving a hundred
            megabytes to find out that nothing has.
            """
            model = self.ctx["registry"].get(urn(name))
            if not model:
                raise self.not_found(f"no model {name}")
            who = self.authorise(request, "document:read", model=model)
            kinds = ([k.strip() for k in documents.split(",") if k.strip()]
                     if documents else list(DEFAULT_DOCUMENTS))
            pack = self.guard(lambda: self.ctx["export"].build(
                model["urn"], documents=kinds, include_attachments=attachments,
                actor=self.actor(who)))
            return {**pack["manifest"], "pack_digest": pack["digest"],
                    "filename": pack["filename"], "detail": pack["detail"]}

        # ------------------------------------------------- sharing a pack
        @self.app.get(f"{api}/export-shares/posture", tags=["documents"])
        def share_posture(request: Request):
            """What a share is, and the portal it deliberately is not."""
            self.authorise(request, "document:read")
            from core.export.sharing import ExportSharing
            return ExportSharing.posture()

        @self.app.get(f"{api}/export-shares", tags=["documents"])
        def shares(request: Request, reference: Optional[str] = None):
            """Every share, live ones first — or the status of one."""
            self.authorise(request, "document:read",
                           estate_wide="reading who packs were shared with")
            engine = self.ctx["export_sharing"]
            if reference is None:
                return self.guard(lambda: engine.across_the_estate())
            return self.guard(lambda: engine.status(reference))

        @self.app.post(f"{api}/export-shares", status_code=201,
                       tags=["documents"])
        def create_share(request: Request, body: ShareIn):
            """Create a time-boxed link to one sealed pack.

            It points at a **content digest**, never a path: a share pointing
            at a location would serve whatever is at that location later.
            """
            model = self.guard(
                lambda: self.ctx["registry"].require(body.urn))
            who = self.authorise(request, "document:read", model=model)
            return self.guard(lambda: self.ctx["export_sharing"].share(
                body.urn, recipient=body.recipient, purpose=body.purpose,
                days=body.days, max_reads=body.max_reads,
                content_digest=body.content_digest,
                pack_digest=body.pack_digest, filename=body.filename,
                actor=self.actor(who)))

        @self.app.post(f"{api}/export-shares/{{reference}}/revoke",
                       tags=["documents"])
        def revoke_share(request: Request, reference: str, reason: str = ""):
            """Stop it serving. Keeps everything it served."""
            who = self.authorise(request, "document:read",
                                 estate_wide="revoking an export share")
            return self.guard(lambda: self.ctx["export_sharing"].revoke(
                reference, reason, actor=self.actor(who)))

        # ------------------------------------------------ rendering a document
        @self.app.get(f"{api}/document-rendering/formats", tags=["documents"])
        def rendering_formats(request: Request):
            """What is emitted, and what is refused with the reason."""
            self.authorise(request, "document:read")
            from core.docs.rendering import DocumentRendering
            return DocumentRendering.formats()

        @self.app.get(f"{api}/document-rendering/{{document_id}}",
                      tags=["documents"])
        def render_document(request: Request, document_id: str,
                            format: str = "latex"):
            """Emit a typesetting source with the citations intact.

            MAYA does not render it. Rendering needs a toolchain and a house
            template, and a firm's document standard is not a register's
            decision — but the citations survive typesetting, which is the
            property that matters.
            """
            self.authorise(request, "document:read",
                           estate_wide="rendering a compiled document")
            return self.guard(
                lambda: self.ctx["document_rendering"].render(document_id,
                                                              format))
