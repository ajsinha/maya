"""
Admin (§16.2): system health, users/roles/groups, sessions, namespaces,
grants on any object, the jobs console, the audit explorer, effective
configuration, storage (fragment sharing) and integrity verification, and
the estate export that is MAYA's only schema-upgrade path.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from maya.web.routes.tables import first_page
from maya.web.routes.common import (action, client, download, flash, form, invalidate_health,
                                    page, parse_json, render)

router = APIRouter()
GRANT_KINDS = ["feature", "featureset", "model", "training_warrant", "execution_warrant",
               "namespace"]
LEVELS = ["read", "read_write", "approve", "own", "admin"]


@router.get("/admin")
@page
async def admin_home(request: Request) -> Any:
    return RedirectResponse("/admin/health", status_code=303)


@router.get("/admin/health")
@page
async def health(request: Request) -> Any:
    async with client(request) as sdk:
        h = await sdk.admin.health()
    return await render(request, "admin/health.html", {"h": h})


# -- users, roles, groups, sessions ---------------------------------------------------------
@router.get("/admin/users")
@page
async def users(request: Request) -> Any:
    async with client(request) as sdk:
        rows = await sdk.admin.users()
        roles = await sdk.admin.roles()
        groups = await sdk.admin.groups()
        sessions = await sdk.auth.sessions() if "admin" in request.session.get("roles", []) else []
    object_types = sorted({k for r in roles for k in r["capabilities"]})
    return await render(request, "admin/users.html", {
        "rows": rows, "roles": roles, "groups": groups, "sessions": sessions,
        "object_types": object_types})


@router.post("/admin/users")
@action
async def create_user(request: Request) -> Any:
    data = await request.form()
    async with client(request) as sdk:
        await sdk.admin.create_user(data["username"], password=data.get("password") or None,
                                    email=data.get("email", ""),
                                    display_name=data.get("display_name", ""),
                                    roles=data.getlist("roles"),
                                    is_service=bool(data.get("is_service")),
                                    desk=data.get("desk") or None)
    flash(request, f"User {data['username']} created; they must change the password at first login.",
          "success")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{username}/roles")
@action
async def set_roles(request: Request, username: str) -> Any:
    data = await request.form()
    async with client(request) as sdk:
        await sdk.admin.set_roles(username, data.getlist("roles"))
    flash(request, f"Roles of {username} updated.", "success")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{username}/password")
@action
async def reset_password(request: Request, username: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        await sdk.admin.reset_password(username, data.get("new_password", ""))
    flash(request, f"Password of {username} reset; they must change it at next login.", "success")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{username}/mfa-reset")
@action
async def reset_mfa(request: Request, username: str) -> Any:
    async with client(request) as sdk:
        await sdk.admin.reset_mfa(username)
    flash(request, f"Two-factor authentication of {username} reset; they enroll again.",
          "success")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{username}/status")
@action
async def set_status(request: Request, username: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        await sdk.admin.update_user(username, status=data.get("status", "active"))
    flash(request, f"{username} is now {data.get('status')}.", "success")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/roles")
@action
async def create_role(request: Request) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        await sdk.admin.create_role(data["name"], parse_json(data.get("capabilities"),
                                                             "Capabilities", {}),
                                    description=data.get("description", ""))
    flash(request, f"Role {data['name']} created.", "success")
    return RedirectResponse("/admin/users#roles", status_code=303)


@router.post("/admin/groups")
@action
async def create_group(request: Request) -> Any:
    data = await request.form()
    members = [m.strip() for m in data.get("members", "").split(",") if m.strip()]
    async with client(request) as sdk:
        await sdk.admin.create_group(data["name"], description=data.get("description", ""),
                                     roles=data.getlist("roles"), members=members)
    flash(request, f"Group {data['name']} created.", "success")
    return RedirectResponse("/admin/users#groups", status_code=303)


@router.post("/admin/sessions/{session_id}/end")
@action
async def end_session(request: Request, session_id: str) -> Any:
    async with client(request) as sdk:
        await sdk.auth.end_session(session_id)
    flash(request, "Session terminated.", "success")
    return RedirectResponse("/admin/users#sessions", status_code=303)


# -- events and webhooks ------------------------------------------------------------------------
@router.get("/admin/webhooks")
@page
async def webhooks(request: Request) -> Any:
    show = request.query_params.get("deliveries")
    async with client(request) as sdk:
        rows = await sdk.events.webhooks()
        deliveries = await sdk.events.deliveries(show) if show else None
    return await render(request, "admin/webhooks.html", {
        "rows": rows, "deliveries": deliveries, "shown": show,
        "new_secret": request.session.pop("new_webhook_secret", None)})


@router.post("/admin/webhooks")
@action
async def create_webhook(request: Request) -> Any:
    data = await form(request)
    types = [t.strip() for t in (data.get("event_types") or "").split(",") if t.strip()]
    async with client(request) as sdk:
        hook = await sdk.events.create_webhook(data.get("name", ""), data.get("url", ""), types,
                                               data.get("description", ""))
    request.session["new_webhook_secret"] = hook["secret"]
    flash(request, "Webhook created. Copy its signing secret now: it is shown once.", "warning")
    return RedirectResponse("/admin/webhooks", status_code=303)


@router.post("/admin/webhooks/{webhook_id}/ping")
@action
async def ping_webhook(request: Request, webhook_id: str) -> Any:
    async with client(request) as sdk:
        out = await sdk.events.ping(webhook_id)
    flash(request, f"Ping {out['state']} (HTTP {out['last_status'] or '—'})"
          + (f": {out['last_error']}" if out.get("last_error") else ""),
          "success" if out["state"] == "delivered" else "warning")
    return RedirectResponse(f"/admin/webhooks?deliveries={webhook_id}", status_code=303)


@router.post("/admin/webhooks/{webhook_id}/delete")
@action
async def delete_webhook(request: Request, webhook_id: str) -> Any:
    async with client(request) as sdk:
        await sdk.events.delete_webhook(webhook_id)
    flash(request, "Webhook deactivated; its pending deliveries were dropped.", "info")
    return RedirectResponse("/admin/webhooks", status_code=303)


@router.get("/admin/events")
@page
async def events_page(request: Request) -> Any:
    q = request.query_params
    async with client(request) as sdk:
        page = await first_page(request, sdk, "events", type=q.get("type") or None)
    return await render(request, "admin/events.html", {"page": page,
                                                       "type": q.get("type", "")})


# -- custody anchors (§29.6) --------------------------------------------------------------------
@router.get("/admin/custody")
@page
async def custody_page(request: Request) -> Any:
    verify = request.query_params.get("verify") == "1"
    async with client(request) as sdk:
        data = await sdk.custody.anchors()
        report = await sdk.custody.verify() if verify else None
    return await render(request, "admin/custody.html", {**data, "report": report})


@router.post("/admin/custody/anchor")
@action
async def custody_anchor(request: Request) -> Any:
    async with client(request) as sdk:
        row = await sdk.custody.anchor()
    flash(request, f"Chain head anchored at seq {row['seq']}." if row else
          "The audit log is empty; nothing to anchor.", "success" if row else "info")
    return RedirectResponse("/admin/custody", status_code=303)


# -- SQL source connections --------------------------------------------------------------------
@router.get("/admin/sources")
@page
async def sources(request: Request) -> Any:
    async with client(request) as sdk:
        rows = await sdk.sources.connections()
    return await render(request, "admin/sources.html", {"rows": rows})


@router.post("/admin/sources")
@action
async def create_source(request: Request) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        await sdk.sources.create_connection(data.get("name", ""), data.get("url", ""),
                                            data.get("password_env") or None,
                                            data.get("description", ""))
    flash(request, "Connection saved.", "success")
    return RedirectResponse("/admin/sources", status_code=303)


@router.post("/admin/sources/{name}/test")
@action
async def test_source(request: Request, name: str) -> Any:
    async with client(request) as sdk:
        out = await sdk.sources.test_connection(name)
    flash(request, f"{name}: connected ({out['dialect']}, read-only)" if out["ok"]
          else f"{name}: {out['error']}", "success" if out["ok"] else "danger")
    return RedirectResponse("/admin/sources", status_code=303)


@router.post("/admin/sources/{name}/delete")
@action
async def delete_source(request: Request, name: str) -> Any:
    async with client(request) as sdk:
        await sdk.sources.delete_connection(name)
    flash(request, f"Connection {name} deleted.", "info")
    return RedirectResponse("/admin/sources", status_code=303)


# -- namespaces and grants ----------------------------------------------------------------------
@router.get("/admin/namespaces")
@page
async def namespaces(request: Request) -> Any:
    async with client(request) as sdk:
        rows = await sdk.namespaces.list()
    return await render(request, "admin/namespaces.html", {"rows": rows})


@router.post("/admin/namespaces")
@action
async def create_namespace(request: Request) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        await sdk.namespaces.create(data["name"], description=data.get("description", ""),
                                    parent=data.get("parent") or None,
                                    preset=data.get("preset", "standard"),
                                    default_visibility=data.get("default_visibility",
                                                                "namespace_read"),
                                    production=bool(data.get("production")),
                                    classification=data.get("classification", "internal"))
    flash(request, f"Namespace {data['name']} created.", "success")
    return RedirectResponse("/admin/namespaces", status_code=303)


@router.post("/admin/namespaces/{name}")
@action
async def update_namespace(request: Request, name: str) -> Any:
    data = await form(request)
    changes = {k: data[k] for k in ("sod", "default_visibility", "classification") if data.get(k)}
    async with client(request) as sdk:
        await sdk.namespaces.update(name, **changes)
    flash(request, f"Namespace {name} updated.", "success")
    return RedirectResponse("/admin/namespaces", status_code=303)


@router.get("/admin/grants")
@page
async def grants(request: Request) -> Any:
    qp = request.query_params
    kind, ref = qp.get("kind", "feature"), qp.get("ref", "")
    rows: list[dict[str, Any]] = []
    recert: list[dict[str, Any]] = []
    async with client(request) as sdk:
        if ref:
            rows = await sdk.access.grants(kind, ref)
        recert = await sdk.access.recertification()
    return await render(request, "admin/grants.html", {
        "rows": rows, "kind": kind, "ref": ref, "kinds": GRANT_KINDS, "levels": LEVELS,
        "recert": recert})


def _conditions(data: dict[str, Any]) -> dict[str, Any]:
    """§11.4 conditions from the form: a row filter, a cut-off date, masks as attr:how."""
    out: dict[str, Any] = {}
    if (data.get("row_filter") or "").strip():
        out["row_filter"] = data["row_filter"].strip()
    if (data.get("until") or "").strip():
        out["time_bound"] = {"until": data["until"].strip()}
    masks = {}
    for part in (data.get("masks") or "").split(","):
        if ":" in part:
            attr, how = (x.strip() for x in part.split(":", 1))
            masks[attr] = how
    if masks:
        out["column_mask"] = masks
    return out


@router.post("/admin/grants")
@action
async def grant(request: Request) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        row = await sdk.access.grant(data["kind"], data["ref"], data["principal_type"],
                                     data.get("principal_id") or "*", data["level"],
                                     days=int(data["days"]) if data.get("days") else None,
                                     deny=bool(data.get("deny")),
                                     conditions=_conditions(data))
    if row.get("inert_reason"):
        flash(request, f"Grant recorded but INERT: {row['inert_reason']}", "warning")
    else:
        flash(request, "Grant recorded.", "success")
    return RedirectResponse(f"/admin/grants?kind={data['kind']}&ref={data['ref']}",
                            status_code=303)


@router.post("/admin/grants/{grant_id}/revoke")
@action
async def revoke_grant(request: Request, grant_id: str) -> Any:
    async with client(request) as sdk:
        await sdk.access.revoke(grant_id)
    flash(request, "Grant revoked.", "success")
    return RedirectResponse(request.headers.get("referer", "/admin/grants"), status_code=303)


# -- operations -----------------------------------------------------------------------------------
@router.get("/admin/jobs")
@page
async def jobs(request: Request) -> Any:
    async with client(request) as sdk:
        page = await first_page(request, sdk, "jobs")
    return await render(request, "admin/jobs.html", {"page": page})


@router.post("/admin/jobs/{job_id}/{verb}")
@action
async def job_action(request: Request, job_id: str, verb: str) -> Any:
    async with client(request) as sdk:
        if verb == "cancel":
            await sdk.jobs.cancel(job_id)
        elif verb == "retry":
            await sdk.jobs.retry(job_id)
    flash(request, f"Job {job_id[:8]}: {verb} requested.", "info")
    return RedirectResponse("/admin/jobs", status_code=303)


@router.get("/admin/audit")
@page
async def audit(request: Request) -> Any:
    qp = request.query_params
    async with client(request) as sdk:
        page = await first_page(request, sdk, "audit", q=qp.get("q") or None,
                                action=qp.get("action") or None)
        chain = await sdk.admin.verify_audit()
    return await render(request, "admin/audit.html", {
        "page": page, "chain": chain, "q": qp.get("q", ""), "action": qp.get("action", "")})


@router.get("/admin/config")
@page
async def config(request: Request) -> Any:
    async with client(request) as sdk:
        rows = await sdk.admin.config()
    return await render(request, "admin/config.html", {"rows": rows})


@router.get("/admin/storage")
@page
async def storage(request: Request) -> Any:
    async with client(request) as sdk:
        report = await sdk.admin.storage()
    return await render(request, "admin/storage.html", {
        "r": report, "integrity": request.session.pop("integrity", None),
        "maintained": request.session.pop("maintained", None)})


@router.post("/admin/lake/maintain")
@action
async def lake_maintain(request: Request) -> Any:
    async with client(request) as sdk:
        out = await sdk.admin.lake_maintain()
    request.session["maintained"] = {k: out[k] for k in ("filesRemoved", "filesAdded",
                                                         "vacuumed")} | {
        "tables": [t["table"] for t in out["tables"]]}
    flash(request, "Lake compacted and vacuumed.", "success")
    return RedirectResponse("/admin/storage", status_code=303)


@router.post("/admin/integrity")
@action
async def integrity(request: Request) -> Any:
    async with client(request) as sdk:
        out = await sdk.admin.verify_integrity()
    request.session["integrity"] = {"checked": out["checked"], "drift": out["drift"],
                                    "audit_chain": out["audit_chain"]}
    invalidate_health()
    flash(request, f"Integrity verified: {out['checked']} pin(s), {len(out['drift'])} with drift.",
          "danger" if out["drift"] else "success")
    return RedirectResponse("/admin/storage", status_code=303)


@router.get("/admin/estate")
@page
async def estate(request: Request) -> Any:
    async with client(request) as sdk:
        result = await sdk.admin.export_estate()
    return download({**result, "content_type": "application/zip"}, "estate.mayabundle")
