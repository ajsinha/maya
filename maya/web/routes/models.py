"""
Models (§8, §16.2, §17): list, create, the model page (formula rendered with
KaTeX, input contract, maturity, spec-document editor with live preview and
PDF render, Python artifact editor with the six-rung validation ladder,
reference code, conformance run, parameter sets) and the mathematical diff.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import difflib
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from maya.core.errors import MayaError
from maya.web.routes.tables import first_page
from maya.web.routes.common import (
    action,
    api_json,
    client,
    download,
    flash,
    form,
    is_admin,
    page,
    parse_json,
    render,
)

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
        page = await first_page(request, sdk, "models", q=request.query_params.get("q") or None)
    return await render(request, "models/list.html", {"page": page})


@router.get("/models/new")
@page
async def new_model(request: Request) -> Any:
    qp = request.query_params
    async with client(request) as sdk:
        namespaces = await sdk.namespaces.list()
    # The kernel wizard hands its work over through the query string rather than a session:
    # what it produces is a draft of two text fields, and a draft nobody has committed to
    # should not outlive the click that carried it here.
    return await render(
        request,
        "models/new.html",
        {
            "namespaces": namespaces,
            "kinds": KINDS,
            "prefill": {
                "formula": qp.get("formula", ""),
                "roles": qp.get("roles", ""),
                "python": qp.get("python", ""),
            },
        },
    )


@router.get("/models/kernel")
@page
async def kernel_wizard(request: Request) -> Any:
    """Design your compute kernel: mathematics in, typed IR and one Python function out."""
    from maya.web.kernel_templates import GROUPS, for_ui

    return await render(request, "models/kernel.html", {"templates": for_ui(), "groups": GROUPS})


@router.post("/ui/kernel")
@api_json
async def kernel_translate(request: Request) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        return await sdk.models.kernel(
            data.get("formula", ""),
            roles=_roles(data.get("roles", "")),
            name=data.get("name") or "compute",
            python_source=data.get("python_source") or None,
        )


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
        await sdk.models.create(
            data["namespace"],
            data["name"],
            kind=data.get("kind", "formula"),
            description=data.get("description", ""),
            **_source_fields(data),
            vendor=parse_json(data.get("vendor"), "Vendor details", {}),
        )
        if workbook:
            out = await sdk.models.import_workbook(
                ref,
                workbook,
                output=data.get("workbook_output") or None,
                roles=_roles(data.get("workbook_roles", "")),
                filename=upload.filename,
            )
            check = out["workbook"]["check"]
            flash(
                request,
                f"Model created from {upload.filename}. {check['statement']}",
                "danger"
                if check["status"] == "disagreed"
                else "warning"
                if check["status"] == "unchecked"
                else "success",
            )
            return RedirectResponse(f"/models/{ref}?tab=definition", status_code=303)
    flash(
        request, "Model created as draft v1 with a firm-standard specification document.", "success"
    )
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
    if data.get("mode") == "preview":  # lift and check, import nothing
        async with client(request) as sdk:
            ir = await sdk.models.lift_workbook(
                workbook,
                output=data.get("workbook_output") or None,
                roles=_roles(data.get("workbook_roles", "")),
                filename=upload.filename,
            )
        check = ir["lifted_from"]["workbook"]["check"]
        inputs = ", ".join(f"{i['name']} ({i['role']})" for i in ir.get("inputs", []))
        flash(
            request,
            f"Preview of {upload.filename}, nothing imported: output "
            f"{ir['outputs'][0]['name']}; inputs {inputs or 'none'}. "
            f"{check['statement']}",
            "danger" if check["status"] == "disagreed" else "info",
        )
        return RedirectResponse(f"/models/{ns}/{name}?tab=definition", status_code=303)
    async with client(request) as sdk:
        out = await sdk.models.import_workbook(
            f"{ns}/{name}",
            workbook,
            output=data.get("workbook_output") or None,
            roles=_roles(data.get("workbook_roles", "")),
            filename=upload.filename,
        )
    check = out["workbook"]["check"]
    flash(
        request,
        f"Lifted {upload.filename}. {check['statement']}",
        "danger"
        if check["status"] == "disagreed"
        else "warning"
        if check["status"] == "unchecked"
        else "success",
    )
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
        v = next((x for x in versions if str(x["version_no"]) == qp.get("v")), None) or (
            versions[0] if versions else None
        )
        reference, history, comments = None, [], []
        if v:
            history = await sdk.workflow.history("model_version", v["id"])
            comments = await sdk.workflow.comments("model_version", v["id"])
            if (v.get("formula_ir") or {}).get("body"):
                try:
                    reference = (await sdk.models.reference_code(f"{ns}/{name}", v["version_no"]))[
                        "source"
                    ]
                except MayaError:
                    reference = None
        impact = await sdk.catalog.dependents(f"maya://model/{ns}/{name}")
        documents = await sdk.documents.list(f"{ns}/{name}")
        templates = await sdk.documents.templates()
        ai = await sdk.ai.status()
    return await render(
        request,
        "models/model.html",
        {
            "documents": documents,
            "doc_templates": templates,
            "ai": ai,
            "impact": impact,
            "m": m,
            "v": v,
            "reference": reference,
            "history": history,
            "comments": comments,
            "maturities": MATURITIES,
            "is_admin": is_admin(request),
            "tab": qp.get("tab", "overview"),
            "job_id": qp.get("job"),
            "root": f"maya://model/{ns}/{name}@v{v['version_no']}" if v else "",
            "direction": "both",
            "depth": "3",
            "editable": bool(v and v["state"] in ("draft", "changes_requested")),
        },
    )


@router.post("/models/{ns}/{name}/documents")
@action
async def generate_document(request: Request, ns: str, name: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        job = await sdk.documents.generate(
            f"{ns}/{name}",
            data.get("kind", "model_card"),
            version_no=int(data["version_no"]) if data.get("version_no") else None,
            template=data.get("template") or None,
            use_ai=bool(data.get("use_ai")),
            profile=data.get("profile") or None,
        )
    flash(
        request,
        f"Generating it as job {job['id'][:8]}; it appears below when it finishes.",
        "success",
    )
    return RedirectResponse(f"/models/{ns}/{name}?tab=documents&job={job['id']}", status_code=303)


@router.get("/models/{ns}/{name}/documents/{doc_id}")
@page
async def view_document(request: Request, ns: str, name: str, doc_id: str) -> Any:
    """The document as a page of its own, drafted sections labelled."""
    from fastapi.responses import HTMLResponse

    async with client(request) as sdk:
        await sdk.documents.get(doc_id)  # read access, and it exists
        out = await sdk.documents.render(doc_id, "html")
    # typeset its maths with the KaTeX MAYA serves (a downloaded copy shows the TeX source)
    data = out["data"]
    page_html = (
        (data.decode("utf-8") if isinstance(data, bytes) else data)
        .replace(
            "</head>", '<link rel="stylesheet" href="/static/vendor/katex/katex.min.css"></head>', 1
        )
        .replace(
            "</body>",
            '<script src="/static/vendor/katex/katex.min.js"></script>'
            '<script src="/static/js/maths.js"></script></body>',
            1,
        )
    )
    return HTMLResponse(page_html)


@router.get("/models/{ns}/{name}/documents/{doc_id}/download")
@page
async def download_document(request: Request, ns: str, name: str, doc_id: str) -> Any:
    fmt = request.query_params.get("format", "pdf")
    async with client(request) as sdk:
        out = await sdk.documents.render(doc_id, fmt)
    return download(out, f"document-{doc_id[:8]}.{fmt}")


@router.post("/models/{ns}/{name}/documents/{doc_id}/delete")
@action
async def delete_document(request: Request, ns: str, name: str, doc_id: str) -> Any:
    async with client(request) as sdk:
        await sdk.documents.delete(doc_id)
    flash(request, "Draft document deleted.", "success")
    return RedirectResponse(f"/models/{ns}/{name}?tab=documents", status_code=303)


@router.post("/models/{ns}/{name}/documents/{doc_id}/approve")
@action
async def approve_document(request: Request, ns: str, name: str, doc_id: str) -> Any:
    async with client(request) as sdk:
        await sdk.documents.approve(doc_id)
    flash(request, "Document approved; its drafted sections now say who reviewed them.", "success")
    return RedirectResponse(f"/models/{ns}/{name}?tab=documents", status_code=303)


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
        flash(
            request,
            "DRAFT RENDER: Tectonic is not available, so this PDF is MAYA's structural "
            "draft, watermarked on every page and refused wherever the PDF is evidence.",
            "warning",
        )
    else:
        flash(request, "PDF built with Tectonic — a true LaTeX build.", "success")
    return RedirectResponse(f"/models/{ns}/{name}?tab=spec&v={version_no}", status_code=303)


@router.get("/models/{ns}/{name}/spec/{version_no}/drafts")
@page
async def spec_drafts(request: Request, ns: str, name: str, version_no: int) -> Any:
    """Drafts for the specification sections nobody has written yet (§29.8)."""
    async with client(request) as sdk:
        drafts = await sdk.assistant.draft_spec(f"{ns}/{name}", version_no)
    return await render(
        request,
        "models/spec_drafts.html",
        {"ref": f"{ns}/{name}", "version_no": version_no, "d": drafts},
    )


@router.get("/models/{ns}/{name}/spec/{version_no}.pdf")
@page
async def spec_pdf(request: Request, ns: str, name: str, version_no: int) -> Any:
    async with client(request) as sdk:
        result = await sdk.models.spec_pdf(f"{ns}/{name}", version_no)
    return download({**result, "content_type": "application/pdf"}, f"{name}-v{version_no}-spec.pdf")


@router.post("/models/{ns}/{name}/artifact")
@action
async def upload_artifact(request: Request, ns: str, name: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.models.upload_artifact(
            f"{ns}/{name}",
            data.get("source", ""),
            sample=parse_json(data.get("sample"), "Sample"),
            params=parse_json(data.get("params"), "Params"),
        )
    flash(
        request, "Artifact stored by hash; the validation ladder is running in the sandbox.", "info"
    )
    return RedirectResponse(f"/models/{ns}/{name}?tab=code&job={out['job']['id']}", status_code=303)


@router.post("/models/{ns}/{name}/transition")
@action
async def transition(request: Request, ns: str, name: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.models.transition(
            f"{ns}/{name}",
            int(data["version_no"]),
            data["transition"],
            rationale=data.get("rationale") or None,
            force=bool(data.get("force")),
            successor=data.get("successor") or None,
        )
    flash(request, out["message"], "success" if out["moved"] else "info")
    return RedirectResponse(f"/models/{ns}/{name}", status_code=303)


@router.post("/models/{ns}/{name}/new-draft")
@action
async def new_draft(request: Request, ns: str, name: str) -> Any:
    async with client(request) as sdk:
        v = await sdk.models.new_draft(f"{ns}/{name}")
    flash(request, f"Draft v{v['version_no']} opened.", "success")
    return RedirectResponse(
        f"/models/{ns}/{name}?v={v['version_no']}&tab=definition", status_code=303
    )


@router.post("/models/{ns}/{name}/conformance/{version_no}")
@action
async def conformance(request: Request, ns: str, name: str, version_no: int) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        result = await sdk.models.conformance(
            f"{ns}/{name}", version_no, n=int(data.get("n") or 500)
        )
    return await render(
        request,
        "models/conformance.html",
        {"result": result, "ns": ns, "name": name, "version_no": version_no},
    )


SPEC_CONTEXT = 2  # lines of unchanged document shown either side of a change


def spec_diff(old: str, new: str, context: int = SPEC_CONTEXT) -> dict[str, Any]:
    """The specification document, side by side (§17.1).

    The model diff the API returns says *whether* the document changed; a reviewer
    needs to see what. The comparison is a line alignment done here, in the web tier,
    over text the SDK already returned with each version — no new endpoint, and no
    second opinion about what the document says. Unchanged stretches are dropped and
    counted rather than paged through.
    """
    a, b = (old or "").splitlines(), (new or "").splitlines()
    aligned: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                aligned.append(_row("same", i1 + k, a[i1 + k], j1 + k, b[j1 + k]))
        elif tag == "replace":
            for k in range(max(i2 - i1, j2 - j1)):
                left = a[i1 + k] if i1 + k < i2 else None
                right = b[j1 + k] if j1 + k < j2 else None
                aligned.append(
                    _row(
                        "changed",
                        i1 + k if left is not None else None,
                        left,
                        j1 + k if right is not None else None,
                        right,
                    )
                )
        elif tag == "delete":
            aligned += [_row("removed", k, a[k], None, None) for k in range(i1, i2)]
        else:
            aligned += [_row("added", None, None, k, b[k]) for k in range(j1, j2)]
    near: set[int] = set()
    for i, row in enumerate(aligned):
        if row["kind"] != "same":
            near.update(range(max(0, i - context), min(len(aligned), i + context + 1)))
    rows = [row for i, row in enumerate(aligned) if i in near]
    changed = sum(1 for row in aligned if row["kind"] != "same")
    return {"rows": rows, "skipped": len(aligned) - len(rows), "changed": changed}


def _row(
    kind: str, left_no: int | None, left: str | None, right_no: int | None, right: str | None
) -> dict[str, Any]:
    return {
        "kind": kind,
        "left_no": None if left_no is None else left_no + 1,
        "left": left,
        "right_no": None if right_no is None else right_no + 1,
        "right": right,
    }


@router.get("/models/{ns}/{name}/diff")
@page
async def diff(request: Request, ns: str, name: str) -> Any:
    qp = request.query_params
    async with client(request) as sdk:
        m = await sdk.models.get(f"{ns}/{name}")
        result = None
        if qp.get("v1") and qp.get("v2"):
            result = await sdk.models.diff(f"{ns}/{name}", int(qp["v1"]), int(qp["v2"]))
    document = None
    if result:
        by_no = {str(v["version_no"]): v for v in m["versions"]}
        old, new = by_no.get(qp["v1"], {}), by_no.get(qp["v2"], {})
        document = spec_diff(old.get("spec_latex") or "", new.get("spec_latex") or "")
    return await render(
        request,
        "models/diff.html",
        {
            "m": m,
            "result": result,
            "document": document,
            "v1": qp.get("v1", ""),
            "v2": qp.get("v2", ""),
        },
    )
