"""
Model governance: the findings register, materiality tiers and periodic review.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pytest

from maya.core.clock import utcnow
from maya.core.errors import NotApproved, PermissionDenied, ValidationFailed, WarrantSuspended


@pytest.fixture(scope="module")
def gov(world):
    w = world
    w.p.models.create(
        w.mona,
        namespace="eq",
        name="gov_lin",
        formula="yhat = a*x + b",
        roles={"a": "parameter", "b": "parameter"},
    )
    return w


def _live_warrant(w, name: str, approved_days_ago: int) -> str:
    """A model version approved long ago and one sealed, live execution warrant on it.

    Built directly: the warrant chain has its own tests, and what is under test here is
    what governance does to a warrant that is live."""
    with w.p.uow("test") as uow:
        model = uow.repo("models").find_one(name="gov_lin")
        v = uow.repo("model_versions").find_one(model_id=model["id"], version_no=1)
        uow.repo("model_versions").update(
            v["id"], {"approved_at": utcnow() - dt.timedelta(days=approved_days_ago)}
        )
        ew = uow.repo("execution_warrants").add(
            {
                "namespace_id": model["namespace_id"],
                "name": name,
                "state": "approved",
                "owner_id": model["owner_id"],
                "model_version_id": v["id"],
                "spec": {"environments": ["dev"], "contact": "risk@example.com"},
                "sealed_at": utcnow(),
                "valid_from": utcnow(),
                "valid_to": utcnow() + dt.timedelta(days=90),
            }
        )
        return ew["id"]


def test_a_finding_is_raised_remediated_and_closed_by_someone_independent(gov):
    w = gov
    f = w.p.governance.raise_finding(
        w.devi, "eq/gov_lin", "Intercept unstable across samples", "high", detail="see memo"
    )
    assert f["state"] == "open" and f["owner"] == "mona"
    assert f["due_date"] == utcnow().date() + dt.timedelta(days=90)
    w.p.governance.move_finding(w.mona, f["id"], "start")
    w.p.governance.move_finding(w.mona, f["id"], "remediated")
    with pytest.raises(PermissionDenied, match="does not close"):
        w.p.governance.move_finding(w.mona, f["id"], "close", "fixed it")
    with pytest.raises(ValidationFailed, match="note"):
        w.p.governance.move_finding(w.devi, f["id"], "close")
    done = w.p.governance.move_finding(w.devi, f["id"], "close", "re-ran; stable now")
    assert done["state"] == "closed" and done["closed_by"] == "devi"
    assert [h["action"] for h in done["history"]] == ["raised", "start", "remediated", "close"]
    with pytest.raises(NotApproved):
        w.p.governance.move_finding(w.devi, f["id"], "start")
    assert f["id"] not in {r["id"] for r in w.p.governance.findings(w.devi, state="active")}


def test_the_owner_does_not_accept_the_risk_in_their_own_model(gov):
    w = gov
    f = w.p.governance.raise_finding(w.devi, "eq/gov_lin", "No challenger", "low")
    with pytest.raises(PermissionDenied):
        w.p.governance.move_finding(w.mona, f["id"], "accept", "fine")
    out = w.p.governance.move_finding(w.admin, f["id"], "accept", "compensating control")
    assert out["state"] == "accepted" and out["resolution"] == "compensating control"


def test_the_tier_is_derived_and_an_override_that_lowers_it_is_flagged(gov):
    w = gov
    base = w.p.governance.profile(w.mona, "eq/gov_lin")
    assert base["derived_tier"] == 3 and not base["declared"]
    prof = w.p.governance.set_profile(w.mona, "eq/gov_lin", use="regulatory", exposure=5e9)
    assert prof["derived_tier"] == 1 and prof["tier"] == 1 and prof["review_days"] == 365
    with pytest.raises(ValidationFailed, match="reason"):
        w.p.governance.set_profile(w.mona, "eq/gov_lin", use="regulatory", tier_override=3)
    low = w.p.governance.set_profile(
        w.mona,
        "eq/gov_lin",
        use="regulatory",
        exposure=5e9,
        tier_override=3,
        override_reason="shadow use only",
    )
    assert low["tier"] == 3 and low["override_lowers"]
    with pytest.raises(PermissionDenied):
        w.p.governance.set_profile(w.devi, "eq/gov_lin", use="internal")
    w.p.governance.set_profile(w.mona, "eq/gov_lin", use="regulatory", exposure=5e9)


def test_an_overdue_review_suspends_live_warrants_and_a_review_lifts_only_those(gov):
    w = gov
    ew_id = _live_warrant(w, "gov_live", approved_days_ago=400)  # tier 1: yearly
    other = _live_warrant(w, "gov_breached", approved_days_ago=400)
    with w.p.uow("test") as uow:  # suspended for something else entirely
        uow.repo("execution_warrants").update(
            other, {"suspended_at": utcnow(), "suspend_reason": "covenant breach"}
        )
    assert w.p.governance.profile(w.mona, "eq/gov_lin")["review_overdue"]
    with pytest.raises(PermissionDenied):
        w.p.governance.sweep(w.devi)
    out = w.p.governance.sweep(w.admin)
    assert out["suspended"] == [ew_id]
    with w.p.uow() as uow:
        ew = uow.repo("execution_warrants").require(ew_id)
    with pytest.raises(WarrantSuspended, match="Periodic review overdue"):
        w.p.execution.check(ew)
    with pytest.raises(PermissionDenied, match="owner"):
        w.p.governance.record_review(w.mona, "eq/gov_lin", "satisfactory", "all good")
    rec = w.p.governance.record_review(w.devi, "eq/gov_lin", "satisfactory", "backtest reviewed")
    assert rec["reinstated"] == [ew_id] and not rec["review_overdue"]
    assert rec["next_review_due"] == utcnow().date() + dt.timedelta(days=365)
    with w.p.uow() as uow:
        assert uow.repo("execution_warrants").require(ew_id)["suspended_at"] is None
        assert uow.repo("execution_warrants").require(other)["suspend_reason"] == "covenant breach"
    assert w.p.governance.sweep(w.admin)["suspended"] == []
    row = next(r for r in w.p.governance.overview(w.mona)["models"] if r["name"] == "gov_lin")
    assert row["tier"] == 1 and not row["review_overdue"]


def test_the_register_is_reachable_through_the_sdk(gov):
    from maya.sdk.client import Client

    assert hasattr(Client, "__init__")
    from maya.sdk.resources import ENDPOINTS

    assert ENDPOINTS[("POST", "/governance/findings")] == "Governance.raise_finding"
