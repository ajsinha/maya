"""
Connectors: models imported from MLflow and SageMaker, lineage exported as OpenLineage.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from maya.api import schemas_governance as s
from maya.api.deps import Me, Plat, ok
from maya.security.authz import Principal

router = APIRouter(tags=["integrations"])


@router.post("/integrations/mlflow/import", status_code=201)
def mlflow_import(body: s.MlflowImportIn, me: Principal = Me, plat: Any = Plat) -> Response:
    """Register a black-box draft from an MLflow ``MLmodel`` file; its signature is the
    input contract and its provenance is sealed into the IR."""
    return ok(plat.integrations.import_mlflow(me, **body.model_dump()), 201)


@router.post("/integrations/mlflow/fetch", status_code=201)
def mlflow_fetch(body: s.MlflowFetchIn, me: Principal = Me, plat: Any = Plat) -> Response:
    """The same, fetching the registered version's MLmodel from the configured server."""
    return ok(plat.integrations.fetch_mlflow(me, **body.model_dump()), 201)


@router.post("/integrations/sagemaker/import", status_code=201)
def sagemaker_import(body: s.SagemakerImportIn, me: Principal = Me, plat: Any = Plat) -> Response:
    """Register a black-box draft from a SageMaker ``DescribeModelPackage`` document."""
    return ok(plat.integrations.import_sagemaker(me, **body.model_dump()), 201)


@router.get("/integrations/openlineage/events")
def openlineage_events(me: Principal = Me, plat: Any = Plat) -> Response:
    """MAYA's lineage as OpenLineage RunEvents (administrators)."""
    return ok(plat.integrations.openlineage_events(me))


@router.post("/integrations/openlineage/emit")
def openlineage_emit(me: Principal = Me, plat: Any = Plat) -> Response:
    """Post the events to the configured OpenLineage endpoint (administrators)."""
    return ok(plat.integrations.emit_openlineage(me))


@router.post("/integrations/mlflow/sync")
def mlflow_sync(me: Principal = Me, plat: Any = Plat) -> Response:
    """Point the live alias at MLflow versions with a live warrant, and remove it elsewhere
    (administrators; also runs every five minutes on its own)."""
    return ok(plat.integrations.sync_mlflow(me))
