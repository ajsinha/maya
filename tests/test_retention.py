"""
Retention (§7.3): cold pins named, retired pins archived, an archive that no longer hashes
true refused. None of §7.3 was built — pins were never deleted, which is what it asks for,
but nothing said which had gone cold and nothing could archive a retired one.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pytest

from maya.core.errors import NotApproved, PermissionDenied, ValidationFailed
from tests.conftest import approved_feature, price_csv


@pytest.fixture(scope="module")
def pinned(world):
    w = world
    w.p.access.create_namespace(w.admin, name="ret")
    ref = approved_feature(w, "ret_px", price_csv(8), ns="ret")
    for day in (5, 6):
        w.p.features.pin(w.mick, ref, version_no=1, pin_name="eod", as_of=dt.date(2026, 1, day))
    w.drain()
    with w.p.uow() as uow:
        feature = uow.repo("features").find_one(name="ret_px")
        pins = uow.repo("feature_pins").list(feature_id=feature["id"], state="sealed")
    assert len(pins) == 2, pins
    return w, ref, pins


def test_reading_a_pin_is_remembered_so_cold_can_mean_something(pinned):
    w, ref, pins = pinned
    w.p.features.preview(w.mick, f"maya://feature/{ref}#eod/2026-01-05")
    with w.p.uow() as uow:
        read = uow.repo("feature_pins").require(pins[0]["id"])
    assert read["last_read_at"] is not None


def test_cold_names_the_pins_nobody_has_read(pinned):
    w, _, pins = pinned
    fresh = w.p.retention.cold_report(w.admin, days=3650)
    assert fresh["cold_pins"] == 0 and fresh["warm_pins"] >= 2
    with w.p.uow("admin") as uow:  # the estate ages
        uow.repo("feature_pins").update(
            pins[1]["id"], {"last_read_at": dt.datetime.now(dt.UTC) - dt.timedelta(days=400)}
        )
    cold = w.p.retention.cold_report(w.admin, days=365)
    assert cold["cold_pins"] == 1 and cold["cold_bytes"] > 0
    assert [p["id"] for p in cold["pins"]] == [pins[1]["id"]]
    assert "object-store backend" in cold["note"], "MAYA names cold pins; it does not move them"


def test_only_a_retired_pin_is_archived_and_only_by_an_administrator(pinned):
    w, _, pins = pinned
    with pytest.raises(NotApproved, match="Only a retired pin"):
        w.p.retention.archive(w.admin, pins[0]["id"])
    w.p.features.retire_pin(w.admin, pins[0]["id"], "superseded by the January restatement")
    with pytest.raises(PermissionDenied, match="for administrators"):
        w.p.retention.archive(w.mick, pins[0]["id"])


def test_an_archived_pin_reads_back_and_a_damaged_archive_is_refused(pinned):
    w, _, pins = pinned
    pin_id = pins[0]["id"]
    with w.p.uow() as uow:
        if uow.repo("feature_pins").require(pin_id)["state"] != "retired":
            w.p.features.retire_pin(w.admin, pin_id, "superseded")
    out = w.p.retention.archive(w.admin, pin_id)
    assert out["rows"] > 0 and out["bytes"] > 0 and out["blob"]
    assert "not deleted" in out["note"], "the fragments are shared and stay"
    again = w.p.retention.archive(w.admin, pin_id)
    assert again["already"] and again["blob"] == out["blob"], "archiving twice is one archive"
    back = w.p.retention.restore(w.admin, pin_id)
    assert back["verified"] and back["table"].num_rows == out["rows"]
    assert back["manifest"]["content_hash"] == pins[0]["content_hash"]
    assert back["manifest"]["retire_reason"]
    with w.p.uow("admin") as uow:  # the archive rots
        uow.repo("feature_pins").update(pin_id, {"content_hash": "0" * 64})
    with pytest.raises(ValidationFailed, match="no longer hashes"):
        w.p.retention.restore(w.admin, pin_id)


def test_a_pin_that_was_never_archived_says_so(pinned):
    w, _, pins = pinned
    with pytest.raises(ValidationFailed, match="not been archived"):
        w.p.retention.restore(w.admin, pins[1]["id"])


def test_the_collector_removes_only_fragments_no_pin_references(pinned):
    """§29.3's collector: provably safe, which means the proof is the order of the checks.
    A fragment is a candidate only if no pin row of *any* state names it — so the orphan
    here is made the way real ones are, by a pin row going away and its bytes staying."""
    w, ref, pins = pinned
    lake_table = w.p.lake.rel(w.p.lake.table_path("pins", "ret", "ret_px"))
    w.p.features.pin(w.mick, ref, version_no=1, pin_name="doomed", as_of=dt.date(2026, 2, 2))
    w.drain()
    with w.p.uow("admin") as uow:
        doomed = uow.repo("feature_pins").find_one(pin_name="doomed")
        loose = set(doomed["fragments"])
        uow.repo("feature_pins").delete(doomed["id"])
    claimed = set()
    with w.p.uow() as uow:
        for row in uow.repo("feature_pins").list():
            claimed.update(row["fragments"] or [])
    loose -= claimed  # the fragments this pin alone held
    plan = w.p.retention.collect(w.admin, dry_run=True)
    assert plan["dry_run"] and plan["orphans"] >= len(loose) and loose
    assert "nothing was removed" in plan["note"]
    with w.p.uow() as uow:
        before = uow.repo("fragments").count()
    done = w.p.retention.collect(w.admin, dry_run=False)
    assert done["collected"] >= len(loose) and done["files_removed"] >= 1
    with w.p.uow() as uow:
        assert uow.repo("fragments").count() == before - done["collected"]
        for digest in loose:
            assert uow.repo("fragments").find_one(hash=digest, lake_table=lake_table) is None
    # every surviving pin still reads: nothing it references was touched
    for pin in pins:
        with w.p.uow() as uow:
            row = uow.repo("feature_pins").get(pin["id"])
        if row and row["state"] == "sealed":
            table = w.p.lake.read_pin("pins", "ret", "ret_px", row["fragments"])
            assert table.num_rows == row["row_count"]
    assert w.p.ops.verify_integrity(w.admin)["drift"] == []


def test_the_collector_is_for_administrators_and_refuses_a_racing_pass(pinned):
    w, _, _ = pinned
    with pytest.raises(PermissionDenied, match="for administrators"):
        w.p.retention.collect(w.mick, dry_run=True)
    import datetime as _dt

    with w.p.uow("admin") as uow:  # a pin created "now" means a pass cannot prove anything
        feature = uow.repo("features").find_one(name="ret_px")
        version = uow.repo("feature_versions").find_one(feature_id=feature["id"])
        uow.repo("feature_pins").add(
            {
                "feature_id": feature["id"],
                "feature_version_id": version["id"],
                "pin_name": "racing",
                "as_of_date": _dt.date(2026, 3, 1),
                "as_of_known": _dt.datetime.now(_dt.UTC) + _dt.timedelta(minutes=5),
                "state": "materializing",
                "fragments": [],
                "created_at": _dt.datetime.now(_dt.UTC) + _dt.timedelta(minutes=5),
            }
        )
    out = w.p.retention.collect(w.admin, dry_run=False)
    assert out["collected"] == 0 and "cannot prove" in out["refused"]
