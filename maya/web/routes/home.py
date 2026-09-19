"""
Home dashboard, search, inbox, lineage canvas, help/about, and the small
JSON endpoints the pages' own scripts call (job progress, lineage graph).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from maya.core.errors import MayaError
from maya.core.version import HIGHLIGHTS
from maya.web.routes.common import action, api_json, client, page, render

router = APIRouter()


@router.get("/")
@page
async def dashboard(request: Request) -> Any:
    async with client(request) as sdk:
        queue = await sdk.workflow.queue()
        features = await sdk.features.list()
        models = await sdk.models.list()
        jobs = await sdk.jobs.list()
        try:
            health = await sdk.admin.health()
        except MayaError:
            health = None
    recent = sorted(features, key=lambda f: str(f.get("updated_at")), reverse=True)[:10]
    return await render(request, "dashboard.html", {
        "queue": queue, "recent": recent, "models": models[:10], "jobs": jobs[:10],
        "health_full": health, "counts": {"features": len(features), "models": len(models),
                                          "queue": len(queue)}})


@router.get("/search")
@page
async def search(request: Request) -> Any:
    q = request.query_params.get("q", "").strip()
    hits: list[dict[str, Any]] = []
    if q:
        async with client(request) as sdk:
            hits = await sdk.access.search(q)
    for h in hits:
        h["href"] = _href(h)
    return await render(request, "search.html", {"q": q, "hits": hits})


def _href(hit: dict[str, Any]) -> str:
    ns, name, kind = hit.get("namespace"), hit.get("name"), hit.get("kind")
    return {"feature": f"/catalog/features/{ns}/{name}",
            "featureset": f"/catalog/featuresets/{ns}/{name}",
            "model": f"/models/{ns}/{name}",
            "warrant/train": f"/warrants/training/{hit.get('id')}",
            "warrant/exec": f"/warrants/execution/{hit.get('id')}",
            "namespace": "/admin/namespaces"}.get(kind, "/")


@router.get("/inbox")
@page
async def inbox(request: Request) -> Any:
    async with client(request) as sdk:
        items = await sdk.access.inbox()
    return await render(request, "inbox.html", {"items": items})


@router.post("/inbox/read")
@action
async def mark_read(request: Request) -> Any:
    async with client(request) as sdk:
        await sdk.access.mark_read(None)
    return RedirectResponse("/inbox", status_code=303)


@router.get("/lineage")
@page
async def lineage(request: Request) -> Any:
    qp = request.query_params
    return await render(request, "lineage.html", {
        "root": qp.get("root", ""), "direction": qp.get("direction", "both"),
        "depth": qp.get("depth", "3")})


@router.get("/ui/lineage")
@api_json
async def lineage_json(request: Request) -> Any:
    qp = request.query_params
    async with client(request) as sdk:
        return await sdk.access.lineage(qp.get("root", ""), direction=qp.get("direction", "both"),
                                        depth=int(qp.get("depth", "3")))


@router.get("/ui/jobs/{job_id}")
@api_json
async def job_json(request: Request, job_id: str) -> Any:
    async with client(request) as sdk:
        job = await sdk.jobs.get(job_id)
    return {"id": job["id"], "state": job["state"], "progress": job["progress"],
            "message": job["message"], "error_text": job["error"]}


@router.get("/about")
async def about(request: Request) -> Any:
    """Public, like Help: what MAYA is, before anyone has an account."""
    return await render(request, "help/about.html", {"highlights": HIGHLIGHTS,
                                                     "public_nav": True})


@router.get("/help")
async def help_index(request: Request) -> Any:
    from maya.web.help_catalog import CATEGORIES
    return await render(request, "help/index.html", {"catalog": CATEGORIES, "public_nav": True})


@router.get("/help/{slug}")
async def help_topic(request: Request, slug: str) -> Any:
    from maya.web.help_catalog import find
    topic = find(slug)
    if topic is None:
        return RedirectResponse("/help", status_code=303)
    return await render(request, f"help/topics/{slug}.html", {"topic": topic,
                                                              "public_nav": True})
