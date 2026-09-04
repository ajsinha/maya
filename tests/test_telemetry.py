"""
MAYA — tests for telemetry ingestion.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Two streams, because a score exists when the model runs and an outcome is
learned later. The gap between them is the thing a performance monitor has to
reason about, and a collector that flattened them into one would take that
reasoning away before it started.
"""
from __future__ import annotations

import datetime as dt

import pytest

from core.telemetry import TelemetryError

URN = "maya://model/credit.pd.smallbiz"
DAY = 86400.0
T0 = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc).timestamp()


def scores(n=5, at=T0, ingest=None):
    return [{"entity_id": f"B{i}", "scored_at": at + i,
             "ingest_ts": ingest if ingest is not None else at + i,
             "score": 0.1 + i * 0.05} for i in range(n)]


def outcomes(n=3, label_at=None, ingest=None):
    at = label_at if label_at is not None else T0 + 90 * DAY
    return [{"entity_id": f"B{i}", "label": i % 2, "label_ts": at,
             "ingest_ts": ingest if ingest is not None else at} for i in range(n)]


class TestIngestionIsIdempotent:
    def test_a_batch_is_written_once(self, telemetry, approved_version):
        first = telemetry.ingest(URN, "3.2.1", "scores", scores())
        assert first["rows"] == 5 and not first["duplicate"]

    def test_delivering_the_same_batch_again_changes_nothing(self, telemetry,
                                                             approved_version):
        """Real collectors deliver at least once. A monitor that double-counted
        a redelivered batch would report a population that never existed."""
        batch = scores()
        telemetry.ingest(URN, "3.2.1", "scores", batch)
        again = telemetry.ingest(URN, "3.2.1", "scores", batch)
        assert again["duplicate"] and again["rows"] == 0
        assert len(telemetry.rows(URN, "3.2.1")) == 5

    def test_a_genuinely_different_batch_is_written(self, telemetry,
                                                    approved_version):
        telemetry.ingest(URN, "3.2.1", "scores", scores())
        telemetry.ingest(URN, "3.2.1", "scores", scores(3, at=T0 + DAY))
        assert len(telemetry.rows(URN, "3.2.1")) == 8


class TestARowMustCarryItsOwnClock:
    def test_a_score_without_a_timestamp_is_refused(self, telemetry,
                                                    approved_version):
        """Inferring it from when the batch arrived is how every window
        becomes wrong."""
        with pytest.raises(TelemetryError) as exc:
            telemetry.ingest(URN, "3.2.1", "scores",
                             [{"entity_id": "B1", "score": 0.4}])
        assert exc.value.code == "malformed_row"
        assert "cannot be inferred from" in exc.value.remediation

    def test_an_outcome_without_a_label_time_is_refused(self, telemetry,
                                                        approved_version):
        with pytest.raises(TelemetryError) as exc:
            telemetry.ingest(URN, "3.2.1", "outcomes",
                             [{"entity_id": "B1", "label": 1}])
        assert exc.value.code == "malformed_row"

    def test_an_unknown_stream_is_refused_with_the_list(self, telemetry,
                                                        approved_version):
        with pytest.raises(TelemetryError) as exc:
            telemetry.ingest(URN, "3.2.1", "guesses", scores())
        assert exc.value.code == "unknown_stream"

    def test_an_empty_batch_is_refused(self, telemetry, approved_version):
        with pytest.raises(TelemetryError) as exc:
            telemetry.ingest(URN, "3.2.1", "scores", [])
        assert exc.value.code == "empty_batch"

    def test_a_sample_rate_that_is_not_a_proportion_is_refused(self, telemetry,
                                                               approved_version):
        with pytest.raises(TelemetryError) as exc:
            telemetry.ingest(URN, "3.2.1", "scores", scores(), sample_rate=1.4)
        assert exc.value.code == "bad_sample_rate"

    def test_a_version_that_does_not_exist_is_refused(self, telemetry,
                                                      approved_version):
        with pytest.raises(TelemetryError) as exc:
            telemetry.ingest(URN, "9.9.9", "scores", scores())
        assert exc.value.code == "no_such_version"


class TestTheTwoStreamsAreJoinedAtReadTime:
    @pytest.fixture
    def sent(self, telemetry, approved_version):
        telemetry.ingest(URN, "3.2.1", "scores", scores(5))
        telemetry.ingest(URN, "3.2.1", "outcomes", outcomes(3))
        return telemetry

    def test_unlabelled_rows_come_back_unlabelled_rather_than_dropped(self, sent):
        """The monitor decides maturity per row. A join that discarded the
        unlabelled would hand it a cohort that looks complete and is not."""
        cohort = sent.cohort(URN, "3.2.1")
        assert len(cohort) == 5
        assert sum(1 for r in cohort if "label" in r) == 3

    def test_a_window_excludes_what_arrived_after_it(self, sent):
        """A review of last quarter should see the population last quarter saw."""
        before_labels = sent.cohort(URN, "3.2.1", known_by=T0 + DAY)
        assert len(before_labels) == 5
        assert all("label" not in r for r in before_labels)

    def test_a_time_window_filters_by_the_row_s_own_clock(self, sent):
        assert len(sent.rows(URN, "3.2.1", "scores", since=T0 + 2)) == 3

    def test_the_sample_rate_travels_with_the_rows(self, telemetry,
                                                   approved_version):
        telemetry.ingest(URN, "3.2.1", "scores", scores(4), sample_rate=0.05)
        assert all(r["sample_rate"] == 0.05
                   for r in telemetry.cohort(URN, "3.2.1"))


class TestTheStatusSaysWhetherAnythingIsArriving:
    def test_silence_is_reported_in_days(self, telemetry, approved_version):
        telemetry.ingest(URN, "3.2.1", "scores", scores(3))
        status = telemetry.status(URN, "3.2.1", now=T0 + 10 * DAY)
        assert status["silent_days"] == pytest.approx(10.0, abs=0.1)
        assert "nothing scored for" in status["detail"]

    def test_a_version_that_has_sent_nothing_says_so(self, telemetry,
                                                     approved_version):
        status = telemetry.status(URN, "3.2.1")
        assert status["scores"] == 0
        assert "cannot be evaluated from storage" in status["detail"]

    def test_a_sample_speaks_for_itself_and_says_so(self, telemetry,
                                                    approved_version):
        telemetry.ingest(URN, "3.2.1", "scores", scores(4), sample_rate=0.01)
        assert "speaks for the sample" in telemetry.status(URN, "3.2.1")["detail"]

    def test_the_labelled_fraction_is_reported(self, telemetry, approved_version):
        telemetry.ingest(URN, "3.2.1", "scores", scores(10))
        telemetry.ingest(URN, "3.2.1", "outcomes", outcomes(4))
        assert telemetry.status(URN, "3.2.1")["labelled_fraction"] == 0.4


class TestAMonitorCanBeEvaluatedFromStorage:
    @pytest.fixture
    def watched(self, monitoring, telemetry, registry, approved_version):
        version = registry.version(URN, "3.2.1")
        monitor = monitoring.registry.define(
            approved_version["model_id"], "psi-drift", "input_drift", "stability.psi",
            {"max": 0.25}, "person/j.okafor",
            model_version_id=version["id"])
        telemetry.ingest(URN, "3.2.1", "scores", scores(20, at=T0))
        telemetry.ingest(URN, "3.2.1", "scores",
                         scores(20, at=T0 + 200 * DAY))
        return monitor

    def test_a_drift_monitor_reads_both_windows_from_storage(self, monitoring,
                                                             watched):
        out = monitoring.evaluate_from_telemetry(
            watched["id"], since=T0 + 199 * DAY, until=T0 + 300 * DAY,
            reference_from=T0 - DAY, reference_to=T0 + DAY)
        assert out["observation"]["value"] is not None

    def test_a_window_with_no_telemetry_is_refused(self, monitoring, watched):
        from core.monitoring import MonitorError
        with pytest.raises(MonitorError) as exc:
            monitoring.evaluate_from_telemetry(watched["id"],
                                               since=T0 + 900 * DAY)
        assert exc.value.code == "no_telemetry_in_window"

    def test_an_empty_reference_window_is_refused(self, monitoring, watched):
        from core.monitoring import MonitorError
        with pytest.raises(MonitorError) as exc:
            monitoring.evaluate_from_telemetry(
                watched["id"], since=T0 - DAY, until=T0 + DAY,
                reference_from=T0 + 900 * DAY, reference_to=T0 + 901 * DAY)
        assert exc.value.code == "empty_reference_window"

    def test_a_service_without_telemetry_says_so(self, db, catalogue, evidence,
                                                 approved_version, findings):
        from core.monitoring import (BreachRegister, MonitorError, MonitorRegistry,
                                     MonitoringService)
        from db import BreachRepository, MonitorRepository, ObservationRepository
        bare = MonitoringService(
            MonitorRegistry(MonitorRepository(db), catalogue, evidence),
            ObservationRepository(db),
            BreachRegister(BreachRepository(db), findings, evidence),
            catalogue, evidence)
        with pytest.raises(MonitorError) as exc:
            bare.evaluate_from_telemetry("any")
        assert exc.value.code == "no_telemetry"
