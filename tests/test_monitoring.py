"""
MAYA — monitoring: drift, delayed labels, and breaches that become findings.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

Two things are worth testing hardest. TestDelayedLabels, because a performance
number computed over an immature cohort is biased rather than merely noisy, and
publishing it beside honest numbers is how a dashboard quietly stops being
trustworthy. And TestTheLoop, because a breach that does not become a refusal is
a dashboard, and dashboards change nothing.
"""
import time

import pytest

from core.monitoring import MonitorError, OutcomeWindow
from core.monitoring.breaches import BreachRegister
from core.validation import ValidationError
from tests.conftest import URN

DAY = 86400.0
NOW = 1_800_000_000.0


def cohort(n, scored_at, labelled=True, sep=True):
    """n rows scored at one moment; separable scores unless told otherwise."""
    rows = []
    for i in range(n):
        score = (i / max(n - 1, 1))
        label = (1 if score > 0.5 else 0) if sep else (i % 2)
        rows.append({"scored_at": scored_at, "score": score,
                     "label": label if labelled else None})
    return rows


# ============================================================ outcome windows
class TestDelayedLabels:
    def test_a_cohort_matures_after_the_declared_delay(self):
        window = OutcomeWindow(365)
        assert not window.is_mature(NOW, now=NOW + 100 * DAY)
        assert window.is_mature(NOW, now=NOW + 366 * DAY)

    def test_maturity_is_decided_per_row_not_per_batch(self):
        """A window spans days; the old end may be measurable when the new is not."""
        window = OutcomeWindow(30)
        rows = cohort(2, NOW - 40 * DAY) + cohort(2, NOW - 5 * DAY)
        mature, immature = window.split(rows, now=NOW)
        assert len(mature) == 2 and len(immature) == 2

    def test_the_report_says_when_the_rest_becomes_measurable(self):
        window = OutcomeWindow(30)
        report = window.report(cohort(4, NOW - 5 * DAY), now=NOW)
        assert report["measurable"] == 0 and report["waiting"] == 4
        assert report["next_maturity_at"] == NOW + 25 * DAY
        assert "outcome window" in report["detail"]

    def test_a_zero_delay_window_is_immediately_mature(self):
        assert OutcomeWindow(0).is_mature(NOW, now=NOW)


# ============================================================== definitions
class TestMonitorDefinitions:
    def test_a_drift_monitor_is_defined(self, monitors, a_model):
        m = monitors.define(a_model["id"], "score drift", "score_drift",
                            "stability.psi", {"max": 0.25}, "person/j.okafor")
        assert m["kind"] == "score_drift" and m["status"] == "active"

    def test_a_test_that_cannot_answer_the_question_is_refused(self, monitors, a_model):
        """Caught when it is written, not at three in the morning."""
        with pytest.raises(MonitorError) as exc:
            monitors.define(a_model["id"], "wrong", "input_drift",
                            "discrimination.gini", {"min": 0.4}, "person/o")
        assert exc.value.code == "test_not_admissible"
        assert "stability.psi" in exc.value.remediation

    def test_a_performance_monitor_must_declare_its_label_delay(self, monitors, a_model):
        with pytest.raises(MonitorError) as exc:
            monitors.define(a_model["id"], "gini", "performance",
                            "discrimination.gini", {"min": 0.4}, "person/o")
        assert exc.value.code == "label_delay_required"
        assert "365" in exc.value.remediation

    def test_a_monitor_with_no_threshold_is_refused(self, monitors, a_model):
        with pytest.raises(MonitorError, match="can never breach"):
            monitors.define(a_model["id"], "x", "score_drift", "stability.psi",
                            {}, "person/o")

    def test_an_unknown_kind_is_refused(self, monitors, a_model):
        with pytest.raises(MonitorError, match="unknown monitor kind"):
            monitors.define(a_model["id"], "x", "vibes", "stability.psi",
                            {"max": 0.2}, "person/o")

    def test_an_unknown_test_is_refused(self, monitors, a_model):
        with pytest.raises(ValidationError, match="no test"):
            monitors.define(a_model["id"], "x", "score_drift", "stability.made_up",
                            {"max": 0.2}, "person/o")

    def test_duplicate_names_are_refused(self, monitors, a_model):
        monitors.define(a_model["id"], "psi", "score_drift", "stability.psi",
                        {"max": 0.25}, "person/o")
        with pytest.raises(MonitorError, match="already exists"):
            monitors.define(a_model["id"], "psi", "score_drift", "stability.psi",
                            {"max": 0.25}, "person/o")

    def test_a_never_evaluated_monitor_is_due(self, monitors, a_model):
        monitors.define(a_model["id"], "psi", "score_drift", "stability.psi",
                        {"max": 0.25}, "person/o", cadence_days=1)
        assert len(monitors.due(a_model["id"], now=NOW)) == 1


# ================================================================ evaluation
class TestEvaluation:
    def test_a_stable_distribution_passes(self, monitoring, drift_monitor):
        reference = [i / 100 for i in range(100)]
        rows = [{"scored_at": NOW, "score": i / 100} for i in range(100)]
        result = monitoring.evaluate(drift_monitor["id"], rows, reference, now=NOW)
        assert result["observation"]["passed"] is True
        assert result["breach"] is None

    def test_a_shifted_distribution_breaches(self, monitoring, drift_monitor):
        reference = [i / 100 for i in range(100)]
        rows = [{"scored_at": NOW, "score": 0.99} for _ in range(100)]
        result = monitoring.evaluate(drift_monitor["id"], rows, reference, now=NOW)
        assert result["observation"]["passed"] is False
        assert result["breach"] is not None

    def test_a_drift_monitor_needs_a_reference(self, monitoring, drift_monitor):
        rows = [{"scored_at": NOW, "score": 0.4}]
        with pytest.raises(MonitorError) as exc:
            monitoring.evaluate(drift_monitor["id"], rows, None, now=NOW)
        assert exc.value.code == "no_reference"

    def test_a_paused_monitor_is_not_evaluated(self, monitors, monitoring,
                                               drift_monitor):
        monitors.set_status(drift_monitor["id"], "paused")
        with pytest.raises(MonitorError, match="paused"):
            monitoring.evaluate(drift_monitor["id"], [], [0.1], now=NOW)

    def test_evaluation_is_refused_over_an_immature_cohort(self, monitoring,
                                                           performance_monitor):
        """The whole point: refuse, and say when it becomes measurable."""
        rows = cohort(20, NOW - 10 * DAY)
        with pytest.raises(MonitorError) as exc:
            monitoring.evaluate(performance_monitor["id"], rows, now=NOW)
        assert exc.value.code == "cohort_immature"
        assert "no outcomes have matured" in exc.value.detail
        assert exc.value.remediation.startswith("wait for the outcome window")

    def test_a_matured_cohort_is_measured(self, monitoring, performance_monitor):
        rows = cohort(20, NOW - 400 * DAY)
        result = monitoring.evaluate(performance_monitor["id"], rows, now=NOW)
        assert result["observation"]["passed"] is True
        assert result["observation"]["sample_size"] == 20

    def test_only_the_matured_part_is_measured(self, monitoring, performance_monitor):
        rows = cohort(20, NOW - 400 * DAY) + cohort(50, NOW - 5 * DAY)
        result = monitoring.evaluate(performance_monitor["id"], rows, now=NOW)
        assert result["observation"]["sample_size"] == 20, \
            "the immature 50 must not be counted"
        assert "20 of 70 rows have matured" in result["observation"]["detail"]

    def test_the_observation_carries_its_window_and_digest(self, monitoring,
                                                           performance_monitor):
        rows = cohort(20, NOW - 400 * DAY)
        obs = monitoring.evaluate(performance_monitor["id"], rows,
                                  now=NOW)["observation"]
        assert obs["window_start"] and obs["window_end"] and obs["digest"]


# ================================================================== the loop
class TestTheLoop:
    """Measurement to obligation to refusal, without anybody watching."""

    def test_a_breach_raises_a_finding(self, monitoring, findings,
                                       performance_monitor, a_model):
        rows = cohort(20, NOW - 400 * DAY, sep=False)   # no discrimination at all
        result = monitoring.evaluate(performance_monitor["id"], rows, now=NOW)
        assert result["breach"] is not None
        raised = findings.open_for(a_model["id"])
        assert len(raised) == 1
        assert raised[0]["source"] == "monitoring"
        assert raised[0]["category"] == "monitoring"
        assert "Monitor breach" in raised[0]["title"]

    def test_a_critical_breach_blocks_warrant_resolution(
            self, monitoring, findings, performance_monitor, repos, registry,
            evidence, a_model, approved_version):
        from core.execution import WarrantError, WarrantService
        warrants = WarrantService(repos["warrants"], registry, evidence,
                                  jitter_pct=0, blocking=findings)
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        warrants.issue(URN, "prod", "svc/pricing", "origination_decision")
        assert warrants.resolve(URN, "prod", "svc/pricing", "origination_decision")

        # A Critical monitor breaches; its finding blocks by default.
        monitoring.registry.monitors.set({"breach_severity": "Critical"},
                                         id=performance_monitor["id"])
        monitoring.evaluate(performance_monitor["id"],
                            cohort(20, NOW - 400 * DAY, sep=False), now=NOW)

        with pytest.raises(WarrantError) as exc:
            warrants.resolve(URN, "prod", "svc/pricing", "origination_decision")
        assert exc.value.code == "blocked"

    def test_recovery_closes_the_breach_but_not_the_finding(
            self, monitoring, findings, performance_monitor, a_model):
        monitoring.evaluate(performance_monitor["id"],
                            cohort(20, NOW - 400 * DAY, sep=False), now=NOW)
        assert len(monitoring.breaches.open_for(a_model["id"])) == 1

        monitoring.evaluate(performance_monitor["id"],
                            cohort(20, NOW - 400 * DAY, sep=True), now=NOW + DAY)
        assert monitoring.breaches.open_for(a_model["id"]) == []
        assert len(findings.open_for(a_model["id"])) == 1, \
            "a metric recovering is not evidence that anyone understood why it moved"

    def test_persistent_breaches_escalate(self, monitoring, findings,
                                          performance_monitor, a_model):
        for i in range(3):
            monitoring.evaluate(performance_monitor["id"],
                                cohort(20, NOW - 400 * DAY, sep=False),
                                now=NOW + i * DAY)
        severities = [f["severity"] for f in findings.open_for(a_model["id"])]
        assert "High" in severities, "a run of breaches is a condition, not a data point"

    def test_escalation_stops_at_critical(self):
        assert BreachRegister.escalate("Medium", 3, 3) == "High"
        assert BreachRegister.escalate("Medium", 6, 3) == "Critical"
        assert BreachRegister.escalate("Medium", 99, 3) == "Critical"

    def test_escalation_is_off_when_the_threshold_is_zero(self):
        assert BreachRegister.escalate("Medium", 50, 0) == "Medium"

    def test_status_summarises_for_the_model_page(self, monitoring, drift_monitor,
                                                  a_model):
        status = monitoring.status(a_model["id"])
        assert status["monitors"] == 1 and status["active"] == 1
        assert status["open_breaches"] == 0 and status["worst_breach"] is None


class TestDriftIsMeasuredOverTheWholeWindow:
    """A 17x breach was reported as a pass.

    `_drift` cut both series to the length of the shorter, to satisfy an
    equal-length check written for paired label/score tests. Telemetry returns
    rows in write order, so the slice kept was the OLDEST — precisely the part
    of a window that has not drifted yet. The observation's own detail line then
    stated how many observations were in the window, which was true, while the
    number beside it had been computed from a fraction of them.
    """

    REFERENCE = [i / 200 for i in range(200)]
    # First half matches the reference, second half has moved to [2, 3).
    DRIFTED = ([i % 200 / 200 for i in range(2600)]
               + [2 + (i % 200) / 200 for i in range(2600)])

    def test_a_two_sample_test_accepts_series_of_different_lengths(self, catalogue):
        """Two distributions have no reason to be the same size, and a 200-point
        reference against a 5,200-row window is the ordinary case."""
        out = catalogue.run("stability.psi", self.REFERENCE, self.DRIFTED,
                            {"max": 0.2})
        assert out.value is not None

    def test_drift_arriving_late_in_the_window_is_caught(self, catalogue):
        out = catalogue.run("stability.psi", self.REFERENCE, self.DRIFTED,
                            {"max": 0.2})
        assert out.passed is False, "this is a breach and must be reported as one"
        assert out.value > 1.0

    def test_the_oldest_slice_alone_would_have_missed_it(self, catalogue):
        """The measurement that used to be taken, kept as the counter-example."""
        out = catalogue.run("stability.psi", self.REFERENCE[:200],
                            self.DRIFTED[:200], {"max": 0.2})
        assert out.passed is True and out.value < 0.01

    def test_a_paired_test_still_refuses_unequal_series(self, catalogue):
        """The check was right for the tests it was written for. A label and a
        score belong to the same observation."""
        from core.validation.common import ValidationError
        with pytest.raises(ValidationError, match="same observation"):
            catalogue.run("discrimination.auc", [0, 1, 0], [0.1, 0.9],
                          {"min": 0.5})
