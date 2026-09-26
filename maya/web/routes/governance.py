"""
Model governance pages: the findings register, one model's tier, review schedule and
findings, one finding's history, and the ongoing-monitoring dashboards.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from maya.web.charts import line_chart
from maya.web.routes.common import (
    action,
    client,
    download,
    flash,
    form,
    is_admin,
    page,
    render,
)

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


@router.get("/governance/inventory")
@page
async def governance_inventory(request: Request) -> Any:
    fmt = request.query_params.get("format", "xlsx")
    framework = request.query_params.get("framework", "sr11-7")
    async with client(request) as sdk:
        result = await sdk.governance.inventory(format=fmt, framework=framework)
    today = dt.date.today().strftime("%Y%m%d")
    return download(result, f"maya-inventory-{framework}-{today}.{fmt}")


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
            answers={k[2:]: v for k, v in data.items() if k.startswith("q_") and v},
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


WINDOWS = (7, 30, 90, 365)


def _window(request: Request, default: int) -> int:
    try:
        days = int(request.query_params.get("days", default))
    except ValueError:
        return default
    return days if days in WINDOWS else default


@router.get("/monitoring")
@page
async def monitoring_page(request: Request) -> Any:
    days = _window(request, 30)
    async with client(request) as sdk:
        overview = await sdk.monitoring.overview(days=days)
    return await render(
        request, "monitoring/index.html", {"m": overview, "days": days, "windows": WINDOWS}
    )


def dashboard(m: dict[str, Any]) -> dict[str, Any]:
    """Chart geometry for one warrant's series: volume, then each attribute's charts."""
    marks = [b["at"] for b in m["breaches"]]
    volume = [{"at": d["date"], "rows": d["rows"], "runs": d["runs"]} for d in m["daily"]]
    charts = {
        "rows": line_chart(volume, "rows", marks=marks, floor=0),
        "runs": line_chart(volume, "runs", floor=0),
        "attrs": [],
    }
    for side in ("inputs", "outputs"):
        for attr, points in sorted(m["series"][side].items()):
            b = m["bounds"].get(attr, {})
            group = {"attr": attr, "side": side, "charts": []}
            if any(p["psi"] is not None for p in points):
                group["charts"].append(
                    (
                        "Population stability index",
                        line_chart(
                            points,
                            "psi",
                            bounds=[(0.10, "watch"), (b.get("psi_max"), "covenant")],
                            marks=marks,
                            floor=0,
                        ),
                    )
                )
            if any(p["null_rate"] is not None for p in points):
                group["charts"].append(
                    (
                        "Null rate",
                        line_chart(
                            points,
                            "null_rate",
                            bounds=[(b.get("null_max"), "covenant")],
                            marks=marks,
                            floor=0,
                        ),
                    )
                )
            if any(p["mean"] is not None for p in points):
                group["charts"].append(
                    (
                        "Mean",
                        line_chart(
                            points,
                            "mean",
                            bounds=[(b.get("lo"), "min"), (b.get("hi"), "max")],
                            marks=marks,
                        ),
                    )
                )
            elif any(p["max"] is not None for p in points):
                group["charts"].append(
                    (
                        "Maximum",
                        line_chart(points, "max", bounds=[(b.get("hi"), "max")], marks=marks),
                    )
                )
            if group["charts"]:
                charts["attrs"].append(group)
    return charts


@router.get("/monitoring/warrants/{ew_id}")
@page
async def monitoring_warrant(request: Request, ew_id: str) -> Any:
    days = _window(request, 90)
    async with client(request) as sdk:
        m = await sdk.monitoring.warrant(ew_id, days=days)
    return await render(
        request,
        "monitoring/warrant.html",
        {"m": m, "charts": dashboard(m), "days": days, "windows": WINDOWS},
    )


@router.get("/governance/challenges")
@page
async def challenges_page(request: Request) -> Any:
    async with client(request) as sdk:
        rows = await sdk.challenges.list()
        warrants = [w for w in await sdk.training.list() if w.get("holdout_hash")]
    return await render(request, "governance/challenges.html", {"rows": rows, "warrants": warrants})


@router.post("/governance/challenges")
@action
async def challenge_create(request: Request) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        row = await sdk.challenges.create(
            data.get("champion", ""),
            data.get("challenger", ""),
            metric=data.get("metric") or "rmse",
            champion_parameter_set_id=data.get("champion_parameter_set_id") or None,
            challenger_parameter_set_id=data.get("challenger_parameter_set_id") or None,
        )
    flash(request, f"Scored: {row['result']['verdict'].replace('_', ' ')}.", "success")
    return RedirectResponse(f"/governance/challenges/{row['id']}", status_code=303)


@router.get("/governance/challenges/{challenge_id}")
@page
async def challenge_page(request: Request, challenge_id: str) -> Any:
    async with client(request) as sdk:
        row = await sdk.challenges.get(challenge_id)
    return await render(request, "governance/challenge.html", {"c": row})


@router.post("/governance/challenges/{challenge_id}/decision")
@action
async def challenge_decide(request: Request, challenge_id: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        row = await sdk.challenges.decide(
            challenge_id, data.get("decision", ""), data.get("rationale", "")
        )
    flash(request, f"Decision recorded: {row['state']}.", "success")
    return RedirectResponse(f"/governance/challenges/{challenge_id}", status_code=303)


__all__ = ["router"]
