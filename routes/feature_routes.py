"""
MAYA — feature platform endpoints.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from routes.base import Routes


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


class FeatureRoutes(Routes):
    def register(self) -> None:
        f = self.ctx["features"]

        @self.app.get(f"{self.api}/features", tags=["features"])
        def list_features(entity: Optional[str] = None):
            return {"features": f.features.many(entity=entity)}

        @self.app.post(f"{self.api}/features", status_code=201, tags=["features"])
        def define(body: FeatureIn):
            near = [x["name"] for x in f.similar(body.name, body.description)]
            return {"feature": self.guard(lambda: f.define(**body.model_dump())),
                    "possible_duplicates": near}

        @self.app.post(f"{self.api}/features/{{name}}/certify", tags=["features"])
        def certify(name: str, level: str = "certified"):
            return self.guard(lambda: f.certify(name, level))

        @self.app.get(f"{self.api}/feature-views", tags=["features"])
        def list_views():
            return {"views": f.views.many()}

        @self.app.post(f"{self.api}/feature-views", status_code=201, tags=["features"])
        def create_view(body: ViewIn):
            return self.guard(lambda: f.create_view(
                body.name, body.entity, body.owner, body.features, body.description))

        @self.app.post(f"{self.api}/feature-views/{{name}}/materialise", status_code=201,
                       tags=["features"])
        def materialise(name: str, body: MaterialiseIn):
            return self.guard(lambda: f.materialise(name, body.rows))

        @self.app.get(f"{self.api}/feature-views/{{name}}/versions", tags=["features"])
        def versions(name: str):
            view = f.views.one(name=name)
            if not view:
                raise self.not_found(f"no feature view {name}")
            return {"versions": f.view_versions.many(feature_view_id=view["id"])}

        @self.app.get(f"{self.api}/feature-views/{{name}}/versions/{{version}}/retirable",
                      tags=["features"])
        def retirable(name: str, version: int):
            ok, pinned_by = self.guard(lambda: f.can_retire(name, version))
            return {"retirable": ok, "pinned_by": pinned_by}

        @self.app.post(f"{self.api}/feature-contracts", status_code=201, tags=["features"])
        def bind(body: ContractIn):
            return self.guard(lambda: f.bind_contract(body.model_version_id, body.items))

        @self.app.get(f"{self.api}/feature-contracts/{{model_version_id}}/namespaces",
                      tags=["features"])
        def namespaces(model_version_id: str):
            """What serving MUST read. Law L-17 compares this to what it did read."""
            return {"namespaces": self.guard(
                lambda: f.serving_namespaces(model_version_id))}

        @self.app.post(f"{self.api}/training-sets", status_code=201, tags=["features"])
        def training_set(body: TrainingSetIn):
            return self.guard(lambda: f.build_training_set(
                body.name, body.spine, body.views, body.as_of,
                body.valid_time_bound, body.transaction_time_bound))
