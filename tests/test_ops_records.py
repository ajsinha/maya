"""
Two operations records §20 asks for and MAYA had nowhere to keep: a restore
drill's result, and integrity verification that happens on a schedule rather
than when somebody remembers.

Both are small, and both were "documented" before this: the drill in a Markdown
table inside a runbook, the verification in a sentence saying it should be
periodic. A row in the estate's own database is the difference between a claim
and a record — the model risk function can query it, an alert can fire on its
age, and it survives the person who ran the drill.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pytest

from maya.core.errors import PermissionDenied, ValidationFailed
from tests.conftest import World, build_platform


@pytest.fixture(scope="module")
def ops():
    platform = build_platform()
    w = World(platform)
    yield w
    platform.shutdown()


def test_a_drill_is_recorded_audited_and_readable(ops):
    w = ops
    row = w.p.ops.record_restore_drill(
        w.tess,
        dialect="postgresql",
        pins_checked=5,
        drift=0,
        duration_seconds=3.1,
        notes="pg_dump/pg_restore into a scratch database",
    )
    assert row["outcome"] == "passed" and row["verified_by"] == "tess"
    assert row["audit_chain_ok"] and row["anchors_ok"]
    listed = w.p.ops.restore_drills(w.admin)
    assert row["id"] in [d["id"] for d in listed]
    with w.p.uow() as uow:
        entry = uow.repo("audit_events").list(
            action="restore_drill.recorded", order_by=["-seq"], limit=1
        )[0]
    assert entry["actor"] == "tess" and entry["detail"]["pins_checked"] == 5
    assert entry["object_ref"].endswith(row["id"])


def test_a_failed_drill_is_recorded_as_failed_with_its_cause(ops):
    w = ops
    row = w.p.ops.record_restore_drill(
        w.tess,
        outcome="failed",
        pins_checked=5,
        drift=2,
        audit_chain_ok=True,
        anchors_ok=False,
        duration_seconds=90.0,
        notes="two pins drifted; storage.root restored from an older moment than the database",
    )
    assert row["outcome"] == "failed" and row["drift"] == 2 and row["anchors_ok"] is False
    with pytest.raises(ValidationFailed, match="did not pass"):
        w.p.ops.record_restore_drill(w.tess, outcome="passed", drift=1)
    with pytest.raises(ValidationFailed, match="passed"):
        w.p.ops.record_restore_drill(w.tess, outcome="inconclusive")


def test_only_administrators_and_techops_record_or_read_drills(ops):
    w = ops
    for principal in (w.dana, w.mona):
        with pytest.raises(PermissionDenied):
            w.p.ops.record_restore_drill(principal, pins_checked=1)
        with pytest.raises(PermissionDenied):
            w.p.ops.restore_drills(principal)


def test_the_drill_status_says_overdue_when_the_quarter_has_passed(ops):
    w = ops
    status = w.p.ops.restore_drill_status(w.admin)
    assert status["overdue"] is False and status["age_days"] == 0
    assert "last drill" in status["detail"]
    with w.p.uow() as uow:
        for drill in uow.repo("restore_drills").list():
            uow.repo("restore_drills").update(
                drill["id"],
                {"performed_at": drill["performed_at"] - dt.timedelta(days=200)},
            )
    stale = w.p.ops.restore_drill_status(w.admin)
    assert stale["overdue"] is True and stale["age_days"] > 92


def test_an_estate_with_no_drill_says_so_rather_than_looking_fine():
    platform = build_platform()
    w = World(platform)
    status = platform.ops.restore_drill_status(w.admin)
    assert status["last"] is None and status["overdue"] is True
    assert status["detail"] == "no restore drill has been recorded"
    platform.shutdown()


def test_the_drill_age_reaches_metrics_so_an_alert_can_fire_on_it(ops):
    """The SLO rules file alerts on ``maya_restore_drill_age_days``; that number has to
    exist in the exposition, or the alert is decoration."""
    from maya.observability.collectors import Collectors

    samples = {name: value for name, _, value in Collectors(ops.p).posture()}
    assert samples["maya_restore_drill_age_days"] >= 0
    assert samples["maya_default_admin_password"] in (0.0, 1.0)


def test_integrity_verification_is_scheduled_and_deduplicated():
    """§21.3 asks for *periodic* verification. Two nodes inside one interval must queue
    one sweep, not two full re-reads of the lake."""
    platform = build_platform()
    World(platform)  # the users the seed does not make; the sweep runs as 'system'
    first = platform.ops.schedule_integrity_verification()
    second = platform.ops.schedule_integrity_verification()
    assert first is not None and second["id"] == first["id"], "the interval window dedupes"
    with platform.uow() as uow:
        assert uow.repo("jobs").count(job_type="integrity.verify") == 1
        assert first["idempotency_key"].startswith("integrity.verify:")
    assert platform.jobs.drain() >= 1
    with platform.uow() as uow:
        assert uow.repo("jobs").require(first["id"])["state"] == "succeeded"
        assert uow.repo("audit_events").list(action="integrity.verified", limit=1)
    platform.shutdown()


def test_the_scheduler_registers_the_sweep_and_zero_turns_it_off():
    on = build_platform()
    try:
        assert "integrity.verify" in [name for name, _, _ in on.scheduler.tasks]
    finally:
        on.shutdown()
    off = build_platform(["--integrity.verify.interval_seconds=0"])
    try:
        assert "integrity.verify" not in [name for name, _, _ in off.scheduler.tasks]
        assert off.ops.schedule_integrity_verification() is None
    finally:
        off.shutdown()
