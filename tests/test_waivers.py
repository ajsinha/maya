"""Controls a model is not meeting, and who said that was acceptable.

Every estate has these and most keep them in a spreadsheet, which is how a
temporary exception reaches its fourth year. The four rules here are the overlay
register's four pointed at a different object — a waiver and a management
adjustment are the same governance animal, in that both are a temporary
departure from the framework and both fail by quietly becoming permanent.
"""
from __future__ import annotations

import time

import pytest

from core.waivers import (QUORUM_BY_TIER, WAIVABLE, WaiverError,
                          WaiverRegister)
from tests.conftest import URN


@pytest.fixture
def waivers(repos, db, registry, evidence, findings):
    from db import WaiverRepository

    registry.register(URN, "SB PD", "credit.pd", "credit", "person/j.okafor",
                      "LE-US-01", "12-month PD")
    return WaiverRegister(WaiverRepository(db), evidence, registry,
                          findings=findings, max_days=90, renewal_limit=3)


def _tier(registry, tier: int):
    model = registry.require(URN)
    registry.set_tier(model["id"], tier)


class TestNoIndefiniteExceptions:
    """The requirement's own phrase, and the whole point of the register."""

    def test_a_waiver_with_no_window_is_refused(self, waivers):
        with pytest.raises(WaiverError) as exc:
            waivers.propose(URN, "annual_review", "r", "c", 0)
        assert exc.value.code == "no_expiry"
        assert "decision to stop applying a control" in exc.value.detail

    def test_a_window_past_the_maximum_is_refused(self, waivers):
        with pytest.raises(WaiverError) as exc:
            waivers.propose(URN, "annual_review", "r", "c", 400)
        assert exc.value.code == "window_too_long"
        # And it says what to do instead, which is the point of the limit.
        assert "renew" in exc.value.remediation

    def test_the_expiry_is_stamped_from_the_window(self, waivers):
        made = waivers.propose(URN, "annual_review", "r", "c", 30)
        assert made["expires_at"] > time.time()


class TestTheGapAndTheContainment:
    def test_a_waiver_with_no_compensating_control_is_refused(self, waivers):
        with pytest.raises(WaiverError) as exc:
            waivers.propose(URN, "annual_review", "because we are busy", "", 30)
        assert exc.value.code == "no_compensating_control"
        # The remediation names the honest alternative rather than only saying no.
        assert "accepted risk" in exc.value.remediation

    def test_a_waiver_with_no_rationale_is_refused(self, waivers):
        with pytest.raises(WaiverError) as exc:
            waivers.propose(URN, "annual_review", "  ", "c", 30)
        assert exc.value.code == "no_rationale"


class TestWhatMayBeWaived:
    def test_the_control_must_be_one_some_tier_requires(self, waivers):
        with pytest.raises(WaiverError) as exc:
            waivers.propose(URN, "being_careful", "r", "c", 30)
        assert exc.value.code == "unknown_control"
        assert "would relax nothing" in exc.value.detail

    @pytest.mark.parametrize("control", WAIVABLE)
    def test_every_control_the_lattice_requires_can_be_waived(self, waivers,
                                                              control):
        waivers.propose(URN, control, "r", "c", 30)

    def test_the_waivable_set_is_derived_from_what_is_required(self):
        """Not a second list. A waiver of a control nothing requires would read
        on a report as though something had been relaxed.

        Both sources: the tiers' controls and the designations'. A bank that
        cannot yet reconcile its submissions needs somewhere to SAY so, or a
        designation-driven requirement is one people meet on paper.
        """
        from core.risk.designations import DESIGNATION_CONTROLS
        from core.risk.lattices import CONTROLS
        assert set(WAIVABLE) == ({c for cs in CONTROLS.values() for c in cs}
                                 | set(DESIGNATION_CONTROLS))


class TestApprovalScalesWithRisk:
    def test_a_tier_one_waiver_takes_two_signatures(self, waivers, registry):
        _tier(registry, 1)
        made = waivers.propose(URN, "independent_validation", "r", "c", 30,
                               actor="person/a.mehta")
        one = waivers.approve(made["id"], "model_risk_manager",
                              actor="person/s.iqbal")
        assert one["status"] == "proposed", "one signature is not a quorum"
        two = waivers.approve(made["id"], "validator", actor="person/v.chen")
        assert two["status"] == "active"

    def test_a_tier_four_waiver_takes_one(self, waivers, registry):
        _tier(registry, 4)
        made = waivers.propose(URN, "condition_monitoring", "r", "c", 30,
                               actor="person/a.mehta")
        assert waivers.approve(made["id"], "model_risk_manager",
                               actor="person/s.iqbal")["status"] == "active"

    def test_an_untiered_model_takes_the_strictest(self, waivers):
        """A model nobody has tiered is not a safe model — the same reading the
        risk lattice applies to an unassessed component."""
        assert waivers.quorum_for(None) == max(QUORUM_BY_TIER.values())

    def test_two_signatures_must_be_two_roles(self, waivers, registry):
        _tier(registry, 1)
        made = waivers.propose(URN, "annual_review", "r", "c", 30,
                               actor="person/a.mehta")
        waivers.approve(made["id"], "model_risk_manager", actor="person/s.iqbal")
        with pytest.raises(WaiverError) as exc:
            waivers.approve(made["id"], "model_risk_manager",
                            actor="person/v.chen")
        assert exc.value.code == "role_already_signed"
        assert "one opinion held twice" in exc.value.detail


class TestTheProposerMayNotApprove:
    def test_it_is_refused(self, waivers):
        made = waivers.propose(URN, "annual_review", "r", "c", 30,
                               actor="person/a.mehta")
        with pytest.raises(WaiverError) as exc:
            waivers.approve(made["id"], "model_risk_manager",
                            actor="person/a.mehta")
        assert exc.value.code == "proposer_may_not_approve"

    def test_one_person_cannot_sign_twice(self, waivers, registry):
        _tier(registry, 1)
        made = waivers.propose(URN, "annual_review", "r", "c", 30,
                               actor="person/a.mehta")
        waivers.approve(made["id"], "model_risk_manager", actor="person/s.iqbal")
        with pytest.raises(WaiverError) as exc:
            waivers.approve(made["id"], "validator", actor="person/s.iqbal")
        assert exc.value.code == "already_signed"


class TestRenewalIsNotFree:
    def _active(self, waivers, registry):
        _tier(registry, 4)
        made = waivers.propose(URN, "condition_monitoring", "r", "c", 30,
                               actor="person/a.mehta")
        return waivers.approve(made["id"], "model_risk_manager",
                               actor="person/s.iqbal")

    def test_renewing_counts(self, waivers, registry):
        row = self._active(waivers, registry)
        assert waivers.renew(row["id"], 30)["renewals"] == 1

    def test_past_the_limit_it_raises_a_finding(self, waivers, registry,
                                                findings):
        row = self._active(waivers, registry)
        for _ in range(4):
            row = waivers.renew(row["id"], 30)
        assert row["renewals"] == 4
        raised = [f for f in findings.open_for(row["model_id"])
                  if f["category"] == "waiver"]
        assert raised, "a control relaxed four times running is the framework"
        assert "framework" in raised[0]["description"]

    def test_a_proposed_waiver_cannot_be_renewed(self, waivers):
        made = waivers.propose(URN, "annual_review", "r", "c", 30)
        with pytest.raises(WaiverError) as exc:
            waivers.renew(made["id"], 30)
        assert exc.value.code == "not_active"


class TestExpiry:
    def test_the_batch_closes_a_waiver_whose_window_ended(self, waivers,
                                                          registry):
        _tier(registry, 4)
        made = waivers.propose(URN, "condition_monitoring", "r", "c", 1,
                               actor="person/a.mehta")
        waivers.approve(made["id"], "model_risk_manager", actor="person/s.iqbal")
        out = waivers.expire_due(now=time.time() + 2 * 86400)
        assert out["count"] == 1
        assert waivers.require(made["id"])["status"] == "expired"

    def test_a_waiver_still_in_its_window_is_untouched(self, waivers, registry):
        _tier(registry, 4)
        made = waivers.propose(URN, "condition_monitoring", "r", "c", 30,
                               actor="person/a.mehta")
        waivers.approve(made["id"], "model_risk_manager", actor="person/s.iqbal")
        assert waivers.expire_due()["count"] == 0

    def test_an_overdue_waiver_is_reported_as_such_before_the_batch_runs(
            self, waivers, registry):
        """A date nobody read is the failure mandatory expiry exists to
        prevent, so the reader is told the batch is behind rather than told
        the waiver is in force."""
        _tier(registry, 4)
        made = waivers.propose(URN, "condition_monitoring", "r", "c", 1,
                               actor="person/a.mehta")
        waivers.approve(made["id"], "model_risk_manager", actor="person/s.iqbal")
        out = waivers.for_model(URN)
        assert out["overdue"] == 0
        later = waivers.across_the_estate(now=time.time() + 2 * 86400)
        assert later["overdue"] == 1
        assert "the batch has not run" in later["detail"]


class TestRevocation:
    def test_a_waiver_is_revoked_and_never_deleted(self, waivers, registry):
        _tier(registry, 4)
        made = waivers.propose(URN, "condition_monitoring", "r", "c", 30,
                               actor="person/a.mehta")
        waivers.approve(made["id"], "model_risk_manager", actor="person/s.iqbal")
        waivers.revoke(made["id"], "the control is being met again")
        row = waivers.require(made["id"])
        assert row["status"] == "revoked" and row["closure_reason"]

    def test_revoking_without_a_reason_is_refused(self, waivers, registry):
        _tier(registry, 4)
        made = waivers.propose(URN, "condition_monitoring", "r", "c", 30,
                               actor="person/a.mehta")
        waivers.approve(made["id"], "model_risk_manager", actor="person/s.iqbal")
        with pytest.raises(WaiverError) as exc:
            waivers.revoke(made["id"], "  ")
        assert exc.value.code == "no_reason"


class TestTheEstateView:
    def test_it_sorts_by_tier_because_that_is_what_worst_means(
            self, waivers, registry, evidence):
        """The same control relaxed on a tier 1 and a tier 4 model are
        different sentences, and a list sorted by date buries the first."""
        _tier(registry, 1)
        made = waivers.propose(URN, "independent_validation", "r", "c", 30,
                               actor="person/a.mehta")
        waivers.approve(made["id"], "model_risk_manager", actor="person/s.iqbal")
        waivers.approve(made["id"], "validator", actor="person/v.chen")
        estate = waivers.across_the_estate()
        assert estate["active"] == 1
        assert estate["models"][0]["tier"] == 1
        assert "independent_validation" in estate["models"][0]["controls"]

    def test_an_empty_register_says_so(self, waivers):
        assert "no control is currently waived" in \
            waivers.across_the_estate()["detail"]
