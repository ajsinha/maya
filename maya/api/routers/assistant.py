"""
The recorded challenger's memos (§29.8).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
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


@router.post("/assistant/memos/{memo_id}/stance")
def respond(memo_id: str, body: StanceIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.assistant.respond(me, memo_id, body.stance, body.note))
