"""The value the model was trained on, and the value it was actually given.

Skew is almost never *the two stores disagree*. It is that the two stores were
asked different questions: the online store answered *what is the value now*, and
training asked *what was knowable at the moment of the decision*.
"""
from __future__ import annotations

import pytest

from core.features.common import FeatureError
from core.features.skew import (AGREES, FUTURE_VALUE, LATE_ARRIVAL, STALE,
                                UNKNOWN, UNMATCHED, VERDICTS, SkewDetector)

DECISION = 1000.0
NOW = 2000.0


@pytest.fixture
def detector():
    return SkewDetector()


def _row(value, event, ingest):
    return {"value": value, "event_ts": event, "ingest_ts": ingest}


class TestTheVerdicts:
    def test_every_verdict_says_what_it_means_and_how_bad(self):
        assert all(v["means"] and v["severity"] for v in VERDICTS.values())

    def test_the_two_nobody_looks_for_are_the_serious_ones(self):
        assert VERDICTS[FUTURE_VALUE]["severity"] == "high"
        assert VERDICTS[LATE_ARRIVAL]["severity"] == "high"
        assert VERDICTS[STALE]["severity"] == "medium"

    def test_the_future_value_verdict_says_why_backtests_looked_fine(self):
        assert "every backtest looked fine" in VERDICTS[FUTURE_VALUE]["means"]

    def test_the_late_arrival_verdict_says_why_one_clock_cannot_see_it(self):
        assert "an event-time-only store cannot tell this" in (
            VERDICTS[LATE_ARRIVAL]["means"])


class TestTheOrdinaryCases:
    def test_the_knowable_value_agrees(self, detector):
        history = [_row(1.0, 900.0, 900.0)]
        out = detector.compare(history, "value", 1.0, DECISION, now=NOW)
        assert out["verdict"] == AGREES

    def test_a_float32_online_store_still_agrees(self, detector):
        """Loose enough that precision does not read as skew."""
        history = [_row(0.1, 900.0, 900.0)]
        out = detector.compare(history, "value", 0.10000001, DECISION, now=NOW)
        assert out["verdict"] == AGREES

    def test_an_older_value_is_stale(self, detector):
        history = [_row(1.0, 800.0, 800.0), _row(2.0, 950.0, 950.0)]
        out = detector.compare(history, "value", 1.0, DECISION, now=NOW)
        assert out["verdict"] == STALE
        assert out["expected_at_decision"] == 2.0

    def test_nothing_offline_is_not_agreement(self, detector):
        """A different fact from agreement."""
        out = detector.compare([], "value", 1.0, DECISION, now=NOW)
        assert out["verdict"] == UNKNOWN

    def test_a_value_matching_nothing_is_the_worst_case(self, detector):
        """The two are computing different things, which a freshness SLA would
        never catch."""
        history = [_row(1.0, 900.0, 900.0)]
        out = detector.compare(history, "value", 99.0, DECISION, now=NOW)
        assert out["verdict"] == UNMATCHED
        assert VERDICTS[UNMATCHED]["severity"] == "high"


class TestTheCasesOnlyTwoClocksCanSeparate:
    def test_serving_a_value_that_was_not_yet_true_is_the_classic_bug(
            self, detector):
        """The model was trained on what was knowable and served tomorrow's
        value — and every backtest looked fine."""
        history = [
            _row(1.0, 900.0, 900.0),      # knowable at the decision
            _row(2.0, 1500.0, 1500.0),    # true and known only afterwards
        ]
        out = detector.compare(history, "value", 2.0, DECISION, now=NOW)
        assert out["verdict"] == FUTURE_VALUE
        assert out["expected_at_decision"] == 1.0

    def test_a_value_true_then_but_arriving_later_is_the_subtler_leak(
            self, detector):
        """The online store answered with something the decision path could not
        legitimately have had, and an event-time-only store cannot tell it from
        a correct answer."""
        history = [
            _row(1.0, 900.0, 900.0),
            # TRUE before the decision, but not KNOWN until after it — the
            # late-arriving row that makes leakage possible.
            _row(5.0, 950.0, 1800.0),
        ]
        out = detector.compare(history, "value", 5.0, DECISION, now=NOW)
        assert out["verdict"] == LATE_ARRIVAL
        assert out["matched_ingest"] == 1800.0

    def test_the_two_leaks_are_told_apart_by_the_event_clock(self, detector):
        """The same served value is tomorrow's value or a late arrival
        depending only on when it became TRUE — which is what having two clocks
        rather than one buys, and they have different causes and fixes."""
        not_yet_true = [_row(1.0, 900.0, 900.0), _row(7.0, 1500.0, 1500.0)]
        arrived_late = [_row(1.0, 900.0, 900.0), _row(7.0, 950.0, 1500.0)]
        assert detector.compare(not_yet_true, "value", 7.0, DECISION,
                                now=NOW)["verdict"] == FUTURE_VALUE
        assert detector.compare(arrived_late, "value", 7.0, DECISION,
                                now=NOW)["verdict"] == LATE_ARRIVAL


class TestABatch:
    def test_an_empty_batch_is_refused(self, detector):
        """A skew check over no observations reports no skew, which is the same
        answer as a clean estate and a different fact."""
        with pytest.raises(FeatureError) as caught:
            detector.observe([])
        assert "a different fact" in str(caught.value)

    def test_a_clean_batch_says_what_it_is_not(self, detector):
        """A perfectly fresh store computing a subtly different feature passes
        every freshness check ever written."""
        out = detector.observe([
            {"entity": "c-1", "at": DECISION, "served": 1.0,
             "history": [_row(1.0, 900.0, 900.0)]}], now=NOW)
        assert out["serious"] == 0
        assert "NOT: a freshness check" in out["detail"]

    def test_serious_divergence_is_counted_and_explained(self, detector):
        out = detector.observe([
            {"entity": "c-1", "at": DECISION, "served": 2.0,
             "history": [_row(1.0, 900.0, 900.0), _row(2.0, 1500.0, 1500.0)]},
            {"entity": "c-2", "at": DECISION, "served": 1.0,
             "history": [_row(1.0, 900.0, 900.0)]}], now=NOW)
        assert out["serious"] == 1
        assert out["by_verdict"][FUTURE_VALUE] == 1
        assert "invisible to all of them" in out["detail"]

    def test_it_lands_on_the_evidence_chain(self, evidence):
        detector = SkewDetector(evidence)
        detector.observe([{"entity": "c-1", "at": DECISION, "served": 1.0,
                           "history": [_row(1.0, 900.0, 900.0)]}],
                         urn="maya://model/x", now=NOW)
        assert any(n["kind"] == "skew_checked" for n in evidence.repo.many())


class TestOverHttp:
    def test_a_comparison_is_served(self, registered, people):
        from tests.conftest import URN as U
        r = registered.post("/api/v1/skew", auth=("admin", "maya-admin-dev"),
                        json={"observations": [
                            {"entity": "c-1", "at": DECISION, "served": 2.0,
                             "history": [
                                 {"value": 1.0, "event_ts": 900.0,
                                  "ingest_ts": 900.0},
                                 {"value": 2.0, "event_ts": 1500.0,
                                  "ingest_ts": 1500.0}]}],
                              "urn": U})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["by_verdict"][FUTURE_VALUE] == 1
        assert "invisible to all of them" in body["detail"]

    def test_an_empty_batch_is_refused(self, registered, people):
        from tests.conftest import URN as U
        r = registered.post("/api/v1/skew", auth=("admin", "maya-admin-dev"),
                            json={"urn": U, "observations": []})
        assert r.status_code >= 400, r.text
        assert "a different fact" in r.json()["detail"]
