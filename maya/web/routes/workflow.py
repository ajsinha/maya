"""
Workflow (§10, §16.2): my queue, the review screen, policies — viewed with
their live population and managed through a structured editor that
validates as you edit and previews the change against the population —
YAML import/export as a projection, campaigns, SLA aging and break-glass.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from maya.core.errors import ValidationFailed
from maya.web.routes.common import (action, api_json, client, flash, form, is_admin, page,
                                    render)

router = APIRouter()
OBJECT_TYPES = ["feature_version", "featureset_version", "model_version", "parameter_set",
                "training_warrant", "execution_warrant"]
CHECKS = ["definition_valid", "quality_passes", "members_approved", "no_open_blocking_comments",
          "formula_typechecks", "spec_document_complete", "code_artifact_validated",
          "spec_true_build", "composite_members_mature", "contract_valid", "leakage_certified",
          "parameters_within_bounds", "data_verified_or_justified", "parameters_approved"]


@router.get("/workflow")
@page
async def queue(request: Request) -> Any:
    async with client(request) as sdk:
        items = await sdk.workflow.queue()
    return await render(request, "workflow/queue.html", {"items": items})


@router.get("/workflow/review/{object_type}/{object_id}")
@page
async def review(request: Request, object_type: str, object_id: str) -> Any:
    async with client(request) as sdk:
        history = await sdk.workflow.history(object_type, object_id)
        comments = await sdk.workflow.comments(object_type, object_id)
        policies = await sdk.workflow.policies()
    active = next((p for p in policies if p["object_type"] == object_type and
                   p["state"] == "active"), None)
    events = [e for e in history if e.get("to_state")]
    state = events[-1]["to_state"] if events else "draft"
    ref = next((e.get("object_ref") for e in reversed(events) if e.get("object_ref")), object_id)
    names = []
    if active:
        for name, t in (active["policy"].get("transitions") or {}).items():
            sources = t.get("from") or []
            if state in (sources if isinstance(sources, list) else [sources]):
                names.append(name)
    return await render(request, "workflow/review.html", {
        "object_type": object_type, "object_id": object_id, "history": history,
        "comments": comments, "state": state, "ref": ref, "names": names, "policy": active,
        "is_admin": is_admin(request)})


@router.post("/workflow/review/{object_type}/{object_id}/transition")
@action
async def review_transition(request: Request, object_type: str, object_id: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.workflow.transition(object_type, object_id, data["transition"],
                                            rationale=data.get("rationale") or None,
                                            force=bool(data.get("force")))
    flash(request, out["message"], "success" if out["moved"] else "info")
    return RedirectResponse(f"/workflow/review/{object_type}/{object_id}", status_code=303)


# -- policies -------------------------------------------------------------------------------
@router.get("/workflow/policies")
@page
async def policies(request: Request) -> Any:
    async with client(request) as sdk:
        rows = await sdk.workflow.policies()
    return await render(request, "workflow/policies.html",
                        {"rows": rows, "object_types": OBJECT_TYPES})


@router.get("/workflow/policies/{policy_id}")
@page
async def policy_editor(request: Request, policy_id: str) -> Any:
    async with client(request) as sdk:
        pol = await sdk.workflow.policy(policy_id)
        roles = [r["name"] for r in await sdk.admin.roles()]
    editor = {"object_type": pol["object_type"], "scope": pol["scope"], "policy": pol["policy"],
              "roles": roles, "checks": CHECKS, "population": pol["population"]}
    return await render(request, "workflow/policy.html",
                        {"p": pol, "editor_json": json.dumps(editor, default=str)
                         .replace("</", "<\\/")})


@router.post("/workflow/policies/validate")
@api_json
async def policy_validate(request: Request) -> Any:
    body = await request.json()
    async with client(request) as sdk:
        return await sdk.workflow.validate_policy(body["object_type"], body["policy"])


@router.post("/workflow/policies/save")
@api_json
async def policy_save(request: Request) -> Any:
    body = await request.json()
    async with client(request) as sdk:
        row = await sdk.workflow.draft_policy(body["object_type"], body["policy"],
                                              scope=body.get("scope", "*"),
                                              note=body.get("note", ""))
    return {"id": row["id"], "version_no": row["version_no"], "impact": row.get("impact")}


@router.post("/workflow/policies/{policy_id}/activate")
@action
async def policy_activate(request: Request, policy_id: str) -> Any:
    async with client(request) as sdk:
        row = await sdk.workflow.activate_policy(policy_id)
    flash(request, f"Policy v{row['version_no']} is active; the previous version is retained.",
          "success")
    return RedirectResponse(f"/workflow/policies/{policy_id}", status_code=303)


@router.post("/workflow/policies/import")
@action
async def policy_import(request: Request) -> Any:
    data = await form(request)
    if not data.get("yaml", "").strip():
        raise ValidationFailed("Paste a policy in YAML")
    async with client(request) as sdk:
        row = await sdk.workflow.import_policy(data["object_type"], data["yaml"],
                                               scope=data.get("scope") or "*")
    flash(request, f"Imported as draft v{row['version_no']}; another admin activates it.",
          "success")
    return RedirectResponse(f"/workflow/policies/{row['id']}", status_code=303)


# -- campaigns and reports --------------------------------------------------------------------
@router.get("/workflow/campaigns")
@page
async def campaigns(request: Request) -> Any:
    async with client(request) as sdk:
        rows = await sdk.workflow.campaigns()
        items = await sdk.workflow.queue()
    return await render(request, "workflow/campaigns.html", {"rows": rows, "items": items})


@router.post("/workflow/campaigns")
@action
async def run_campaign(request: Request) -> Any:
    data = await request.form()
    items = []
    for value in data.getlist("item"):
        object_type, object_id = value.split("|", 1)
        items.append({"object_type": object_type, "id": object_id})
    if not items:
        raise ValidationFailed("Select at least one object for the campaign")
    async with client(request) as sdk:
        row = await sdk.workflow.run_campaign(data.get("name") or "campaign", data["transition"],
                                              items, data.get("rationale", ""))
    ok = sum(1 for r in row["results"] if r["ok"])
    flash(request, f"Campaign '{row['name']}': {ok} of {len(row['results'])} succeeded.",
          "success" if ok == len(row["results"]) else "warning")
    return RedirectResponse("/workflow/campaigns", status_code=303)


@router.get("/workflow/aging")
@page
async def aging(request: Request) -> Any:
    async with client(request) as sdk:
        rows = await sdk.workflow.aging()
    return await render(request, "workflow/aging.html", {"rows": rows})


@router.get("/workflow/break-glass")
@page
async def break_glass(request: Request) -> Any:
    days = int(request.query_params.get("days") or 31)
    async with client(request) as sdk:
        rows = await sdk.workflow.break_glass(days)
    return await render(request, "workflow/break_glass.html", {"rows": rows, "days": days})
