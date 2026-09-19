"""
Lake maintenance (§7.4): compaction and vacuum of every lake table, leaving
sealed pins, previews and as-of-knowledge answers exactly as they were.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt

import pytest

from maya.core.errors import PermissionDenied
from tests.conftest import World, approved_feature, build_platform, price_csv


@pytest.fixture(scope="module")
def lake():
    platform = build_platform(["--lake.maintenance.vacuum_retention_hours=0"])
    w = World(platform)
    platform.access.create_namespace(w.admin, name="eq")
    yield w
    platform.shutdown()


def test_compaction_and_vacuum_change_nothing_anyone_can_read(lake):
    w = lake
    ref = approved_feature(w, "busy", price_csv(5))
    known = dt.datetime(2026, 3, 1, tzinfo=dt.timezone.utc)
    for k in range(1, 8):                      # many small restatements: many small files
        w.p.features.ingest(w.dana, ref, price_csv(5, bump=float(k)), fmt="csv",
                            knowledge_time=known + dt.timedelta(days=k))
    v1 = f"maya://feature/{ref}@v1"
    pin = w.p.features.pin(w.mick, ref, version_no=1, pin_name="eom", as_of=dt.date(2026, 1, 31))
    w.drain()
    latest = w.p.features.preview(w.dana, v1)["rows"]
    early = w.p.features.preview(w.dana, v1, as_of_known=known + dt.timedelta(days=2))["rows"]
    files_before = sum(len(w.p.lake.delta.files(t)) for t in w.p.lake.tables())

    out = w.p.ops.lake_maintenance(w.admin)
    assert out["filesRemoved"] > out["filesAdded"] and out["vacuumed"] == out["filesRemoved"]
    assert sum(len(w.p.lake.delta.files(t)) for t in w.p.lake.tables()) < files_before
    assert w.p.features.preview(w.dana, v1)["rows"] == latest
    assert w.p.features.preview(w.dana, v1, as_of_known=known + dt.timedelta(days=2))[
        "rows"] == early
    integrity = w.p.ops.verify_integrity(w.admin)
    assert integrity["drift"] == [] and integrity["checked"] >= 1
    with w.p.uow() as uow:
        audit = uow.repo("audit_events").list(action="lake.maintained")[-1]["detail"]
    assert audit["filesRemoved"] == out["filesRemoved"] and audit["tables"] >= 2
    again = w.p.ops.lake_maintenance(w.admin)
    assert again["filesRemoved"] == 0 and again["vacuumed"] == 0
    assert pin is not None


def test_only_admins_and_techops_maintain_the_lake(lake):
    with pytest.raises(PermissionDenied):
        lake.p.ops.lake_maintenance(lake.dana)
    assert lake.p.ops.lake_maintenance(lake.tess)["tables"]


def test_the_scheduler_runs_it_daily(lake):
    tasks = {name: seconds for name, seconds, _ in lake.p.scheduler.tasks}
    assert tasks["lake.maintenance"] == 86400
