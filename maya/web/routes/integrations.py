"""
Connectors page: import a model from MLflow or SageMaker; export lineage as OpenLineage.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from maya.web.routes.common import action, client, flash, form, is_admin, page, parse_json, render

router = APIRouter()


def _names(text: str | None) -> list[str] | None:
    items = [s.strip() for s in (text or "").replace("\n", ",").split(",") if s.strip()]
    return items or None


@router.get("/integrations")
@page
async def integrations_page(request: Request) -> Any:
    async with client(request) as sdk:
        namespaces = await sdk.namespaces.list()
    return await render(
        request,
        "integrations.html",
        {"namespaces": namespaces, "admin": is_admin(request)},
    )


def _done(request: Request, row: dict[str, Any]) -> RedirectResponse:
    src = row.get("imported_from", {}).get("source", "")
    flash(
        request, f"Imported from {src} as a black-box draft; review it like any model.", "success"
    )
    ns = row.get("namespace") or ""
    return RedirectResponse(f"/models/{ns}/{row['name']}" if ns else "/models", status_code=303)


@router.post("/integrations/mlflow")
@action
async def mlflow_import(request: Request) -> Any:
    data = await request.form()
    upload = data.get("mlmodel_file")
    text = str(data.get("mlmodel") or "")
    if upload is not None and hasattr(upload, "read"):
        body = await upload.read()
        text = body.decode("utf-8") if body else text
    async with client(request) as sdk:
        if data.get("model_name"):
            row = await sdk.integrations.fetch_mlflow(
                str(data.get("namespace", "")),
                str(data.get("name", "")),
                str(data.get("model_name", "")),
                str(data.get("version", "")),
                str(data.get("estimates", "")),
                str(data.get("description", "")),
            )
        else:
            row = await sdk.integrations.import_mlflow(
                str(data.get("namespace", "")),
                str(data.get("name", "")),
                text,
                str(data.get("estimates", "")),
                str(data.get("description", "")),
            )
    return _done(request, {**row, "namespace": data.get("namespace")})


@router.post("/integrations/sagemaker")
@action
async def sagemaker_import(request: Request) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        row = await sdk.integrations.import_sagemaker(
            data.get("namespace", ""),
            data.get("name", ""),
            parse_json(data.get("package"), "The model package description", {}),
            data.get("estimates", ""),
            _names(data.get("inputs")),
            _names(data.get("outputs")),
        )
    return _done(request, {**row, "namespace": data.get("namespace")})


@router.get("/integrations/openlineage.json")
@page
async def openlineage_download(request: Request) -> Any:
    async with client(request) as sdk:
        events = await sdk.integrations.openlineage_events()
    return Response(
        json.dumps(events, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="maya-openlineage.json"'},
    )


@router.post("/integrations/openlineage")
@action
async def openlineage_emit(request: Request) -> Any:
    async with client(request) as sdk:
        out = await sdk.integrations.emit_openlineage()
    level = "success" if not out["failed"] else "warning"
    flash(request, f"{out['sent']} of {out['events']} OpenLineage event(s) sent.", level)
    return RedirectResponse("/integrations", status_code=303)


@router.post("/integrations/mlflow/sync")
@action
async def mlflow_sync(request: Request) -> Any:
    async with client(request) as sdk:
        out = await sdk.integrations.sync_mlflow()
    if not out["configured"]:
        flash(
            request,
            "No MLflow tracking server is configured (integrations.mlflow.tracking_uri).",
            "warning",
        )
    else:
        flash(
            request,
            f"MLflow alias '{out['alias']}': set on {len(out['set'])}, removed from {len(out['removed'])}, {len(out['failed'])} failed.",
            "success" if not out["failed"] else "warning",
        )
    return RedirectResponse("/integrations", status_code=303)


__all__ = ["router"]
