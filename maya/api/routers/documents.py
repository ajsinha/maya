"""
Documents generated from a model's record, and the AI gateway's status.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from maya.api import schemas_governance as s
from maya.api.deps import Me, Plat, ok
from maya.security.authz import Principal

router = APIRouter(tags=["documents"])


@router.get("/ai/status")
def ai_status(me: Principal = Me, plat: Any = Plat) -> Response:
    """The model profiles, where each points and whether it looks usable, and every language-model
    provider on offer (built-in or plugin). Nothing is called."""
    return ok(plat.ai.status(me))


@router.get("/documents/templates")
def document_templates(me: Principal = Me, plat: Any = Plat) -> Response:
    """The document templates on offer: the built-ins, and the firm's own in
    documents.template_dir, which replace a built-in of the same name."""
    return ok(plat.documents.templates(me))


@router.post("/models/{namespace}/{name}/documents", status_code=202)
def generate_document(
    namespace: str, name: str, body: s.DocumentIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    """Generate a model card, validation report or model documentation from the model's record,
    as a job. Sections the template drafts with a language model are labelled as drafted."""
    job = plat.documents.submit(
        me,
        f"{namespace}/{name}",
        body.version_no,
        kind=body.kind,
        template=body.template,
        use_ai=body.use_ai,
        profile=body.profile,
    )
    return ok(job, 202)


@router.get("/models/{namespace}/{name}/documents")
def list_documents(namespace: str, name: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.documents.list(me, f"{namespace}/{name}"))


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    row = plat.documents.get(me, doc_id)
    return ok({**row, "markdown": plat.documents.labelled_markdown(row)})


@router.get("/documents/{doc_id}/render")
def render_document(
    doc_id: str, format: str = "md", me: Principal = Me, plat: Any = Plat
) -> Response:
    """The document as Markdown, HTML or PDF, with each drafted section labelled."""
    out = plat.documents.render(me, doc_id, format)
    headers = {"Content-Disposition": f'attachment; filename="{out["filename"]}"'}
    if out.get("draft_render"):
        headers["X-Maya-Draft-Render"] = "true"
    return Response(out["data"], media_type=out["content_type"], headers=headers)


@router.post("/documents/{doc_id}/approve")
def approve_document(doc_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    """Approve a document, drafted sections and all: someone other than whoever generated it."""
    return ok(plat.documents.approve(me, doc_id))
