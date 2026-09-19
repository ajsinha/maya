"""
Job fairness and backpressure (§15.2, §15.4).

The thing being proved is the one the specification actually promises: that one
person's campaign cannot starve everyone else. So the tests are written as that
scenario — one user queues ten jobs, another queues one — and assert on the
*order the queue hands them out*, which is the only place fairness is either
real or absent. The backpressure tests assert that the refusal happens before a
row is written and that it says how long to wait, because a refusal without a
number is indistinguishable from a failure.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pytest

from maya.core.errors import QuotaExceeded
from maya.jobs.queue import Fairness
from tests.conftest import World, build_platform


@pytest.fixture(scope="module")
def jobs():
    platform = build_platform()
    w = World(platform)
    platform.jobs.register("test.noop", lambda ctx, params: {"ok": True})
    yield w
    platform.shutdown()


def _queue(w, owner: str, n: int, *, job_type: str = "test.noop") -> list[str]:
    ids = []
    for i in range(n):
        with w.p.uow(owner) as uow:
            ids.append(w.p.jobs.submit(uow, job_type, {"i": i, "owner": owner}, owner=owner)["id"])
    return ids


def _claim_order(w, count: int, **fairness) -> list[str]:
    """The owners the queue hands out, in order, without running anything."""
    owners = []
    for i in range(count):
        with w.p.uow("system") as uow:
            job = uow.repo("jobs").claim_next(f"w{i}", **fairness)
            if job is None:
                break
            owners.append(job["owner"])
    return owners


def _drain_all(w) -> None:
    with w.p.uow("system") as uow:
        for job in uow.repo("jobs").list(limit=10000):
            if job["state"] in ("queued", "running"):
                uow.repo("jobs").update(job["id"], {"state": "cancelled"})


def test_strict_arrival_order_starves_the_second_user(jobs):
    """The behaviour before §15.2 was built, kept as the contrast the fair test needs:
    with `fair=False` the campaign runs first and the other user waits for all of it."""
    w = jobs
    _drain_all(w)
    _queue(w, "dana", 10)
    _queue(w, "mona", 1)
    order = _claim_order(w, 11, fair=False, max_per_user=0)
    assert order == ["dana"] * 10 + ["mona"]
    _drain_all(w)


def test_fair_queueing_interleaves_one_persons_campaign_with_everyone_else(jobs):
    """§15.2: "a weighted queue so one person's fifty-feature campaign cannot starve
    everyone else". Each owner's first waiting job goes before anyone's second."""
    w = jobs
    _drain_all(w)
    _queue(w, "dana", 10)
    _queue(w, "mona", 1)
    _queue(w, "devi", 2)
    order = _claim_order(w, 13, fair=True, max_per_user=0)
    assert order[:3] == ["dana", "mona", "devi"], "every owner's first job goes first"
    assert order[3] == "dana" and order[4] == "devi", "then the seconds"
    assert order[5:] == ["dana"] * 8, "only then the rest of the campaign"
    assert order.index("mona") == 1, "the single job waited behind one, not behind ten"
    _drain_all(w)


def test_the_per_user_concurrency_cap_passes_over_an_owner_already_at_it(jobs):
    """§15.2's other half: a cap on how many of one owner's jobs run at once, so a
    campaign cannot hold every worker even when it is next in line."""
    w = jobs
    _drain_all(w)
    _queue(w, "dana", 5)
    _queue(w, "mona", 1)
    first = _claim_order(w, 1, fair=True, max_per_user=1)
    assert first == ["dana"]  # now running, so dana is at the cap
    second = _claim_order(w, 1, fair=True, max_per_user=1)
    assert second == ["mona"], "dana is at one running job, so the next claim skips dana"
    third = _claim_order(w, 1, fair=True, max_per_user=1)
    assert third == [], "both owners are at the cap; nothing else is handed out"
    _drain_all(w)


def test_a_full_queue_refuses_new_work_with_an_honest_wait_estimate(jobs):
    """§15.4: shed load deliberately, and say how long. The row is never written."""
    w = jobs
    _drain_all(w)
    w.p.jobs.fairness = Fairness(max_depth=3, per_user_queued=0, seconds_per_job=10)
    try:
        _queue(w, "dana", 3)
        with pytest.raises(QuotaExceeded) as exc:
            _queue(w, "mona", 1)
        assert "queue is full" in exc.value.message
        assert exc.value.context["reason"] == "queue_depth"
        assert exc.value.context["estimated_wait_seconds"] > 0
        assert str(exc.value.context["estimated_wait_seconds"]) in exc.value.message
        with w.p.uow() as uow:
            assert uow.repo("jobs").count(state="queued", owner="mona") == 0
    finally:
        w.p.jobs.fairness = Fairness()
        _drain_all(w)


def test_one_owner_cannot_fill_the_queue_on_their_own(jobs):
    """The per-user queued cap: the queue as a whole still has room, but this owner
    does not, so everyone else's submissions keep working."""
    w = jobs
    _drain_all(w)
    w.p.jobs.fairness = Fairness(max_depth=0, per_user_queued=2)
    try:
        _queue(w, "dana", 2)
        with pytest.raises(QuotaExceeded, match="too many jobs waiting"):
            _queue(w, "dana", 1)
        _queue(w, "mona", 1)  # somebody else is unaffected
        with w.p.uow() as uow:
            assert uow.repo("jobs").count(state="queued", owner="mona") == 1
    finally:
        w.p.jobs.fairness = Fairness()
        _drain_all(w)


def test_shedding_is_counted_and_the_wait_estimate_follows_the_workers(jobs):
    w = jobs
    from maya.observability.metrics import METRICS

    before = METRICS._counters.get("maya_job_shed_total", {}).copy()
    _drain_all(w)
    w.p.jobs.fairness = Fairness(max_depth=1)
    try:
        _queue(w, "dana", 1)
        with pytest.raises(QuotaExceeded):
            _queue(w, "mona", 1)
    finally:
        w.p.jobs.fairness = Fairness()
        _drain_all(w)
    after = METRICS._counters.get("maya_job_shed_total", {})
    assert sum(after.values()) > sum(before.values())
    w.p.jobs.n_workers = 4
    try:
        assert w.p.jobs.wait_estimate(100) == int(100 * 10 / 4)
    finally:
        w.p.jobs.n_workers = 2


def test_job_wait_time_is_measured_and_exported(jobs):
    """§20's "job queue wait time", which had no metric at all."""
    w = jobs
    from maya.observability.metrics import METRICS

    _drain_all(w)
    with w.p.uow("dana") as uow:
        job = w.p.jobs.submit(uow, "test.noop", {"waited": True}, owner="dana")
    with w.p.uow("system") as uow:  # pretend it was submitted a minute ago
        uow.repo("jobs").update(
            job["id"], {"created_at": job["created_at"] - dt.timedelta(seconds=60)}
        )
    assert w.p.jobs.run_one("t") is True
    body = METRICS.render()
    assert 'maya_job_wait_seconds_count{type="test.noop"}' in body
    row = METRICS._hist["maya_job_wait_seconds"][(("type", "test.noop"),)]
    assert row[-2] >= 55, "the wait recorded is the time it actually sat in the queue"


def test_fairness_is_read_from_configuration(jobs):
    f = Fairness.from_settings(jobs.p.settings)
    assert f.fair is True and f.per_user_concurrent == 4 and f.max_depth == 2000
    assert jobs.p.jobs.fairness.per_user_queued == 200
