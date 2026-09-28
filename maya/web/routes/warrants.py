"""
Warrants (§9, §16.2): training warrants (contract report, leakage
certificate, custody chain, checksummed data download, parameter upload,
blind holdout scoring, seal/revoke/clone, reproducibility bundle), bundle
verification, and execution warrants as live instruments (token, reported
executions and covenant breaches, reinstate/revoke).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from maya.core.errors import ValidationFailed
from maya.web.routes.common import (
    action,
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


def _float(data: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(data.get(key) or default)
    except ValueError as exc:
        raise ValidationFailed(f"'{key}' must be a number") from exc


@router.get("/warrants")
@page
async def warrants(request: Request) -> Any:
    async with client(request) as sdk:
        training = await sdk.training.list()
        execution = await sdk.execution.list()
    return await render(
        request, "warrants/list.html", {"training": training, "execution": execution}
    )


# -- training warrants -----------------------------------------------------------------
@router.get("/warrants/training/new")
@page
async def training_new(request: Request) -> Any:
    async with client(request) as sdk:
        namespaces = await sdk.namespaces.list()
        models = [
            f"maya://model/{m['namespace']}/{m['name']}@v{m['latest_version']}"
            for m in await sdk.models.list()
            if m["latest_state"] in ("approved", "published")
        ]
        fsets = []
        for s in await sdk.featuresets.list():
            if s["latest_state"] in ("approved", "published"):
                fsets.append(f"{s['ref']}@v{s['latest_version']}")
            if s["pins"]:
                detail = await sdk.featuresets.get(s["ref"])
                fsets += [p["ref"] for p in detail["pins"] if p["state"] == "sealed"]
    return await render(
        request,
        "warrants/training_new.html",
        {"namespaces": namespaces, "models": models, "fsets": fsets},
    )


@router.post("/warrants/training/new")
@action
async def training_create(request: Request) -> Any:
    data = await form(request)
    spec = {
        "split": {
            "train": _float(data, "train", 0.7),
            "validation": _float(data, "validation", 0.15),
            "test": _float(data, "test", 0.15),
        },
        "seed": int(data.get("seed") or 42),
        "target": data.get("target") or None,
        "bindings": parse_json(data.get("bindings"), "Bindings", {}),
        "holdout": data.get("holdout", "escrowed"),
        "shape": data.get("shape") or "tabular",
        "leakage_lag_days": int(data.get("leakage_lag_days") or 1),
        "expiry_days": int(data.get("expiry_days") or 365),
        "allow_non_causal": bool(data.get("allow_non_causal")),
        "non_causal_justification": data.get("non_causal_justification", ""),
        "leakage_justification": data.get("leakage_justification", ""),
        "objective": data.get("objective", ""),
    }
    async with client(request) as sdk:
        w = await sdk.training.create(
            data["namespace"], data["name"], data["model"], data["featureset"], spec
        )
    flash(
        request,
        "Training warrant drawn: contract validated, leakage certificate issued.",
        "success",
    )
    return RedirectResponse(f"/warrants/training/{w['id']}", status_code=303)


@router.get("/warrants/training/{wid}")
@page
async def training(request: Request, wid: str) -> Any:
    async with client(request) as sdk:
        w = await sdk.training.get(wid)
        history = await sdk.workflow.history("training_warrant", wid)
        comments = await sdk.workflow.comments("training_warrant", wid)
        evidence = await sdk.evidence.list(wid)
    return await render(
        request,
        "warrants/training.html",
        {
            "w": w,
            "evidence": evidence,
            "history": history,
            "comments": comments,
            "is_admin": is_admin(request),
            "bundle": request.session.pop("bundle", None),
            "tab": request.query_params.get("tab", "overview"),
            "root": w["uri"],
            "direction": "both",
            "depth": "3",
        },
    )


@router.post("/warrants/training/{wid}/evidence")
@action
async def training_evidence(request: Request, wid: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        row = await sdk.evidence.compute(
            wid,
            parameter_set_id=data.get("parameter_set_id") or None,
            segment=data.get("segment") or None,
            importance=bool(data.get("importance")),
            repeats=int(data.get("repeats") or 5),
        )
    flagged = (row["result"].get("segments") or {}).get("flagged") or []
    note = f" Flagged segments: {', '.join(flagged)}." if flagged else ""
    flash(request, f"Evidence computed; one holdout attempt counted.{note}", "success")
    return RedirectResponse(f"/warrants/training/{wid}?tab=evidence", status_code=303)


@router.post("/warrants/training/{wid}/dispatch")
@action
async def training_dispatch(request: Request, wid: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.evidence.dispatch(
            wid,
            data.get("image", ""),
            data.get("entrypoint") or "python train.py",
            data.get("maya_url") or str(request.base_url).rstrip("/"),
        )
    return await render(request, "warrants/dispatch.html", {"d": out, "wid": wid})


@router.post("/warrants/training/{wid}/refit")
@action
async def training_refit(request: Request, wid: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        row = await sdk.evidence.refit(wid, data.get("parameter_set_id") or None)
    r = row["result"]
    verdict = "agrees with" if r.get("agrees") else "differs from"
    note = f" MAYA's fit {verdict} the parameter set." if "agrees" in r else ""
    flash(
        request,
        f"Reference re-fit: RMSE {r['rmse_maya']:.6g} on {r['rows']} training rows.{note}",
        "success",
    )
    return RedirectResponse(f"/warrants/training/{wid}?tab=evidence", status_code=303)


@router.post("/warrants/training/{wid}/transition")
@action
async def training_transition(request: Request, wid: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.training.transition(
            wid,
            data["transition"],
            rationale=data.get("rationale") or None,
            force=bool(data.get("force")),
        )
    flash(request, out["message"], "success" if out["moved"] else "info")
    return RedirectResponse(f"/warrants/training/{wid}", status_code=303)


@router.post("/warrants/training/{wid}/seal")
@action
async def training_seal(request: Request, wid: str) -> Any:
    async with client(request) as sdk:
        await sdk.training.seal(wid)
    flash(request, "Warrant sealed: immutable, and its referenced objects undeletable.", "success")
    return RedirectResponse(f"/warrants/training/{wid}", status_code=303)


@router.post("/warrants/training/{wid}/revoke")
@action
async def training_revoke(request: Request, wid: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        await sdk.training.revoke(wid, data.get("reason", ""))
    flash(
        request, "Warrant revoked; every execution warrant built on it was revoked too.", "warning"
    )
    return RedirectResponse(f"/warrants/training/{wid}", status_code=303)


@router.post("/warrants/training/{wid}/clone")
@action
async def training_clone(request: Request, wid: str) -> Any:
    data = await form(request)
    changes = parse_json(data.get("changes"), "Changes", {})
    async with client(request) as sdk:
        new = await sdk.training.clone(wid, **changes)
    flash(request, "Cloned into a new draft in the same experiment family.", "success")
    return RedirectResponse(f"/warrants/training/{new['id']}", status_code=303)


@router.get("/warrants/training/{wid}/data")
@page
async def training_data(request: Request, wid: str) -> Any:
    async with client(request) as sdk:
        result = await sdk.training.data(wid)
    return download(result, f"training-{wid[:8]}.parquet")


@router.post("/warrants/training/{wid}/parameters")
@action
async def upload_parameters(request: Request, wid: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        ps = await sdk.training.upload_parameters(
            wid,
            parse_json(data.get("values"), "Parameter values", {}),
            metrics=parse_json(data.get("metrics"), "Metrics", {}),
            data_checksum=data.get("data_checksum") or None,
            name=data.get("name") or None,
            notes=data.get("notes", ""),
            member_alias=data.get("member_alias") or None,
        )
    if ps.get("flag") == "unverified_data":
        flash(
            request,
            "Parameters stored but flagged unverified_data: the checksum does not "
            "match any download MAYA issued for this warrant.",
            "warning",
        )
    else:
        flash(
            request, "Parameters stored; trained on data MAYA issued (checksum matched).", "success"
        )
    return RedirectResponse(f"/warrants/training/{wid}?tab=params", status_code=303)


@router.post("/warrants/parameters/{ps_id}/transition")
@action
async def parameter_transition(request: Request, ps_id: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.training.parameter_transition(
            ps_id,
            data["transition"],
            rationale=data.get("rationale") or None,
            force=bool(data.get("force")),
            justification=data.get("justification") or None,
        )
    flash(request, out["message"], "success" if out["moved"] else "info")
    return RedirectResponse(request.headers.get("referer", "/warrants"), status_code=303)


@router.post("/warrants/training/{wid}/score")
@action
async def score(request: Request, wid: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.training.score_holdout(
            wid,
            parameter_set_id=data.get("parameter_set_id") or None,
            values=parse_json(data.get("values"), "Values"),
        )
    flash(
        request,
        f"Blind score, attempt {out['attempt']}: "
        + ", ".join(
            f"{k}={v:.6g}" if isinstance(v, float) else f"{k}={v}"
            for k, v in out["metrics"].items()
        ),
        "info",
    )
    return RedirectResponse(f"/warrants/training/{wid}?tab=holdout", status_code=303)


@router.post("/warrants/training/{wid}/bundle")
@action
async def export_bundle(request: Request, wid: str) -> Any:
    async with client(request) as sdk:
        out = await sdk.training.export_bundle(wid)
    request.session["bundle"] = {
        "blob": out["blob"],
        "size": out["size"],
        "reexecutable": out["manifest"]["reexecutable"],
        "reason": out["manifest"].get("not_reexecutable_reason"),
    }
    flash(request, "Reproducibility bundle exported and signed.", "success")
    return RedirectResponse(f"/warrants/training/{wid}", status_code=303)


@router.get("/warrants/bundles/{digest}")
@page
async def bundle_download(request: Request, digest: str) -> Any:
    async with client(request) as sdk:
        result = await sdk.admin.blob(digest)
    return download({**result, "content_type": "application/zip"}, f"maya-bundle-{digest[:12]}.zip")


@router.get("/warrants/verify")
@page
async def verify_page(request: Request) -> Any:
    return await render(request, "warrants/verify.html", {"report": None})


@router.post("/warrants/verify")
@action
async def verify(request: Request) -> Any:
    data = await request.form()
    upload = data.get("file")
    if upload is None or not getattr(upload, "filename", ""):
        raise ValidationFailed("Choose a bundle to verify")
    async with client(request) as sdk:
        report = await sdk.training.verify_bundle(await upload.read())
    return await render(request, "warrants/verify.html", {"report": report})


# -- execution warrants ----------------------------------------------------------------
@router.get("/warrants/execution/new")
@page
async def execution_new(request: Request) -> Any:
    async with client(request) as sdk:
        namespaces = await sdk.namespaces.list()
        options = []
        for w in await sdk.training.list():
            detail = await sdk.training.get(w["id"])
            for ps in detail["parameter_sets"]:
                options.append({"warrant": w, "ps": ps})
    return await render(
        request,
        "warrants/execution_new.html",
        {
            "namespaces": namespaces,
            "options": options,
            "preselect": request.query_params.get("training_warrant_id", ""),
        },
    )


@router.post("/warrants/execution/new")
@action
async def execution_create(request: Request) -> Any:
    data = await request.form()
    choice = data.get("choice", "")
    tw, ps = (choice.split("|", 1) + [""])[:2] if choice else (None, None)
    spec = {
        "valid_days": int(data.get("valid_days") or 90),
        "environments": data.getlist("environments") or ["dev"],
        "contact": data.get("contact", ""),
        "limits": {},
        "covenants": parse_json(data.get("covenants"), "Covenants", []),
    }
    async with client(request) as sdk:
        ew = await sdk.execution.create(
            data["namespace"],
            data["name"],
            training_warrant_id=tw or None,
            model=data.get("model") or None,
            parameter_set_id=ps or None,
            spec=spec,
        )
    return RedirectResponse(f"/warrants/execution/{ew['id']}", status_code=303)


@router.get("/warrants/execution/{eid}")
@page
async def execution(request: Request, eid: str) -> Any:
    async with client(request) as sdk:
        ew = await sdk.execution.get(eid)
        batches = await sdk.evidence.batches(eid)
        history = await sdk.workflow.history("execution_warrant", eid)
        comments = await sdk.workflow.comments("execution_warrant", eid)
    return await render(
        request,
        "warrants/execution.html",
        {
            "ew": ew,
            "batches": batches,
            "history": history,
            "comments": comments,
            "is_admin": is_admin(request),
            "token": request.session.pop("ew_token", None),
        },
    )


@router.post("/warrants/execution/{eid}/transition")
@action
async def execution_transition(request: Request, eid: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.execution.transition(
            eid,
            data["transition"],
            rationale=data.get("rationale") or None,
            force=bool(data.get("force")),
        )
    flash(request, out["message"], "success" if out["moved"] else "info")
    return RedirectResponse(f"/warrants/execution/{eid}", status_code=303)


@router.post("/warrants/execution/{eid}/seal")
@action
async def execution_seal(request: Request, eid: str) -> Any:
    async with client(request) as sdk:
        await sdk.execution.seal(eid)
    flash(request, "Execution warrant sealed and live.", "success")
    return RedirectResponse(f"/warrants/execution/{eid}", status_code=303)


@router.post("/warrants/execution/{eid}/token")
@action
async def execution_token(request: Request, eid: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.execution.token(eid, data.get("environment", "dev"))
    request.session["ew_token"] = {"token": out["token"], "claims": out["claims"]}
    return RedirectResponse(f"/warrants/execution/{eid}", status_code=303)


@router.post("/warrants/execution/{eid}/report")
@action
async def execution_report(request: Request, eid: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        out = await sdk.execution.report(
            eid,
            data.get("environment", "dev"),
            int(data.get("rows") or 0),
            input_stats=parse_json(data.get("input_stats"), "Input stats", {}),
            output_stats=parse_json(data.get("output_stats"), "Output stats", {}),
        )
    if out["breaches"]:
        flash(
            request,
            "Covenant breached — the warrant is SUSPENDED: "
            + "; ".join(b["detail"] for b in out["breaches"]),
            "danger",
        )
    else:
        flash(request, "Execution recorded; all covenants hold.", "success")
    return RedirectResponse(f"/warrants/execution/{eid}", status_code=303)


@router.post("/warrants/execution/{eid}/batches")
@action
async def execution_batch(request: Request, eid: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        job = await sdk.evidence.batch_score(eid, data.get("pin", ""), data.get("environment", ""))
    flash(
        request,
        f"Batch queued as job {job['id'][:8]}; its result appears below when it finishes.",
        "success",
    )
    return RedirectResponse(f"/warrants/execution/{eid}", status_code=303)


@router.get("/warrants/execution/{eid}/batches/{job_id}/output")
@page
async def execution_batch_output(request: Request, eid: str, job_id: str) -> Any:
    async with client(request) as sdk:
        result = await sdk.evidence.batch_output(eid, job_id)
    return download(
        {**result, "content_type": "application/vnd.apache.parquet"}, f"batch-{job_id[:8]}.parquet"
    )


@router.post("/warrants/execution/{eid}/reinstate")
@action
async def execution_reinstate(request: Request, eid: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        await sdk.execution.reinstate(eid, data.get("reason", ""))
    flash(request, "Warrant reinstated by an explicit, audited decision.", "success")
    return RedirectResponse(f"/warrants/execution/{eid}", status_code=303)


@router.post("/warrants/execution/{eid}/revoke")
@action
async def execution_revoke(request: Request, eid: str) -> Any:
    data = await form(request)
    async with client(request) as sdk:
        await sdk.execution.revoke(eid, data.get("reason", ""))
    flash(request, "Warrant revoked; every consuming call now fails closed.", "warning")
    return RedirectResponse(f"/warrants/execution/{eid}", status_code=303)


@router.get("/warrants/execution/{eid}/manifest.pdf")
@page
async def execution_manifest(request: Request, eid: str) -> Any:
    """The manifest a person reads, prints or files (§9.2)."""
    async with client(request) as sdk:
        out = await sdk.execution.manifest_pdf(eid)
    return download({**out, "content_type": "application/pdf"}, f"execution-{eid[:8]}-manifest.pdf")


@router.get("/warrants/execution/{eid}/bundle.json")
@page
async def execution_bundle(request: Request, eid: str) -> Any:
    """Everything needed to run the warrant; ``offline=1`` is the unattested copy."""
    import json

    qp = request.query_params
    offline = qp.get("offline") == "1"
    async with client(request) as sdk:
        out = await sdk.execution.bundle(eid, qp.get("environment") or "dev", offline=offline)
    name = f"execution-{eid[:8]}-{'offline-unattested' if offline else 'live'}.json"
    return download(
        {
            "data": json.dumps(out, indent=2, default=str).encode(),
            "content_type": "application/json",
        },
        name,
    )
