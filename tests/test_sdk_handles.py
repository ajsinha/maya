"""
§18.2.4's object shape, and §18.2.5's cache. The SDK spoke only in dictionaries: correct,
and nothing like what the specification writes. Here the documented shapes are exercised —
`client.feature(ref).version(n).pin(...)`, `job.wait(progress=...)`, `pin.to_arrow()`,
`with warrant.data() as ds: ds.X, ds.y` — and the cache is shown to hold sealed pins only,
to verify every hit, and to treat a damaged file as a miss.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pytest

from maya.core.errors import MayaError, ValidationFailed
from maya.sdk import Client
from maya.sdk.cache import PinCache
from maya.sdk.handles import JobHandle, Record, wrap
from maya.server import build_app
from tests.conftest import PASSWORD, World, approved_feature, build_platform, price_csv
from tests.test_warrants import XY_DEF, complete_spec, xy_csv


@pytest.fixture(scope="module")
def sdk(tmp_path_factory):
    platform = build_platform()
    platform.jobs.start()
    w = World(platform)
    platform.access.create_namespace(w.admin, name="hdl", preset="standard")
    approved_feature(w, "hdl_px", price_csv(6), ns="hdl")
    platform.features.create(w.dana, namespace="hdl", name="hdl_xy", definition=XY_DEF)
    platform.features.ingest(w.dana, "hdl/hdl_xy", xy_csv(), fmt="csv")
    platform.features.transition(w.dana, "hdl/hdl_xy", 1, "submit")
    platform.features.transition(w.mick, "hdl/hdl_xy", 1, "approve")
    fs_def = {
        "index": ["date", "symbol"],
        "members": [
            {"attr": a, "ref": "maya://feature/hdl/hdl_xy@v1", "source_attr": a} for a in ("x", "y")
        ],
    }
    platform.featuresets.create(w.devi, namespace="hdl", name="hdl_panel", definition=fs_def)
    platform.featuresets.transition(w.devi, "hdl/hdl_panel", 1, "submit")
    platform.featuresets.transition(w.mick, "hdl/hdl_panel", 1, "approve")
    platform.models.create(
        w.mona, namespace="hdl", name="hdl_lin", formula="yhat = a*x", roles={"a": "parameter"}
    )
    platform.models.update_draft(w.mona, "hdl/hdl_lin", spec_latex=complete_spec("hdl_lin"))
    platform.models.transition(w.mona, "hdl/hdl_lin", 1, "submit")
    platform.models.transition(w.mgr, "hdl/hdl_lin", 1, "approve")
    platform.features.pin(
        w.mick, "hdl/hdl_px", version_no=1, pin_name="base", as_of=dt.date(2026, 1, 4)
    )
    platform.jobs.drain()
    app = build_app(platform)
    anon = Client(app=app, channel="sdk")
    cache_dir = tmp_path_factory.mktemp("pincache")
    clients = {}
    for user in ("mick", "devi"):
        token = anon.auth.login(user, PASSWORD)["token"]
        client = Client(app=app, token=token, channel="sdk")
        client.cache = PinCache(cache_dir / user)
        clients[user] = client
    yield clients, platform
    platform.shutdown()


def test_a_record_is_a_dict_and_reads_like_an_object(sdk):
    clients, _ = sdk
    feature = clients["mick"].feature("hdl/hdl_px")
    assert feature.name == "hdl_px" == feature["name"]
    assert isinstance(feature, dict) and feature.ref == "hdl/hdl_px"
    assert feature.versions[0].state == "approved"
    with pytest.raises(AttributeError, match="no field 'nonsense'"):
        feature.nonsense
    plain = wrap({"a": {"b": [{"c": 1}]}})
    assert plain.a.b[0].c == 1, "records nest"
    assert Record({"x": 1}) == {"x": 1}, "and still compare as the payload"


def test_a_feature_pins_through_its_version_and_the_job_waits(sdk):
    clients, _ = sdk
    feature = clients["mick"].feature("hdl/hdl_px")
    seen: list[tuple[int, str]] = []
    job = feature.version(1).pin("q1", as_of=dt.date(2026, 1, 5))
    assert isinstance(job, JobHandle)
    done = job.wait(progress=lambda row: seen.append((row["progress"], row["message"])))
    assert done["state"] == "succeeded" and seen, "progress was reported while waiting"
    pins = clients["mick"].feature("hdl/hdl_px").pins()
    q1 = next(p for p in pins if p["pin_name"] == "q1")
    assert q1.content_hash and q1.state == "sealed"


def test_a_pin_becomes_a_table_a_frame_and_a_file(sdk, tmp_path):
    clients, _ = sdk
    pins = clients["mick"].feature("hdl/hdl_px").pins()
    pin = next(p for p in pins if p["state"] == "sealed")
    table = pin.to_arrow()
    assert table.num_rows > 0 and "close" in table.column_names
    assert len(pin.to_pandas()) == table.num_rows
    out = pin.to_file(tmp_path / "pin.parquet")
    assert out.exists() and out.stat().st_size > 0


def test_a_sealed_pin_is_cached_by_content_hash_and_verified(sdk):
    clients, _ = sdk
    client = clients["mick"]
    pin = next(p for p in client.feature("hdl/hdl_px").pins() if p["state"] == "sealed")
    client.cache.clear()
    first = pin.to_arrow()
    stats = client.cache.stats()
    assert stats["files"] == 1 and stats["bytes"] > 0
    calls: list[str] = []
    original = client.features.download
    client.features.download = lambda *a, **kw: (calls.append("download"), original(*a, **kw))[1]
    try:
        again = pin.to_arrow()
        assert not calls, "the second read came from the cache"
        assert again.equals(first)
        # a damaged cache file is a miss, not an answer
        for path in client.cache.directory.rglob("*"):
            if path.is_file():
                path.write_bytes(b"not parquet")
        third = pin.to_arrow()
        assert calls == ["download"], "a file that will not read is fetched again"
        assert third.equals(first)
    finally:
        client.features.download = original


def test_nothing_but_a_sealed_pin_is_cached(sdk):
    clients, _ = sdk
    client = clients["mick"]
    client.cache.clear()
    client.features.preview("maya://feature/hdl/hdl_px@v1")
    client.features.get("hdl/hdl_px")
    assert client.cache.stats()["files"] == 0, "definitions and live resolutions are never cached"
    assert "sealed pins only" in client.cache.stats()["cached"]


def test_a_download_that_does_not_match_its_checksum_is_refused():
    cache = PinCache()

    class Lying:
        class features:  # noqa: N801 - a stand-in for the resource namespace
            @staticmethod
            def download(ref, **kw):
                import io

                import pyarrow as pa
                import pyarrow.parquet as pq

                buf = io.BytesIO()
                pq.write_table(pa.table({"x": [1, 2, 3]}), buf)
                return {"data": buf.getvalue(), "manifest": {"checksum": "0" * 64}}

    with pytest.raises(ValidationFailed, match="does not match the checksum"):
        cache.pin_bytes(
            Lying(), "eq/px", {"content_hash": None, "pin_name": "q", "as_of_date": "x"}
        )


def test_a_warrant_hands_back_its_data_as_a_context_manager(sdk):
    clients, platform = sdk
    client = clients["devi"]
    clients["mick"].featureset("hdl/hdl_panel").pin(
        "h1", as_of=dt.date(2026, 1, 5), cascade=True
    ).wait()  # the manager pins; the developer trains
    created = client.training.create(
        "hdl",
        "hdl_calib",
        model="hdl/hdl_lin@v1",
        featureset="maya://featureset/hdl/hdl_panel#h1/2026-01-05",
        spec={"target": "y"},
    )
    warrant = client.warrant(created["id"])
    with warrant.data() as ds:
        assert ds.table.num_rows > 0
        assert "y" not in ds.X.columns and len(ds.y) == ds.table.num_rows
        assert ds.checksum, "the checksum a parameter upload must quote"
        checksum = ds.checksum
    assert ds.table is None, "leaving the block drops the frame"
    uploaded = warrant.upload_parameters({"a": 2.0}, data_checksum=checksum)
    assert uploaded["verified_data"] is True
    scored = warrant.score_holdout(parameter_set_id=uploaded["id"])
    assert scored.metrics.rows > 0


def test_a_record_without_a_client_says_so_rather_than_failing_obscurely():
    from maya.sdk.handles import FeatureHandle

    orphan = FeatureHandle({"name": "px"})
    with pytest.raises(MayaError, match="no client to act through"):
        orphan.ref
