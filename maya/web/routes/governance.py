"""
Model governance pages (§ governance): the findings register, one model's tier, review
schedule and findings, and one finding's history.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from maya.web.routes.common import action, client, flash, form, is_admin, page, render

router = APIRouter()

SEVERITIES = ("critical", "high", "medium", "low")
SOURCES = ("validation", "audit", "monitoring", "review", "self-identified")
USES = ("regulatory", "financial_reporting", "business_decision", "internal")
OUTCOMES = ("satisfactory", "needs_improvement", "unsatisfactory")
# what each move is called on a button, and whether it asks for a note
MOVES = {
    "open": [
        ("start", "Start remediation", False),
        ("remediated", "Mark remediated", False),
        ("accept", "Accept the risk", True),
    ],
    "remediating": [("remediated", "Mark remediated", False), ("accept", "Accept the risk", True)],
    "remediated": [
        ("close", "Confirm the fix and close", True),
        ("reject", "Send back: not fixed", True),
        ("accept", "Accept the risk", True),
    ],
    "closed": [("reopen", "Reopen", True)],
    "accepted": [("reopen", "Reopen", True)],
}


def _num(value: Any, cast: Any = float) -> Any:
    return cast(value) if value not in (None, "") else None


@router.get("/governance")
@page
async def governance_page(request: Request) -> Any:
    state = request.query_params.get("state", "active")
    async with client(request) as sdk:
        overview = await sdk.governance.overview()
        findings = await sdk.governance.findings(state=state or None)
    return await render(
        request,
        "governance/index.html",
        {
            "overview": overview,
            "findings": findings,
            "state": state,
            "severities": SEVERITIES,
            "sources": SOURCES,
            "admin": is_admin(request),
        },
    )


@router.get("/governance/models/{namespace}/{name}")
@page
async def governance_model(request: Request, namespace: str, name: str) -> Any:
    async with client(request) as sdk:
        prof = await sdk.governance.profile(f"{namespace}/{name}")
    return await render(
        request,
        "governance/model.html",
        {
            "g": prof,
            "ns_name": namespace,
            "name": name,
            "severities": SEVERITIES,
            "sources": SOURCES,
            "uses": USES,
            "outcomes": OUTCOMES,
            "moves": MOVES,
        },
    )


@router.get("/governance/findings/{finding_id}")
@page
async def governance_finding(request: Request, finding_id: str) -> Any:
    async with client(request) as sdk:
        finding = await sdk.governance.finding(finding_id)
    return await render(
        request, "governance/finding.html", {"f": finding, "moves": MOVES.get(finding["state"], [])}
    )


@router.post("/governance/findings")
@action
async def governance_raise(request: Request) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        row = await sdk.governance.raise_finding(
            data.get("model", ""),
            data.get("title", ""),
            data.get("severity", ""),
            detail=data.get("detail") or None,
            source=data.get("source") or "validation",
            owner=data.get("owner") or None,
            due_date=data.get("due_date") or None,
            version_no=_num(data.get("version_no"), int),
        )
    flash(request, f"Finding raised, due {row['due_date']}.", "success")
    return RedirectResponse(f"/governance/findings/{row['id']}", status_code=303)


@router.post("/governance/findings/{finding_id}/move")
@action
async def governance_move(request: Request, finding_id: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        row = await sdk.governance.move_finding(
            finding_id, data.get("action", ""), data.get("note") or None
        )
    flash(request, f"Finding is now {row['state']}.", "success")
    return RedirectResponse(f"/governance/findings/{finding_id}", status_code=303)


@router.post("/governance/models/{namespace}/{name}/profile")
@action
async def governance_profile(request: Request, namespace: str, name: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.governance.set_profile(
            f"{namespace}/{name}",
            use=data.get("use") or None,
            exposure=_num(data.get("exposure")),
            tier_override=_num(data.get("tier_override"), int),
            override_reason=data.get("override_reason") or None,
            review_days=_num(data.get("review_days"), int),
        )
    flash(request, f"Tier {out['tier']} (derived: {out['derived_tier']}).", "success")
    return RedirectResponse(f"/governance/models/{namespace}/{name}", status_code=303)


@router.post("/governance/models/{namespace}/{name}/review")
@action
async def governance_review(request: Request, namespace: str, name: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.governance.record_review(
            f"{namespace}/{name}", data.get("outcome", ""), data.get("note", "")
        )
    lifted = len(out.get("reinstated") or [])
    extra = f" {lifted} warrant(s) suspended for the overdue review reinstated." if lifted else ""
    flash(request, f"Review recorded; next due {out['next_review_due']}.{extra}", "success")
    return RedirectResponse(f"/governance/models/{namespace}/{name}", status_code=303)


@router.post("/governance/sweep")
@action
async def governance_sweep(request: Request) -> Any:
    async with client(request) as sdk:
        out = await sdk.governance.sweep()
    flash(request, f"{len(out['suspended'])} warrant(s) suspended for overdue reviews.", "info")
    return RedirectResponse("/governance", status_code=303)


__all__ = ["router"]
