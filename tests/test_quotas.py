"""
Namespace storage quotas (§7.3). `quota_bytes` was stored on every namespace and read by
nothing, so the figure an administrator set meant nothing at all. It is now checked when a
pin is requested — against an estimate, before a worker spends minutes — and again against
the real figure before any bytes are written.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pytest

from maya.core.errors import QuotaExceeded
from maya.services import quota
from tests.conftest import approved_feature, price_csv


@pytest.fixture(scope="module")
def metered(world):
    w = world
    w.p.access.create_namespace(w.admin, name="qta")
    ref = approved_feature(w, "qta_px", price_csv(30), ns="qta")
    w.p.features.pin(w.mick, ref, version_no=1, pin_name="q", as_of=dt.date(2026, 1, 10))
    w.drain()
    return w, ref


def _namespace(w, name: str) -> dict:
    with w.p.uow() as uow:
        return uow.repo("namespaces").find_one(name=name)


def test_usage_counts_stored_bytes_once_per_fragment(metered):
    w, ref = metered
    ns = _namespace(w, "qta")
    with w.p.uow() as uow:
        held = quota.usage(uow, ns["id"])
    assert held["pins"] >= 1 and held["stored_bytes"] > 0
    assert held["logical_bytes"] >= held["stored_bytes"], "compression and dedup, not inflation"
    # a second pin of the same data adds nothing: the fragments are already there
    w.p.features.pin(w.mick, ref, version_no=1, pin_name="q2", as_of=dt.date(2026, 1, 10))
    w.drain()
    with w.p.uow() as uow:
        after = quota.usage(uow, ns["id"])
    assert after["pins"] == held["pins"] + 1
    assert after["stored_bytes"] == held["stored_bytes"], "the same bytes are not charged twice"


def test_a_pin_is_refused_when_the_namespace_has_no_room(metered):
    w, ref = metered
    ns = _namespace(w, "qta")
    with w.p.uow("admin") as uow:
        held = quota.usage(uow, ns["id"])["stored_bytes"]
        uow.repo("namespaces").update(ns["id"], {"quota_bytes": held + 10})
    try:
        with pytest.raises(QuotaExceeded) as exc:
            w.p.features.pin(w.mick, ref, version_no=1, pin_name="over", as_of=dt.date(2026, 1, 20))
        assert "quota" in exc.value.message and exc.value.context["stored_bytes"] == held
        with w.p.uow() as uow:
            assert uow.repo("feature_pins").find_one(pin_name="over") is None, (
                "nothing is left half-created"
            )
    finally:
        with w.p.uow("admin") as uow:
            uow.repo("namespaces").update(ns["id"], {"quota_bytes": None})


def test_the_real_figure_is_checked_before_bytes_are_written(metered):
    """The estimate can be wrong — a first pin has nothing to estimate from. The writer's
    own figure is checked too, so the quota holds even then."""
    w, _ = metered
    fresh = approved_feature(w, "qta_new", price_csv(30, ("XXX", "YYY")), ns="qta")
    ns = _namespace(w, "qta")
    with w.p.uow("admin") as uow:
        uow.repo("namespaces").update(ns["id"], {"quota_bytes": 1})
    try:
        w.p.features.pin(
            w.mick, fresh, version_no=1, pin_name="firstever", as_of=dt.date(2026, 1, 20)
        )
        w.drain()
        with w.p.uow() as uow:
            pin = uow.repo("feature_pins").find_one(pin_name="firstever")
        assert pin["state"] == "failed" and "quota" in (pin["failure"] or "").lower()
    finally:
        with w.p.uow("admin") as uow:
            uow.repo("namespaces").update(ns["id"], {"quota_bytes": None})


def test_a_namespace_without_a_quota_is_not_limited(metered):
    w, ref = metered
    ns = _namespace(w, "qta")
    assert ns["quota_bytes"] is None
    w.p.features.pin(w.mick, ref, version_no=1, pin_name="free", as_of=dt.date(2026, 1, 25))
    w.drain()
    with w.p.uow() as uow:
        assert uow.repo("feature_pins").find_one(pin_name="free")["state"] == "sealed"


def test_a_feature_reports_its_footprint_and_what_one_more_pin_would_cost(metered):
    w, ref = metered
    report = w.p.features.footprint(w.mick, ref)
    assert report["namespace"] == "qta"
    assert report["held"]["stored_bytes"] > 0
    assert report["next_pin_estimate"]["bytes"] > 0
    assert "pin" in report["next_pin_estimate"]["basis"]


def test_an_estimate_says_where_its_figure_came_from(metered):
    w, ref = metered
    with w.p.uow() as uow:
        feature = uow.repo("features").find_one(name="qta_px")
        from_prior = quota.estimate(
            uow, feature_id=feature["id"], rows=1000, schema=[{"name": "close", "type": "float64"}]
        )
        from_schema = quota.estimate(
            uow, feature_id=None, rows=1000, schema=[{"name": "close", "type": "float64"}]
        )
        nothing = quota.estimate(uow, feature_id=None, rows=None, schema=[])
    assert "last sealed pin" in from_prior["basis"] and from_prior["bytes"] > 0
    assert "compressed" in from_schema["basis"]
    assert nothing["bytes"] is None and "cannot be estimated" in nothing["basis"]
