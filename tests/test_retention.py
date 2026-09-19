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
