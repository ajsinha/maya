"""
Workflow (§10, §16.2): my queue, the review screen, policies — viewed with
their live population and managed through a structured editor that
validates as you edit and previews the change against the population —
YAML import/export as a projection, campaigns, SLA aging and break-glass.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from maya.core.errors import ValidationFailed
from maya.web.routes.common import action, api_json, client, flash, form, is_admin, page, render

router = APIRouter()
OBJECT_TYPES = [
    "feature_version",
    "featureset_version",
    "model_version",
    "parameter_set",
    "training_warrant",
    "execution_warrant",
]
CHECKS = [
    "definition_valid",
    "quality_passes",
    "members_approved",
    "no_open_blocking_comments",
    "formula_typechecks",
    "spec_document_complete",
    "code_artifact_validated",
    "spec_true_build",
    "composite_members_mature",
    "contract_valid",
    "leakage_certified",
    "parameters_within_bounds",
    "data_verified_or_justified",
    "parameters_approved",
]


@router.get("/workflow")
@page
async def queue(request: Request) -> Any:
    async with client(request) as sdk:
        items = await sdk.workflow.queue()
    return await render(request, "workflow/queue.html", {"items": items})


REF_IN_TEXT = re.compile(r"maya://[A-Za-z0-9_./@#-]+")


def review_overlay(r: dict[str, Any]) -> dict[str, list[str]]:
    """The change under review, as the canvas draws it (§16.3): added green, changed
    amber, removed struck through.

    The marks come from the semantic diff the review already shows, so the picture and
    the table cannot disagree: a reference the diff names on the old side alone is
    removed, on the new side alone added, on both changed. The object under review is
    itself changed — or added, when no approved version precedes it.
    """
    was: set[str] = set()
    now: set[str] = set()
    diff = r.get("diff") or {}
    for entry in diff.get("entries") or []:
        was |= set(REF_IN_TEXT.findall(str(entry.get("was") or "")))
        now |= set(REF_IN_TEXT.findall(str(entry.get("now") or "")))
    overlay = {
        "added": sorted(now - was),
        "removed": sorted(was - now),
        "changed": sorted(was & now),
    }
    ref = str(r.get("ref") or "")
    if ref.startswith("maya://"):
        overlay["added" if not diff.get("against") else "changed"].append(ref)
    return overlay


@router.get("/workflow/review/{object_type}/{object_id}")
@page
async def review(request: Request, object_type: str, object_id: str) -> Any:
    """The review screen (§10.3, §10.6). The route stays thin: one SDK call assembles
    the diff, the impact list, the governing policy, the SoD and what is outstanding."""
    async with client(request) as sdk:
        r = await sdk.workflow.review(object_type, object_id)
        history = await sdk.workflow.history(object_type, object_id)
        comments = await sdk.workflow.comments(object_type, object_id)
        memos = (
            await sdk.assistant.memos(object_type, object_id)
            if object_type in ("feature_version", "featureset_version", "model_version")
            else None
        )
    return await render(
        request,
        "workflow/review.html",
        {
            "object_type": object_type,
            "object_id": object_id,
            "history": history,
            "comments": comments,
            "state": r["state"],
            "ref": r["ref"],
            "r": r,
            "names": [t["name"] for t in r["transitions"] if t["available"]],
            "policy": r["policy"],
            "memos": memos,
            "is_admin": is_admin(request),
            "review_overlay": review_overlay(r),
            "root": r["ref"] if str(r["ref"]).startswith("maya://") else "",
            "direction": "downstream",
            "depth": "3",
        },
    )


@router.post("/workflow/review/{object_type}/{object_id}/transition")
@action
async def review_transition(request: Request, object_type: str, object_id: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.workflow.transition(
            object_type,
            object_id,
            data["transition"],
            rationale=data.get("rationale") or None,
            force=bool(data.get("force")),
        )
    flash(request, out["message"], "success" if out["moved"] else "info")
    return RedirectResponse(f"/workflow/review/{object_type}/{object_id}", status_code=303)


# -- access requests (§11.5) ----------------------------------------------------------------
@router.get("/workflow/access-requests")
@page
async def access_requests(request: Request) -> Any:
    async with client(request) as sdk:
        rows = await sdk.workflow.access_requests(state=request.query_params.get("state") or None)
    return await render(
        request,
        "workflow/access_requests.html",
        {"rows": rows, "state": request.query_params.get("state", "")},
    )


@router.post("/workflow/access-requests")
@action
async def request_access(request: Request) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        await sdk.workflow.request_access(
            data["kind"],
            data["ref"],
            level=data.get("level") or "read",
            reason=data.get("reason", ""),
        )
    flash(request, "Access requested; the owner has an item to decide.", "success")
    return RedirectResponse(request.headers.get("referer", "/workflow/access-requests"), 303)


@router.post("/workflow/access-requests/{request_id}/decide")
@action
async def decide_access_request(request: Request, request_id: str) -> Any:
    data = await form(request)
    approve = data.get("decision") == "approve"
    async with client(request) as sdk:
        await sdk.workflow.decide_access_request(
            request_id,
            approve,
            note=data.get("note", ""),
            days=int(data["days"]) if data.get("days") else None,
        )
    flash(
        request,
        "Access granted, time-boxed and audited." if approve else "Request refused and audited.",
        "success" if approve else "info",
    )
    return RedirectResponse("/workflow/access-requests", status_code=303)


@router.post("/workflow/access-requests/{request_id}/withdraw")
@action
async def withdraw_access_request(request: Request, request_id: str) -> Any:
    async with client(request) as sdk:
        await sdk.workflow.withdraw_access_request(request_id)
    flash(request, "Request withdrawn.", "info")
    return RedirectResponse("/workflow/access-requests", status_code=303)


# -- policies -------------------------------------------------------------------------------
@router.get("/workflow/policies")
@page
async def policies(request: Request) -> Any:
    async with client(request) as sdk:
        rows = await sdk.workflow.policies()
    return await render(
        request, "workflow/policies.html", {"rows": rows, "object_types": OBJECT_TYPES}
    )


@router.get("/workflow/policies/{policy_id}")
@page
async def policy_editor(request: Request, policy_id: str) -> Any:
    async with client(request) as sdk:
        pol = await sdk.workflow.policy(policy_id)
        roles = [r["name"] for r in await sdk.admin.roles()]
    editor = {
        "object_type": pol["object_type"],
        "scope": pol["scope"],
        "policy": pol["policy"],
        "roles": roles,
        "checks": CHECKS,
        "population": pol["population"],
    }
    return await render(
        request,
        "workflow/policy.html",
        {"p": pol, "editor_json": json.dumps(editor, default=str).replace("</", "<\\/")},
    )


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
        row = await sdk.workflow.draft_policy(
            body["object_type"],
            body["policy"],
            scope=body.get("scope", "*"),
            note=body.get("note", ""),
        )
    return {"id": row["id"], "version_no": row["version_no"], "impact": row.get("impact")}


@router.post("/workflow/policies/{policy_id}/activate")
@action
async def policy_activate(request: Request, policy_id: str) -> Any:
    async with client(request) as sdk:
        row = await sdk.workflow.activate_policy(policy_id)
    flash(
        request,
        f"Policy v{row['version_no']} is active; the previous version is retained.",
        "success",
    )
    return RedirectResponse(f"/workflow/policies/{policy_id}", status_code=303)


@router.post("/workflow/policies/import")
@action
async def policy_import(request: Request) -> Any:
    data = await form(request)
    if not data.get("yaml", "").strip():
        raise ValidationFailed("Paste a policy in YAML")
    async with client(request) as sdk:
        row = await sdk.workflow.import_policy(
            data["object_type"], data["yaml"], scope=data.get("scope") or "*"
        )
    flash(
        request, f"Imported as draft v{row['version_no']}; another admin activates it.", "success"
    )
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
        row = await sdk.workflow.run_campaign(
            data.get("name") or "campaign", data["transition"], items, data.get("rationale", "")
        )
    ok = sum(1 for r in row["results"] if r["ok"])
    flash(
        request,
        f"Campaign '{row['name']}': {ok} of {len(row['results'])} succeeded.",
        "success" if ok == len(row["results"]) else "warning",
    )
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


@router.get("/workflow/delegations")
@page
async def delegations_page(request: Request) -> Any:
    async with client(request) as sdk:
        rows = await sdk.workflow.delegations()
        users = await sdk.admin.users()
    return await render(
        request,
        "workflow/delegations.html",
        {
            "rows": rows,
            "users": [
                u["username"] for u in users if u["username"] != request.session.get("username")
            ],
        },
    )


@router.post("/workflow/delegations")
@action
async def delegate(request: Request) -> Any:
    data = await request.form()
    async with client(request) as sdk:
        await sdk.workflow.delegate(
            data.get("to", ""),
            data.get("starts_on", ""),
            data.get("ends_on", ""),
            data.getlist("object_types"),
            data.get("reason", ""),
        )
    flash(request, f"Approvals delegated to {data.get('to')}.", "success")
    return RedirectResponse("/workflow/delegations", status_code=303)


@router.post("/workflow/delegations/{delegation_id}/revoke")
@action
async def revoke_delegation(request: Request, delegation_id: str) -> Any:
    async with client(request) as sdk:
        await sdk.workflow.revoke_delegation(delegation_id)
    flash(request, "Delegation revoked.", "info")
    return RedirectResponse("/workflow/delegations", status_code=303)


@router.post("/workflow/review/{object_type}/{object_id}/challenge")
@action
async def ask_challenge(request: Request, object_type: str, object_id: str) -> Any:
    async with client(request) as sdk:
        await sdk.assistant.request(object_type, object_id)
    flash(request, "A fresh challenge memo is being written.", "info")
    return RedirectResponse(f"/workflow/review/{object_type}/{object_id}", status_code=303)


@router.post("/workflow/review/{object_type}/{object_id}/challenge/{memo_id}")
@action
async def respond_challenge(
    request: Request, object_type: str, object_id: str, memo_id: str
) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        await sdk.assistant.respond(memo_id, data.get("stance", ""), data.get("note", ""))
    flash(request, "Your response to the challenge is recorded.", "success")
    return RedirectResponse(f"/workflow/review/{object_type}/{object_id}", status_code=303)


@router.get("/workflow/policies/{policy_id}/policy.yaml")
@page
async def policy_yaml(request: Request, policy_id: str) -> Any:
    from fastapi.responses import Response

    async with client(request) as sdk:
        text = await sdk.workflow.policy_yaml(policy_id)
    return Response(
        text if isinstance(text, (bytes, str)) else str(text),
        media_type="application/yaml",
        headers={"Content-Disposition": f'attachment; filename="policy-{policy_id[:8]}.yaml"'},
    )
