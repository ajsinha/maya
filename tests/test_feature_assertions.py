"""What must be true of a feature's values, checked every time they are loaded.

Most "model failures" are data failures, and the ones that hurt are not the
loads that fail — those get noticed — but the loads that SUCCEED while being
wrong. A column that arrives 60% null because an upstream join changed, a rate
that arrives in basis points instead of percent, an identifier that stopped
being unique: each materialises cleanly, passes every schema check the platform
has, and is discovered a quarter later by somebody reconciling a number.
"""
from __future__ import annotations

import pytest

from core.features.assertions import check, evaluate, validate
from core.features.common import FeatureError


class TestDeclaringThem:
    @pytest.mark.parametrize("kind,extra", [
        ("not_null", {"max_null_rate": 0.01}),
        ("in_range", {"minimum": 0, "maximum": 1}),
        ("in_set", {"allowed": ["a", "b"]}),
        ("unique", {"max_duplicate_rate": 0.0}),
    ])
    def test_every_kind_is_accepted(self, kind, extra):
        assert validate([{"kind": kind, **extra}])[0]["kind"] == kind

    def test_an_unknown_kind_is_refused_by_name(self):
        with pytest.raises(FeatureError) as exc:
            validate([{"kind": "looks_sensible"}])
        assert "the four are" in str(exc.value)

    def test_an_in_range_with_no_bounds_asserts_nothing(self):
        with pytest.raises(FeatureError, match="asserts nothing"):
            validate([{"kind": "in_range"}])

    def test_an_impossible_range_is_refused_rather_than_quarantining_everything(self):
        with pytest.raises(FeatureError, match="can never hold"):
            validate([{"kind": "in_range", "minimum": 10, "maximum": 1}])

    def test_an_empty_set_is_refused(self):
        with pytest.raises(FeatureError, match="can never hold"):
            validate([{"kind": "in_set", "allowed": []}])

    def test_not_null_defaults_to_zero(self):
        """A feature that may be null usually says so; one that says nothing
        usually should not be."""
        assert validate([{"kind": "not_null"}])[0]["max_null_rate"] == 0.0


class TestTheNumberMattersAsMuchAsTheVerdict:
    """*`balance` failed not_null* sends somebody to look. *`balance` is 61%
    null against a limit of 1%* tells them what happened before they arrive."""

    def test_a_null_failure_reports_the_rate_and_the_limit(self):
        out = evaluate({"kind": "not_null", "max_null_rate": 0.1},
                       [1, None, None, 4])
        assert out["passed"] is False
        assert out["observed"] == 0.5
        assert "50.0%" in out["detail"] and "10.0%" in out["detail"]

    def test_a_range_failure_names_offending_values(self):
        out = evaluate({"kind": "in_range", "minimum": 0, "maximum": 1},
                       [0.5, 55.0])
        assert out["passed"] is False
        assert 55.0 in out["offending_examples"]

    def test_the_unit_change_is_the_one_this_catches(self):
        """A rate arriving in basis points instead of percent is still a
        number, and every other check the platform has passes it."""
        as_percent = evaluate({"kind": "in_range", "minimum": 0, "maximum": 1},
                              [0.03, 0.04])
        as_bps = evaluate({"kind": "in_range", "minimum": 0, "maximum": 1},
                          [300.0, 400.0])
        assert as_percent["passed"] and not as_bps["passed"]

    def test_a_stranger_in_a_closed_set_is_named(self):
        out = evaluate({"kind": "in_set", "allowed": ["A", "B"]},
                       ["A", "B", "C"])
        assert out["passed"] is False and "C" in out["offending_examples"]

    def test_duplicates_are_counted_against_non_null_values(self):
        out = evaluate({"kind": "unique", "max_duplicate_rate": 0.0},
                       ["x", "x", None])
        assert out["passed"] is False and out["observed"] == 0.5

    def test_an_empty_column_passes_and_says_why(self):
        out = evaluate({"kind": "not_null", "max_null_rate": 0.0}, [])
        assert out["passed"] and out["detail"] == "no rows to check"

    def test_nulls_are_not_range_failures(self):
        """Nulls are `not_null`'s business. Counting them twice would make one
        bad load look like two different problems."""
        out = evaluate({"kind": "in_range", "minimum": 0, "maximum": 1},
                       [0.5, None])
        assert out["passed"]


class TestTheReport:
    def test_it_names_the_feature_the_assertion_and_the_number(self):
        out = check([{"pd": None}, {"pd": 0.5}],
                    {"pd": validate([{"kind": "not_null"}])})
        assert not out["passed"]
        assert "pd:" in out["failed"][0] and "50.0%" in out["failed"][0]

    def test_a_feature_with_no_assertions_is_not_counted(self):
        out = check([{"x": 1}], {"x": []})
        assert out["checked"] == 0 and out["passed"]

    def test_all_holding_says_so(self):
        out = check([{"pd": 0.5}], {"pd": validate([{"kind": "not_null"}])})
        assert out["passed"] and "all held" in out["detail"]


class TestQuarantine:
    """A failing load is quarantined, not rejected. Deleting the evidence of a
    bad load is how nobody finds out what arrived."""

    @pytest.fixture
    def loaded(self, full_features):
        f = full_features
        f.define("pd", "borrower_id", "numeric", "probability of default",
                 "person/d.raman",
                 assertions=[{"kind": "in_range", "minimum": 0, "maximum": 1}])
        f.create_view("book", "borrower_id", "person/j.okafor", ["pd"])
        return f

    def test_a_good_load_is_not_quarantined(self, loaded):
        loaded.materialise("book", [{"entity_id": "B1", "event_ts": 1.0,
                                     "ingest_ts": 1.0, "pd": 0.2}], ["pd"])
        pinned = loaded.views.pinned("book", 1)
        assert pinned["delta_version"] is not None

    def test_a_bad_load_is_recorded_and_readable(self, loaded):
        """The rows are written and the version exists: the load is evidence of
        what arrived."""
        out = loaded.materialise("book", [{"entity_id": "B1", "event_ts": 1.0,
                                           "ingest_ts": 1.0, "pd": 55.0}],
                                 ["pd"])
        assert out["row_count"] == 1
        assert out["quarantined"] is True
        assert "55" in str(out["assertion_report"])

    def test_nothing_may_pin_a_quarantined_version(self, loaded):
        """What quarantine buys. A featureset that could bind one would make
        every assertion advisory."""
        loaded.materialise("book", [{"entity_id": "B1", "event_ts": 1.0,
                                     "ingest_ts": 1.0, "pd": 55.0}], ["pd"])
        with pytest.raises(FeatureError) as exc:
            loaded.views.pinned("book", 1)
        assert "QUARANTINED" in str(exc.value)
        assert "advisory" in str(exc.value), "say why it is refused"
        assert "Load again" in str(exc.value), "and what to do"

    def test_a_feature_with_no_assertions_never_quarantines(self, full_features):
        f = full_features
        f.define("anything", "borrower_id", "numeric", "d", "person/d.raman")
        f.create_view("loose", "borrower_id", "person/j.okafor", ["anything"])
        out = f.materialise("loose", [{"entity_id": "B1", "event_ts": 1.0,
                                       "ingest_ts": 1.0, "anything": 1e9}],
                            ["anything"])
        assert out["quarantined"] is False
