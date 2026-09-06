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
from routes.base import Routes


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
