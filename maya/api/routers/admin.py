"""
Authentication, identity, access and operations endpoints (§12, §11, §20).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from maya.api import schemas as s
from maya.api.deps import Me, Plat, ok
from maya.core.errors import PermissionDenied
from maya.security.authz import Principal

router = APIRouter()


# -- auth ----------------------------------------------------------------------------
@router.post("/auth/login", tags=["auth"])
def login(body: s.LoginIn, request: Request, plat: Any = Plat) -> Response:
    ip = request.client.host if request.client else None
    channel = request.headers.get("x-maya-channel", "api")
    return ok(
        plat.auth.login(
            body.username,
            body.password,
            ip=ip,
            user_agent=request.headers.get("user-agent"),
            channel=channel,
        )
    )


def _bearer(request: Request) -> str:
    return request.headers.get("authorization", "")[7:].strip()


@router.get("/auth/sso/config", tags=["auth"])
def sso_config(plat: Any = Plat) -> Response:
    """Public: which sign-in methods this deployment offers."""
    return ok(plat.sso.public_config())


@router.post("/auth/sso/start", tags=["auth"])
def sso_start(plat: Any = Plat) -> Response:
    """Public: state, nonce and PKCE verifier for the caller to keep, and the IdP URL."""
    return ok(plat.sso.start())


@router.post("/auth/sso/callback", tags=["auth"])
def sso_callback(body: s.SsoCallbackIn, request: Request, plat: Any = Plat) -> Response:
    ip = request.client.host if request.client else None
    return ok(
        plat.sso.callback(
            body.code,
            body.code_verifier,
            body.nonce,
            ip=ip,
            user_agent=request.headers.get("user-agent"),
        )
    )


@router.get("/auth/mfa", tags=["auth"])
def mfa_status(request: Request, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.sso.mfa_status(_bearer(request)))


@router.post("/auth/mfa/verify", tags=["auth"])
def mfa_verify(body: s.CodeIn, request: Request, me: Principal = Me, plat: Any = Plat) -> Response:
    ip = request.client.host if request.client else None
    return ok(plat.sso.verify(_bearer(request), body.code, ip=ip))


@router.post("/auth/mfa/enroll", tags=["auth"])
def mfa_enroll(request: Request, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.sso.enroll(me, _bearer(request)))


@router.post("/auth/mfa/confirm", tags=["auth"])
def mfa_confirm(body: s.CodeIn, request: Request, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.sso.confirm(me, _bearer(request), body.code))


@router.post("/users/{username}/mfa-reset", tags=["admin"])
def mfa_reset(username: str, me: Principal = Me, plat: Any = Plat) -> Response:
    plat.sso.reset(me, username)
    return ok({"ok": True})


@router.post("/auth/logout", tags=["auth"])
def logout(request: Request, me: Principal = Me, plat: Any = Plat) -> Response:
    """End this session. After a SAML sign-in with single logout configured,
    ``slo_redirect`` is where the browser goes so the IdP ends its session too."""
    return ok(plat.sso.logout(request.headers.get("authorization", "")[7:].strip()))


@router.get("/auth/me", tags=["auth"])
def whoami(me: Principal = Me, plat: Any = Plat) -> Response:
    with plat.uow() as uow:
        user = uow.repo("users").require(me.user_id)
    from maya.services.access import public_user

    return ok(
        {
            **public_user(user),
            "roles": me.roles,
            "capabilities": me.capabilities,
            "groups": me.groups,
            "channel": me.channel,
            "principal_type": me.principal_type,
        }
    )


@router.post("/auth/password", tags=["auth"])
def change_password(body: s.PasswordIn, me: Principal = Me, plat: Any = Plat) -> Response:
    plat.auth.change_password(me, body.old_password, body.new_password)
    return ok({"ok": True})


@router.get("/auth/api-keys", tags=["auth"])
def list_keys(all: bool = False, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.auth.list_api_keys(me, all_users=all and me.is_admin))


@router.post("/auth/api-keys", tags=["auth"], status_code=201)
def create_key(body: s.ApiKeyIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.auth.create_api_key(me, **body.model_dump()), 201)


@router.delete("/auth/api-keys/{key_id}", tags=["auth"])
def revoke_key(key_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    plat.auth.revoke_api_key(me, key_id)
    return ok({"ok": True})


@router.get("/auth/sessions", tags=["auth"])
def sessions(me: Principal = Me, plat: Any = Plat) -> Response:
    _admin(me)
    return ok(plat.auth.list_sessions())


@router.delete("/auth/sessions/{session_id}", tags=["auth"])
def end_session(session_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    _admin(me)
    plat.auth.terminate_session(me, session_id)
    return ok({"ok": True})


def _admin(me: Principal) -> None:
    if not me.is_admin:
        raise PermissionDenied("Administrators only")


# -- users, roles, groups --------------------------------------------------------------
@router.get("/users", tags=["admin"])
def users(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.access.list_users(me))


@router.post("/users", tags=["admin"], status_code=201)
def create_user(body: s.UserIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.access.create_user(me, **body.model_dump()), 201)


@router.patch("/users/{username}", tags=["admin"])
def update_user(
    username: str, body: dict[str, Any], me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(plat.access.update_user(me, username, body))


@router.put("/users/{username}/roles", tags=["admin"])
def set_roles(username: str, body: s.RolesIn, me: Principal = Me, plat: Any = Plat) -> Response:
    plat.access.set_roles(me, username, body.roles)
    return ok({"ok": True})


@router.post("/users/{username}/password-reset", tags=["admin"])
def reset_password(
    username: str, body: s.ResetIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    plat.access.reset_password(me, username, body.new_password)
    return ok({"ok": True})


@router.get("/roles", tags=["admin"])
def roles(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.access.list_roles())


@router.post("/roles", tags=["admin"], status_code=201)
def create_role(body: s.RoleIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.access.create_role(me, body.name, body.description, body.capabilities), 201)


@router.get("/groups", tags=["admin"])
def groups(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.access.list_groups())


@router.post("/groups", tags=["admin"], status_code=201)
def create_group(body: s.GroupIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(
        plat.access.create_group(me, body.name, body.description, body.roles, body.members), 201
    )


# -- namespaces and grants ---------------------------------------------------------------
@router.get("/namespaces", tags=["access"])
def namespaces(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.access.list_namespaces())


@router.post("/namespaces", tags=["access"], status_code=201)
def create_namespace(body: s.NamespaceIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.access.create_namespace(me, **body.model_dump()), 201)


@router.patch("/namespaces/{name}", tags=["access"])
def update_namespace(
    name: str, body: dict[str, Any], me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(plat.access.update_namespace(me, name, body))


@router.get("/grants", tags=["access"])
def grants(
    kind: str,
    ref: str,
    page_size: int | None = None,
    cursor: str | None = None,
    sort: str | None = None,
    total: bool = False,
    me: Principal = Me,
    plat: Any = Plat,
) -> Response:
    obj = plat.access.resolve_object(kind, ref)
    if page_size is not None or cursor is not None:
        return ok(
            plat.access.grants_page(
                kind, obj["id"], page_size=page_size, cursor=cursor, sort=sort, total=total
            )
        )
    return ok(plat.access.grants_for(kind, obj["id"]))


@router.post("/grants", tags=["access"], status_code=201)
def grant(body: s.GrantIn, me: Principal = Me, plat: Any = Plat) -> Response:
    obj = plat.access.resolve_object(body.kind, body.object_ref)
    return ok(
        plat.access.grant(
            me,
            kind=body.kind,
            obj=obj,
            principal_type=body.principal_type,
            principal_id=body.principal_id,
            level=body.level,
            days=body.days,
            deny=body.deny,
            conditions=body.conditions,
        ),
        201,
    )


@router.delete("/grants/{grant_id}", tags=["access"])
def revoke_grant(grant_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    plat.access.revoke_grant(me, grant_id)
    return ok({"ok": True})


@router.get("/access/recertification", tags=["access"])
def recertification(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.access.recertification(me))


# -- audit, inbox, search --------------------------------------------------------------
@router.get("/audit", tags=["audit"])
def audit(
    q: str | None = None,
    action: str | None = None,
    limit: int = 1000,
    page_size: int | None = None,
    cursor: str | None = None,
    sort: str | None = None,
    total: bool = False,
    me: Principal = Me,
    plat: Any = Plat,
) -> Response:
    if page_size is not None or cursor is not None:
        return ok(
            plat.access.audit_page(
                me, q=q, action=action, page_size=page_size, cursor=cursor, sort=sort, total=total
            )
        )
    return ok(plat.access.audit_log(me, limit=limit, q=q, action=action))


@router.get("/audit/verify", tags=["audit"])
def audit_verify(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.access.verify_audit())


@router.get("/inbox", tags=["inbox"])
def inbox(
    page_size: int | None = None,
    cursor: str | None = None,
    sort: str | None = None,
    total: bool = False,
    me: Principal = Me,
    plat: Any = Plat,
) -> Response:
    if page_size is not None or cursor is not None:
        return ok(
            plat.access.inbox_page(me, page_size=page_size, cursor=cursor, sort=sort, total=total)
        )
    return ok(plat.access.inbox(me))


@router.post("/inbox/read", tags=["inbox"])
def mark_read(body: s.ReadIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok({"marked": plat.access.mark_read(me, body.ids)})


@router.get("/search", tags=["catalog"])
def search(q: str, limit: int = 50, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.ops.search(me, q, limit=limit))


@router.post("/search/reindex", tags=["ops"])
def reindex_search(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.ops.reindex_search(me))


@router.get("/lineage", tags=["lineage"])
def lineage(
    root: str, direction: str = "both", depth: int = 3, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(plat.ops.lineage(root, direction=direction, depth=min(depth, 8), p=me))


# -- operations -----------------------------------------------------------------------------
@router.get("/system/health", tags=["ops"])
def system_health(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.ops.health())


@router.get("/system/config", tags=["ops"])
def system_config(me: Principal = Me, plat: Any = Plat) -> Response:
    _admin(me)
    return ok(plat.settings.effective())


@router.post("/system/lake/maintain", tags=["ops"])
def lake_maintain(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.ops.lake_maintenance(me))


@router.get("/system/storage", tags=["ops"])
def storage(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.ops.storage_report())


@router.post("/system/integrity", tags=["ops"])
def integrity(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.ops.verify_integrity(me))


@router.get("/system/estate", tags=["ops"])
def estate(me: Principal = Me, plat: Any = Plat) -> Response:
    _admin(me)
    return Response(
        plat.ops.export_estate(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=estate.mayabundle"},
    )


@router.get("/jobs", tags=["jobs"])
def jobs(
    all: bool = False,
    q: str | None = None,
    page_size: int | None = None,
    cursor: str | None = None,
    sort: str | None = None,
    total: bool = False,
    me: Principal = Me,
    plat: Any = Plat,
) -> Response:
    if page_size is not None or cursor is not None:
        return ok(
            plat.ops.jobs_page(
                me, all_users=all, q=q, page_size=page_size, cursor=cursor, sort=sort, total=total
            )
        )
    return ok(plat.ops.jobs(me, all_users=all))


@router.get("/jobs/{job_id}", tags=["jobs"])
def job(job_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.ops.job(me, job_id))


@router.post("/jobs/{job_id}/cancel", tags=["jobs"])
def cancel_job(job_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.ops.cancel_job(me, job_id))


@router.post("/jobs/{job_id}/retry", tags=["jobs"])
def retry_job(job_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.ops.retry_job(me, job_id))


@router.get("/jobs/{job_id}/events", tags=["jobs"])
async def job_events(job_id: str, me: Principal = Me, plat: Any = Plat) -> StreamingResponse:
    """Server-sent events of a job's progress until it reaches a terminal state."""
    plat.ops.job(me, job_id)

    async def stream() -> Any:
        last = None
        for _ in range(3600):
            job = await asyncio.to_thread(plat.ops.job, me, job_id)
            snap = (job["state"], job["progress"], job["message"])
            if snap != last:
                last = snap
                payload = {k: job[k] for k in ("id", "state", "progress", "message", "error")}
                yield f"data: {json.dumps(payload)}\n\n"
            if job["state"] in ("succeeded", "failed", "cancelled", "dead_letter"):
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/bundles/verify", tags=["warrants"])
async def verify_bundle(
    file: UploadFile = File(...), me: Principal = Me, plat: Any = Plat
) -> Response:
    data = await file.read()
    return ok(await asyncio.to_thread(plat.bundles.verify, data))


@router.get("/blobs/{digest}", tags=["ops"])
def blob(digest: str, me: Principal = Me, plat: Any = Plat) -> Response:
    """A blob this principal exported or uploaded (bundles, estates); audited."""
    return Response(plat.ops.read_blob(me, digest), media_type="application/octet-stream")
