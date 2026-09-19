"""
Feature and feature set endpoints (§5, §6, §18.1).

Objects are addressed as ``/{namespace}/{name}``; data endpoints take a full
reference in ``ref`` so a version (``@vN``) or a pin (``#series/date``) can be
named exactly.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, File, Form, Header, UploadFile
from fastapi.responses import Response

from maya.api import schemas as s
from maya.api.deps import Me, Plat, ok, parse_date, parse_instant, ref_of
from maya.security.authz import Principal

router = APIRouter()
MEDIA = {"parquet": "application/vnd.apache.parquet", "arrow": "application/vnd.apache.arrow.file",
         "csv": "text/csv", "json": "application/json", "ndjson": "application/x-ndjson"}


def _data_response(result: dict[str, Any], fmt: str, stem: str) -> Response:
    ext = {"arrow": "arrow", "parquet": "parquet", "csv": "csv", "json": "json",
           "ndjson": "ndjson"}[fmt]
    return Response(result["data"], media_type=MEDIA[fmt], headers={
        "Content-Disposition": f"attachment; filename={stem}.{ext}",
        "X-Maya-Manifest": json.dumps(result["manifest"], default=str)})


# -- features --------------------------------------------------------------------------
@router.get("/features", tags=["features"])
def list_features(namespace: str | None = None, q: str | None = None,
                  status: str | None = None, page_size: int | None = None, cursor: str | None = None,
                  sort: str | None = None, total: bool = False, me: Principal = Me,
                  plat: Any = Plat) -> Response:
    """The features you may read. Opt-in cursor paging: pass ``page_size`` or ``cursor``."""
    if page_size is not None or cursor is not None:
        return ok(plat.features.page(me, namespace=namespace, q=q, status=status, page_size=page_size, cursor=cursor, sort=sort, total=total))
    return ok(plat.features.list(me, namespace=namespace, q=q, status=status))


@router.post("/features", tags=["features"], status_code=201)
def create_feature(body: s.DefinitionIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.features.create(me, namespace=body.namespace, name=body.name,
                                   definition=body.definition, description=body.description,
                                   tags=body.tags), 201)


@router.post("/features/infer", tags=["features"])
async def infer_schema(file: UploadFile = File(...), fmt: str = Form("csv"),
                       me: Principal = Me, plat: Any = Plat) -> Response:
    data = await file.read()
    return ok(await asyncio.to_thread(plat.features.infer, data, fmt))


@router.post("/features/quick", tags=["features"], status_code=201)
async def quick_feature(file: UploadFile = File(...), name: str = Form(...),
                        fmt: str = Form("csv"), me: Principal = Me, plat: Any = Plat) -> Response:
    data = await file.read()
    return ok(await asyncio.to_thread(plat.features.quick, me, data, name=name, fmt=fmt), 201)


@router.get("/features/{namespace}/{name}", tags=["features"])
def get_feature(namespace: str, name: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.features.get(me, ref_of("feature", namespace, name)))


@router.put("/features/{namespace}/{name}/draft", tags=["features"])
def update_feature_draft(namespace: str, name: str, body: s.DraftIn, me: Principal = Me,
                         plat: Any = Plat) -> Response:
    return ok(plat.features.update_draft(me, ref_of("feature", namespace, name), body.definition,
                                         expected_version=body.expected_version,
                                         description=body.description, tags=body.tags))


@router.post("/features/{namespace}/{name}/drafts", tags=["features"], status_code=201)
def new_feature_draft(namespace: str, name: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.features.new_draft(me, ref_of("feature", namespace, name)), 201)


@router.post("/features/{namespace}/{name}/clone", tags=["features"], status_code=201)
def clone_feature(namespace: str, name: str, body: s.CloneIn, me: Principal = Me,
                  plat: Any = Plat) -> Response:
    return ok(plat.features.clone(me, ref_of("feature", namespace, name), name=body.name,
                                  namespace=body.namespace, extend=body.extend), 201)


@router.post("/features/{namespace}/{name}/ingest", tags=["features"], status_code=201)
async def ingest_feature(namespace: str, name: str, file: UploadFile = File(...),
                         fmt: str = Form("csv"), knowledge_time: str | None = Form(None),
                         note: str = Form(""), me: Principal = Me, plat: Any = Plat) -> Response:
    data = await file.read()
    kt = parse_instant(knowledge_time, "knowledge_time")
    result = await asyncio.to_thread(plat.features.ingest, me, ref_of("feature", namespace, name),
                                     data, fmt=fmt, filename=file.filename or "",
                                     knowledge_time=kt, note=note)
    return ok(result, 201)


@router.post("/features/{namespace}/{name}/pull", tags=["features"], status_code=201)
async def pull_feature(namespace: str, name: str, body: s.PullIn, me: Principal = Me,
                       plat: Any = Plat) -> Response:
    """Snapshot an sql-sourced feature's reviewed query into its ingest log."""
    kt = parse_instant(body.knowledge_time, "knowledge_time")
    return ok(await asyncio.to_thread(plat.sources.pull, me, ref_of("feature", namespace, name),
                                      knowledge_time=kt), 201)


@router.get("/sql-connections", tags=["sources"])
def connections(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.sources.list())


@router.post("/sql-connections", tags=["sources"], status_code=201)
def create_connection(body: s.ConnectionIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.sources.create(me, **body.model_dump()), 201)


@router.delete("/sql-connections/{name}", tags=["sources"])
def delete_connection(name: str, me: Principal = Me, plat: Any = Plat) -> Response:
    plat.sources.delete(me, name)
    return ok({"ok": True})


@router.post("/sql-connections/{name}/test", tags=["sources"])
async def test_connection(name: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(await asyncio.to_thread(plat.sources.test, me, name))


@router.post("/features/{namespace}/{name}/versions/{version_no}/transitions/{transition}",
             tags=["features"])
def feature_transition(namespace: str, name: str, version_no: int, transition: str,
                       body: s.TransitionIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.features.transition(me, ref_of("feature", namespace, name), version_no,
                                       transition, rationale=body.rationale, force=body.force))


@router.get("/features/{namespace}/{name}/compare", tags=["features"])
def compare_feature(namespace: str, name: str, v1: int, v2: int, me: Principal = Me,
                    plat: Any = Plat) -> Response:
    return ok(plat.features.compare(me, ref_of("feature", namespace, name), v1, v2))


@router.post("/features/{namespace}/{name}/draft-preview", tags=["features"])
def feature_draft_preview(namespace: str, name: str, as_of_known: str | None = None,
                          me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.features.draft_preview(me, ref_of("feature", namespace, name),
                                          as_of_known=parse_instant(as_of_known, "as_of_known")))


@router.post("/features/{namespace}/{name}/pins", tags=["features"], status_code=202)
def pin_feature(namespace: str, name: str, body: s.PinIn, me: Principal = Me, plat: Any = Plat,
                idempotency_key: str | None = Header(default=None)) -> Response:
    return ok(plat.features.pin(me, ref_of("feature", namespace, name),
                                version_no=body.version_no, pin_name=body.pin_name,
                                as_of=parse_date(body.as_of, "as_of"),
                                as_of_known=parse_instant(body.as_of_known, "as_of_known"),
                                idempotency_key=idempotency_key), 202)


@router.post("/pins/{pin_id}/approve", tags=["features"], status_code=202)
def approve_pin(pin_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.features.approve_pin_request(me, pin_id), 202)


@router.post("/pins/{pin_id}/retire", tags=["features"])
def retire_pin(pin_id: str, body: s.ReasonIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.features.retire_pin(me, pin_id, body.reason))


@router.get("/feature-data/preview", tags=["features"])
def feature_preview(ref: str, as_of_known: str | None = None, start: str | None = None,
                    end: str | None = None, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.features.preview(me, ref, as_of_known=parse_instant(as_of_known, "as_of_known"),
                                    start=parse_date(start, "start"), end=parse_date(end, "end")))


@router.get("/feature-data", tags=["features"])
def feature_data(ref: str, format: str = "parquet", csv_encoding: str | None = None,
                 as_of_known: str | None = None, me: Principal = Me, plat: Any = Plat) -> Response:
    result = plat.features.download(me, ref, fmt=format, csv_encoding=csv_encoding,
                                    as_of_known=parse_instant(as_of_known, "as_of_known"))
    return _data_response(result, format, "feature")


# -- feature sets -------------------------------------------------------------------------
@router.get("/featuresets", tags=["featuresets"])
def list_featuresets(namespace: str | None = None, q: str | None = None,
                     page_size: int | None = None, cursor: str | None = None,
                  sort: str | None = None, total: bool = False, me: Principal = Me, plat: Any = Plat) -> Response:
    if page_size is not None or cursor is not None:
        return ok(plat.featuresets.page(me, namespace=namespace, q=q, page_size=page_size, cursor=cursor, sort=sort, total=total))
    return ok(plat.featuresets.list(me, namespace=namespace, q=q))


@router.post("/featuresets", tags=["featuresets"], status_code=201)
def create_featureset(body: s.DefinitionIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.featuresets.create(me, namespace=body.namespace, name=body.name,
                                      definition=body.definition, description=body.description,
                                      tags=body.tags), 201)


@router.get("/featuresets/{namespace}/{name}", tags=["featuresets"])
def get_featureset(namespace: str, name: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.featuresets.get(me, ref_of("featureset", namespace, name)))


@router.put("/featuresets/{namespace}/{name}/draft", tags=["featuresets"])
def update_featureset_draft(namespace: str, name: str, body: s.DraftIn, me: Principal = Me,
                            plat: Any = Plat) -> Response:
    return ok(plat.featuresets.update_draft(me, ref_of("featureset", namespace, name),
                                            body.definition, expected_version=body.expected_version))


@router.post("/featuresets/{namespace}/{name}/drafts", tags=["featuresets"], status_code=201)
def new_featureset_draft(namespace: str, name: str, me: Principal = Me,
                         plat: Any = Plat) -> Response:
    return ok(plat.featuresets.new_draft(me, ref_of("featureset", namespace, name)), 201)


@router.post("/featuresets/{namespace}/{name}/versions/{version_no}/transitions/{transition}",
             tags=["featuresets"])
def featureset_transition(namespace: str, name: str, version_no: int, transition: str,
                          body: s.TransitionIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.featuresets.transition(me, ref_of("featureset", namespace, name), version_no,
                                          transition, rationale=body.rationale, force=body.force))


@router.post("/featuresets/{namespace}/{name}/draft-preview", tags=["featuresets"])
def featureset_draft_preview(namespace: str, name: str, me: Principal = Me,
                             plat: Any = Plat) -> Response:
    return ok(plat.featuresets.draft_preview(me, ref_of("featureset", namespace, name)))


@router.post("/featuresets/{namespace}/{name}/pins", tags=["featuresets"], status_code=202)
def pin_featureset(namespace: str, name: str, body: s.PinIn, me: Principal = Me,
                   plat: Any = Plat, idempotency_key: str | None = Header(default=None)
                   ) -> Response:
    return ok(plat.featuresets.pin(me, ref_of("featureset", namespace, name),
                                   version_no=body.version_no, pin_name=body.pin_name,
                                   as_of=parse_date(body.as_of, "as_of"),
                                   as_of_known=parse_instant(body.as_of_known, "as_of_known"),
                                   cascade=body.cascade, idempotency_key=idempotency_key), 202)


@router.get("/featureset-data/preview", tags=["featuresets"])
def featureset_preview(ref: str, as_of_known: str | None = None, me: Principal = Me,
                       plat: Any = Plat) -> Response:
    return ok(plat.featuresets.preview(me, ref,
                                       as_of_known=parse_instant(as_of_known, "as_of_known")))


@router.get("/featureset-data", tags=["featuresets"])
def featureset_data(ref: str, format: str = "parquet", shape: str = "tabular",
                    csv_encoding: str | None = None, me: Principal = Me,
                    plat: Any = Plat) -> Response:
    result = plat.featuresets.download(me, ref, fmt=format, shape=shape,
                                       csv_encoding=csv_encoding)
    return _data_response(result, format, "featureset")
