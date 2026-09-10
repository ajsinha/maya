"""One number for a model, two versions compared, and numbers MAYA did not compute.

The three failure modes these modules exist to prevent: a mean that dilutes an
expired validation into a comfortable score, a significant difference that
nobody would act on, and an external system that marks its own homework.
"""
from __future__ import annotations

import pytest

from core.monitoring.challengers import (CHALLENGER_AHEAD, CHAMPION_AHEAD,
                                         EXACT, INSUFFICIENT, MINIMUM_PAIRS,
                                         NO_DIFFERENCE, ChampionChallenger,
                                         _sign_flip_p)
from core.monitoring.common import MonitorError
from core.monitoring.external import EXTERNAL, MAYA, ExternalObservations
from core.monitoring.health import COMPONENTS, WEIGHTS, ModelHealth
from tests.conftest import URN

DAY = 86400.0


@pytest.fixture
def health(registry, monitoring, findings, overlays):
    return ModelHealth(registry, monitoring=monitoring, findings=findings,
                       overlays=overlays)


@pytest.fixture
def external(monitoring, registry, catalogue, evidence):
    return ExternalObservations(monitoring, registry, catalogue, evidence)


def _observe(monitoring, monitor_id, values, start=0.0, step=DAY):
    """Write observations directly, the way an evaluation would have."""
    for i, value in enumerate(values):
        monitoring.observations.add({
            "monitor_id": monitor_id, "value": value,
            "passed": True, "detail": "seeded", "sample_size": 100,
            "window_start": start + i * step, "window_end": start + (i + 1) * step,
            "matured": True, "digest": "sha256:seed", "computed_at": start + i * step})


# ---------------------------------------------------------------- the score
class TestAnUnmeasuredComponentIsNotAGoodOne:
    def test_a_model_nobody_has_looked_at_is_not_derivable(self, health, a_model):
        """No monitors, no validation, no findings — and no score.

        A naive composite reads 'nothing bad to say' as health. This says the
        score is of nothing rather than of zero.
        """
        out = health.of_model(URN)
        assert out["derivable"] is False or out["coverage"] < 1.0
        assert "open_findings" in out["measured"]      # zero findings IS measured

    def test_absent_components_are_named_not_scored(self, health, a_model):
        out = health.of_model(URN)
        assert "performance" in out["not_measured"]
        absent = next(c for c in out["components"] if c["component"] == "performance")
        assert absent["score"] is None and absent["measured"] is False

    def test_coverage_travels_with_the_score(self, health, a_model):
        out = health.of_model(URN)
        assert 0.0 <= out["coverage"] <= 1.0
        assert "coverage" in out and out["coverage"] < 1.0

    def test_thin_coverage_says_so_in_the_detail(self, health, a_model):
        out = health.of_model(URN)
        if out["coverage"] < 0.5:
            assert "how little is known" in out["detail"]

    def test_the_weights_sum_to_one(self):
        """A composite whose weights do not sum to one has a scale nobody chose."""
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

    def test_every_component_publishes_when_it_is_absent(self):
        for spec in COMPONENTS:
            assert spec["absent_when"] and spec["asks"]


class TestTheBandIsNotTheMean:
    def test_an_overdue_critical_finding_caps_the_band(self, health, a_model,
                                                       findings):
        """The whole point. A model can score well and still be poor."""
        findings.raise_finding(a_model["id"], "Critical", "Model is wrong",
                               "person/j.okafor", due_at=1.0)
        out = health.of_model(URN, now=10.0 * DAY)
        assert out["band"] == "poor"
        assert any("past their remediation date" in c["why"] for c in out["caps"])

    def test_the_arithmetic_is_reported_beside_the_capped_band(self, health,
                                                               a_model, findings):
        findings.raise_finding(a_model["id"], "Critical", "Model is wrong",
                               "person/j.okafor", due_at=1.0)
        out = health.of_model(URN, now=10.0 * DAY)
        assert out["arithmetic_band"] is not None
        assert "no amount of good news elsewhere outweighs that" in out["detail"]

    def test_no_findings_scores_full_marks_and_is_measured(self, health, a_model):
        component = next(c for c in health.of_model(URN)["components"]
                         if c["component"] == "open_findings")
        assert component["measured"] and component["score"] == 1.0

    def test_no_overlay_is_a_measurement_not_an_absence(self, health, a_model):
        """A model carrying no overlay is not unmeasured: nothing is adjusted."""
        component = next(c for c in health.of_model(URN)["components"]
                         if c["component"] == "overlay_reliance")
        assert component["measured"] and component["score"] == 1.0

    def test_a_failing_monitor_lowers_the_score(self, health, monitoring,
                                               drift_monitor, a_model):
        _observe(monitoring, drift_monitor["id"], [0.1])
        good = health.of_model(URN)["score"]
        monitoring.observations.set({"passed": False},
                                    monitor_id=drift_monitor["id"])
        assert health.of_model(URN)["score"] < good

    def test_the_estate_sorts_the_worst_first(self, health, a_model, findings):
        findings.raise_finding(a_model["id"], "Critical", "Model is wrong",
                               "person/j.okafor", due_at=1.0)
        out = health.across_the_estate(now=10.0 * DAY)
        assert out["models"][0]["band"] == "poor"
        assert URN in out["capped"]


# -------------------------------------------------------- champion/challenger
@pytest.fixture
def two_versions(registry, a_model, kernel_spec, contract_spec):
    registry.create_version(URN, "1.0.0", kernel_spec, contract_spec,
                            artifact_digest="sha256:" + "a" * 64)
    registry.create_version(URN, "2.0.0", kernel_spec, contract_spec,
                            artifact_digest="sha256:" + "b" * 64)
    return registry.version(URN, "1.0.0"), registry.version(URN, "2.0.0")


@pytest.fixture
def compared(registry, monitoring, catalogue):
    return ChampionChallenger(registry, monitoring, catalogue)


def _paired(monitors, monitoring, a_model, two_versions, left, right,
            test_key="discrimination.gini", kind="performance"):
    champion, challenger = two_versions
    a = monitors.define(a_model["id"], f"{test_key} champion", kind, test_key,
                        {"min": 0.4}, "person/j.okafor",
                        model_version_id=champion["id"], label_delay_days=30)
    b = monitors.define(a_model["id"], f"{test_key} challenger", kind, test_key,
                        {"min": 0.4}, "person/j.okafor",
                        model_version_id=challenger["id"], label_delay_days=30)
    _observe(monitoring, a["id"], left)
    _observe(monitoring, b["id"], right)
    return a, b


class TestSignificanceIsNotMateriality:
    def test_too_few_windows_refuses_to_produce_a_p_value(
            self, compared, monitors, monitoring, a_model, two_versions):
        _paired(monitors, monitoring, a_model, two_versions,
                [0.50, 0.51], [0.60, 0.61])
        out = compared.compare(URN, "1.0.0", "2.0.0")
        assert out["tests"][0]["tested"] is False
        assert out["tests"][0]["recommendation"] == INSUFFICIENT
        assert "coin landing the same way" in out["tests"][0]["detail"]

    def test_a_consistent_large_gap_favours_the_challenger(
            self, compared, monitors, monitoring, a_model, two_versions):
        _paired(monitors, monitoring, a_model, two_versions,
                [0.50, 0.51, 0.49, 0.50, 0.52, 0.50],
                [0.60, 0.61, 0.59, 0.60, 0.62, 0.60])
        out = compared.compare(URN, "1.0.0", "2.0.0")
        test = out["tests"][0]
        assert test["significant"] and test["material"]
        assert test["recommendation"] == CHALLENGER_AHEAD
        assert out["recommendation"]["verdict"] == CHALLENGER_AHEAD

    def test_a_significant_but_tiny_gap_is_not_a_reason_to_move(
            self, compared, monitors, monitoring, a_model, two_versions):
        """With enough windows any difference is significant. This one is not
        worth a redeployment, and the answer says so."""
        _paired(monitors, monitoring, a_model, two_versions,
                [0.500, 0.501, 0.499, 0.500, 0.502, 0.500],
                [0.502, 0.503, 0.501, 0.502, 0.504, 0.502])
        test = compared.compare(URN, "1.0.0", "2.0.0")["tests"][0]
        assert test["significant"] and not test["material"]
        assert test["recommendation"] == NO_DIFFERENCE
        assert "not worth a redeployment" in test["detail"]

    def test_lower_is_better_flips_the_direction(
            self, compared, monitors, monitoring, a_model, two_versions):
        """A challenger with LOWER Brier is better, and a comparison that got
        this backwards would recommend the worse model with a straight face."""
        _paired(monitors, monitoring, a_model, two_versions,
                [0.30, 0.31, 0.29, 0.30, 0.32, 0.30],
                [0.20, 0.21, 0.19, 0.20, 0.22, 0.20],
                test_key="calibration.brier", kind="calibration")
        test = compared.compare(URN, "1.0.0", "2.0.0")["tests"][0]
        assert test["direction"] == "lower_is_better"
        assert test["recommendation"] == CHALLENGER_AHEAD

    def test_the_champion_can_win(
            self, compared, monitors, monitoring, a_model, two_versions):
        _paired(monitors, monitoring, a_model, two_versions,
                [0.60, 0.61, 0.59, 0.60, 0.62, 0.60],
                [0.50, 0.51, 0.49, 0.50, 0.52, 0.50])
        out = compared.compare(URN, "1.0.0", "2.0.0")
        assert out["tests"][0]["recommendation"] == CHAMPION_AHEAD
        assert out["recommendation"]["action"] == "no action"


class TestTheRecommendationIsNeverToPromote:
    def test_the_strongest_action_is_to_open_a_validation(
            self, compared, monitors, monitoring, a_model, two_versions):
        _paired(monitors, monitoring, a_model, two_versions,
                [0.50, 0.51, 0.49, 0.50, 0.52, 0.50],
                [0.60, 0.61, 0.59, 0.60, 0.62, 0.60])
        out = compared.compare(URN, "1.0.0", "2.0.0")
        assert out["recommendation"]["action"] == "open a validation of the challenger"
        assert "promote" not in out["recommendation"]["action"]

    def test_a_trade_off_is_a_judgement_rather_than_a_number(
            self, compared, monitors, monitoring, a_model, two_versions):
        _paired(monitors, monitoring, a_model, two_versions,
                [0.50, 0.51, 0.49, 0.50, 0.52, 0.50],
                [0.60, 0.61, 0.59, 0.60, 0.62, 0.60])
        _paired(monitors, monitoring, a_model, two_versions,
                [0.20, 0.21, 0.19, 0.20, 0.22, 0.20],
                [0.30, 0.31, 0.29, 0.30, 0.32, 0.30],
                test_key="calibration.brier", kind="calibration")
        out = compared.compare(URN, "1.0.0", "2.0.0")
        assert out["recommendation"]["verdict"] == NO_DIFFERENCE
        assert "trade-off" in out["recommendation"]["detail"]


class TestThePairingIsByWindow:
    def test_windows_are_matched_not_zipped(
            self, compared, monitors, monitoring, a_model, two_versions):
        """Two monitors on different schedules produce interleaved histories,
        and zipping them would pair last quarter against this one."""
        champion, challenger = two_versions
        a = monitors.define(a_model["id"], "a", "performance",
                            "discrimination.gini", {"min": 0.4},
                            "person/j.okafor", model_version_id=champion["id"],
                            label_delay_days=30)
        b = monitors.define(a_model["id"], "b", "performance",
                            "discrimination.gini", {"min": 0.4},
                            "person/j.okafor", model_version_id=challenger["id"],
                            label_delay_days=30)
        _observe(monitoring, a["id"], [0.5] * 8, start=0.0)
        _observe(monitoring, b["id"], [0.6] * 8, start=4 * DAY)
        assert compared.compare(URN, "1.0.0", "2.0.0")["tests"][0]["pairs"] == 4

    def test_two_versions_sharing_no_question_is_refused_by_name(
            self, compared, monitors, monitoring, a_model, two_versions):
        champion, _ = two_versions
        monitors.define(a_model["id"], "only here", "performance",
                        "discrimination.gini", {"min": 0.4}, "person/j.okafor",
                        model_version_id=champion["id"], label_delay_days=30)
        with pytest.raises(MonitorError) as e:
            compared.compare(URN, "1.0.0", "2.0.0")
        assert e.value.code == "no_shared_monitor"

    def test_a_version_cannot_be_compared_against_itself(self, compared,
                                                         two_versions):
        with pytest.raises(MonitorError) as e:
            compared.compare(URN, "1.0.0", "1.0.0")
        assert e.value.code == "same_version"


class TestTheSignificanceTestNamesItsMethod:
    def test_small_samples_are_exact(self):
        p, method = _sign_flip_p([0.1] * 6)
        assert method == EXACT and p == pytest.approx(2 / 64)

    def test_large_samples_say_they_are_approximate(self):
        p, method = _sign_flip_p([0.1 + 0.001 * i for i in range(20)])
        assert method != EXACT and 0.0 <= p <= 1.0

    def test_no_difference_gives_a_p_value_of_one(self):
        p, _ = _sign_flip_p([0.0] * 6)
        assert p == pytest.approx(1.0)

    def test_the_minimum_is_stated_rather_than_implicit(self):
        assert MINIMUM_PAIRS >= 5


# -------------------------------------------------------- external monitoring
class TestMayaTakesTheNumberAndRefusesTheVerdict:
    def test_the_threshold_is_ours(self, external, drift_monitor, monitoring):
        """The monitor's max is 0.25. A PSI of 0.9 breaches, whatever the
        sending system thinks — and there is no field for it to think it in."""
        out = external.ingest(drift_monitor["id"], 0.9,
                              computed_by="acme-mlops", window_start=0.0,
                              window_end=DAY, sample_size=5000)
        assert out["observation"]["passed"] is False
        assert out["breach"] is not None

    def test_a_passing_external_number_is_judged_the_same_way(
            self, external, drift_monitor):
        out = external.ingest(drift_monitor["id"], 0.05,
                              computed_by="acme-mlops", window_start=0.0,
                              window_end=DAY)
        assert out["observation"]["passed"] is True

    def test_the_ingest_signature_has_no_passed_parameter(self):
        import inspect
        assert "passed" not in inspect.signature(
            ExternalObservations.ingest).parameters

    def test_an_unnamed_source_is_refused(self, external, drift_monitor):
        with pytest.raises(MonitorError) as e:
            external.ingest(drift_monitor["id"], 0.1, computed_by="  ",
                            window_start=0.0, window_end=DAY)
        assert e.value.code == "computed_by_required"

    def test_a_window_is_required(self, external, drift_monitor):
        with pytest.raises(MonitorError) as e:
            external.ingest(drift_monitor["id"], 0.1, computed_by="acme")
        assert e.value.code == "window_required"

    def test_an_inverted_window_is_refused(self, external, drift_monitor):
        with pytest.raises(MonitorError) as e:
            external.ingest(drift_monitor["id"], 0.1, computed_by="acme",
                            window_start=DAY, window_end=0.0)
        assert e.value.code == "window_inverted"


class TestProvenanceTravelsWithTheNumber:
    def test_the_source_is_recorded_on_the_observation(self, external,
                                                       drift_monitor, monitoring):
        external.ingest(drift_monitor["id"], 0.05, computed_by="acme-mlops",
                        method="psi over 10 bins", window_start=0.0,
                        window_end=DAY)
        row = monitoring.history(drift_monitor["id"])[-1]
        assert row["source"] == EXTERNAL and row["computed_by"] == "acme-mlops"
        assert "judged here against this firm's threshold" in row["detail"]

    def test_mayas_own_observations_carry_the_default_source(
            self, monitoring, drift_monitor, scored):
        _labels, scores = scored
        monitoring.evaluate(drift_monitor["id"],
                            [{"scored_at": float(i), "score": s}
                             for i, s in enumerate(scores)],
                            reference=list(scores))
        assert monitoring.history(drift_monitor["id"])[-1]["source"] == MAYA

    def test_provenance_says_what_cannot_be_replayed(self, external,
                                                     drift_monitor):
        external.ingest(drift_monitor["id"], 0.05, computed_by="acme-mlops",
                        window_start=0.0, window_end=DAY)
        out = external.provenance(drift_monitor["id"])
        assert out["replayable"] == 0
        assert "cannot be replayed" in out["detail"]

    def test_the_estate_reports_the_split(self, external, drift_monitor,
                                          a_model):
        external.ingest(drift_monitor["id"], 0.05, computed_by="acme-mlops",
                        window_start=0.0, window_end=DAY)
        out = external.across_the_estate()
        assert out["external"] == 1 and out["replayable"] == 0
        assert "acme-mlops" in out["systems"]

    def test_an_unevaluated_estate_says_so_rather_than_reporting_zero_percent(
            self, external, a_model, drift_monitor):
        out = external.across_the_estate()
        assert "no monitor anywhere in the estate has been evaluated" in out["detail"]

    def test_a_retired_monitor_will_not_take_a_number(self, external, monitors,
                                                      drift_monitor):
        monitors.set_status(drift_monitor["id"], "retired")
        with pytest.raises(MonitorError) as e:
            external.ingest(drift_monitor["id"], 0.05, computed_by="acme",
                            window_start=0.0, window_end=DAY)
        assert e.value.code == "monitor_inactive"
