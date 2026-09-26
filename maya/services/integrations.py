"""
Connectors: models trained elsewhere come in, and MAYA's lineage goes out.

* **MLflow.** A model logged with MLflow carries an ``MLmodel`` file: its flavours, the run
  that produced it, and -- when it was logged with one -- a signature naming its input and
  output columns. Importing reads that file (uploaded, or fetched from the tracking server
  configured in ``integrations.mlflow.tracking_uri``) and registers a *black box* draft whose
  input contract is the signature, with the MLflow provenance sealed into the IR, so it goes
  through review, warrants and scoring like any other model. A model logged without a
  signature is refused: MAYA's contract checks need the input names, and guessing them
  would make every later check a check of the guess.
* **Amazon SageMaker.** A model package's ``DescribeModelPackage`` document names the
  image, the model data, the approval status and any metrics, but not the inputs -- SageMaker
  does not record them -- so the importer takes the input names from the caller (or from a
  ``maya:inputs`` customer metadata property) and says so in the provenance.
* **OpenLineage.** MAYA's lineage edges, grouped by what they produce, become OpenLineage
  ``RunEvent`` documents: one job per produced object, its sources as inputs. They can be
  downloaded, or posted to the endpoint in ``integrations.openlineage.url`` (Marquez, or any
  OpenLineage consumer), with a bearer token from the environment variable the settings name.

What is **not** claimed: none of these has been exercised against a live MLflow server, a
SageMaker account or a hosted OpenLineage consumer from this code base's tests. They are
tested against the documents those systems publish and against a recorded HTTP exchange.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import builtins
import json
import os
import uuid
from typing import Any

import yaml

from maya.core.errors import PermissionDenied, ValidationFailed
from maya.core.version import VERSION
from maya.security.authz import Principal

SCHEMA_URL = "https://openlineage.io/spec/2-0-2/OpenLineage.json#/definitions/RunEvent"
PRODUCER = f"https://github.com/ajsinha/maya/tree/v{VERSION}"
_NS = uuid.UUID("6f1f6c1e-6d0b-4a7e-9d1c-6d6179614f4c")
_TYPES = {
    "double": "float64",
    "float": "float64",
    "long": "int64",
    "integer": "int64",
    "boolean": "bool",
    "string": "string",
    "datetime": "datetime",
    "binary": "binary",
}


def parse_mlmodel(text: str) -> dict[str, Any]:
    """The facts MAYA needs from an MLflow ``MLmodel`` file."""
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValidationFailed(f"Not an MLmodel file: {exc}") from exc
    if not isinstance(doc, dict) or "flavors" not in doc:
        raise ValidationFailed("Not an MLmodel file: it has no 'flavors'")
    sig = doc.get("signature") or {}
    if not sig.get("inputs"):
        raise ValidationFailed(
            "This MLflow model was logged without a signature, so its input columns are not "
            "recorded. Log it with a signature (mlflow.models.infer_signature), or register "
            "it in MAYA as a black box and declare the inputs yourself."
        )

    def columns(raw: Any) -> list[dict[str, Any]]:
        spec = json.loads(raw) if isinstance(raw, str) else raw
        out = []
        for i, col in enumerate(spec or []):
            if col.get("type") == "tensor":
                raise ValidationFailed(
                    "The signature is tensor-based; MAYA's contract is column-based, one named "
                    "input per column"
                )
            out.append(
                {
                    "name": col.get("name") or f"col_{i}",
                    "type": _TYPES.get(str(col.get("type")), "float64"),
                }
            )
        return out

    inputs, outputs = (
        columns(sig["inputs"]),
        columns(sig.get("outputs")) or [{"name": "prediction", "type": "float64"}],
    )
    flavors = doc["flavors"]
    return {
        "inputs": inputs,
        "outputs": outputs,
        "flavors": sorted(flavors),
        "run_id": doc.get("run_id"),
        "model_uuid": doc.get("model_uuid"),
        "created": doc.get("utc_time_created"),
        "mlflow_version": doc.get("mlflow_version"),
        "loader": (flavors.get("python_function") or {}).get("loader_module"),
    }


def parse_model_package(doc: dict[str, Any] | str) -> dict[str, Any]:
    """The facts MAYA needs from a SageMaker ``DescribeModelPackage`` response."""
    if isinstance(doc, str):
        try:
            doc = json.loads(doc)
        except json.JSONDecodeError as exc:
            raise ValidationFailed(f"Not a model package description: {exc}") from exc
    if not isinstance(doc, dict) or "ModelPackageArn" not in doc:
        raise ValidationFailed("Not a model package description: it has no ModelPackageArn")
    containers = (doc.get("InferenceSpecification") or {}).get("Containers") or []
    meta = doc.get("CustomerMetadataProperties") or {}
    return {
        "arn": doc["ModelPackageArn"],
        "group": doc.get("ModelPackageGroupName"),
        "version": doc.get("ModelPackageVersion"),
        "approval": doc.get("ModelApprovalStatus"),
        "description": doc.get("ModelPackageDescription") or "",
        "images": [c.get("Image") for c in containers if c.get("Image")],
        "model_data": [c.get("ModelDataUrl") for c in containers if c.get("ModelDataUrl")],
        "framework": next(
            (
                f"{c.get('Framework')} {c.get('FrameworkVersion') or ''}".strip()
                for c in containers
                if c.get("Framework")
            ),
            None,
        ),
        "declared_inputs": [
            s.strip() for s in str(meta.get("maya:inputs", "")).split(",") if s.strip()
        ],
    }


class IntegrationService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- models in -------------------------------------------------------------------
    def _register(
        self,
        p: Principal,
        namespace: str,
        name: str,
        *,
        inputs: builtins.list[dict[str, Any]],
        outputs: builtins.list[dict[str, Any]],
        estimates: str,
        architecture: str,
        provenance: dict[str, Any],
        description: str,
    ) -> dict[str, Any]:
        if not estimates.strip():
            raise ValidationFailed(
                "Say in a sentence what the model estimates; a black box is reviewed on it"
            )
        ir = {
            "inputs": [{**i, "role": "feature"} for i in inputs],
            "outputs": outputs,
            "black_box": {
                "estimates": estimates.strip(),
                "architecture": architecture,
                "provenance": provenance,
            },
        }
        model = self.p.models.create(
            p, namespace=namespace, name=name, kind="black_box", ir=ir, description=description
        )
        with self.p.uow(p.username) as uow:
            uow.audit(
                "model.imported",
                object_type="model",
                object_ref=f"maya://model/{namespace}/{name}",
                detail={
                    "source": provenance["source"],
                    **{k: v for k, v in provenance.items() if k in ("run_id", "arn", "uri")},
                },
            )
        return {**model, "imported_from": provenance}

    def import_mlflow(
        self,
        p: Principal,
        *,
        namespace: str,
        name: str,
        mlmodel: str,
        estimates: str,
        description: str = "",
        uri: str | None = None,
    ) -> dict[str, Any]:
        """Register an MLflow model from its ``MLmodel`` file."""
        facts = parse_mlmodel(mlmodel)
        return self._register(
            p,
            namespace,
            name,
            inputs=facts["inputs"],
            outputs=facts["outputs"],
            estimates=estimates,
            architecture=f"MLflow model; flavours {', '.join(facts['flavors'])}",
            provenance={"source": "mlflow", "uri": uri, **facts},
            description=description,
        )

    def fetch_mlflow(
        self,
        p: Principal,
        *,
        namespace: str,
        name: str,
        model_name: str,
        version: str,
        estimates: str,
        description: str = "",
        http: Any = None,
    ) -> dict[str, Any]:
        """Fetch a registered model version's ``MLmodel`` from the configured tracking
        server and import it. Only the configured server is contacted: a URL typed into a
        form is how a server is made to fetch from somewhere it should not."""
        base = (self.p.settings.get("integrations.mlflow.tracking_uri") or "").rstrip("/")
        if not base:
            raise ValidationFailed(
                "No MLflow tracking server is configured (integrations.mlflow.tracking_uri); "
                "upload the model's MLmodel file instead"
            )
        headers = {}
        token_env = self.p.settings.get("integrations.mlflow.token_env")
        if token_env and os.environ.get(token_env):
            headers["Authorization"] = f"Bearer {os.environ[token_env]}"
        import httpx

        client = http or httpx.Client(timeout=30)
        try:
            mv = client.get(
                f"{base}/api/2.0/mlflow/model-versions/get",
                params={"name": model_name, "version": version},
                headers=headers,
            )
            mv.raise_for_status()
            info = mv.json()["model_version"]
            source, run_id = info.get("source", ""), info.get("run_id")
            if source.startswith("mlflow-artifacts:/"):
                path = source[len("mlflow-artifacts:/") :].strip("/")
                url, params = f"{base}/api/2.0/mlflow-artifacts/artifacts/{path}/MLmodel", {}
            elif source.startswith("runs:/") or run_id:
                sub = source.split("/", 2)[2] if source.startswith("runs:/") else ""
                url = f"{base}/get-artifact"
                params = {"path": f"{sub}/MLmodel".lstrip("/"), "run_uuid": run_id}
            else:
                raise ValidationFailed(
                    f"The model's artifacts live at '{source}', which the tracking server does "
                    "not serve; upload its MLmodel file instead"
                )
            art = client.get(url, params=params, headers=headers)
            art.raise_for_status()
        except httpx.HTTPError as exc:
            raise ValidationFailed(f"The MLflow tracking server refused or failed: {exc}") from exc
        finally:
            if http is None:
                client.close()
        return self.import_mlflow(
            p,
            namespace=namespace,
            name=name,
            mlmodel=art.text,
            estimates=estimates,
            description=description,
            uri=f"models:/{model_name}/{version}",
        )

    def import_sagemaker(
        self,
        p: Principal,
        *,
        namespace: str,
        name: str,
        package: dict[str, Any] | str,
        estimates: str,
        inputs: builtins.list[str] | None = None,
        outputs: builtins.list[str] | None = None,
    ) -> dict[str, Any]:
        """Register a SageMaker model package from its description."""
        facts = parse_model_package(package)
        names = [n for n in (inputs or []) if n] or facts["declared_inputs"]
        if not names:
            raise ValidationFailed(
                "SageMaker does not record a model package's inputs. Name them, or add a "
                "'maya:inputs' customer metadata property listing them, comma-separated."
            )
        return self._register(
            p,
            namespace,
            name,
            inputs=[{"name": n, "type": "float64"} for n in names],
            outputs=[{"name": n} for n in (outputs or ["prediction"])],
            estimates=estimates,
            architecture="SageMaker model package"
            + (f"; {facts['framework']}" if facts["framework"] else "")
            + (f"; image {facts['images'][0]}" if facts["images"] else ""),
            provenance={
                "source": "sagemaker",
                **facts,
                "inputs_from": "caller" if inputs else "maya:inputs metadata",
            },
            description=facts["description"],
        )

    # -- lineage out -----------------------------------------------------------------
    def openlineage_events(self, p: Principal) -> builtins.list[dict[str, Any]]:
        """Every lineage edge, grouped by what it produces, as OpenLineage RunEvents."""
        if not p.is_admin:
            raise PermissionDenied("Exporting the whole lineage graph is for administrators")
        ns = self.p.settings.get("integrations.openlineage.namespace") or "maya"
        by_dst: dict[str, builtins.list[dict[str, Any]]] = {}
        with self.p.uow() as uow:
            for e in uow.repo("lineage_edges").list(order_by=["created_at"]):
                by_dst.setdefault(e["dst_ref"], []).append(e)
        events = []
        for dst, edges in sorted(by_dst.items()):
            when = max(e["created_at"] for e in edges)
            events.append(
                {
                    "eventType": "COMPLETE",
                    "eventTime": when.isoformat(),
                    "producer": PRODUCER,
                    "schemaURL": SCHEMA_URL,
                    "run": {"runId": str(uuid.uuid5(_NS, f"{dst}|{when.isoformat()}"))},
                    "job": {
                        "namespace": ns,
                        "name": dst,
                        "facets": {
                            "maya": {
                                "_producer": PRODUCER,
                                "_schemaURL": SCHEMA_URL,
                                "edges": sorted({e["edge_type"] for e in edges}),
                            }
                        },
                    },
                    "inputs": [
                        {"namespace": ns, "name": src}
                        for src in sorted({e["src_ref"] for e in edges})
                    ],
                    "outputs": [{"namespace": ns, "name": dst}],
                }
            )
        return events

    def emit_openlineage(self, p: Principal, http: Any = None) -> dict[str, Any]:
        """Post every event to the configured OpenLineage endpoint."""
        events = self.openlineage_events(p)
        url = (self.p.settings.get("integrations.openlineage.url") or "").rstrip("/")
        if not url:
            raise ValidationFailed(
                "No OpenLineage endpoint is configured (integrations.openlineage.url); "
                "download the events instead"
            )
        headers = {"Content-Type": "application/json"}
        key_env = self.p.settings.get("integrations.openlineage.api_key_env")
        if key_env and os.environ.get(key_env):
            headers["Authorization"] = f"Bearer {os.environ[key_env]}"
        import httpx

        client = http or httpx.Client(timeout=30)
        sent, failed = 0, []
        try:
            for ev in events:
                try:
                    r = client.post(f"{url}/api/v1/lineage", json=ev, headers=headers)
                    r.raise_for_status()
                    sent += 1
                except httpx.HTTPError as exc:
                    failed.append({"job": ev["job"]["name"], "error": str(exc)[:200]})
        finally:
            if http is None:
                client.close()
        with self.p.uow(p.username) as uow:
            uow.audit(
                "lineage.openlineage_emitted",
                object_type="integration",
                object_ref="openlineage",
                detail={"sent": sent, "failed": len(failed), "url": url},
            )
        return {"events": len(events), "sent": sent, "failed": failed}
