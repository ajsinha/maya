"""
LLM application pages: the list, one application (versions, evaluation sets, runs,
submission and decision) and one run's case-by-case results.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from maya.core.errors import NotFound
from maya.web.routes.common import action, client, flash, form, page, parse_json, render

router = APIRouter()


@router.get("/llm")
@page
async def llm_page(request: Request) -> Any:
    async with client(request) as sdk:
        apps = await sdk.llm.apps()
        namespaces = await sdk.namespaces.list()
    return await render(request, "llm/list.html", {"apps": apps, "namespaces": namespaces})


@router.post("/llm")
@action
async def llm_create(request: Request) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        app = await sdk.llm.create_app(
            data.get("namespace", ""),
            data.get("name", ""),
            data.get("use_case", ""),
            data.get("description", ""),
        )
    flash(request, "Application registered. Write its first version.", "success")
    return RedirectResponse(f"/llm/{data.get('namespace')}/{app['name']}", status_code=303)


@router.get("/llm/{ns}/{name}")
@page
async def llm_app(request: Request, ns: str, name: str) -> Any:
    async with client(request) as sdk:
        app = await sdk.llm.app(f"{ns}/{name}")
    draft = app["versions"][0] if app["versions"] else None
    by_version = {v["id"]: v["version_no"] for v in app["versions"]}
    sets = {e["id"]: e for e in app["eval_sets"]}
    for run in app["runs"]:
        run["version_no"] = by_version.get(run["version_id"])
        es = sets.get(run["eval_set_id"]) or {}
        run["eval_set"] = es.get("name")
        run["stale"] = es.get("content_hash") != run["eval_set_hash"]
    return await render(request, "llm/app.html", {"a": app, "draft": draft})


@router.get("/llm/{ns}/{name}/runs/{run_id}")
@page
async def llm_run(request: Request, ns: str, name: str, run_id: str) -> Any:
    async with client(request) as sdk:
        app = await sdk.llm.app(f"{ns}/{name}")
    run = next((r for r in app["runs"] if r["id"] == run_id), None)
    if run is None:
        raise NotFound("No such evaluation run")
    return await render(request, "llm/run.html", {"a": app, "r": run})


@router.post("/llm/{ns}/{name}/draft")
@action
async def llm_draft(request: Request, ns: str, name: str) -> Any:
    data = await form(request)
    blocked = [t.strip() for t in data.get("blocked_terms", "").split(",") if t.strip()]
    async with client(request) as sdk:
        v = await sdk.llm.save_version(
            f"{ns}/{name}",
            provider=data.get("provider", ""),
            model=data.get("model", ""),
            prompt_template=data.get("prompt_template", ""),
            system_prompt=data.get("system_prompt", ""),
            parameters=parse_json(data.get("parameters"), "Parameters", {}),
            guardrails={
                "blocked_terms": blocked,
                "pii": bool(data.get("pii")),
                "max_chars": int(data["max_chars"]) if data.get("max_chars") else None,
                "min_pass_rate": float(data.get("min_pass_rate") or 1.0),
            },
        )
    flash(request, f"Saved as version {v['version_no']} (draft).", "success")
    return RedirectResponse(f"/llm/{ns}/{name}", status_code=303)


@router.post("/llm/{ns}/{name}/eval-sets")
@action
async def llm_eval_set(request: Request, ns: str, name: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        es = await sdk.llm.save_eval_set(
            f"{ns}/{name}",
            data.get("set_name", ""),
            parse_json(data.get("cases"), "The cases", []),
            data.get("description", ""),
        )
    flash(request, f"Evaluation set '{es['name']}' saved: {len(es['cases'])} case(s).", "success")
    return RedirectResponse(f"/llm/{ns}/{name}", status_code=303)


@router.post("/llm/{ns}/{name}/runs")
@action
async def llm_run_eval(request: Request, ns: str, name: str) -> Any:
    data = await form(request)
    responses = None
    if data.get("mode") == "recorded":
        responses = parse_json(data.get("responses"), "The recorded answers", {})
    async with client(request) as sdk:
        run = await sdk.llm.run_eval(
            f"{ns}/{name}", int(data.get("version_no", 0)), data.get("eval_set", ""), responses
        )
    flash(request, f"{run['passed']} of {run['cases']} case(s) passed.", "success")
    return RedirectResponse(f"/llm/{ns}/{name}/runs/{run['id']}", status_code=303)


@router.post("/llm/{ns}/{name}/versions/{version_no}/submit")
@action
async def llm_submit(request: Request, ns: str, name: str, version_no: int) -> Any:
    async with client(request) as sdk:
        await sdk.llm.submit(f"{ns}/{name}", version_no)
    flash(request, f"Version {version_no} submitted for review.", "success")
    return RedirectResponse(f"/llm/{ns}/{name}", status_code=303)


@router.post("/llm/{ns}/{name}/versions/{version_no}/decision")
@action
async def llm_decide(request: Request, ns: str, name: str, version_no: int) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        v = await sdk.llm.decide(
            f"{ns}/{name}", version_no, data.get("decision", ""), data.get("note", "")
        )
    flash(request, f"Version {version_no} {v['state']}.", "success")
    return RedirectResponse(f"/llm/{ns}/{name}", status_code=303)


__all__ = ["router"]
