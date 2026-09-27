"""
Home dashboard, search, inbox, help/about, and the small JSON endpoint the
pages' own scripts call for job progress. The lineage canvas has its own
module (``routes/lineage.py``).

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
async def front(request: Request) -> Any:
    """The front door. Signed in, it is the dashboard; signed out, it is the landing page.

    A visitor who arrives at MAYA should be told what MAYA is, not handed a password box:
    a sign-in form answers "who are you" to somebody who has not yet been told why they
    would want an account here."""
    if not request.session.get("token"):
        return await render(request, "landing.html", {"public_nav": True})
    return await dashboard(request)


@page
async def dashboard(request: Request) -> Any:
    async with client(request) as sdk:
        queue = await sdk.workflow.queue()
        features = await sdk.features.page(page_size=10, sort="-updated", total=True)
        models = await sdk.models.page(page_size=10, total=True)
        jobs = await sdk.jobs.list()
        try:
            health = await sdk.admin.health()
        except MayaError:
            health = None
    return await render(
        request,
        "dashboard.html",
        {
            "queue": queue,
            "recent": features["items"],
            "models": models["items"],
            "jobs": jobs[:10],
            "health_full": health,
            "counts": {
                "features": features["total"],
                "models": models["total"],
                "queue": len(queue),
            },
        },
    )


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
    return {
        "feature": f"/catalog/features/{ns}/{name}",
        "featureset": f"/catalog/featuresets/{ns}/{name}",
        "model": f"/models/{ns}/{name}",
        "warrant/train": f"/warrants/training/{hit.get('id')}",
        "warrant/exec": f"/warrants/execution/{hit.get('id')}",
        "namespace": "/admin/namespaces",
    }.get(kind, "/")


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


@router.get("/ui/jobs/{job_id}")
@api_json
async def job_json(request: Request, job_id: str) -> Any:
    async with client(request) as sdk:
        job = await sdk.jobs.get(job_id)
    return {
        "id": job["id"],
        "state": job["state"],
        "progress": job["progress"],
        "message": job["message"],
        "error_text": job["error"],
    }


@router.get("/about")
async def about(request: Request) -> Any:
    """Public, like Help: what MAYA is, before anyone has an account."""
    return await render(request, "help/about.html", {"highlights": HIGHLIGHTS, "public_nav": True})


@router.get("/help")
async def help_index(request: Request) -> Any:
    from maya.web.help_catalog import CATEGORIES, GUIDES

    from maya.web.case_studies import catalog as studies

    return await render(
        request,
        "help/index.html",
        {"catalog": CATEGORIES, "guides": GUIDES, "studies": studies(), "public_nav": True},
    )


@router.get("/help/guides")
async def help_guides(request: Request) -> Any:
    from maya.web.help_catalog import GUIDES

    return await render(request, "help/guides.html", {"guides": GUIDES, "public_nav": True})


@router.get("/help/guides/{slug}")
async def help_guide(request: Request, slug: str) -> Any:
    from maya.web.guide_render import render as render_guide
    from maya.web.help_catalog import find_guide

    guide = find_guide(slug)
    if guide is None:
        return RedirectResponse("/help/guides", status_code=303)
    try:
        doc = render_guide(slug)
    except FileNotFoundError:
        return RedirectResponse("/help/guides", status_code=303)
    return await render(
        request, "help/guide.html", {"guide": guide, "doc": doc, "public_nav": True}
    )


@router.get("/help/case-studies")
async def help_case_studies(request: Request) -> Any:
    from maya.web.case_studies import catalog

    return await render(
        request, "help/case_studies.html", {"studies": catalog(), "public_nav": True}
    )


@router.get("/help/case-studies/{slug}")
async def help_case_study(request: Request, slug: str) -> Any:
    from maya.web import case_studies

    studies = case_studies.catalog()
    study = next((s for s in studies if s["slug"] == slug), None)
    if study is None:
        return RedirectResponse("/help/case-studies", status_code=303)
    i = studies.index(study)
    return await render(
        request,
        "help/case_study.html",
        {
            "study": study,
            "doc": case_studies.render(slug),
            "prev": studies[i - 1] if i else None,
            "next": studies[i + 1] if i + 1 < len(studies) else None,
            "public_nav": True,
        },
    )


@router.get("/help/{slug}")
async def help_topic(request: Request, slug: str) -> Any:
    from maya.web.help_catalog import find

    topic = find(slug)
    if topic is None:
        return RedirectResponse("/help", status_code=303)
    from maya.web.help_catalog import companion

    return await render(
        request,
        f"help/topics/{slug}.html",
        {"topic": topic, "companion": companion(slug), "public_nav": True},
    )
