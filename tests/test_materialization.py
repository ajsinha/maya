"""
Feature-set pin materialization per namespace (§6, revision 2.3): ``always`` writes
the resolved output at sealing; ``on_demand`` writes it at the first read; ``never``
writes nothing and replays from the member pins on every read.

Whatever the policy, a pin is the same content: the replay must reproduce the hash
sealed at pinning, or nothing is served and integrity verification reports drift.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt

import pytest

from maya.core.errors import IntegrityError, ValidationFailed
from tests.conftest import approved_feature, price_csv

AS_OF = dt.date(2026, 1, 8)


@pytest.fixture(scope="module")
def sets(world):
    w = world
    w.p.access.create_namespace(w.admin, name="mat")
    ref = approved_feature(w, "matpx", price_csv(8), ns="mat")
    out = {}
    for day, policy in enumerate(("always", "on_demand", "never"), start=1):
        ns = f"mat_{policy}"
        w.p.access.create_namespace(w.admin, name=ns)
        if policy != "always":
            w.p.access.update_namespace(w.admin, ns, {"materialize_policy": policy})
        # distinct definitions (no near-copies), identical output: each starts before the data
        fs = {"index": ["date", "symbol"], "filters": {"start": f"2020-01-0{day}"}, "members": [
            {"attr": "close", "ref": f"maya://feature/{ref}@v1", "source_attr": "close"}]}
        w.p.featuresets.create(w.devi, namespace=ns, name="panel", definition=fs)
        w.p.featuresets.transition(w.devi, f"{ns}/panel", 1, "submit")
        w.p.featuresets.transition(w.mick, f"{ns}/panel", 1, "approve")
        w.p.featuresets.pin(w.mick, f"{ns}/panel", version_no=1, pin_name="m", as_of=AS_OF,
                            cascade=True)
        w.drain()
        out[policy] = f"maya://featureset/{ns}/panel#m/{AS_OF.isoformat()}"
    return w, out


def _pin(w, ref):
    return w.p.featuresets.load(ref)[3]


def _frame(w, ref):
    return w.p.featuresets.resolve_ref(w.mick, ref).df


def test_every_policy_seals_the_same_content(sets):
    w, refs = sets
    hashes = {p: _pin(w, r)["content_hash"] for p, r in refs.items()}
    assert len(set(hashes.values())) == 1, hashes
    assert _pin(w, refs["always"])["lake_table"]
    assert _pin(w, refs["never"])["lake_table"] is None
    assert _pin(w, refs["on_demand"])["lake_table"] is None
    assert not w.p.featuresets.stored(_pin(w, refs["never"]))


def test_never_replays_every_read_and_serves_the_same_rows(sets):
    w, refs = sets
    expected = _frame(w, refs["always"])
    for _ in range(2):
        assert _frame(w, refs["never"]).equals(expected)
    assert _pin(w, refs["never"])["lake_table"] is None, "never is never written"


def test_on_demand_is_written_at_the_first_read(sets):
    w, refs = sets
    expected = _frame(w, refs["always"])
    assert _frame(w, refs["on_demand"]).equals(expected)
    pin = _pin(w, refs["on_demand"])
    assert w.p.featuresets.stored(pin) and pin["lake_table"]
    assert _frame(w, refs["on_demand"]).equals(expected)       # now from the lake
    with w.p.uow() as uow:
        assert uow.repo("audit_events").find_one(action="pin.materialized")


def test_integrity_verification_replays_unwritten_pins(sets):
    w, refs = sets
    report = w.p.ops.verify_integrity(w.admin)
    mine = [r for r in report["results"] if "mat_" in r["pin"]]
    assert len(mine) == 3 and all(r["ok"] for r in mine), mine
    assert any(r.get("replayed") for r in mine)


def test_a_replay_that_does_not_reproduce_the_seal_is_not_served(sets):
    w, refs = sets
    pin = _pin(w, refs["never"])
    with w.p.uow() as uow:
        uow.repo("feature_set_pins").update(pin["id"], {"content_hash": "0" * 64})
    try:
        with pytest.raises(IntegrityError, match="did not reproduce"):
            _frame(w, refs["never"])
        drift = w.p.ops.verify_integrity(w.admin)["drift"]
        assert any("mat_never" in d["pin"] for d in drift)
    finally:
        with w.p.uow() as uow:
            uow.repo("feature_set_pins").update(pin["id"], {"content_hash": pin["content_hash"]})


def test_an_unknown_policy_is_refused(sets):
    w, _ = sets
    with pytest.raises(ValidationFailed, match="materialize_policy"):
        w.p.access.update_namespace(w.admin, "mat_always", {"materialize_policy": "lazy"})
