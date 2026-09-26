"""
Connectors: MLflow and SageMaker model import, OpenLineage export, Snowflake and
Databricks sources. Tested against the documents those systems publish and a recorded
HTTP exchange; none is exercised against a live account here.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json

import httpx
import pytest

from maya.core.errors import PermissionDenied, ValidationFailed
from maya.persistence import external
from maya.services.integrations import parse_mlmodel
from tests.conftest import World, build_platform, price_csv, approved_feature

MLMODEL = """\
artifact_path: model
flavors:
  python_function:
    env:
      conda: conda.yaml
    loader_module: mlflow.sklearn
    model_path: model.pkl
    python_version: 3.11.4
  sklearn:
    pickled_model: model.pkl
    serialization_format: cloudpickle
    sklearn_version: 1.4.2
mlflow_version: 2.12.1
model_uuid: 3b8f1f0e2a8c4e6f9d0b7a6c5e4d3c2b
run_id: 9f1c2d3e4b5a69788796a5b4c3d2e1f0
signature:
  inputs: '[{"type": "double", "name": "ltv", "required": true}, {"type": "long", "name": "age", "required": true}]'
  outputs: '[{"type": "double", "name": "pd", "required": true}]'
  params: null
utc_time_created: '2026-05-04 10:21:33.120000'
"""

PACKAGE = {
    "ModelPackageArn": "arn:aws:sagemaker:eu-west-2:123456789012:model-package/pd-models/3",
    "ModelPackageGroupName": "pd-models",
    "ModelPackageVersion": 3,
    "ModelApprovalStatus": "Approved",
    "ModelPackageDescription": "Retail PD, gradient boosted",
    "InferenceSpecification": {
        "Containers": [
            {
                "Image": "123456789012.dkr.ecr.eu-west-2.amazonaws.com/xgb:1.7-1",
                "ModelDataUrl": "s3://models/pd/3/model.tar.gz",
                "Framework": "XGBOOST",
                "FrameworkVersion": "1.7",
            }
        ]
    },
    "CustomerMetadataProperties": {"maya:inputs": "ltv, dti"},
}


@pytest.fixture(scope="module")
def estate():
    platform = build_platform(
        [
            "--integrations.mlflow.tracking_uri=http://mlflow.test",
            "--integrations.openlineage.url=http://marquez.test",
        ]
    )
    w = World(platform)
    platform.access.create_namespace(w.admin, name="eq", preset="standard")
    yield w
    platform.shutdown()


def test_an_mlflow_signature_becomes_the_input_contract(estate):
    w = estate
    facts = parse_mlmodel(MLMODEL)
    assert [i["name"] for i in facts["inputs"]] == ["ltv", "age"]
    assert facts["inputs"][1]["type"] == "int64" and facts["flavors"] == [
        "python_function",
        "sklearn",
    ]
    w.p.integrations.import_mlflow(
        w.mona,
        namespace="eq",
        name="pd_mlflow",
        mlmodel=MLMODEL,
        estimates="the 12-month probability of default of a retail loan",
    )
    v = w.p.models.get(w.mona, "eq/pd_mlflow")["versions"][0]
    assert v["opaque"] and [c["name"] for c in v["input_contract"]] == ["ltv", "age"]
    prov = v["formula_ir"]["black_box"]["provenance"]
    assert prov["source"] == "mlflow" and prov["run_id"].startswith("9f1c")


def test_an_mlflow_model_without_a_usable_signature_is_refused():
    with pytest.raises(ValidationFailed, match="without a signature"):
        parse_mlmodel("flavors:\n  python_function: {}\n")
    tensor = MLMODEL.replace(
        """'[{"type": "double", "name": "ltv", "required": true}, {"type": "long", "name": "age", "required": true}]'""",
        """'[{"type": "tensor", "tensor-spec": {"dtype": "float32", "shape": [-1, 4]}}]'""",
    )
    with pytest.raises(ValidationFailed, match="tensor"):
        parse_mlmodel(tensor)
    with pytest.raises(ValidationFailed, match="Not an MLmodel"):
        parse_mlmodel("just: text")


def test_mlflow_fetch_talks_only_to_the_configured_server(estate):
    w = estate
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path == "/api/2.0/mlflow/model-versions/get":
            return httpx.Response(
                200,
                json={
                    "model_version": {
                        "name": "pd",
                        "version": "4",
                        "run_id": "9f1c",
                        "source": "runs:/9f1c/model",
                    }
                },
            )
        if request.url.path == "/get-artifact":
            assert request.url.params["path"] == "model/MLmodel"
            return httpx.Response(200, text=MLMODEL)
        return httpx.Response(404)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    out = w.p.integrations.fetch_mlflow(
        w.mona,
        namespace="eq",
        name="pd_fetched",
        model_name="pd",
        version="4",
        estimates="probability of default",
        http=http,
    )
    assert out["imported_from"]["uri"] == "models:/pd/4"
    assert all(u.startswith("http://mlflow.test/") for u in seen) and len(seen) == 2


def test_a_sagemaker_package_is_imported_with_named_inputs(estate):
    w = estate
    out = w.p.integrations.import_sagemaker(
        w.mona, namespace="eq", name="pd_sm", package=PACKAGE, estimates="retail PD"
    )
    prov = out["imported_from"]
    assert prov["inputs_from"] == "maya:inputs metadata" and prov["approval"] == "Approved"
    v = w.p.models.get(w.mona, "eq/pd_sm")["versions"][0]
    assert [c["name"] for c in v["input_contract"]] == ["ltv", "dti"]
    bare = {k: v for k, v in PACKAGE.items() if k != "CustomerMetadataProperties"}
    with pytest.raises(ValidationFailed, match="does not record"):
        w.p.integrations.import_sagemaker(
            w.mona, namespace="eq", name="pd_sm2", package=bare, estimates="retail PD"
        )


def test_lineage_goes_out_as_openlineage_run_events(estate):
    w = estate
    import datetime as dt

    ref = approved_feature(w, "px_ol", price_csv(days=3))
    w.p.features.pin(w.mick, ref, version_no=1, pin_name="ol", as_of=dt.date(2026, 1, 3))
    w.drain()
    with pytest.raises(PermissionDenied):
        w.p.integrations.openlineage_events(w.mona)
    events = w.p.integrations.openlineage_events(w.admin)
    assert events and all(e["eventType"] == "COMPLETE" and e["inputs"] for e in events)
    assert events[0]["schemaURL"].startswith("https://openlineage.io/spec/")
    assert json.loads(json.dumps(events, default=str)) == events  # plain JSON throughout

    posted = []

    def handler(request: httpx.Request) -> httpx.Response:
        posted.append(json.loads(request.content))
        return httpx.Response(201)

    out = w.p.integrations.emit_openlineage(
        w.admin, http=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert out["sent"] == len(events) == len(posted) and not out["failed"]


def test_snowflake_and_databricks_sources_are_accepted_with_their_guards():
    assert external.check_url("snowflake://reader@acct/db/sch?warehouse=wh&role=READER")
    assert external.check_url(
        "databricks://token@adb-1.azuredatabricks.net?http_path=/sql/1.0/warehouses/x"
    )
    with pytest.raises(ValidationFailed, match="read-only role"):
        external.check_url("snowflake://reader@acct/db/sch")
    with pytest.raises(ValidationFailed, match="never stores"):
        external.check_url("snowflake://reader:secret@acct/db?role=R")
    with pytest.raises(ValidationFailed, match="Supported source databases"):
        external.check_url("mysql://reader@host/db")
    try:
        import snowflake.sqlalchemy  # noqa: F401
    except ImportError:
        with pytest.raises(ValidationFailed, match="snowflake-sqlalchemy"):
            external.read_query("snowflake://r@a/db?role=R", None, "select 1")
