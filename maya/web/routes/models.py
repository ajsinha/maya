"""
Models (§8, §16.2, §17): list, create, the model page (formula rendered with
KaTeX, input contract, maturity, spec-document editor with live preview and
PDF render, Python artifact editor with the six-rung validation ladder,
reference code, conformance run, parameter sets) and the mathematical diff.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from maya.core.errors import MayaError
from maya.web.routes.common import (action, client, download, flash, form, is_admin, page,
                                    parse_json, render)

router = APIRouter()
KINDS = ["formula", "black_box", "composite", "vendor"]
MATURITIES = ["experimental", "candidate", "approved", "restricted", "deprecated", "retired"]


def _roles(text: str) -> dict[str, str]:
    """``name: role`` lines → the roles map parse_model takes."""
    out = {}
    for line in (text or "").splitlines():
        if ":" in line:
            name, role = line.split(":", 1)
            if name.strip():
                out[name.strip()] = role.strip() or "feature"
    return out


def _source_fields(data: dict[str, Any]) -> dict[str, Any]:
    mode = data.get("authoring", "formula")
    if mode == "formula" and data.get("formula", "").strip():
        return {"formula": data["formula"], "roles": _roles(data.get("roles", ""))}
    if mode == "python" and data.get("python_source", "").strip():
        return {"python_source": data["python_source"]}
    if mode == "ir" and data.get("ir", "").strip():
        return {"ir": parse_json(data["ir"], "Formula IR")}
    return {}


@router.get("/models")
@page
async def models(request: Request) -> Any:
    async with client(request) as sdk:
        rows = await sdk.models.list(q=request.query_params.get("q") or None)
    return await render(request, "models/list.html", {"rows": rows})


@router.get("/models/new")
@page
async def new_model(request: Request) -> Any:
    async with client(request) as sdk:
        namespaces = await sdk.namespaces.list()
    return await render(request, "models/new.html", {"namespaces": namespaces, "kinds": KINDS})


@router.post("/models/new")
@action
async def create_model(request: Request) -> Any:
    data = await form(request)
    upload = data.get("workbook") if data.get("authoring") == "workbook" else None
    workbook = await upload.read() if upload is not None and hasattr(upload, "read") else b""
    if data.get("authoring") == "workbook" and not workbook:
        flash(request, "Choose an .xlsx workbook to lift.", "danger")
        return RedirectResponse("/models/new", status_code=303)
    ref = f"{data['namespace']}/{data['name']}"
    async with client(request) as sdk:
        await sdk.models.create(data["namespace"], data["name"], kind=data.get("kind", "formula"),
                                description=data.get("description", ""), **_source_fields(data),
                                vendor=parse_json(data.get("vendor"), "Vendor details", {}))
        if workbook:
            out = await sdk.models.import_workbook(
                ref, workbook, output=data.get("workbook_output") or None,
                roles=_roles(data.get("workbook_roles", "")), filename=upload.filename)
            check = out["workbook"]["check"]
            flash(request, f"Model created from {upload.filename}. {check['statement']}",
                  "danger" if check["status"] == "disagreed" else
                  "warning" if check["status"] == "unchecked" else "success")
            return RedirectResponse(f"/models/{ref}?tab=definition", status_code=303)
    flash(request, "Model created as draft v1 with a firm-standard specification document.",
          "success")
    return RedirectResponse(f"/models/{data['namespace']}/{data['name']}", status_code=303)


@router.post("/models/{ns}/{name}/workbook")
@action
async def import_workbook(request: Request, ns: str, name: str) -> Any:
    data = await form(request)
    upload = data.get("workbook")
    workbook = await upload.read() if upload is not None and hasattr(upload, "read") else b""
    if not workbook:
        flash(request, "Choose an .xlsx workbook to lift.", "danger")
        return RedirectResponse(f"/models/{ns}/{name}?tab=definition", status_code=303)
    async with client(request) as sdk:
        out = await sdk.models.import_workbook(f"{ns}/{name}", workbook,
                                               output=data.get("workbook_output") or None,
                                               roles=_roles(data.get("workbook_roles", "")),
                                               filename=upload.filename)
    check = out["workbook"]["check"]
    flash(request, f"Lifted {upload.filename}. {check['statement']}",
          "danger" if check["status"] == "disagreed" else
          "warning" if check["status"] == "unchecked" else "success")
    return RedirectResponse(f"/models/{ns}/{name}?tab=definition", status_code=303)


@router.get("/models/{ns}/{name}/versions/{version_no}/workbook.xlsx")
@page
async def workbook_download(request: Request, ns: str, name: str, version_no: int) -> Any:
    async with client(request) as sdk:
        result = await sdk.models.workbook(f"{ns}/{name}", version_no)
    return download(result, f"{name}-v{version_no}.xlsx")


@router.get("/models/{ns}/{name}")
@page
async def model(request: Request, ns: str, name: str) -> Any:
    qp = request.query_params
    async with client(request) as sdk:
        m = await sdk.models.get(f"{ns}/{name}")
        versions = m["versions"]
        v = next((x for x in versions if str(x["version_no"]) == qp.get("v")), None) or \
            (versions[0] if versions else None)
        reference, history, comments = None, [], []
        if v:
            history = await sdk.workflow.history("model_version", v["id"])
            comments = await sdk.workflow.comments("model_version", v["id"])
            if (v.get("formula_ir") or {}).get("body"):
                try:
                    reference = (await sdk.models.reference_code(f"{ns}/{name}",
                                                                 v["version_no"]))["source"]
                except MayaError:
                    reference = None
    return await render(request, "models/model.html", {
        "m": m, "v": v, "reference": reference, "history": history, "comments": comments,
        "maturities": MATURITIES, "is_admin": is_admin(request), "tab": qp.get("tab", "overview"),
        "job_id": qp.get("job"), "root": f"maya://model/{ns}/{name}@v{v['version_no']}" if v
        else "", "direction": "both", "depth": "3",
        "editable": bool(v and v["state"] in ("draft", "changes_requested"))})


@router.post("/models/{ns}/{name}/formula")
@action
async def save_formula(request: Request, ns: str, name: str) -> Any:
    data = await form(request)
    fields = _source_fields(data)
    if data.get("maturity"):
        fields["maturity"] = data["maturity"]
    async with client(request) as sdk:
        await sdk.models.update_draft(f"{ns}/{name}", **fields)
    flash(request, "Draft saved. The formula below is rendered from the stored IR.", "success")
    return RedirectResponse(f"/models/{ns}/{name}?tab=definition", status_code=303)


@router.post("/models/{ns}/{name}/spec")
@action
async def save_spec(request: Request, ns: str, name: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        await sdk.models.update_draft(f"{ns}/{name}", spec_latex=data.get("spec_latex", ""))
    flash(request, "Specification document saved.", "success")
    return RedirectResponse(f"/models/{ns}/{name}?tab=spec", status_code=303)


@router.post("/models/{ns}/{name}/render/{version_no}")
@action
async def render_spec(request: Request, ns: str, name: str, version_no: int) -> Any:
    async with client(request) as sdk:
        out = await sdk.models.render_spec(f"{ns}/{name}", version_no)
    if out.get("draft_render"):
        flash(request, "DRAFT RENDER: Tectonic is not available, so this PDF is MAYA's structural "
                       "draft, watermarked on every page and refused wherever the PDF is evidence.",
              "warning")
    else:
        flash(request, "PDF built with Tectonic — a true LaTeX build.", "success")
    return RedirectResponse(f"/models/{ns}/{name}?tab=spec&v={version_no}", status_code=303)


@router.get("/models/{ns}/{name}/spec/{version_no}.pdf")
@page
async def spec_pdf(request: Request, ns: str, name: str, version_no: int) -> Any:
    async with client(request) as sdk:
        result = await sdk.models.spec_pdf(f"{ns}/{name}", version_no)
    return download({**result, "content_type": "application/pdf"},
                    f"{name}-v{version_no}-spec.pdf")


@router.post("/models/{ns}/{name}/artifact")
@action
async def upload_artifact(request: Request, ns: str, name: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.models.upload_artifact(f"{ns}/{name}", data.get("source", ""),
                                               sample=parse_json(data.get("sample"), "Sample"),
                                               params=parse_json(data.get("params"), "Params"))
    flash(request, "Artifact stored by hash; the validation ladder is running in the sandbox.",
          "info")
    return RedirectResponse(f"/models/{ns}/{name}?tab=code&job={out['job']['id']}",
                            status_code=303)


@router.post("/models/{ns}/{name}/transition")
@action
async def transition(request: Request, ns: str, name: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.models.transition(f"{ns}/{name}", int(data["version_no"]),
                                          data["transition"], rationale=data.get("rationale") or
                                          None, force=bool(data.get("force")),
                                          successor=data.get("successor") or None)
    flash(request, out["message"], "success" if out["moved"] else "info")
    return RedirectResponse(f"/models/{ns}/{name}", status_code=303)


@router.post("/models/{ns}/{name}/new-draft")
@action
async def new_draft(request: Request, ns: str, name: str) -> Any:
    async with client(request) as sdk:
        v = await sdk.models.new_draft(f"{ns}/{name}")
    flash(request, f"Draft v{v['version_no']} opened.", "success")
    return RedirectResponse(f"/models/{ns}/{name}?v={v['version_no']}&tab=definition",
                            status_code=303)


@router.post("/models/{ns}/{name}/conformance/{version_no}")
@action
async def conformance(request: Request, ns: str, name: str, version_no: int) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        result = await sdk.models.conformance(f"{ns}/{name}", version_no,
                                              n=int(data.get("n") or 500))
    return await render(request, "models/conformance.html",
                        {"result": result, "ns": ns, "name": name, "version_no": version_no})


@router.get("/models/{ns}/{name}/diff")
@page
async def diff(request: Request, ns: str, name: str) -> Any:
    qp = request.query_params
    async with client(request) as sdk:
        m = await sdk.models.get(f"{ns}/{name}")
        result = None
        if qp.get("v1") and qp.get("v2"):
            result = await sdk.models.diff(f"{ns}/{name}", int(qp["v1"]), int(qp["v2"]))
    return await render(request, "models/diff.html",
                        {"m": m, "result": result, "v1": qp.get("v1", ""), "v2": qp.get("v2", "")})
