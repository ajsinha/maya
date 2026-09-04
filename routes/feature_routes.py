"""
MAYA — feature platform endpoints.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from core.features import AssemblyRejected, FeatureError


class FeatureIn(BaseModel):
    name: str
    entity: str
    dtype: str
    description: str
    owner: str
    business_definition: str = ""
    source_system: str = ""
    sensitivity: str = "internal"
    pii: bool = False
    protected_basis: bool = False
    proxy_risk: str = "none"


class ViewIn(BaseModel):
    name: str
    entity: str
    owner: str
    features: List[str]
    description: str = ""


class MaterialiseIn(BaseModel):
    rows: List[Dict[str, Any]]


class ContractIn(BaseModel):
    model_version_id: str
    items: List[Dict[str, Any]]


class TrainingSetIn(BaseModel):
    name: str
    spine: List[Dict[str, Any]]
    views: List[Dict[str, Any]]
    as_of: float
    valid_time_bound: bool = True
    transaction_time_bound: bool = True


class FeatureRoutes:
    def __init__(self, app: FastAPI, ctx: Dict[str, Any]):
        self.app, self.features = app, ctx["features"]
        self._register()

    def _guard(self, fn):
        try:
            return fn()
        except AssemblyRejected as exc:
            raise HTTPException(422, {"error": "assembly_rejected", "detail": str(exc),
                                      "remediation": "bound the assembly on both valid time "
                                                     "and transaction time"}) from exc
        except FeatureError as exc:
            raise HTTPException(409, {"error": "feature_refused", "detail": str(exc)}) from exc

    def _register(self) -> None:
        api = "/api/v1"

        @self.app.get(f"{api}/features", tags=["features"])
        def list_features(entity: Optional[str] = None):
            return {"features": self.features.features.list(entity)}

        @self.app.post(f"{api}/features", status_code=201, tags=["features"])
        def define(body: FeatureIn):
            near = self.features.similar(body.name, body.description)
            row = self._guard(lambda: self.features.define(**body.model_dump()))
            return {"feature": row,
                    "possible_duplicates": [f["name"] for f in near]}

        @self.app.post(f"{api}/features/{{name}}/certify", tags=["features"])
        def certify(name: str, level: str = "certified"):
            return self._guard(lambda: self.features.certify(name, level))

        @self.app.get(f"{api}/feature-views", tags=["features"])
        def list_views():
            return {"views": self.features.views.list()}

        @self.app.post(f"{api}/feature-views", status_code=201, tags=["features"])
        def create_view(body: ViewIn):
            return self._guard(lambda: self.features.create_view(
                body.name, body.entity, body.owner, body.features, body.description))

        @self.app.post(f"{api}/feature-views/{{name}}/materialise", status_code=201,
                       tags=["features"])
        def materialise(name: str, body: MaterialiseIn):
            return self._guard(lambda: self.features.materialise(name, body.rows))

        @self.app.get(f"{api}/feature-views/{{name}}/versions", tags=["features"])
        def versions(name: str):
            view = self.features.views.by_name(name)
            if not view:
                raise HTTPException(404, {"error": "not_found", "detail": f"no view {name}"})
            return {"versions": self.features.views.versions(view["id"])}

        @self.app.get(f"{api}/feature-views/{{name}}/versions/{{version}}/retirable",
                      tags=["features"])
        def retirable(name: str, version: int):
            ok, consumers = self._guard(lambda: self.features.can_retire(name, version))
            return {"retirable": ok, "pinned_by": consumers}

        @self.app.post(f"{api}/feature-contracts", status_code=201, tags=["features"])
        def bind(body: ContractIn):
            return self._guard(lambda: self.features.bind_contract(
                body.model_version_id, body.items))

        @self.app.get(f"{api}/feature-contracts/{{model_version_id}}/namespaces",
                      tags=["features"])
        def namespaces(model_version_id: str):
            """What serving MUST read. Law L-17 compares this to what it did read."""
            return {"namespaces": self._guard(
                lambda: self.features.serving_namespaces(model_version_id))}

        @self.app.post(f"{api}/training-sets", status_code=201, tags=["features"])
        def training_set(body: TrainingSetIn):
            return self._guard(lambda: self.features.build_training_set(
                body.name, body.spine, body.views, body.as_of,
                body.valid_time_bound, body.transaction_time_bound))
