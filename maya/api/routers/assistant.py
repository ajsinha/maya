"""
The recorded challenger's memos (§29.8).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from maya.api.deps import Me, Plat, ok
from maya.security.authz import Principal

router = APIRouter(tags=["assistant"])


class MemoIn(BaseModel):
    object_type: str
    object_id: str


class StanceIn(BaseModel):
    stance: str
    note: str = ""


@router.get("/assistant/memos")
def memos(object_type: str, object_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.assistant.memos(me, object_type, object_id))


@router.post("/assistant/memos", status_code=202)
def request_memo(body: MemoIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.assistant.request(me, body.object_type, body.object_id), 202)


@router.post("/assistant/drafts/feature")
async def draft_feature(
    description: str = Form(""),
    fmt: str = Form("csv"),
    file: UploadFile | None = File(None),
    me: Principal = Me,
    plat: Any = Plat,
) -> Response:
    """A proposed feature definition from a description and a sample file (§29.8). Nothing
    is created: the draft comes back for a person to read, edit and submit."""
    data = await file.read() if file is not None else None
    return ok(plat.assistant.draft_feature(me, description, data, fmt))


@router.get("/assistant/drafts/spec")
def draft_spec(ref: str, version_no: int, me: Principal = Me, plat: Any = Plat) -> Response:
    """Drafts for the specification sections nobody has written yet (§29.8)."""
    return ok(plat.assistant.draft_spec(me, ref, version_no))


@router.post("/assistant/memos/{memo_id}/stance")
def respond(memo_id: str, body: StanceIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.assistant.respond(me, memo_id, body.stance, body.note))
