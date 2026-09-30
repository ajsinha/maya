"""
SDK: connectors -- MLflow and SageMaker model import, OpenLineage export.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from maya.sdk.base import _Resource, endpoint


class Integrations(_Resource):
    """Models trained elsewhere come in; MAYA's lineage goes out."""

    @endpoint("POST", "/integrations/mlflow/import")
    def import_mlflow(
        self, namespace: str, name: str, mlmodel: str, estimates: str, description: str = ""
    ) -> Any:
        body = {
            "namespace": namespace,
            "name": name,
            "mlmodel": mlmodel,
            "estimates": estimates,
            "description": description,
        }
        return self._c("POST", "/integrations/mlflow/import", json_body=body)

    @endpoint("POST", "/integrations/mlflow/fetch")
    def fetch_mlflow(
        self,
        namespace: str,
        name: str,
        model_name: str,
        version: str,
        estimates: str,
        description: str = "",
    ) -> Any:
        body = {
            "namespace": namespace,
            "name": name,
            "model_name": model_name,
            "version": version,
            "estimates": estimates,
            "description": description,
        }
        return self._c("POST", "/integrations/mlflow/fetch", json_body=body)

    @endpoint("POST", "/integrations/sagemaker/import")
    def import_sagemaker(
        self,
        namespace: str,
        name: str,
        package: dict[str, Any],
        estimates: str,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
    ) -> Any:
        body = {
            "namespace": namespace,
            "name": name,
            "package": package,
            "estimates": estimates,
            "inputs": inputs,
            "outputs": outputs,
        }
        return self._c("POST", "/integrations/sagemaker/import", json_body=body)

    @endpoint("GET", "/integrations/openlineage/events")
    def openlineage_events(self) -> Any:
        return self._c("GET", "/integrations/openlineage/events")

    @endpoint("POST", "/integrations/openlineage/emit")
    def emit_openlineage(self) -> Any:
        return self._c("POST", "/integrations/openlineage/emit")

    @endpoint("POST", "/integrations/mlflow/sync")
    def sync_mlflow(self) -> Any:
        return self._c("POST", "/integrations/mlflow/sync")
