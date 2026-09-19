"""
Workspace endpoints (§28.3, §29.2): stage, preview inside, impact, shadow replay, merge.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from maya.api import schemas as s
from maya.api.deps import Me, Plat, ok
from maya.security.authz import Principal

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("")
def list_workspaces(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workspaces.list(me))


@router.post("", status_code=201)
def create_workspace(body: s.WorkspaceIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workspaces.create(me, body.name, body.description), 201)


@router.get("/{ws_id}")
def get_workspace(ws_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workspaces.get(me, ws_id))


@router.put("/{ws_id}/changes")
def stage(ws_id: str, body: s.StageIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workspaces.stage(me, ws_id, kind=body.kind, ref=body.ref,
                                    definition=body.definition, note=body.note))


@router.delete("/{ws_id}/changes/{change_id}")
def unstage(ws_id: str, change_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    plat.workspaces.unstage(me, ws_id, change_id)
    return ok({"ok": True})


@router.get("/{ws_id}/preview")
async def preview(ws_id: str, ref: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(await asyncio.to_thread(plat.workspaces.preview, me, ws_id, ref))


@router.get("/{ws_id}/impact")
def impact(ws_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workspaces.impact(me, ws_id))


@router.post("/{ws_id}/replay", status_code=202)
def replay(ws_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workspaces.request_replay(me, ws_id), 202)


@router.post("/{ws_id}/submit")
def submit(ws_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workspaces.submit(me, ws_id))


@router.post("/{ws_id}/abandon")
def abandon(ws_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.workspaces.abandon(me, ws_id))
