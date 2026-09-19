"""
SC-2 rehearsed: a two-year-old training run is reproduced from its warrant in under
ten minutes with no human archaeology (spec §2, §18.4, §28.7; plan M7).

The fixture trains a model on 2024 data exactly as a developer would — pin, warrant,
download, parameter upload against the checksum, approval, holdout score, seal — and
exports the bundle a regulator would have received at the time. It then **ages the
whole run by two years** through the repositories: the warrant's created, sealed and
expiry times, its custody trail, its parameter set and holdout score, and the feature
and feature-set pins it was drawn on, all move back 730 days. The warrant is now
expired — live use is refused — which is the point: the evidence must outlive the
licence to use it.

The reproduction is one function of the warrant id and nothing else: export the bundle,
run the bundle's own ``verify.py`` in a clean interpreter (file hashes, signature,
canonical data hash, re-execution of the model). It is timed, and the data and output
hashes it reproduces are compared with the ones recorded two years earlier — byte for
byte, including the checksum the developer downloaded and trained on.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import time
import zipfile

import pyarrow.compute as pc
import pyarrow.parquet as pq
import pytest

from maya.core.canonical import table_content_hash
from maya.core.clock import utcnow
from maya.core.errors import WarrantExpired
from tests.test_warrants import complete_spec

AGE = dt.timedelta(days=730)
LIMIT_SECONDS = 600
PX_2024 = {
    "index": ["date", "symbol"],
    "index_types": {"date": "date", "symbol": "string"},
    "schema": [{"name": "x", "type": "float64"}, {"name": "y", "type": "float64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "not_null", "attr": "x"}],
}


def _csv_2024() -> bytes:
    lines = ["date,symbol,x,y,kt"]
    for i in range(90):
        d = dt.date(2024, 1, 1) + dt.timedelta(days=i)
        for j, s in enumerate(("AAA", "BBB", "CCC", "DDD")):
            x = 1.0 + 0.05 * i + j
            lines.append(f"{d},{s},{x:.3f},{3.0 * x - 1.25:.3f},{d}T21:00:00Z")
    return ("\n".join(lines) + "\n").encode()


def _bundle_manifest(raw: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        return json.loads(z.read("manifest.json"))


@pytest.fixture(scope="module")
def trained(world):
    """A complete 2024 training run, then aged two years. Returns what was recorded then."""
    w = world
    w.p.access.create_namespace(w.admin, name="aged", preset="standard")
    w.p.features.create(w.dana, namespace="aged", name="px2024", definition=PX_2024)
    w.p.features.ingest(w.dana, "aged/px2024", _csv_2024(), fmt="csv")
    w.p.features.transition(w.dana, "aged/px2024", 1, "submit")
    w.p.features.transition(w.mick, "aged/px2024", 1, "approve")
    fs_def = {
        "index": ["date", "symbol"],
        "alignment": {"mode": "inner"},
        "members": [
            {"attr": "x", "ref": "maya://feature/aged/px2024@v1", "source_attr": "x"},
            {"attr": "y", "ref": "maya://feature/aged/px2024@v1", "source_attr": "y"},
        ],
    }
    w.p.featuresets.create(w.devi, namespace="aged", name="panel2024", definition=fs_def)
    w.p.featuresets.transition(w.devi, "aged/panel2024", 1, "submit")
    w.p.featuresets.transition(w.mick, "aged/panel2024", 1, "approve")
    w.p.featuresets.pin(
        w.mick,
        "aged/panel2024",
        version_no=1,
        pin_name="q1",
        as_of=dt.date(2024, 3, 31),
        cascade=True,
    )
    w.drain()
    w.p.models.create(
        w.mona,
        namespace="aged",
        name="lin2024",
        formula="yhat = a*x + b",
        roles={"a": "parameter", "b": "parameter"},
    )
    w.p.models.update_draft(w.mona, "aged/lin2024", spec_latex=complete_spec("lin2024"))
    w.p.models.transition(w.mona, "aged/lin2024", 1, "submit")
    w.p.models.transition(w.mgr, "aged/lin2024", 1, "approve")

    tw = w.p.warrants.create(
        w.devi,
        namespace="aged",
        name="calib2024",
        model="aged/lin2024@v1",
        featureset="maya://featureset/aged/panel2024#q1/2024-03-31",
        spec={"target": "y", "seed": 2024},
    )
    downloaded = w.p.warrants.data(w.devi, tw["id"])["manifest"]["checksum"]
    ps = w.p.warrants.upload_parameters(
        w.devi,
        tw["id"],
        values={"a": 3.0, "b": -1.25},
        metrics={"rmse": 0.0},
        data_checksum=downloaded,
    )
    assert ps["verified_data"]
    w.p.warrants.parameter_transition(w.devi, ps["id"], "submit")
    w.p.warrants.parameter_transition(w.mgr, ps["id"], "approve")
    w.p.warrants.score_holdout(w.devi, tw["id"], parameter_set_id=ps["id"])
    w.p.warrants.transition(w.devi, tw["id"], "submit")
    w.p.warrants.transition(w.mgr, tw["id"], "approve")
    w.p.warrants.seal(w.mgr, tw["id"])
    original = _bundle_manifest(w.p.blobs.get(w.p.bundles.export(w.devi, tw["id"])["blob"]))
    _age(w, tw["id"])
    return {"w": w, "warrant_id": tw["id"], "downloaded": downloaded, "original": original}


def _age(w, warrant_id: str) -> None:
    """Move the run two years into the past, through the repositories."""

    def back(repo, row, *cols):
        repo.update(row["id"], {c: row[c] - AGE for c in cols if row.get(c) is not None})

    with w.p.uow("fixture") as uow:
        tw = uow.repo("training_warrants").require(warrant_id)
        back(uow.repo("training_warrants"), tw, "created_at", "sealed_at", "expires_at")
        for ev in uow.repo("custody_events").list(warrant_id=warrant_id):
            back(uow.repo("custody_events"), ev, "created_at")
        for ps in uow.repo("parameter_sets").list(training_warrant_id=warrant_id):
            back(uow.repo("parameter_sets"), ps, "created_at")
        for hs in uow.repo("holdout_scores").list(training_warrant_id=warrant_id):
            back(uow.repo("holdout_scores"), hs, "created_at")
        fsp = uow.repo("feature_set_pins").require(tw["feature_set_pin_id"])
        back(uow.repo("feature_set_pins"), fsp, "created_at", "as_of_known", "sealed_at")
        for pid in fsp["member_pin_ids"].values():
            fp = uow.repo("feature_pins").require(pid)
            back(uow.repo("feature_pins"), fp, "created_at", "as_of_known", "sealed_at")
        mv = uow.repo("model_versions").require(tw["model_version_id"])
        back(uow.repo("model_versions"), mv, "created_at")


def reproduce(platform, principal, warrant_id: str) -> tuple[dict, dict, bytes, float]:
    """Everything SC-2 allows: a warrant id in, a verified reproduction out. No human step."""
    started = time.perf_counter()
    exported = platform.bundles.export(principal, warrant_id)
    raw = platform.blobs.get(exported["blob"])
    report = platform.bundles.verify_offline(raw)  # the bundle's own verify.py
    return exported["manifest"], report, raw, time.perf_counter() - started


def test_the_fixture_is_really_two_years_old(trained):
    w, wid = trained["w"], trained["warrant_id"]
    now = utcnow()
    with w.p.uow() as uow:
        tw = uow.repo("training_warrants").require(wid)
        custody = uow.repo("custody_events").list(warrant_id=wid)
        fsp = uow.repo("feature_set_pins").require(tw["feature_set_pin_id"])
        members = [uow.repo("feature_pins").require(i) for i in fsp["member_pin_ids"].values()]
    assert now - tw["created_at"] >= AGE and now - tw["sealed_at"] >= AGE
    assert tw["expires_at"] < now - dt.timedelta(days=300)
    assert custody and all(now - ev["created_at"] >= AGE for ev in custody)
    assert now - fsp["sealed_at"] >= AGE and all(now - m["sealed_at"] >= AGE for m in members)
    with pytest.raises(WarrantExpired):  # the live path is closed; evidence is not
        w.p.warrants.data(w.devi, wid)


def test_sc2_a_two_year_old_run_is_reproduced_from_its_warrant_alone(trained):
    w, wid, original = trained["w"], trained["warrant_id"], trained["original"]
    manifest, report, raw, seconds = reproduce(w.p, w.devi, wid)

    assert report["verified"] is True, report
    checks = {c["check"]: c for c in report["checks"]}
    assert checks["re-execution output hash"]["ok"] is True
    assert checks["data content hash (canonical, value-based)"]["ok"] is True
    assert checks["Ed25519 signature over the file list"]["ok"] is True
    assert seconds < LIMIT_SECONDS, f"SC-2: reproduction took {seconds:.1f}s"

    # byte-identical to what was recorded two years ago
    assert manifest["reexecutable"] is True and manifest["output_hash"]
    assert manifest["output_hash"] == original["output_hash"]
    assert manifest["data_content_hash"] == original["data_content_hash"]
    assert checks["re-execution output hash"]["detail"] == original["output_hash"]
    assert manifest["files"]["data/training.parquet"] == original["files"]["data/training.parquet"]
    assert manifest["files"]["model/parameters.json"] == original["files"]["model/parameters.json"]
    assert manifest["sealed_featureset_pin"] == "maya://featureset/aged/panel2024#q1/2024-03-31"

    # the rows the developer downloaded and trained on, recovered exactly from the bundle
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        table = pq.read_table(io.BytesIO(z.read("data/training.parquet")))
        warrant = json.loads(z.read("warrant.json"))
    split = [c for c in table.column_names if "split" in c]
    assert len(split) == 1
    trained_on = table.filter(pc.not_equal(table[split[0]], "test"))
    assert table_content_hash(trained_on) == trained["downloaded"]
    assert 0 < trained_on.num_rows < table.num_rows == 90 * 4
    # and everything needed to redo it is in the bundle, not in someone's memory
    assert warrant["spec"]["seed"] == 2024 and warrant["spec"]["model_ref"].endswith("lin2024@v1")
    assert [e["event"] for e in warrant["custody"]][:2] == ["created", "downloaded"]
