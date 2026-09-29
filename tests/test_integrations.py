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


def test_the_registry_alias_follows_the_warrant(estate):
    """Live warrant: the alias is set. Suspended: it is removed. Nothing changed: no call."""
    import datetime as dt

    from maya.core.clock import utcnow

    w = estate
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.content or str(request.url.params)))
        return httpx.Response(200, json={})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with w.p.uow("test") as uow:  # the model fetched from models:/pd/4 earlier in this module
        model = uow.repo("models").find_one(name="pd_fetched")
        v = uow.repo("model_versions").find_one(model_id=model["id"], version_no=1)
        ew = uow.repo("execution_warrants").add(
            {
                "namespace_id": model["namespace_id"],
                "name": "pd_live",
                "state": "approved",
                "owner_id": model["owner_id"],
                "model_version_id": v["id"],
                "spec": {"environments": ["prod"]},
                "sealed_at": utcnow(),
                "valid_from": utcnow(),
                "valid_to": utcnow() + dt.timedelta(days=30),
            }
        )
    first = w.p.integrations.sync_mlflow(w.admin, http=http)
    assert first["set"] == ["pd/4"] and calls[-1][0] == "POST" and b'"maya-live"' in calls[-1][2]
    assert w.p.integrations.sync_mlflow(w.admin, http=http)["set"] == [] and len(calls) == 1
    with w.p.uow("test") as uow:
        uow.repo("execution_warrants").update(
            ew["id"], {"suspended_at": utcnow(), "suspend_reason": "drift"}
        )
    third = w.p.integrations.sync_mlflow(w.admin, http=http)
    assert third["removed"] == ["pd/4"] and calls[-1][0] == "DELETE"
    with pytest.raises(PermissionDenied):
        w.p.integrations.sync_mlflow(w.mona, http=http)


def test_a_guarded_scoring_call_is_licensed_reported_and_refused_once_suspended(estate):
    import datetime as dt

    import numpy as np
    import pandas as pd

    from maya.core.clock import utcnow
    from maya.core.errors import WarrantSuspended
    from maya.sdk.guard import WarrantGuard

    w = estate
    with w.p.uow("test") as uow:
        model = uow.repo("models").find_one(name="pd_sm")
        v = uow.repo("model_versions").find_one(model_id=model["id"], version_no=1)
        ew = uow.repo("execution_warrants").add(
            {
                "namespace_id": model["namespace_id"],
                "name": "pd_guarded",
                "state": "approved",
                "owner_id": model["owner_id"],
                "model_version_id": v["id"],
                "spec": {
                    "environments": ["prod"],
                    "contact": "risk@example.com",
                    "covenants": [
                        {
                            "kind": "input_psi",
                            "attr": "ltv",
                            "max": 0.25,
                            "baseline": [25, 25, 25, 25],
                            "bin_edges": [0.0, 0.25, 0.5, 0.75, 1.0],
                        }
                    ],
                },
                "sealed_at": utcnow(),
                "valid_from": utcnow(),
                "valid_to": utcnow() + dt.timedelta(days=30),
            }
        )
    from maya.api.app import create_api
    from maya.sdk import Client

    app = create_api(w.p)
    admin = Client(app=app, token=Client(app=app).auth.login("admin", "maya-dev-admin")["token"])
    guard = WarrantGuard(admin, ew["id"], "prod", recheck_seconds=0)
    rng = np.random.default_rng(0)
    steady = pd.DataFrame({"ltv": rng.uniform(0, 1, 400), "dti": rng.uniform(0, 1, 400)})
    out = guard.score(lambda x: {"prediction": x["ltv"] * 0.1}, steady)
    assert len(out["prediction"]) == 400
    reports = w.p.monitoring.warrant(w.admin, ew["id"])
    assert reports["runs"] == 1 and reports["series"]["inputs"]["ltv"][-1]["psi"] < 0.1
    drifted = pd.DataFrame({"ltv": rng.uniform(0.8, 1, 400), "dti": rng.uniform(0, 1, 400)})
    guard.score(lambda x: {"prediction": x["ltv"] * 0.1}, drifted)  # breaks the covenant
    with pytest.raises(WarrantSuspended, match="risk@example.com"):
        guard.score(lambda x: {"prediction": x["ltv"] * 0.1}, steady)


def test_a_second_version_of_the_same_registered_model_never_takes_the_alias_off_the_live_one(
    estate,
):
    """An MLflow alias names one version per registered model. With pd/4 live and pd/5 not,
    the alias must end on pd/4, and nothing may delete it."""
    import copy
    import datetime as dt

    from maya.core.clock import utcnow

    w = estate
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.content or str(request.url.params)))
        return httpx.Response(200, json={})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with w.p.uow("test") as uow:
        model = uow.repo("models").find_one(name="pd_fetched")
        v = uow.repo("model_versions").find_one(model_id=model["id"], version_no=1)
        ir = copy.deepcopy(v["formula_ir"])
        ir["black_box"]["provenance"]["uri"] = "models:/pd/5"
        row = {k: val for k, val in v.items() if k not in ("id", "created_at", "updated_at")}
        uow.repo("model_versions").add({**row, "version_no": 99, "formula_ir": ir})
        for ew in uow.repo("execution_warrants").list(model_version_id=v["id"]):
            uow.repo("execution_warrants").update(
                ew["id"],
                {
                    "suspended_at": None,
                    "suspend_reason": None,
                    "valid_to": utcnow() + dt.timedelta(days=30),
                },
            )
    w.p.integrations._mlflow_alias = {}  # a fresh process: nothing assumed
    out = w.p.integrations.sync_mlflow(w.admin, http=http)
    assert out["set"] == ["pd/4"] and out["removed"] == []
    assert [c[0] for c in calls] == ["POST"] and b'"version": "4"' in calls[0][1].replace(
        b'":"', b'": "'
    )
