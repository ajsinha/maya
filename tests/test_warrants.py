"""
The model → warrant → evidence journey (§8, §9, §18.4, §29.1, §29.4, §29.5):
spec-document gating, cascade pin with rollback, contract validation, the
leakage certificate, the checksum cycle, sealing, blind scoring, execution
warrants whose covenant breach suspends them, and a bundle that verifies
offline — and fails after one byte changes.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import io
import zipfile

import pytest

from maya.core.errors import (
    ContractMismatch,
    NotApproved,
    PermissionDenied,
    ValidationFailed,
    WarrantSuspended,
)
from maya.formula.specdoc import REQUIRED_SECTIONS
from tests.conftest import PASSWORD

XY_DEF = {
    "index": ["date", "symbol"],
    "index_types": {"date": "date", "symbol": "string"},
    "schema": [{"name": "x", "type": "float64"}, {"name": "y", "type": "float64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "not_null", "attr": "x"}],
}


def xy_csv(days: int = 60, late: bool = False) -> bytes:
    lines = ["date,symbol,x,y,kt"]
    for i in range(days):
        d = dt.date(2026, 1, 1) + dt.timedelta(days=i)
        known = d + dt.timedelta(days=30 if late else 0)
        for j, s in enumerate(("AAA", "BBB", "CCC")):
            x = 1.0 + i * 0.1 + j
            lines.append(f"{d},{s},{x:.3f},{2.0 * x + 0.5:.3f},{known}T18:00:00Z")
    return ("\n".join(lines) + "\n").encode()


def complete_spec(name: str) -> str:
    body = "\n".join(
        f"\\section{{{s}}}\n{s} for {name}: stated in full.\n" for s in REQUIRED_SECTIONS
    )
    return f"\\documentclass{{article}}\n\\begin{{document}}\n{body}\n\\end{{document}}\n"


@pytest.fixture(scope="module")
def journey(world):
    w = world
    w.p.access.create_user(w.admin, username="mgr2", password=PASSWORD, roles=["model_manager"])
    w.p.access.create_namespace(w.admin, name="quant", preset="standard")
    w.p.features.create(w.dana, namespace="quant", name="xy", definition=XY_DEF)
    w.p.features.ingest(w.dana, "quant/xy", xy_csv(), fmt="csv")
    w.p.features.transition(w.dana, "quant/xy", 1, "submit")
    w.p.features.transition(w.mick, "quant/xy", 1, "approve")
    fs_def = {
        "index": ["date", "symbol"],
        "grid": "as_is",
        "alignment": {"mode": "inner"},
        "members": [
            {"attr": "x", "ref": "maya://feature/quant/xy@v1", "source_attr": "x"},
            {"attr": "y", "ref": "maya://feature/quant/xy@v1", "source_attr": "y"},
        ],
    }
    w.p.featuresets.create(w.devi, namespace="quant", name="panel", definition=fs_def)
    w.p.featuresets.transition(w.devi, "quant/panel", 1, "submit")
    w.p.featuresets.transition(w.mick, "quant/panel", 1, "approve")
    w.p.featuresets.pin(
        w.mick, "quant/panel", version_no=1, pin_name="q1", as_of=dt.date(2026, 2, 28), cascade=True
    )
    w.drain()
    w.p.models.create(
        w.mona,
        namespace="quant",
        name="linear",
        formula="yhat = a*x + b",
        roles={"a": "parameter", "b": "parameter"},
    )
    return w


def test_featureset_refuses_to_pin_unpinned_members_without_cascade(journey):
    w = journey
    with pytest.raises(NotApproved, match="cascade"):
        w.p.featuresets.pin(
            w.mick, "quant/panel", version_no=1, pin_name="nocascade", as_of=dt.date(2026, 2, 28)
        )
    fs = w.p.featuresets.get(w.devi, "quant/panel")
    assert fs["pins"][0]["state"] == "sealed" and len(fs["pins"][0]["member_pin_ids"]) == 1


def test_cascade_rolls_back_entirely_on_a_member_failure(journey):
    w = journey
    bad = dict(XY_DEF, quality=[{"check": "range", "attr": "x", "min": 0, "max": 100}])
    w.p.features.create(w.dana, namespace="quant", name="xy_strict", definition=bad)
    w.p.features.ingest(w.dana, "quant/xy_strict", xy_csv(), fmt="csv")
    w.p.features.transition(w.dana, "quant/xy_strict", 1, "submit")
    w.p.features.transition(w.mick, "quant/xy_strict", 1, "approve")
    # the data goes bad after approval: a vendor restatement out of the contract's range
    w.p.features.ingest(
        w.dana,
        "quant/xy_strict",
        b"date,symbol,x,y,kt\n2026-01-05,AAA,5000,1,2026-01-06T00:00:00Z\n",
        fmt="csv",
    )
    fs_def = {
        "index": ["date", "symbol"],
        "members": [
            {"attr": "x", "ref": "maya://feature/quant/xy@v1", "source_attr": "x"},
            {"attr": "x2", "ref": "maya://feature/quant/xy_strict@v1", "source_attr": "x"},
        ],
    }
    w.p.featuresets.create(w.devi, namespace="quant", name="doomed", definition=fs_def)
    w.p.featuresets.transition(w.devi, "quant/doomed", 1, "submit")
    w.p.featuresets.transition(w.mick, "quant/doomed", 1, "approve")
    w.p.featuresets.pin(
        w.mick,
        "quant/doomed",
        version_no=1,
        pin_name="boom",
        as_of=dt.date(2026, 2, 28),
        cascade=True,
    )
    w.drain()
    with w.p.uow() as uow:
        fsp = uow.repo("feature_set_pins").find_one(pin_name="boom")
        assert fsp["state"] == "failed"
        assert uow.repo("feature_pins").count(pin_name="boom") == 0, "cascade left member pins"


def test_model_submission_is_blocked_by_an_incomplete_spec(journey):
    w = journey
    with pytest.raises(NotApproved, match="spec_document_complete"):
        w.p.models.transition(w.mona, "quant/linear", 1, "submit")
    w.p.models.update_draft(w.mona, "quant/linear", spec_latex=complete_spec("linear"))
    assert w.p.models.transition(w.mona, "quant/linear", 1, "submit")["state"] == "in_review"
    assert w.p.models.transition(w.mgr, "quant/linear", 1, "approve")["state"] == "approved"


def test_contract_mismatch_is_refused_listing_every_attribute(journey):
    w = journey
    w.p.models.create(w.mona, namespace="quant", name="needs_z", formula="out = z * w2 + x")
    w.p.models.update_draft(w.mona, "quant/needs_z", spec_latex=complete_spec("needs_z"))
    w.p.models.transition(w.mona, "quant/needs_z", 1, "submit")
    w.p.models.transition(w.mgr, "quant/needs_z", 1, "approve")
    with pytest.raises(ContractMismatch) as exc:
        w.p.warrants.create(
            w.devi,
            namespace="quant",
            name="bad",
            model="quant/needs_z@v1",
            featureset="maya://featureset/quant/panel#q1/2026-02-28",
            spec={},
        )
    assert "z" in exc.value.message and "w2" in exc.value.message


def test_leakage_certificate_refuses_late_knowledge(journey):
    w = journey
    w.p.features.create(w.dana, namespace="quant", name="late", definition=XY_DEF)
    w.p.features.ingest(w.dana, "quant/late", xy_csv(late=True), fmt="csv")
    w.p.features.transition(w.dana, "quant/late", 1, "submit")
    w.p.features.transition(w.mick, "quant/late", 1, "approve")
    fs_def = {
        "index": ["date", "symbol"],
        "members": [
            {"attr": "x", "ref": "maya://feature/quant/late@v1", "source_attr": "x"},
            {"attr": "y", "ref": "maya://feature/quant/late@v1", "source_attr": "y"},
        ],
    }
    w.p.featuresets.create(w.devi, namespace="quant", name="leaky", definition=fs_def)
    w.p.featuresets.transition(w.devi, "quant/leaky", 1, "submit")
    w.p.featuresets.transition(w.mick, "quant/leaky", 1, "approve")
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="leaky_tw",
        model="quant/linear@v1",
        featureset="maya://featureset/quant/leaky@v1",
        spec={"target": "y"},
    )
    cert = tw["leakage_certificate"]
    assert cert["status"] == "refused" and cert["violations"] == 180
    assert cert["signature"]["algorithm"] == "Ed25519"
    with pytest.raises(NotApproved, match="leakage_certified"):
        w.p.warrants.transition(w.devi, tw["id"], "submit")


def test_the_checksum_cycle_seal_score_execute_and_bundle(journey, tmp_path):
    w = journey
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="calib",
        model="quant/linear@v1",
        featureset="maya://featureset/quant/panel#q1/2026-02-28",
        spec={"target": "y", "seed": 7},
    )
    assert tw["leakage_certificate"]["status"] == "certified"
    data = w.p.warrants.data(w.devi, tw["id"])
    checksum = data["manifest"]["checksum"]
    assert data["manifest"]["escrowed_holdout"] is True
    good = w.p.warrants.upload_parameters(
        w.devi, tw["id"], values={"a": 2.0, "b": 0.5}, metrics={"rmse": 0.0}, data_checksum=checksum
    )
    bad = w.p.warrants.upload_parameters(
        w.devi, tw["id"], values={"a": 2.0, "b": 0.4}, data_checksum="0" * 64
    )
    assert good["verified_data"] and bad["flag"] == "unverified_data"
    w.p.warrants.parameter_transition(w.devi, bad["id"], "submit")
    with pytest.raises(NotApproved, match="unverified_data"):
        w.p.warrants.parameter_transition(w.mgr, bad["id"], "approve")
    w.p.warrants.parameter_transition(w.devi, good["id"], "submit")
    w.p.warrants.parameter_transition(w.mgr, good["id"], "approve")
    score = w.p.warrants.score_holdout(w.devi, tw["id"], parameter_set_id=good["id"])
    assert score["metrics"]["rmse"] < 1e-2 and score["attempt"] == 1
    w.p.warrants.transition(w.devi, tw["id"], "submit")
    w.p.warrants.transition(w.mgr, tw["id"], "approve")
    assert w.p.warrants.seal(w.mgr, tw["id"])["sealed_at"] is not None

    ew = w.p.execution.create(
        w.mgr,
        namespace="quant",
        name="live",
        training_warrant_id=tw["id"],
        parameter_set_id=good["id"],
        spec={
            "environments": ["dev"],
            "contact": "risk@example.com",
            "covenants": [{"kind": "input_null_rate", "attr": "x", "max": 0.1}],
        },
    )
    w.p.execution.transition(w.mgr, ew["id"], "submit")
    w.p.execution.transition(w.principal("mgr2"), ew["id"], "approve")
    w.p.execution.seal(w.mgr, ew["id"])
    assert w.p.execution.bundle(w.devi, ew["id"], "dev")["status"] == "live"
    breach = w.p.execution.report(
        w.devi, ew["id"], environment="dev", rows=10, input_stats={"x": {"null_rate": 0.4}}
    )
    assert breach["status"] == "suspended"
    with pytest.raises(WarrantSuspended, match="risk@example.com"):
        w.p.execution.bundle(w.devi, ew["id"], "dev")
    w.p.execution.reinstate(w.admin, ew["id"], "false positive: vendor file late")
    live = w.p.execution.bundle(w.devi, ew["id"], "dev")
    assert live["status"] == "live" and live["attestation"] == "attested" and live["token"]
    assert w.p.execution.get(w.devi, ew["id"])["offline_use"]["label"] is None
    # offline use is allowed, and visible: unattested on the copy and on the warrant
    copy = w.p.execution.bundle(w.devi, ew["id"], "dev", offline=True)
    assert copy["attestation"] == "unattested" and copy["token"] is None
    shown = w.p.execution.get(w.devi, ew["id"])
    assert shown["offline_use"]["label"] == "unattested"
    assert shown["offline_use"]["copies_issued"] == 1
    assert shown["custody"][-1]["event"] == "offline_issued"
    with w.p.uow() as uow:
        assert uow.repo("audit_events").find_one(action="warrant.offline_issued")

    exported = w.p.bundles.export(w.devi, tw["id"])
    raw = w.p.blobs.get(exported["blob"])
    report = w.p.bundles.verify(raw)
    assert report["verified"], report
    assert any(c["check"] == "re-execution output hash" and c["ok"] for c in report["checks"])
    tampered = _tamper(raw, "model/parameters.json")
    assert w.p.bundles.verify(tampered)["verified"] is False


def _tamper(raw: bytes, member: str) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(raw))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == member:
                data = data.replace(b"2.0", b"2.1")
            z.writestr(info.filename, data)
    return out.getvalue()


def test_model_diff_names_the_compounding_change(journey):
    w = journey
    w.p.models.create(w.mona, namespace="quant", name="disc", formula="pv = K*exp(-r*T)")
    w.p.models.update_draft(w.mona, "quant/disc", spec_latex=complete_spec("disc"))
    w.p.models.transition(w.mona, "quant/disc", 1, "submit")
    w.p.models.transition(w.mgr, "quant/disc", 1, "approve")
    w.p.models.new_draft(w.mona, "quant/disc")
    w.p.models.update_draft(w.mona, "quant/disc", formula="pv = K/(1+r*T)")
    diff = w.p.models.diff(w.mona, "quant/disc", 1, 2)
    assert any("simple compounding" in s for s in diff["statements"]), diff["statements"]


def test_artifact_validation_ladder_runs_as_a_job(journey):
    w = journey
    good = (
        "import numpy as np\n\nclass Model:\n    def fit(self, X, y, ctx):\n        return {}\n\n"
        "    def predict(self, X, params, ctx):\n"
        "        return [params.get('a', 1.0) * v for v in X['x']]\n"
    )
    w.p.models.create(
        w.mona, namespace="quant", name="coded", formula="yhat = a*x", roles={"a": "parameter"}
    )
    w.p.models.upload_artifact(w.mona, "quant/coded", good)
    w.drain()
    model = w.p.models.get(w.mona, "quant/coded")
    report = model["versions"][0]["artifact_report"]
    assert report["passed"] and report["tier"] in ("strong", "moderate", "minimal")
    evil = "import os\nclass Model:\n    def fit(self,X,y,ctx): pass\n    def predict(self,X,p,c): os.system('x')\n"
    w.p.models.upload_artifact(w.mona, "quant/coded", evil)
    w.drain()
    report = w.p.models.get(w.mona, "quant/coded")["versions"][0]["artifact_report"]
    assert not report["passed"]


def test_training_data_download_honours_the_downloaders_masks(journey):
    """A warrant is not a way around a column mask: the download is masked, and the
    checksum MAYA issues is of what was actually delivered."""
    import pyarrow.parquet as pq

    w = journey
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="masked",
        model="quant/linear@v1",
        featureset="maya://featureset/quant/panel#q1/2026-02-28",
        spec={"target": "y"},
    )
    obj = w.p.access.resolve_object("feature", "quant/xy")
    w.p.access.grant(
        w.admin,
        kind="feature",
        obj=obj,
        principal_type="user",
        principal_id="devi",
        level="read",
        conditions={"column_mask": {"y": "null"}},
    )
    data = w.p.warrants.data(w.devi, tw["id"])
    table = pq.read_table(io.BytesIO(data["data"]))
    assert set(table.column("y").to_pylist()) == {None}
    from maya.core.canonical import table_content_hash

    assert table_content_hash(table) == data["manifest"]["checksum"]


def test_featureset_download_refuses_a_shape_it_cannot_write(journey):
    """A download is tabular or wide; asking for tensor must not return tabular labelled tensor."""
    w = journey
    ref = "maya://featureset/quant/panel@v1"
    assert w.p.featuresets.download(w.mick, ref, shape="wide")["manifest"]["shape"] == "wide"
    for bad in ("tensor", "cube"):
        with pytest.raises(ValidationFailed, match="tabular or wide"):
            w.p.featuresets.download(w.mick, ref, shape=bad)


def test_execution_limits_throttle_and_record_overage(journey):
    """Rate and volume limits (§9.2): unknown or non-positive limits are refused; once today's
    allowance is spent, no token or bundle is issued; an over-limit run is recorded, not hidden."""
    from maya.core.errors import QuotaExceeded

    w = journey
    with w.p.uow() as uow:
        tw = uow.repo("training_warrants").find_one(name="calib")
        ps = next(
            p
            for p in uow.repo("parameter_sets").list(training_warrant_id=tw["id"])
            if p["state"] == "approved"
        )
    for bad in ({"max_calls_per_week": 5}, {"max_calls_per_day": 0}):
        with pytest.raises(ValidationFailed, match="[Ll]imit"):
            w.p.execution.create(
                w.mgr,
                namespace="quant",
                name="badlim",
                training_warrant_id=tw["id"],
                parameter_set_id=ps["id"],
                spec={"limits": bad},
            )
    ew = w.p.execution.create(
        w.mgr,
        namespace="quant",
        name="metered",
        training_warrant_id=tw["id"],
        parameter_set_id=ps["id"],
        spec={
            "environments": ["dev"],
            "contact": "desk@example.com",
            "limits": {"max_calls_per_day": 2, "max_rows_per_call": 100},
        },
    )
    assert ew["manifest"]["limits"] == {"max_calls_per_day": 2, "max_rows_per_call": 100}
    w.p.execution.transition(w.mgr, ew["id"], "submit")
    w.p.execution.transition(w.principal("mgr2"), ew["id"], "approve")
    w.p.execution.seal(w.mgr, ew["id"])
    first = w.p.execution.report(w.devi, ew["id"], environment="dev", rows=50, input_stats={})
    assert first["limits_exceeded"] == [] and first["status"] == "live"
    big = w.p.execution.report(w.devi, ew["id"], environment="dev", rows=500, input_stats={})
    assert big["limits_exceeded"] == [{"limit": "max_rows_per_call", "max": 100, "observed": 500}]
    for issue in (
        lambda: w.p.execution.bundle(w.devi, ew["id"], "dev"),
        lambda: w.p.execution.token(w.devi, ew["id"], "dev"),
    ):
        with pytest.raises(QuotaExceeded, match="desk@example.com"):
            issue()
    with w.p.uow() as uow:
        assert uow.repo("audit_events").list(action="warrant.limit_exceeded")
        assert uow.repo("events").list(type="warrant.limit_exceeded")


def test_batch_scoring_is_attested_reported_and_refused_off_warrant(journey):
    """Attested batch scoring: a pin scored under a live warrant, as a job; the output sealed
    by its hash, the run reported, custody updated. A non-pin, or an environment the warrant
    does not cover, is refused before any job is queued."""
    import io

    import pyarrow.parquet as pq

    from maya.core import canonical

    w = journey
    with w.p.uow() as uow:
        tw = uow.repo("training_warrants").find_one(name="calib")
        ps = next(
            p
            for p in uow.repo("parameter_sets").list(training_warrant_id=tw["id"])
            if p["state"] == "approved"
        )
    ew = w.p.execution.create(
        w.mgr,
        namespace="quant",
        name="batch",
        training_warrant_id=tw["id"],
        parameter_set_id=ps["id"],
        spec={"environments": ["dev"], "contact": "desk@example.com"},
    )
    w.p.execution.transition(w.mgr, ew["id"], "submit")
    w.p.execution.transition(w.principal("mgr2"), ew["id"], "approve")
    w.p.execution.seal(w.mgr, ew["id"])
    pin = "maya://featureset/quant/panel#q1/2026-02-28"
    with pytest.raises(ValidationFailed, match="pin"):
        w.p.batches.submit(
            w.devi, ew["id"], pin="maya://featureset/quant/panel@v1", environment="dev"
        )
    with pytest.raises(PermissionDenied):
        w.p.batches.submit(w.devi, ew["id"], pin=pin, environment="prod")
    job = w.p.batches.submit(w.devi, ew["id"], pin=pin, environment="dev")
    w.drain()
    (batch,) = w.p.batches.list(w.devi, ew["id"])
    assert batch["id"] == job["id"] and batch["state"] == "succeeded", batch
    result = batch["result"]
    assert result["status_after"] == "live" and result["rows"] > 0
    out = w.p.batches.output(w.devi, ew["id"], job["id"])
    table = pq.read_table(io.BytesIO(out["data"]))
    assert canonical.table_content_hash(table) == out["content_hash"] == result["output_hash"]
    assert {"date", "symbol", "yhat"} <= set(table.column_names)
    frame = table.to_pandas()
    shown = w.p.execution.get(w.devi, ew["id"])
    assert shown["reports"][-1]["rows"] == result["rows"]
    assert shown["custody"][-1]["event"] == "batch_scored"
    assert shown["custody"][-1]["detail"]["output_hash"] == result["output_hash"]
    assert len(frame) == result["rows"]
