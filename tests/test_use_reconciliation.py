"""What a model was approved for, against what it is actually used for.

Every individual call is already legitimate. A declared use is checked at
resolution against the grant that carries it, and a call for a use nobody holds
is refused on the spot — so there is no single invocation in the log that
anybody should object to. **Off-label use is not a bad call. It is a pattern of
good ones**, and nothing was looking at the pattern.
"""
from __future__ import annotations

import time

import pytest

from core.execution.invocations import InvocationLog
from core.execution.reconciliation import DAY, UseReconciliation


class _Warrants:
    def __init__(self, grants):
        self._grants = grants

    def grants_for(self, urn):
        return self._grants


class _Registry:
    def __init__(self, purpose="12-month PD at origination"):
        self.model = {"id": "m-1", "urn": "maya://model/x", "name": "X",
                      "owner": "person/o", "purpose": purpose, "tier": 2}

    def require(self, urn):
        return self.model

    def list(self):
        return [self.model]


@pytest.fixture
def setup(repos, db, findings):
    from db import InvocationRepository

    log = InvocationLog(InvocationRepository(db))

    def build(grants, purpose="12-month PD at origination"):
        return log, UseReconciliation(
            log, _Warrants(grants), _Registry(purpose), findings=findings,
            attempt_threshold=20, window_days=90)
    return build


def _call(log, use, outcome="ok", principal="svc/a", env="prod", at=None):
    log.record(
        warrant={"warrant_id": "w", "subject": {"model_urn": "maya://model/x"},
                 "authority": {"principal": principal, "declared_use": use,
                               "environment": env},
                 "operation": {"verb": "score"}},
        outcome=outcome, model_id="m-1", at=at)


class TestThePatternNotTheCall:
    def test_persistent_refused_attempts_are_named_as_off_label(self, setup):
        """Every one of these refusals is the control working, which is exactly
        why nothing was looking at them."""
        log, uses = setup([{"declared_use": "origination_decision"}])
        for _ in range(25):
            _call(log, "pricing", outcome="refused", principal="svc/pricing")
        out = uses.for_model("maya://model/x")
        assert out["off_label"], "a pattern of refusals is the signal"
        assert out["off_label"][0]["use"] == "pricing"
        assert out["off_label"][0]["refused"] == 25
        assert "pattern of refusals rather than a bad call" in out["detail"]

    def test_a_few_attempts_are_reported_but_not_off_label(self, setup):
        """Somebody's mistake is not a team's intention."""
        log, uses = setup([{"declared_use": "origination_decision"}])
        for _ in range(3):
            _call(log, "pricing", outcome="refused")
        out = uses.for_model("maya://model/x")
        assert not out["off_label"]
        assert out["attempted_without_a_grant"][0]["use"] == "pricing"

    def test_a_granted_use_nobody_exercises_is_reported(self, setup):
        log, uses = setup([{"declared_use": "origination_decision"},
                           {"declared_use": "stress_testing"}])
        _call(log, "origination_decision")
        out = uses.for_model("maya://model/x")
        assert out["granted_but_never_exercised"] == ["stress_testing"]

    def test_a_use_crossing_environments_is_reported(self, setup):
        log, uses = setup([{"declared_use": "origination_decision"}])
        _call(log, "origination_decision", env="lab")
        _call(log, "origination_decision", env="prod")
        assert uses.for_model("maya://model/x")["crossed_environments"] == \
            ["origination_decision"]

    def test_calls_outside_the_window_are_not_counted(self, setup):
        log, uses = setup([{"declared_use": "origination_decision"}])
        _call(log, "pricing", outcome="refused", at=time.time() - 200 * DAY)
        assert uses.for_model("maya://model/x")["invocations"] == 0

    def test_a_model_nobody_calls_says_so(self, setup):
        _log, uses = setup([{"declared_use": "origination_decision"}])
        out = uses.for_model("maya://model/x")
        assert "nothing can be said about actual use" in out["detail"]


class TestPurposeAgainstTraffic:
    """Both the purpose and the grants were approved, separately, by people who
    never saw them side by side."""

    def test_a_dominant_use_the_purpose_does_not_mention_is_flagged(self, setup):
        log, uses = setup([{"declared_use": "stress_testing"}],
                          purpose="12-month PD at origination")
        for _ in range(10):
            _call(log, "stress_testing")
        mismatch = uses.for_model("maya://model/x")["purpose_mismatch"]
        assert mismatch and mismatch["dominant_use"] == "stress_testing"
        assert "question for a person rather than a defect" in mismatch["detail"]

    def test_a_use_the_purpose_does_mention_is_not_flagged(self, setup):
        log, uses = setup([{"declared_use": "origination_decision"}],
                          purpose="12-month PD at origination")
        for _ in range(10):
            _call(log, "origination_decision")
        assert uses.for_model("maya://model/x")["purpose_mismatch"] is None

    def test_an_evenly_split_model_is_not_flagged(self, setup):
        """A model used for two approved things is not a model being misused,
        and flagging it would be how these reports stop being read."""
        log, uses = setup([{"declared_use": "stress_testing"},
                           {"declared_use": "origination_decision"}],
                          purpose="12-month PD at origination")
        for _ in range(5):
            _call(log, "stress_testing")
            _call(log, "origination_decision")
        assert uses.for_model("maya://model/x")["purpose_mismatch"] is None


class TestTheSweep:
    def test_only_the_persistent_pattern_raises_a_finding(self, setup, findings):
        """A register that raised a finding every time a model's traffic was
        uneven is one whose findings nobody reads."""
        log, uses = setup([{"declared_use": "origination_decision"},
                           {"declared_use": "stress_testing"}])
        for _ in range(25):
            _call(log, "pricing", outcome="refused")
        out = uses.sweep()
        assert out["count"] == 1
        raised = [f for f in findings.open_for("m-1") if f["category"] == "use"]
        assert raised and "four hundred times" not in raised[0]["description"]
        assert "the control working" in raised[0]["description"]

    def test_it_does_not_raise_the_same_finding_twice(self, setup):
        """A quarterly sweep must not produce a quarterly duplicate."""
        log, uses = setup([{"declared_use": "origination_decision"}])
        for _ in range(25):
            _call(log, "pricing", outcome="refused")
        assert uses.sweep()["count"] == 1
        assert uses.sweep()["count"] == 0

    def test_a_clean_estate_raises_nothing(self, setup):
        log, uses = setup([{"declared_use": "origination_decision"}])
        _call(log, "origination_decision")
        out = uses.sweep()
        assert out["count"] == 0 and "no off-label pattern" in out["detail"]
