"""
Workspaces (§28.3, §29.2): rehearse a change on a branch of the catalog, see
what it reaches, replay the dependent models numerically, and submit it for
review — where approval is the merge.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from maya.web.routes.common import action, client, flash, form, page, parse_json, render

router = APIRouter()


@router.get("/workbench/workspaces")
@page
async def workspaces(request: Request) -> Any:
    async with client(request) as sdk:
        rows = await sdk.workspaces.list()
    return await render(request, "workbench/workspaces.html", {"rows": rows})


@router.post("/workbench/workspaces")
@action
async def create(request: Request) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        ws = await sdk.workspaces.create(data.get("name", ""), data.get("description", ""))
    return RedirectResponse(f"/workbench/workspaces/{ws['id']}", status_code=303)


@router.get("/workbench/workspaces/{ws_id}")
@page
async def workspace(request: Request, ws_id: str) -> Any:
    q = request.query_params
    async with client(request) as sdk:
        ws = await sdk.workspaces.get(ws_id)
        impact = (
            await sdk.workspaces.impact(ws_id)
            if ws["changes"]
            else {"downstream": [], "warrants": []}
        )
        preview = await sdk.workspaces.preview(ws_id, q["preview"]) if q.get("preview") else None
        template = None
        if q.get("ref") and q.get("kind"):
            obj = await (
                sdk.features.get(q["ref"])
                if q["kind"] == "feature"
                else sdk.featuresets.get(q["ref"])
            )
            approved = [v for v in obj["versions"] if v["state"] in ("approved", "published")]
            template = json.dumps((approved or obj["versions"])[0]["definition"], indent=2)
    return await render(
        request,
        "workbench/workspace.html",
        {
            "ws": ws,
            "impact": impact,
            "preview": preview,
            "preview_ref": q.get("preview", ""),
            "stage_ref": q.get("ref", ""),
            "stage_kind": q.get("kind", "feature"),
            "template": template,
        },
    )


@router.post("/workbench/workspaces/{ws_id}/stage")
@action
async def stage(request: Request, ws_id: str) -> Any:
    data = await form(request)
    definition = parse_json(data.get("definition"), "definition")
    async with client(request) as sdk:
        await sdk.workspaces.stage(
            ws_id,
            data.get("kind", "feature"),
            data.get("ref", ""),
            definition,
            data.get("note", ""),
        )
    flash(request, "Change staged. Nothing outside this workspace sees it.", "success")
    return RedirectResponse(f"/workbench/workspaces/{ws_id}", status_code=303)


@router.post("/workbench/workspaces/{ws_id}/changes/{change_id}/unstage")
@action
async def unstage(request: Request, ws_id: str, change_id: str) -> Any:
    async with client(request) as sdk:
        await sdk.workspaces.unstage(ws_id, change_id)
    return RedirectResponse(f"/workbench/workspaces/{ws_id}", status_code=303)


@router.post("/workbench/workspaces/{ws_id}/replay")
@action
async def replay(request: Request, ws_id: str) -> Any:
    async with client(request) as sdk:
        job = await sdk.workspaces.shadow_replay(ws_id)
    flash(request, "Shadow replay started; the report appears here when the job finishes.", "info")
    return RedirectResponse(f"/workbench/workspaces/{ws_id}?job={job['id']}", status_code=303)


@router.post("/workbench/workspaces/{ws_id}/submit")
@action
async def submit(request: Request, ws_id: str) -> Any:
    async with client(request) as sdk:
        out = await sdk.workspaces.submit(ws_id)
    flash(
        request,
        f"Submitted {len(out['submitted'])} version(s) for review. The workspace "
        "merges when every one is approved.",
        "success",
    )
    return RedirectResponse(f"/workbench/workspaces/{ws_id}", status_code=303)


@router.post("/workbench/workspaces/{ws_id}/abandon")
@action
async def abandon(request: Request, ws_id: str) -> Any:
    async with client(request) as sdk:
        await sdk.workspaces.abandon(ws_id)
    flash(request, "Workspace abandoned.", "info")
    return RedirectResponse("/workbench/workspaces", status_code=303)
