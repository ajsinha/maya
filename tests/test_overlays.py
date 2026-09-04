"""
MAYA — the overlay register.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

Every bank has overlays. Almost none can say how large they are in aggregate,
how long they have been running, or which have quietly become permanent.

The last of those is what this register is for, and TestPersistenceEscalates is
where it is tested: past the renewal limit an overlay is an unversioned model
change, and the register says so rather than leaving somebody to notice.
"""
import time

import pytest

from core.overlays import OverlayError, analysis
from tests.conftest import URN

DAY = 86400.0
NOW = 1_800_000_000.0


@pytest.fixture
def proposed(overlays, a_model):
    return overlays.propose(
        a_model["id"], "SME sector uplift", "output",
        "The model under-predicts default for hospitality post-2025; this adds "
        "the shortfall observed in outcomes analysis.",
        owner="person/j.okafor", actor="d.raman")


@pytest.fixture
def active(overlays, proposed):
    return overlays.approve(proposed["id"], "s.iqbal")


# =================================================================== proposing
class TestProposing:
    def test_an_overlay_is_proposed_with_a_reference(self, proposed):
        assert proposed["reference"] == "OVL-001"
        assert proposed["status"] == "proposed"

    def test_it_must_say_what_the_model_is_getting_wrong(self, overlays, a_model):
        with pytest.raises(OverlayError) as exc:
            overlays.propose(a_model["id"], "x", "output", "   ", "person/o")
        assert exc.value.code == "rationale_required"
        assert "a validator will challenge" in exc.value.remediation

    def test_an_unknown_kind_is_refused(self, overlays, a_model):
        with pytest.raises(OverlayError, match="unknown overlay kind"):
            overlays.propose(a_model["id"], "x", "vibes", "because", "person/o")

    def test_an_overlay_cannot_run_indefinitely(self, overlays, a_model):
        """An adjustment with no end date is a model change nobody versioned."""
        with pytest.raises(OverlayError) as exc:
            overlays.propose(a_model["id"], "x", "output", "because", "person/o",
                             days=3650)
        assert exc.value.code == "window_too_long"
        assert "re-examined rather than forgotten" in exc.value.remediation


# =================================================================== approving
class TestApproving:
    def test_approval_starts_the_clock(self, active):
        assert active["status"] == "active"
        assert active["effective_from"] and active["expires_at"]
        assert active["expires_at"] - active["effective_from"] == pytest.approx(
            180 * DAY, rel=1e-6)

    def test_the_proposer_cannot_approve_their_own(self, overlays, proposed):
        with pytest.raises(OverlayError) as exc:
            overlays.approve(proposed["id"], "d.raman")
        assert exc.value.code == "self_approval"
        assert "preference, not a control" in exc.value.remediation

    def test_approving_twice_is_refused(self, overlays, active):
        with pytest.raises(OverlayError, match="not proposed"):
            overlays.approve(active["id"], "s.iqbal")


# =================================================================== measuring
class TestMeasuring:
    def test_a_measurement_records_the_magnitude_and_its_share(self, overlays, active):
        m = overlays.measure(active["id"], "2026-Q1", 1_000_000.0, 1_180_000.0,
                             "d.raman")
        assert m["magnitude"] == pytest.approx(180_000.0)
        assert m["pct_of_base"] == pytest.approx(0.18)

    def test_one_measurement_per_period(self, overlays, active):
        overlays.measure(active["id"], "2026-Q1", 1_000.0, 1_100.0)
        with pytest.raises(OverlayError, match="already measured"):
            overlays.measure(active["id"], "2026-Q1", 1_000.0, 1_200.0)

    def test_a_zero_base_leaves_the_share_undefined_rather_than_infinite(
            self, overlays, active):
        m = overlays.measure(active["id"], "2026-Q1", 0.0, 500.0)
        assert m["magnitude"] == 500.0 and m["pct_of_base"] is None


# ==================================================================== renewing
class TestRenewing:
    def test_renewal_requires_a_measurement(self, overlays, active):
        """'We still need it' and 'it is 18% of the provision' are different
        statements, and only the second can be challenged."""
        with pytest.raises(OverlayError) as exc:
            overlays.renew(active["id"], "s.iqbal")
        assert exc.value.code == "unmeasured"

    def test_the_owner_cannot_renew_their_own(self, overlays, active):
        overlays.measure(active["id"], "2026-Q1", 1_000.0, 1_100.0)
        with pytest.raises(OverlayError) as exc:
            overlays.renew(active["id"], "person/j.okafor")
        assert exc.value.code == "self_renewal"
        assert "whether the model should be fixed instead" in exc.value.remediation

    def test_a_measured_overlay_renews_and_counts(self, overlays, active):
        overlays.measure(active["id"], "2026-Q1", 1_000.0, 1_100.0)
        renewed = overlays.renew(active["id"], "s.iqbal")
        assert renewed["renewals"] == 1

    def test_renewing_against_an_unmeasured_period_is_refused(self, overlays, active):
        overlays.measure(active["id"], "2026-Q1", 1_000.0, 1_100.0)
        with pytest.raises(OverlayError, match="no measurement recorded for 2026-Q2"):
            overlays.renew(active["id"], "s.iqbal", period="2026-Q2")


# ======================================================== the point of it all
class TestPersistenceEscalates:
    """Past the limit, an overlay is an unversioned model change."""

    def test_persistence_is_read_from_renewals(self):
        assert analysis.persistence({"renewals": 2}, 2)["persistent"] is False
        assert analysis.persistence({"renewals": 3}, 2)["persistent"] is True

    def test_the_reading_explains_why_it_matters(self):
        detail = analysis.persistence({"renewals": 5}, 2)["detail"]
        assert "evidence the model is wrong" in detail

    def test_exceeding_the_limit_raises_a_finding(self, overlays, findings,
                                                  a_model, active):
        for i, period in enumerate(["2026-Q1", "2026-Q2", "2026-Q3"]):
            overlays.measure(active["id"], period, 1_000.0, 1_100.0 + i * 50)
            overlays.renew(active["id"], "s.iqbal", period=period)

        raised = findings.open_for(a_model["id"])
        assert len(raised) == 1
        assert "Persistent overlay" in raised[0]["title"]
        assert raised[0]["category"] == "overlay"
        assert "unversioned model change" in raised[0]["description"]

    def test_the_finding_is_raised_once_not_every_renewal(self, overlays, findings,
                                                          a_model, active):
        for i, period in enumerate(["2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"]):
            overlays.measure(active["id"], period, 1_000.0, 1_100.0)
            overlays.renew(active["id"], "s.iqbal", period=period)
        assert len(findings.open_for(a_model["id"])) == 1

    def test_within_the_limit_nothing_is_escalated(self, overlays, findings,
                                                   a_model, active):
        overlays.measure(active["id"], "2026-Q1", 1_000.0, 1_100.0)
        overlays.renew(active["id"], "s.iqbal", period="2026-Q1")
        assert findings.open_for(a_model["id"]) == []


# =================================================================== analysis
class TestReadingTheRegister:
    def test_a_growing_overlay_is_reported_as_the_model_falling_behind(self):
        movement = analysis.trend([{"magnitude": 100.0}, {"magnitude": 250.0}])
        assert movement["direction"] == "growing"
        assert "falling further behind" in movement["detail"]

    def test_a_shrinking_overlay_is_the_model_catching_up(self):
        assert analysis.trend([{"magnitude": 250.0},
                               {"magnitude": 100.0}])["direction"] == "shrinking"

    def test_one_period_is_not_a_trend(self):
        assert analysis.trend([{"magnitude": 100.0}])["known"] is False

    def test_materiality_is_relative_to_the_models_own_output(self):
        big = analysis.materiality([{"period": "Q1", "magnitude": 180.0,
                                     "pct_of_base": 0.18}])
        small = analysis.materiality([{"period": "Q1", "magnitude": 1.0,
                                       "pct_of_base": 0.001}])
        assert big["material"] is True and small["material"] is False

    def test_an_unmeasured_overlay_is_reported_as_unmeasured(self):
        assert analysis.materiality([])["measured"] is False

    def test_expiry_is_computed_not_swept(self, overlays, active):
        assert analysis.is_expired(active, now=NOW) is False
        assert analysis.is_expired(active, now=time.time() + 200 * DAY) is True

    def test_the_portfolio_answers_how_much_is_the_model(self, overlays, a_model,
                                                         active):
        overlays.measure(active["id"], "2026-Q1", 1_000_000.0, 1_180_000.0)
        status = overlays.status(a_model["id"])
        assert status["active"] == 1
        assert status["aggregate_magnitude"] == pytest.approx(180_000.0)
        assert "in aggregate" in status["detail"]

    def test_unmeasured_active_overlays_are_counted(self, overlays, a_model, active):
        assert overlays.status(a_model["id"])["unmeasured"] == 1


# ==================================================================== closing
class TestClosing:
    def test_an_overlay_can_be_absorbed_into_the_model(self, overlays, active):
        """The outcome to aim at: it stopped being an overlay because the model
        now does it."""
        closed = overlays.close(active["id"], "absorbed",
                                "built into version 3.3.0 and validated",
                                "s.iqbal")
        assert closed["status"] == "absorbed" and closed["closure_reason"]

    def test_closing_needs_a_reason(self, overlays, active):
        with pytest.raises(OverlayError, match="needs a reason"):
            overlays.close(active["id"], "withdrawn", "  ")

    def test_an_unknown_closure_state_is_refused(self, overlays, active):
        with pytest.raises(OverlayError, match="cannot close as"):
            overlays.close(active["id"], "forgotten", "we stopped looking")

    def test_the_sweep_only_makes_stored_status_agree_with_computed(
            self, overlays, a_model, active):
        assert overlays.sweep_expired(a_model["id"], now=NOW) == []
        swept = overlays.sweep_expired(a_model["id"], now=time.time() + 200 * DAY)
        assert len(swept) == 1 and swept[0]["status"] == "expired"
