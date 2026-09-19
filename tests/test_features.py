"""
Features end to end through the service layer: SC-1 (byte-identical
re-resolution, with the negative case in the same test), SC-11 (point-in-time
after a restatement), SC-12 (an unchanged month costs its delta), quality
contracts blocking pins, pin requests, derived and inherited features,
scratch, downloads.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import io

import pyarrow.parquet as pq
import pytest

from maya.core.errors import (NotApproved, PermissionDenied, QualityCheckFailed,
                              ValidationFailed)
from tests.conftest import PX_DEF, approved_feature, price_csv


def _pin(w, ref, name, as_of, version=1, **kw):
    out = w.p.features.pin(w.mick, ref, version_no=version, pin_name=name, as_of=as_of, **kw)
    w.drain()
    with w.p.uow() as uow:
        return uow.repo("feature_pins").require(out["pin"]["id"])


def test_sc1_repin_is_byte_identical_and_changed_data_is_not(world):
    ref = approved_feature(world, "sc1", price_csv(30))
    a = _pin(world, ref, "s1", dt.date(2026, 1, 30))
    b = _pin(world, ref, "s2", dt.date(2026, 1, 30))
    assert a["state"] == b["state"] == "sealed"
    assert a["content_hash"] == b["content_hash"]
    assert b["bytes_new"] == 0, "an identical pin must write no new fragment"
    # the negative case, same test: changed data must hash differently
    world.p.features.ingest(world.dana, ref, price_csv(30, bump=0.25), fmt="csv")
    c = _pin(world, ref, "s3", dt.date(2026, 1, 30))
    assert c["content_hash"] != a["content_hash"]


def test_sc1_hash_survives_reread_and_integrity_scan(world):
    ref = approved_feature(world, "reread", price_csv(10))
    pin = _pin(world, ref, "eom", dt.date(2026, 1, 10))
    result = world.p.ops.verify_integrity(world.admin)
    mine = [r for r in result["results"] if "/reread#" in r["pin"]]
    assert mine and all(r["ok"] for r in mine)
    download = world.p.features.download(world.dana, f"maya://feature/eq/reread#eom/2026-01-10")
    assert download["manifest"]["content_hash"] == pin["content_hash"]


def test_sc11_point_in_time_after_restatement(world):
    ref = approved_feature(world, "restated", price_csv(5))
    before = dt.datetime.now(dt.timezone.utc)
    restated = price_csv(5, bump=7.0)
    out = world.p.features.ingest(world.dana, ref, restated, fmt="csv",
                                  knowledge_time=before + dt.timedelta(seconds=5))
    assert out["restatement"] is True
    old = world.p.features.preview(world.dana, f"maya://feature/{ref}@v1", as_of_known=before)
    new = world.p.features.preview(world.dana, f"maya://feature/{ref}@v1",
                                   as_of_known=before + dt.timedelta(minutes=1))
    assert old["rows"][0]["close"] == pytest.approx(100.0)
    assert new["rows"][0]["close"] == pytest.approx(107.0)


def test_sc12_unchanged_month_costs_under_five_percent(world):
    """A new pin writes its delta plus the tail fragment it lands in (≈ one fragment
    target, 512 rows by default), so the ratio is size-relative: it holds for real
    panels and needs a test panel far larger than one fragment — 40,000 rows here.

    Fragment boundaries are content-defined, and a row's content includes its
    knowledge time; the tail fragment's length is therefore roughly geometric around
    the target. The knowledge times are fixed so the test is deterministic: with
    wall-clock ingest times it failed about 3% of runs, which is the property holding
    in expectation rather than for every pin."""
    world.p.features.create(world.dana, namespace="eq", name="monthly", definition=PX_DEF)
    ref = "eq/monthly"
    symbols = tuple(f"S{i:02d}" for i in range(40))
    known = dt.datetime(2028, 9, 27, 18, tzinfo=dt.timezone.utc)
    world.p.features.ingest(world.dana, ref, price_csv(1000, symbols=symbols), fmt="csv",
                            knowledge_time=known)
    world.p.features.transition(world.dana, ref, 1, "submit")
    world.p.features.transition(world.mick, ref, 1, "approve")
    first = _pin(world, ref, "m1", dt.date(2028, 9, 26),
                 as_of_known=known + dt.timedelta(hours=1))
    world.p.features.ingest(world.dana, ref, price_csv(10, symbols=symbols, start_day=1001),
                            fmt="csv", knowledge_time=known + dt.timedelta(days=10))
    second = _pin(world, ref, "m2", dt.date(2028, 10, 6),
                  as_of_known=known + dt.timedelta(days=10, hours=1))
    assert second["row_count"] > first["row_count"]
    assert second["bytes_new"] < 0.05 * second["bytes_total"], (
        f"marginal {second['bytes_new']} of {second['bytes_total']}")


def test_quality_contract_blocks_the_pin(world):
    d = dict(PX_DEF, resolution={"grid": {"calendar": "natural_days"}, "rules": {}})
    ref = approved_feature(world, "gappy", price_csv(3), definition=d)
    csv = b"date,symbol,close\n2026-01-10,AAA,1\n"
    world.p.features.ingest(world.dana, ref, csv, fmt="csv")
    pin = _pin(world, ref, "q", dt.date(2026, 1, 10))
    assert pin["state"] == "failed" and "not_null" in pin["failure"]


def test_only_approved_versions_pin_and_designer_needs_approval(world):
    world.p.features.create(world.dana, namespace="eq", name="unapproved", definition=PX_DEF)
    with pytest.raises(NotApproved):
        world.p.features.pin(world.mick, "eq/unapproved", version_no=1, pin_name="x",
                             as_of=dt.date(2026, 1, 1))
    ref = approved_feature(world, "requested", price_csv(5))
    out = world.p.features.pin(world.dana, ref, version_no=1, pin_name="req",
                               as_of=dt.date(2026, 1, 5))
    assert out["job"] is None and out["pin"]["state"] == "requested"
    with pytest.raises(PermissionDenied):
        world.p.features.approve_pin_request(world.dana, out["pin"]["id"])
    world.p.features.approve_pin_request(world.mick, out["pin"]["id"])
    world.drain()
    with world.p.uow() as uow:
        assert uow.repo("feature_pins").require(out["pin"]["id"])["state"] == "sealed"


def test_idempotency_key_never_pins_twice(world):
    ref = approved_feature(world, "idem", price_csv(5))
    a = world.p.features.pin(world.mick, ref, version_no=1, pin_name="i1",
                             as_of=dt.date(2026, 1, 5), idempotency_key="k-1")
    with pytest.raises(Exception):
        world.p.features.pin(world.mick, ref, version_no=1, pin_name="i1",
                             as_of=dt.date(2026, 1, 5), idempotency_key="k-1")
    with world.p.uow() as uow:
        assert uow.repo("jobs").count(idempotency_key="k-1") == 1
    assert a["job"]["idempotency_key"] == "k-1"


def test_segregation_of_duties_refuses_self_approval(world):
    """One person holding designer and manager roles (a small desk) cannot approve their
    own submission under strict SoD — and can when the namespace says so (§28.9)."""
    world.p.access.create_user(world.admin, username="solo", password="Test-password-1",
                               roles=["feature_designer", "feature_manager"])
    solo = world.principal("solo")
    world.p.access.create_namespace(world.admin, name="desk", preset="regulated")
    for name in ("selfie", "selfie2"):
        world.p.features.create(solo, namespace="desk", name=name, definition=PX_DEF)
        world.p.features.ingest(solo, f"desk/{name}", price_csv(3), fmt="csv")
        world.p.features.transition(solo, f"desk/{name}", 1, "submit")
    with pytest.raises(PermissionDenied, match="segregation"):
        world.p.features.transition(solo, "desk/selfie", 1, "approve")
    world.p.access.update_namespace(world.admin, "desk", {"sod": "none"})
    out = world.p.features.transition(solo, "desk/selfie2", 1, "approve")
    assert out["state"] == "approved"


def test_cosmetic_edit_does_not_mint_a_version(world):
    ref = approved_feature(world, "cosmetic", price_csv(3))
    world.p.features.new_draft(world.dana, ref)
    with pytest.raises(ValidationFailed, match="hashes identically"):
        world.p.features.transition(world.dana, ref, 2, "submit")


def test_change_classes(world):
    ref = approved_feature(world, "classy", price_csv(3))
    world.p.features.new_draft(world.dana, ref)
    d = dict(PX_DEF, schema=PX_DEF["schema"] + [{"name": "vol", "type": "float64"}])
    world.p.features.update_draft(world.dana, ref, d)
    world.p.features.transition(world.dana, ref, 2, "submit")
    with world.p.uow() as uow:
        f = uow.repo("features").find_one(name="classy")
        v2 = uow.repo("feature_versions").find_one(feature_id=f["id"], version_no=2)
    assert v2["change_class"] == "additive"


def test_derived_union_and_inheritance(world):
    a = approved_feature(world, "vendor_a", price_csv(5, symbols=("AAA",)))
    b = approved_feature(world, "vendor_b", price_csv(5, symbols=("BBB",)))
    derived = {"index": ["date", "symbol"], "index_types": PX_DEF["index_types"],
               "schema": PX_DEF["schema"],
               "source": {"type": "derived", "derivation": {
                   "operator": "union", "operands": [f"maya://feature/{a}@v1",
                                                     f"maya://feature/{b}@v1"],
                   "options": {"collision": "error"}}},
               "resolution": {"grid": "as_is", "rules": {}}, "transform": [], "quality": []}
    ref = approved_feature(world, "both", definition=derived)
    rows = world.p.features.preview(world.dana, f"maya://feature/{ref}@v1")
    assert rows["total_rows"] == 10
    child = {"extends": {"parent": f"maya://feature/{a}@v1", "binding": "pinned",
                         "override": {"filter": "close > 101"}}}
    cref = approved_feature(world, "a_filtered", definition=child)
    out = world.p.features.preview(world.dana, f"maya://feature/{cref}@v1")
    assert 0 < out["total_rows"] < 5
    lineage = world.p.ops.lineage(f"maya://feature/{ref}@v1", direction="upstream")
    assert any(e["type"] == "operand_of" for e in lineage["edges"])


def test_tracking_binding_is_blocked_in_production(world):
    world.p.access.create_namespace(world.admin, name="prodns", production=True)
    child = {"extends": {"parent": "maya://feature/eq/vendor_a", "binding": "tracking",
                         "override": {}}}
    world.p.features.create(world.dana, namespace="prodns", name="tracker", definition=child)
    with pytest.raises(ValidationFailed, match="production"):
        world.p.features.transition(world.dana, "prodns/tracker", 1, "submit")


def test_scratch_quick_feature_has_zero_ceremony(world):
    out = world.p.features.quick(world.dana, price_csv(4), name="scratchy")
    assert out["ref"] == "maya://feature/scratch.dana/scratchy"
    feature = world.p.features.get(world.dana, out["ref"])
    assert feature["ungoverned"] and feature["versions"][0]["state"] == "approved"
    with pytest.raises(PermissionDenied):
        world.p.features.get(world.mick, out["ref"])


def test_download_formats_and_csv_encoding(world):
    ref = approved_feature(world, "dl", price_csv(4))
    _pin(world, ref, "d", dt.date(2026, 1, 4))
    pin_ref = "maya://feature/eq/dl#d/2026-01-04"
    parquet = world.p.features.download(world.dana, pin_ref, fmt="parquet")
    assert pq.read_table(io.BytesIO(parquet["data"])).num_rows == 8
    csv = world.p.features.download(world.dana, pin_ref, fmt="csv")
    assert b"AAA" in csv["data"]
    with world.p.uow() as uow:
        assert uow.repo("audit_events").count(action="data.downloaded") >= 2


def test_unsupported_source_is_refused_by_name(world):
    d = dict(PX_DEF, source={"type": "python"})
    world.p.features.create(world.dana, namespace="eq", name="pysrc", definition=d)
    with pytest.raises(ValidationFailed, match="python"):
        world.p.features.transition(world.dana, "eq/pysrc", 1, "submit")


def test_quality_failure_raised_directly_by_materialize(world):
    d = dict(PX_DEF, quality=[{"check": "range", "attr": "close", "min": 0, "max": 50}])
    ref = approved_feature(world, "ranged", None, definition=d)
    world.p.features.ingest(world.dana, ref, price_csv(3), fmt="csv")
    out = world.p.features.pin(world.mick, ref, version_no=1, pin_name="r",
                               as_of=dt.date(2026, 1, 3))
    with pytest.raises(QualityCheckFailed):
        world.p.feature_data.materialize(out["pin"]["id"], "mick")
