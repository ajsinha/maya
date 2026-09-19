"""
Catalog screens (§16.2): features and feature sets — lists and object pages
with the five tabs (Overview, Definition, Data, Lineage, History & Comments),
transitions, pins, previews, downloads and version comparison.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from maya.core.errors import MayaError
from maya.web.routes.common import (action, client, download, flash, form, is_admin, page,
                                    render)

router = APIRouter()


def _ref(kind: str, ns: str, name: str) -> str:
    return f"maya://{kind}/{ns}/{name}"


async def _preview(fetch: Any) -> tuple[Any, str | None]:
    try:
        return await fetch, None
    except MayaError as exc:
        return None, f"{type(exc).__name__}: {exc.message}"


# -- features ----------------------------------------------------------------------
@router.get("/catalog/features")
@page
async def features(request: Request) -> Any:
    qp = request.query_params
    async with client(request) as sdk:
        rows = await sdk.features.list(namespace=qp.get("namespace") or None,
                                       q=qp.get("q") or None)
        namespaces = await sdk.namespaces.list()
    return await render(request, "catalog/features.html",
                        {"rows": rows, "namespaces": namespaces, "ns": qp.get("namespace", "")})


@router.get("/catalog/features/{ns}/{name}")
@page
async def feature(request: Request, ns: str, name: str) -> Any:
    ref = _ref("feature", ns, name)
    qp = request.query_params
    async with client(request) as sdk:
        f = await sdk.features.get(ref)
        latest = f["versions"][0] if f["versions"] else None
        history, comments = [], []
        if latest:
            history = await sdk.workflow.history("feature_version", latest["id"])
            comments = await sdk.workflow.comments("feature_version", latest["id"])
        approved = [v for v in f["versions"] if v["state"] in ("approved", "published")]
        data_ref = qp.get("ref") or (f"{ref}@v{approved[0]['version_no']}" if approved else "")
        preview, preview_error = (None, None)
        if data_ref:
            preview, preview_error = await _preview(sdk.features.preview(
                data_ref, as_of_known=qp.get("as_of_known") or None))
    lineage_root = f"{ref}@v{latest['version_no']}" if latest else ref
    return await render(request, "catalog/feature.html", {
        "f": f, "latest": latest, "history": history, "comments": comments,
        "data_ref": data_ref, "preview": preview, "preview_error": preview_error,
        "as_of_known": qp.get("as_of_known", ""), "root": lineage_root, "direction": "both",
        "depth": "3", "is_admin": is_admin(request), "job_id": qp.get("job"),
        "tab": qp.get("tab", "overview")})


@router.post("/catalog/features/{ns}/{name}/transition")
@action
async def feature_transition(request: Request, ns: str, name: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.features.transition(
            _ref("feature", ns, name), int(data["version_no"]), data["transition"],
            rationale=data.get("rationale") or None, force=bool(data.get("force")))
    flash(request, out["message"], "success" if out["moved"] else "info")
    return RedirectResponse(f"/catalog/features/{ns}/{name}", status_code=303)


@router.post("/catalog/features/{ns}/{name}/pin")
@action
async def feature_pin(request: Request, ns: str, name: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.features.pin(_ref("feature", ns, name), int(data["version_no"]),
                                     data["pin_name"], data["as_of"],
                                     as_of_known=data.get("as_of_known") or None,
                                     idempotency_key=data.get("idempotency_key") or None)
    if out.get("job"):
        flash(request, "Pin job queued: resolving, checking quality, writing fragments.", "info")
        return RedirectResponse(f"/catalog/features/{ns}/{name}?tab=pins&job={out['job']['id']}",
                                status_code=303)
    flash(request, "Pin requested: a feature manager must approve it.", "info")
    return RedirectResponse(f"/catalog/features/{ns}/{name}?tab=pins", status_code=303)


@router.post("/catalog/pins/{pin_id}/approve")
@action
async def pin_approve(request: Request, pin_id: str) -> Any:
    async with client(request) as sdk:
        await sdk.features.approve_pin(pin_id)
    flash(request, "Pin approved; materialization queued.", "success")
    return RedirectResponse(request.headers.get("referer", "/"), status_code=303)


@router.post("/catalog/pins/{pin_id}/retire")
@action
async def pin_retire(request: Request, pin_id: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        await sdk.features.retire_pin(pin_id, data.get("reason", ""))
    flash(request, "Pin retired: hidden from pickers, still resolvable for audit.", "success")
    return RedirectResponse(request.headers.get("referer", "/"), status_code=303)


@router.post("/catalog/features/{ns}/{name}/new-draft")
@action
async def feature_new_draft(request: Request, ns: str, name: str) -> Any:
    async with client(request) as sdk:
        v = await sdk.features.new_draft(_ref("feature", ns, name))
    flash(request, f"Draft v{v['version_no']} is open for editing.", "success")
    return RedirectResponse(f"/workbench/features/{ns}/{name}/edit", status_code=303)


@router.post("/catalog/features/{ns}/{name}/clone")
@action
async def feature_clone(request: Request, ns: str, name: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        await sdk.features.clone(_ref("feature", ns, name), data["new_name"],
                                 namespace=data.get("namespace") or None,
                                 extend=bool(data.get("extend")))
    target = data.get("namespace") or ns
    return RedirectResponse(f"/catalog/features/{target}/{data['new_name']}", status_code=303)


@router.post("/catalog/comment")
@action
async def comment(request: Request) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        await sdk.workflow.comment(data["object_type"], data["object_id"], data.get("body", ""),
                                   blocking=bool(data.get("blocking")))
    flash(request, "Comment added.", "success")
    return RedirectResponse(request.headers.get("referer", "/"), status_code=303)


@router.post("/catalog/comments/{comment_id}/resolve")
@action
async def resolve_comment(request: Request, comment_id: str) -> Any:
    async with client(request) as sdk:
        await sdk.workflow.resolve_comment(comment_id)
    return RedirectResponse(request.headers.get("referer", "/"), status_code=303)


@router.get("/catalog/download")
@page
async def data_download(request: Request) -> Any:
    qp = request.query_params
    fmt = qp.get("format", "parquet")
    kind = qp.get("kind", "feature")
    async with client(request) as sdk:
        if kind == "featureset":
            result = await sdk.featuresets.download(qp["ref"], format=fmt,
                                                    shape=qp.get("shape", "tabular"),
                                                    csv_encoding=qp.get("csv_encoding") or None)
        else:
            result = await sdk.features.download(qp["ref"], format=fmt,
                                                 csv_encoding=qp.get("csv_encoding") or None,
                                                 as_of_known=qp.get("as_of_known") or None)
    stem = qp["ref"].replace("maya://", "").replace("/", "_").replace("#", "_").replace("@", "_")
    return download(result, f"{stem}.{fmt}")


@router.get("/catalog/features/{ns}/{name}/compare")
@page
async def feature_compare(request: Request, ns: str, name: str) -> Any:
    qp = request.query_params
    async with client(request) as sdk:
        f = await sdk.features.get(_ref("feature", ns, name))
        result = None
        if qp.get("v1") and qp.get("v2"):
            result = await sdk.features.compare(_ref("feature", ns, name), int(qp["v1"]),
                                                int(qp["v2"]))
    return await render(request, "catalog/compare.html",
                        {"f": f, "result": result, "v1": qp.get("v1", ""), "v2": qp.get("v2", "")})


# -- feature sets -----------------------------------------------------------------------
@router.get("/catalog/featuresets")
@page
async def featuresets(request: Request) -> Any:
    async with client(request) as sdk:
        rows = await sdk.featuresets.list(q=request.query_params.get("q") or None)
    return await render(request, "catalog/featuresets.html", {"rows": rows})


@router.get("/catalog/featuresets/{ns}/{name}")
@page
async def featureset(request: Request, ns: str, name: str) -> Any:
    ref = _ref("featureset", ns, name)
    qp = request.query_params
    async with client(request) as sdk:
        fs = await sdk.featuresets.get(ref)
        latest = fs["versions"][0] if fs["versions"] else None
        history = await sdk.workflow.history("featureset_version", latest["id"]) if latest else []
        comments = await sdk.workflow.comments("featureset_version", latest["id"]) if latest else []
        approved = [v for v in fs["versions"] if v["state"] in ("approved", "published")]
        data_ref = qp.get("ref") or (f"{ref}@v{approved[0]['version_no']}" if approved else "")
        preview, preview_error = (None, None)
        if data_ref:
            preview, preview_error = await _preview(sdk.featuresets.preview(data_ref))
    return await render(request, "catalog/featureset.html", {
        "fs": fs, "latest": latest, "history": history, "comments": comments,
        "data_ref": data_ref, "preview": preview, "preview_error": preview_error,
        "root": f"{ref}@v{latest['version_no']}" if latest else ref, "direction": "both",
        "depth": "3", "is_admin": is_admin(request), "job_id": qp.get("job"),
        "tab": qp.get("tab", "overview")})


@router.post("/catalog/featuresets/{ns}/{name}/transition")
@action
async def featureset_transition(request: Request, ns: str, name: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.featuresets.transition(
            _ref("featureset", ns, name), int(data["version_no"]), data["transition"],
            rationale=data.get("rationale") or None, force=bool(data.get("force")))
    flash(request, out["message"], "success" if out["moved"] else "info")
    return RedirectResponse(f"/catalog/featuresets/{ns}/{name}", status_code=303)


@router.post("/catalog/featuresets/{ns}/{name}/pin")
@action
async def featureset_pin(request: Request, ns: str, name: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.featuresets.pin(_ref("featureset", ns, name), int(data["version_no"]),
                                        data["pin_name"], data["as_of"],
                                        cascade=bool(data.get("cascade")),
                                        as_of_known=data.get("as_of_known") or None)
    flash(request, "Feature set pin queued" + (" with cascade over its members." if
                                              data.get("cascade") else "."), "info")
    return RedirectResponse(f"/catalog/featuresets/{ns}/{name}?tab=pins&job={out['job']['id']}",
                            status_code=303)


@router.post("/catalog/featuresets/{ns}/{name}/new-draft")
@action
async def featureset_new_draft(request: Request, ns: str, name: str) -> Any:
    async with client(request) as sdk:
        await sdk.featuresets.new_draft(_ref("featureset", ns, name))
    return RedirectResponse(f"/workbench/featuresets/{ns}/{name}/edit", status_code=303)
