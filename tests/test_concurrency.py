"""
Concurrency probes (plan gate 23, spec §15.3, §23): no lost updates, no deadlocks, no
duplicate pins — on SQLite and, with ``MAYA_TEST_PG_URL`` set, on PostgreSQL.

* **Parallel pin attempts.** Eight threads race to pin the same feature series and date,
  and eight more the same feature-set series and date: exactly one wins, every other is
  refused as a conflict (never a raw database error), and one pin is sealed.
* **Double-submit idempotency.** The same pin submitted concurrently under one
  idempotency key creates one job and one pin; a generic job submitted concurrently under
  one key is one job, returned to every caller.
* **Cascade deadlock probes.** Cascade pins whose member sets overlap — declared in
  opposite orders — run on parallel workers with the same series and date. Every job
  finishes inside a timeout (members are pinned in sorted id order, so no cycle can
  form), and afterwards every sealed feature-set pin refers only to sealed member pins
  that still exist: no cascade's rollback may remove a pin another cascade sealed on.
* **Cancellation mid-job.** A cascade cancelled after its second member is pinned stops
  at the next stage, rolls back every member pin it made, ends ``cancelled`` — and the
  same name and date can then be pinned. A pin job cancelled while still queued leaves
  its pin failed, not stuck ``materializing``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any, Callable

import pytest

from maya.core.errors import ConflictError
from tests.conftest import PX_DEF, approved_feature, price_csv

AS_OF = dt.date(2026, 1, 10)
TIMEOUT = 120.0


def race(n: int, fn: Callable[[int], Any]) -> list[tuple[str, Any]]:
    """Run ``fn(i)`` on ``n`` threads released together; ('ok', value) or ('err', exc)."""
    gate = threading.Barrier(n)
    out: list[tuple[str, Any]] = [("pending", None)] * n

    def run(i: int) -> None:
        gate.wait()
        try:
            out[i] = ("ok", fn(i))
        except Exception as exc:  # noqa: BLE001 - the outcome is what is asserted
            out[i] = ("err", exc)

    threads = [threading.Thread(target=run, args=(i,), daemon=True) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(TIMEOUT)
    assert not any(t.is_alive() for t in threads), "a racer never returned (deadlock?)"
    return out


def _refused_as_conflicts(outcomes: list[tuple[str, Any]]) -> None:
    errors = [v for kind, v in outcomes if kind == "err"]
    bad = [
        f"{type(e).__module__}.{type(e).__name__}: {e}"
        for e in errors
        if not isinstance(e, ConflictError)
    ]
    assert not bad, "a loser was not refused as a conflict:\n" + "\n".join(bad)


@pytest.fixture(scope="module")
def cw(world):
    for k in range(8):
        approved_feature(world, f"cc{k}", price_csv(10, bump=float(k)))
    return world


def _approved_set(w, name: str, features: list[str]) -> str:
    fs_def = {
        "index": ["date", "symbol"],
        "alignment": {"mode": "inner"},
        "members": [
            {"attr": f, "ref": f"maya://feature/eq/{f}@v1", "source_attr": "close"}
            for f in features
        ],
    }
    w.p.featuresets.create(w.devi, namespace="eq", name=name, definition=fs_def)
    w.p.featuresets.transition(w.devi, f"eq/{name}", 1, "submit")
    w.p.featuresets.transition(w.mick, f"eq/{name}", 1, "approve")
    return f"eq/{name}"


# -- parallel pin attempts -------------------------------------------------------------------
def test_parallel_pins_of_one_feature_series_and_date_one_wins(cw):
    w = cw
    mick = w.mick
    outcomes = race(
        8, lambda i: w.p.features.pin(mick, "eq/cc0", version_no=1, pin_name="race", as_of=AS_OF)
    )
    winners = [v for kind, v in outcomes if kind == "ok"]
    assert len(winners) == 1, outcomes
    _refused_as_conflicts(outcomes)
    w.drain()
    with w.p.uow() as uow:
        pins = uow.repo("feature_pins").list(pin_name="race")
        jobs = uow.repo("jobs").list(job_type="feature.pin")
    assert len(pins) == 1 and pins[0]["state"] == "sealed"
    assert sum(1 for j in jobs if j["params"]["pin_id"] == pins[0]["id"]) == 1


def test_parallel_pins_of_one_featureset_series_and_date_one_wins(cw):
    w = cw
    ref = _approved_set(w, "race_set", ["cc0", "cc1"])
    mick = w.mick
    outcomes = race(
        8,
        lambda i: w.p.featuresets.pin(
            mick, ref, version_no=1, pin_name="frace", as_of=AS_OF, cascade=True
        ),
    )
    assert sum(1 for kind, _ in outcomes if kind == "ok") == 1, outcomes
    _refused_as_conflicts(outcomes)
    w.drain()
    with w.p.uow() as uow:
        pins = uow.repo("feature_set_pins").list(pin_name="frace")
        members = uow.repo("feature_pins").list(pin_name="frace")
    assert [p["state"] for p in pins] == ["sealed"]
    assert len(members) == 2 and {m["state"] for m in members} == {"sealed"}


# -- double-submit idempotency ----------------------------------------------------------------
def test_a_double_submitted_pin_under_one_key_is_one_job_and_one_pin(cw):
    w = cw
    mick = w.mick
    outcomes = race(
        6,
        lambda i: w.p.features.pin(
            mick, "eq/cc1", version_no=1, pin_name="dbl", as_of=AS_OF, idempotency_key="click-1"
        ),
    )
    _refused_as_conflicts(outcomes)
    ok = [v for kind, v in outcomes if kind == "ok"]
    assert ok and len({v["job"]["id"] for v in ok}) == 1 and len({v["pin"]["id"] for v in ok}) == 1
    w.drain()
    with w.p.uow() as uow:
        assert uow.repo("jobs").count(idempotency_key="click-1") == 1
        pins = uow.repo("feature_pins").list(pin_name="dbl")
    assert len(pins) == 1 and pins[0]["state"] == "sealed"


def test_a_job_submitted_concurrently_under_one_key_is_one_job(cw):
    w = cw
    ran: list[dict[str, Any]] = []
    w.p.jobs.register("test.noop", lambda ctx, params: ran.append(params) or {"ok": True})

    def submit(i: int) -> str:
        with w.p.uow("tess") as uow:
            return w.p.jobs.submit(
                uow, "test.noop", {"n": 1}, owner="tess", idempotency_key="nightly-2026-01-10"
            )["id"]

    outcomes = race(8, submit)
    assert all(kind == "ok" for kind, _ in outcomes), outcomes
    assert len({v for _, v in outcomes}) == 1
    with w.p.uow("tess") as uow:
        with pytest.raises(ConflictError, match="different parameters"):
            w.p.jobs.submit(
                uow, "test.noop", {"n": 2}, owner="tess", idempotency_key="nightly-2026-01-10"
            )
    w.drain()
    assert ran == [{"n": 1}]


# -- cascade deadlock probes ------------------------------------------------------------------
def _slow_members(monkeypatch, w, delay: float = 0.02) -> None:
    """Widen the interleaving window between member pins without changing their outcome."""
    real = w.p.feature_data.materialize

    def slow(pin_id: str, actor: str) -> Any:
        time.sleep(delay)
        return real(pin_id, actor)

    monkeypatch.setattr(w.p.feature_data, "materialize", slow)


def _run_workers(w, n: int) -> None:
    """Run the queue on ``n`` parallel workers until it is empty, within the timeout."""

    def work(_: int) -> int:
        done = 0
        while w.p.jobs.run_one(f"probe-{_}"):
            done += 1
        return done

    outcomes = race(n, work)
    assert all(kind == "ok" for kind, _ in outcomes), outcomes


def _assert_sealed_pins_are_whole(w, pin_name: str) -> list[dict[str, Any]]:
    with w.p.uow() as uow:
        fs_pins = uow.repo("feature_set_pins").list(pin_name=pin_name)
        members = {p["id"]: p for p in uow.repo("feature_pins").list(pin_name=pin_name)}
    assert fs_pins and all(p["state"] in ("sealed", "failed") for p in fs_pins), [
        p["state"] for p in fs_pins
    ]
    for p in fs_pins:
        if p["state"] != "sealed":
            continue
        for ref, pid in p["member_pin_ids"].items():
            assert pid in members, f"sealed set pin refers to a removed member pin ({ref})"
            assert members[pid]["state"] == "sealed", (ref, members[pid]["state"])
    assert all(m["state"] == "sealed" for m in members.values()), (
        "a member pin was left behind unsealed"
    )
    return fs_pins


def test_overlapping_cascades_on_parallel_workers_all_finish_whole(cw, monkeypatch):
    w = cw
    names = [f"cc{k}" for k in range(8)]
    sets = [
        _approved_set(w, "ovl_a", names[0:5]),
        _approved_set(w, "ovl_b", list(reversed(names[2:7]))),
        _approved_set(w, "ovl_c", names[4:8] + names[0:2]),
    ]
    _slow_members(monkeypatch, w)
    mick = w.mick
    for ref in sets:
        w.p.featuresets.pin(mick, ref, version_no=1, pin_name="ovl", as_of=AS_OF, cascade=True)
    started = time.monotonic()
    _run_workers(w, 3)
    assert time.monotonic() - started < TIMEOUT
    fs_pins = _assert_sealed_pins_are_whole(w, "ovl")
    assert [p["state"] for p in fs_pins] == ["sealed"] * 3, [p.get("failure") for p in fs_pins]
    with w.p.uow() as uow:
        assert uow.repo("feature_pins").count(pin_name="ovl") == 8
        assert uow.repo("jobs").count(job_type="featureset.pin", state="succeeded") >= 3


def test_a_failing_cascade_never_removes_a_pin_another_cascade_sealed_on(cw, monkeypatch):
    """Two cascades share members; one of them fails on a member only it has. Its
    rollback must not delete a shared member pin the other cascade sealed on."""
    w = cw
    strict = dict(PX_DEF, quality=[{"check": "range", "attr": "close", "min": 0, "max": 1000}])
    approved_feature(w, "cc_bad", price_csv(10), definition=strict)
    # the data goes bad after approval: a restatement outside the contract's range
    w.p.features.ingest(w.dana, "eq/cc_bad", b"date,symbol,close\n2026-01-05,AAA,5000\n", fmt="csv")
    good = _approved_set(w, "shr_good", ["cc0", "cc1", "cc2"])
    doomed = _approved_set(w, "shr_doomed", ["cc0", "cc1", "cc2", "cc_bad"])
    _slow_members(monkeypatch, w)
    mick = w.mick
    for ref in (good, doomed):
        w.p.featuresets.pin(mick, ref, version_no=1, pin_name="shr", as_of=AS_OF, cascade=True)
    _run_workers(w, 2)
    fs_pins = {p["feature_set_id"]: p for p in _assert_sealed_pins_are_whole(w, "shr")}
    with w.p.uow() as uow:
        ids = {
            n: uow.repo("feature_sets").find_one(name=n)["id"] for n in ("shr_good", "shr_doomed")
        }
        assert uow.repo("feature_pins").count(pin_name="shr", state__ne="sealed") == 0
    assert fs_pins[ids["shr_doomed"]]["state"] == "failed"
    assert fs_pins[ids["shr_good"]]["state"] == "sealed", fs_pins[ids["shr_good"]].get("failure")


# -- cancellation --------------------------------------------------------------------------------
def test_a_cascade_cancelled_mid_job_rolls_back_and_frees_its_name(cw, monkeypatch):
    w = cw
    ref = _approved_set(w, "cancel_me", [f"cc{k}" for k in range(6)])
    out = w.p.featuresets.pin(w.mick, ref, version_no=1, pin_name="cxl", as_of=AS_OF, cascade=True)
    job_id = out["job"]["id"]
    real = w.p.feature_data.materialize
    done: list[str] = []

    def then_cancel(pin_id: str, actor: str) -> Any:
        result = real(pin_id, actor)
        done.append(pin_id)
        if len(done) == 2:  # the operator presses cancel while member 3 is next
            w.p.ops.cancel_job(w.mick, job_id)
        return result

    monkeypatch.setattr(w.p.feature_data, "materialize", then_cancel)
    w.drain()
    monkeypatch.undo()
    with w.p.uow() as uow:
        job = uow.repo("jobs").require(job_id)
        fsp = uow.repo("feature_set_pins").require(out["pin"]["id"])
        left = uow.repo("feature_pins").count(pin_name="cxl")
        rolled = uow.repo("audit_events").list(
            action="featureset.cascade_rolled_back", object_ref=fsp["id"]
        )
    assert len(done) == 2, "the cascade kept pinning after cancellation"
    assert job["state"] == "cancelled" and fsp["state"] == "failed"
    assert left == 0 and len(rolled) == 1 and rolled[0]["detail"]["member_pins_removed"] == 2
    again = w.p.featuresets.pin(
        w.mick, ref, version_no=1, pin_name="cxl", as_of=AS_OF, cascade=True
    )
    w.drain()
    with w.p.uow() as uow:
        assert uow.repo("feature_set_pins").require(again["pin"]["id"])["state"] == "sealed"
        assert uow.repo("feature_pins").count(pin_name="cxl", state="sealed") == 6


@pytest.mark.parametrize("kind", ["feature", "featureset"])
def test_a_pin_cancelled_while_queued_is_failed_not_stuck(cw, kind):
    w = cw
    if kind == "feature":
        out = w.p.features.pin(w.mick, "eq/cc3", version_no=1, pin_name="qcx", as_of=AS_OF)

        def again():
            return w.p.features.pin(w.mick, "eq/cc3", version_no=1, pin_name="qcx", as_of=AS_OF)

        table = "feature_pins"
    else:
        ref = _approved_set(w, "queued_cxl", ["cc3", "cc4"])
        out = w.p.featuresets.pin(
            w.mick, ref, version_no=1, pin_name="qcx", as_of=AS_OF, cascade=True
        )

        def again():
            return w.p.featuresets.pin(
                w.mick, ref, version_no=1, pin_name="qcx", as_of=AS_OF, cascade=True
            )

        table = "feature_set_pins"
    assert w.p.ops.cancel_job(w.mick, out["job"]["id"])["state"] == "cancelled"
    w.drain()
    with w.p.uow() as uow:
        pin = uow.repo(table).require(out["pin"]["id"])
    assert pin["state"] == "failed" and "cancel" in (pin.get("failure") or "")
    redo = again()
    w.drain()
    with w.p.uow() as uow:
        assert uow.repo(table).require(redo["pin"]["id"])["state"] == "sealed"


def test_what_a_cascade_does_with_each_kind_of_existing_member_pin():
    """The decision table behind the probes above, case by case."""
    from maya.services.featuresets import FeatureSetService

    class Repo:
        def __init__(self, rows):
            self.rows = rows

        def get(self, key):
            return self.rows.get(key)

    class Uow:
        def repo(self, name):
            assert name == "feature_set_pins"
            return Repo(
                {
                    "busy": {"state": "materializing"},
                    "done": {"state": "sealed"},
                    "dead": {"state": "failed"},
                }
            )

    def pin(state, owner=None):
        return {
            "state": state,
            "pin_name": "q",
            "as_of_date": AS_OF,
            "provenance": {"cascade_of": owner} if owner else {},
        }

    act = FeatureSetService._member_action
    assert act(Uow(), None, "me") == "create"
    assert act(Uow(), pin("sealed"), "me") == "reuse"  # a direct pin
    assert act(Uow(), pin("sealed", "done"), "me") == "reuse"  # its cascade sealed
    assert act(Uow(), pin("sealed", "busy"), "me") == "wait"  # may yet roll back
    assert act(Uow(), pin("sealed", "me"), "me") == "reuse"
    assert act(Uow(), pin("materializing", "busy"), "me") == "wait"
    assert act(Uow(), pin("materializing", "me"), "me") == "replace"  # my own leftover
    assert act(Uow(), pin("materializing", "dead"), "me") == "replace"  # a dead cascade's
    assert act(Uow(), pin("failed", "busy"), "me") == "replace"
    assert act(Uow(), pin("requested"), "me") == "replace"
    with pytest.raises(ConflictError, match="direct pin request"):
        act(Uow(), pin("materializing"), "me")
