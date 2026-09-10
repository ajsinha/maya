"""Two implementations of one model, and the shape of their disagreement.

Independent recode is the strongest form of validation there is and the only one
that catches a specification the code does not implement. The distribution is the
whole contribution: a recode agreeing to twelve decimal places on 9,997 rows and
disagreeing wildly on three is a completely different finding from one off by
1e-9 everywhere, and a pass rate reports them identically.
"""
from __future__ import annotations

import pytest

from core.validation.common import ValidationError
from core.validation.recode import RecodeHarness


@pytest.fixture
def harness():
    return RecodeHarness()


def _pair(n=1000, noise=0.0, cliffs=None):
    model = {f"row-{i}": 1.0 + i * 0.001 for i in range(n)}
    recode = {k: v + noise for k, v in model.items()}
    recode.update(cliffs or {})
    return model, recode


class TestTheShapeNotThePassRate:
    def test_agreement_is_reported_as_agreement(self, harness):
        model, recode = _pair()
        out = harness.compare(model, recode)
        assert out["shape"]["kind"] == "agreement"
        assert out["disagreed"] == 0
        assert "written from the same specification" in out["shape"]["detail"]

    def test_a_handful_of_wild_outliers_is_a_cliff(self, harness):
        """A branch nobody tested — a boundary condition, a missing case in a
        piecewise function, a tie-break."""
        model, recode = _pair(cliffs={"row-7": 999.0, "row-88": -50.0,
                                      "row-500": 1e6})
        out = harness.compare(model, recode)
        assert out["shape"]["kind"] == "cliff"
        assert out["disagreed"] == 3
        assert "branch nobody tested" in out["shape"]["detail"]

    def test_a_few_rows_differing_slightly_is_a_tail_not_a_cliff(self, harness):
        """Float ordering, and the two implementations agree."""
        model, recode = _pair()
        for i in range(20):
            recode[f"row-{i}"] += 1e-7
        out = harness.compare(model, recode)
        assert out["shape"]["kind"] == "tail"
        assert "different order rather than a different calculation" in \
            out["shape"]["detail"]
        assert "the tolerance is a choice" in out["shape"]["detail"]

    def test_everything_differing_by_a_hair_is_the_tolerance_not_the_model(
            self, harness):
        """Calling this systematic would send a validator to re-read a
        specification that is fine."""
        model, recode = _pair(noise=1e-8)
        out = harness.compare(model, recode)
        assert out["shape"]["kind"] == "tolerance"
        assert "tighter than the arithmetic warrants" in out["shape"]["detail"]

    def test_most_outputs_disagreeing_is_systematic(self, harness):
        model, recode = _pair(n=100)
        recode = {k: v * 1.5 for k, v in recode.items()}
        out = harness.compare(model, recode)
        assert out["shape"]["kind"] == "systematic"
        assert "specification is where to look first" in out["shape"]["detail"]

    def test_the_same_pass_rate_can_be_two_different_shapes(self, harness):
        """The point of the whole module: 3 of 1000 disagreeing is one number
        and two entirely different findings."""
        cliff = harness.compare(*_pair(cliffs={"row-1": 500.0, "row-2": 500.0,
                                               "row-3": 500.0}))
        model, recode = _pair()
        for k in ("row-1", "row-2", "row-3"):
            recode[k] += 1e-6
        tail = harness.compare(model, recode)
        assert cliff["disagreed"] == tail["disagreed"] == 3
        assert cliff["shape"]["kind"] != tail["shape"]["kind"]


class TestTheDistribution:
    def test_quantiles_rather_than_a_mean(self, harness):
        """A mean over a bimodal difference describes neither mode."""
        out = harness.compare(*_pair(cliffs={"row-9": 1e6}))
        for q in ("min", "p50", "p90", "p99", "max"):
            assert q in out["distribution"]
        assert out["distribution"]["max"] > out["distribution"]["p50"]

    def test_relative_difference_is_reported_alongside_absolute(self, harness):
        out = harness.compare(*_pair())
        assert "relative_distribution" in out

    def test_the_worst_are_named_because_each_is_a_bug_report(self, harness):
        out = harness.compare(*_pair(cliffs={"row-42": 999.0}))
        assert out["worst"][0]["input"] == "row-42"
        assert out["worst"][0]["model"] != out["worst"][0]["recode"]


class TestWhatItRefuses:
    def test_one_side_alone_establishes_nothing(self, harness):
        with pytest.raises(ValidationError, match="one side alone"):
            harness.compare({"a": 1.0}, {})

    def test_two_unrelated_lists_are_refused(self, harness):
        with pytest.raises(ValidationError) as exc:
            harness.compare({"a": 1.0}, {"b": 1.0})
        assert "two unrelated lists" in str(exc.value)

    def test_inputs_only_one_side_saw_are_reported_not_ignored(self, harness):
        out = harness.compare({"a": 1.0, "b": 2.0}, {"a": 1.0, "c": 3.0})
        assert out["only_in_model"] == ["b"]
        assert out["only_in_recode"] == ["c"]

    def test_where_the_outputs_came_from_is_recorded_not_assumed(self, harness):
        """MAYA does not run the validator's code: executing it would put
        arbitrary code in the control plane."""
        out = harness.compare({"a": 1.0}, {"a": 1.0},
                              model_source="captive engine, warrant w-1",
                              recode_source="validator's notebook, 2026-03-04")
        assert out["sources"]["recode"].startswith("validator's notebook")

    def test_an_unstated_source_says_unstated(self, harness):
        out = harness.compare({"a": 1.0}, {"a": 1.0})
        assert out["sources"] == {"model": "unstated", "recode": "unstated"}


class TestRecording:
    def test_the_shape_goes_on_the_chain_not_only_the_counts(self, evidence):
        """*This recode found a cliff at three inputs* is the sentence a reader
        needs two years later, and a stored pass rate cannot be turned back
        into it."""
        harness = RecodeHarness(evidence=evidence)
        out = harness.compare(*_pair(cliffs={"row-3": 999.0}))
        harness.record("val-1", out)
        entries = [e for e in evidence.for_subjects(["val-1"])
                   if e["kind"] == "independent_recode_compared"]
        assert entries
        assert entries[-1]["payload"]["shape"] == "cliff"
        assert "row-3" in entries[-1]["payload"]["worst_inputs"]

    def test_with_no_evidence_engine_it_still_compares(self):
        harness = RecodeHarness()
        assert harness.record("val-1", harness.compare({"a": 1.0}, {"a": 1.0}))
