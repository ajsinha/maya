"""
Model, warrant and parameter endpoints (§8, §9, §18.1).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response

from maya.api import schemas as s
from maya.api.deps import Me, Plat, ok, ref_of
from maya.security.authz import Principal

router = APIRouter()


# -- models --------------------------------------------------------------------------
@router.get("/models", tags=["models"])
def list_models(
    namespace: str | None = None,
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
            plat.models.page(
                me,
                namespace=namespace,
                q=q,
                page_size=page_size,
                cursor=cursor,
                sort=sort,
                total=total,
            )
        )
    return ok(plat.models.list(me, namespace=namespace, q=q))


@router.post("/models", tags=["models"], status_code=201)
def create_model(body: s.ModelIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.models.create(me, **body.model_dump()), 201)


@router.get("/models/{namespace}/{name}", tags=["models"])
def get_model(namespace: str, name: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.models.get(me, ref_of("model", namespace, name)))


@router.put("/models/{namespace}/{name}/draft", tags=["models"])
def update_model_draft(
    namespace: str, name: str, body: s.ModelDraftIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(plat.models.update_draft(me, ref_of("model", namespace, name), **body.model_dump()))


@router.post("/models/{namespace}/{name}/drafts", tags=["models"], status_code=201)
def new_model_draft(namespace: str, name: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.models.new_draft(me, ref_of("model", namespace, name)), 201)


@router.post("/models/{namespace}/{name}/artifact", tags=["models"], status_code=202)
def upload_artifact(
    namespace: str, name: str, body: s.ArtifactIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(
        plat.models.upload_artifact(
            me,
            ref_of("model", namespace, name),
            body.source,
            sample=body.sample,
            params=body.params,
        ),
        202,
    )


def _roles_form(roles: str) -> dict[str, str]:
    import json

    from maya.core.errors import ValidationFailed

    try:
        out = json.loads(roles or "{}")
    except json.JSONDecodeError as exc:
        raise ValidationFailed(f"roles is not valid JSON: {exc}") from exc
    if not isinstance(out, dict):
        raise ValidationFailed("roles is a JSON object of input name to role")
    return out


@router.post("/models/workbook/lift", tags=["models"])
async def lift_workbook(
    file: UploadFile = File(...),
    output: str = Form(""),
    roles: str = Form("{}"),
    me: Principal = Me,
    plat: Any = Plat,
) -> Response:
    """Preview the formula IR an Excel workbook lifts to (§29.9). Nothing is stored."""
    data = await file.read()
    return ok(
        await asyncio.to_thread(
            plat.models.lift_workbook,
            data,
            output=output or None,
            roles=_roles_form(roles),
            filename=file.filename or "workbook.xlsx",
        )
    )


@router.post("/models/{namespace}/{name}/workbook", tags=["models"])
async def import_workbook(
    namespace: str,
    name: str,
    file: UploadFile = File(...),
    output: str = Form(""),
    roles: str = Form("{}"),
    me: Principal = Me,
    plat: Any = Plat,
) -> Response:
    """Lift a workbook into the model's editable draft, keeping the workbook itself."""
    data = await file.read()
    return ok(
        await asyncio.to_thread(
            plat.models.import_workbook,
            me,
            ref_of("model", namespace, name),
            data,
            output=output or None,
            roles=_roles_form(roles),
            filename=file.filename or "workbook.xlsx",
        )
    )


@router.get("/models/{namespace}/{name}/versions/{version_no}/workbook.xlsx", tags=["models"])
def workbook(
    namespace: str, name: str, version_no: int, me: Principal = Me, plat: Any = Plat
) -> Response:
    out = plat.models.workbook(me, ref_of("model", namespace, name), version_no)
    return Response(
        out["data"],
        media_type=out["content_type"],
        headers={"Content-Disposition": f'attachment; filename="{out["filename"]}"'},
    )


@router.post("/models/{namespace}/{name}/versions/{version_no}/render", tags=["models"])
async def render_spec(
    namespace: str, name: str, version_no: int, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(
        await asyncio.to_thread(
            plat.models.render_spec, me, ref_of("model", namespace, name), version_no
        )
    )


@router.get("/models/{namespace}/{name}/versions/{version_no}/spec.pdf", tags=["models"])
async def spec_pdf(
    namespace: str, name: str, version_no: int, me: Principal = Me, plat: Any = Plat
) -> Response:
    pdf = await asyncio.to_thread(
        plat.models.spec_pdf, me, ref_of("model", namespace, name), version_no
    )
    return Response(pdf, media_type="application/pdf")


@router.post(
    "/models/{namespace}/{name}/versions/{version_no}/transitions/{transition}", tags=["models"]
)
def model_transition(
    namespace: str,
    name: str,
    version_no: int,
    transition: str,
    body: s.TransitionIn,
    me: Principal = Me,
    plat: Any = Plat,
) -> Response:
    return ok(
        plat.models.transition(
            me,
            ref_of("model", namespace, name),
            version_no,
            transition,
            rationale=body.rationale,
            force=body.force,
            successor=body.successor,
        )
    )


@router.get("/models/{namespace}/{name}/diff", tags=["models"])
def model_diff(
    namespace: str, name: str, v1: int, v2: int, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(plat.models.diff(me, ref_of("model", namespace, name), v1, v2))


@router.get("/models/{namespace}/{name}/versions/{version_no}/reference", tags=["models"])
def reference_code(
    namespace: str, name: str, version_no: int, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(
        {"source": plat.models.reference_code(me, ref_of("model", namespace, name), version_no)}
    )


@router.post("/models/{namespace}/{name}/versions/{version_no}/conformance", tags=["models"])
async def conformance(
    namespace: str, name: str, version_no: int, n: int = 500, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(
        await asyncio.to_thread(
            plat.models.conformance, me, ref_of("model", namespace, name), version_no, n=n
        )
    )


# -- training warrants ---------------------------------------------------------------------
@router.get("/warrants/training", tags=["warrants"])
def list_training(
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
            plat.warrants.page(me, q=q, page_size=page_size, cursor=cursor, sort=sort, total=total)
        )
    return ok(plat.warrants.list(me))


@router.post("/warrants/training", tags=["warrants"], status_code=201)
async def create_training(
    body: s.TrainingWarrantIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(
        await asyncio.to_thread(
            plat.warrants.create,
            me,
            namespace=body.namespace,
            name=body.name,
            model=body.model,
            featureset=body.featureset,
            spec=body.spec,
        ),
        201,
    )


@router.get("/warrants/training/{warrant_id}", tags=["warrants"])
def get_training(warrant_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.warrants.get(me, warrant_id))


@router.get("/warrants/training/{warrant_id}/data", tags=["warrants"])
async def training_data(warrant_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    import json

    result = await asyncio.to_thread(plat.warrants.data, me, warrant_id)
    return Response(
        result["data"],
        media_type="application/vnd.apache.parquet",
        headers={
            "X-Maya-Manifest": json.dumps(result["manifest"], default=str),
            "X-Maya-Checksum": result["manifest"]["checksum"],
        },
    )


@router.post("/warrants/training/{warrant_id}/parameters", tags=["warrants"], status_code=201)
def upload_parameters(
    warrant_id: str, body: s.ParametersIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(plat.warrants.upload_parameters(me, warrant_id, **body.model_dump()), 201)


@router.post("/warrants/training/{warrant_id}/transitions/{transition}", tags=["warrants"])
def training_transition(
    warrant_id: str, transition: str, body: s.TransitionIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(
        plat.warrants.transition(
            me, warrant_id, transition, rationale=body.rationale, force=body.force
        )
    )


@router.post("/warrants/training/{warrant_id}/seal", tags=["warrants"])
def seal_training(warrant_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.warrants.seal(me, warrant_id))


@router.post("/warrants/training/{warrant_id}/revoke", tags=["warrants"])
def revoke_training(
    warrant_id: str, body: s.ReasonIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(plat.warrants.revoke(me, warrant_id, body.reason))


@router.post("/warrants/training/{warrant_id}/clone", tags=["warrants"], status_code=201)
async def clone_training(
    warrant_id: str, body: dict[str, Any], me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(await asyncio.to_thread(plat.warrants.clone, me, warrant_id, body), 201)


@router.post("/warrants/training/{warrant_id}/score", tags=["warrants"])
async def score_holdout(
    warrant_id: str, body: s.ScoreIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(
        await asyncio.to_thread(
            plat.warrants.score_holdout,
            me,
            warrant_id,
            parameter_set_id=body.parameter_set_id,
            values=body.values,
        )
    )


@router.post("/warrants/training/{warrant_id}/bundle", tags=["warrants"], status_code=201)
async def export_bundle(warrant_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(await asyncio.to_thread(plat.bundles.export, me, warrant_id), 201)


@router.post("/parameters/{parameter_set_id}/transitions/{transition}", tags=["warrants"])
def parameter_transition(
    parameter_set_id: str,
    transition: str,
    body: s.TransitionIn,
    me: Principal = Me,
    plat: Any = Plat,
) -> Response:
    return ok(
        plat.warrants.parameter_transition(
            me,
            parameter_set_id,
            transition,
            rationale=body.rationale,
            force=body.force,
            justification=body.justification,
        )
    )


# -- execution warrants ------------------------------------------------------------------------
@router.get("/warrants/execution", tags=["warrants"])
def list_execution(
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
            plat.execution.page(me, q=q, page_size=page_size, cursor=cursor, sort=sort, total=total)
        )
    return ok(plat.execution.list(me))


@router.post("/warrants/execution", tags=["warrants"], status_code=201)
def create_execution(body: s.ExecutionWarrantIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.execution.create(me, **body.model_dump()), 201)


@router.get("/warrants/execution/{ew_id}", tags=["warrants"])
def get_execution(ew_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.execution.get(me, ew_id))


@router.post("/warrants/execution/{ew_id}/transitions/{transition}", tags=["warrants"])
def execution_transition(
    ew_id: str, transition: str, body: s.TransitionIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(
        plat.execution.transition(me, ew_id, transition, rationale=body.rationale, force=body.force)
    )


@router.post("/warrants/execution/{ew_id}/seal", tags=["warrants"])
def seal_execution(ew_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.execution.seal(me, ew_id))


@router.post("/warrants/execution/{ew_id}/token", tags=["warrants"])
def execution_token(ew_id: str, environment: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.execution.token(me, ew_id, environment))


@router.get("/warrants/execution/{ew_id}/bundle", tags=["warrants"])
def execution_bundle(
    ew_id: str, environment: str, offline: bool = False, me: Principal = Me, plat: Any = Plat
) -> Response:
    """What the SDK needs to run the warrant. ``offline=true``: a copy to run without
    MAYA, labelled unattested on the bundle and on the warrant."""
    return ok(plat.execution.bundle(me, ew_id, environment, offline=offline))


@router.post("/warrants/execution/{ew_id}/report", tags=["warrants"])
def execution_report(
    ew_id: str, body: s.ReportIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(plat.execution.report(me, ew_id, **body.model_dump()))


@router.post("/warrants/execution/{ew_id}/reinstate", tags=["warrants"])
def reinstate_execution(
    ew_id: str, body: s.ReasonIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(plat.execution.reinstate(me, ew_id, body.reason))


@router.post("/warrants/execution/{ew_id}/revoke", tags=["warrants"])
def revoke_execution(
    ew_id: str, body: s.ReasonIn, me: Principal = Me, plat: Any = Plat
) -> Response:
    return ok(plat.execution.revoke(me, ew_id, body.reason))
