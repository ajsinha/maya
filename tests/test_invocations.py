"""Every time a warrant was actually used, and how it went.

Resolutions were evidence nodes and invocations were not recorded at all, so the
register could say who was ENTITLED to run a model and never who did. The
question that matters most is the third one: which grants has nobody used at
all? A grant nobody has exercised in a year is an authorisation the estate is
carrying for no reason, and least privilege says to withdraw it — but nothing
could name one, so nobody ever did.
"""
from __future__ import annotations

import time

import pytest

from core.execution.invocations import DAY, InvocationLog


@pytest.fixture
def log(repos, db):
    from db import InvocationRepository
    return InvocationLog(InvocationRepository(db))


def _warrant(warrant_id="w-1", principal="svc/scoring", use="origination",
             env="prod", semver="1.0.0"):
    return {"warrant_id": warrant_id,
            "subject": {"model_urn": "maya://model/x", "version": semver,
                        "model_version_id": "v-1"},
            "authority": {"principal": principal, "declared_use": use,
                          "environment": env},
            "operation": {"verb": "score"}}


class TestRecordingTheShapeNotTheContent:
    """Who called, under what use, against which version, how long, how it
    ended. No feature values and no prediction: those carry personal data, and
    a table that quietly accumulated them would be a retention problem nobody
    decided to take on."""

    def test_a_call_is_recorded_with_its_authority_and_latency(self, log):
        row = log.record(warrant=_warrant(), outcome="ok", model_id="m-1",
                         latency_ms=12.5, boundary_ok=True)
        assert row["principal"] == "svc/scoring"
        assert row["declared_use"] == "origination"
        assert row["semver"] == "1.0.0" and row["latency_ms"] == 12.5

    def test_no_feature_values_or_prediction_are_stored(self, log, db):
        log.record(warrant=_warrant(), outcome="ok", model_id="m-1")
        columns = set(db.query("SELECT * FROM warrant_invocation")[0])
        assert not (columns & {"inputs", "features", "prediction", "output"})

    def test_an_unknown_outcome_is_recorded_as_an_error_not_dropped(self, log):
        row = log.record(warrant=_warrant(), outcome="banana", model_id="m-1")
        assert row["outcome"] == "error"


class TestARefusalIsAnOutcomeNotAnAbsence:
    """A log holding only successes makes a model look healthier the more often
    it is refused."""

    def test_refusals_are_counted_and_keyed_by_code(self, log):
        log.record(warrant=_warrant(), outcome="ok", model_id="m-1")
        log.record(warrant=_warrant(), outcome="refused", model_id="m-1",
                   refusal_code="expired")
        out = log.for_model("m-1")
        assert out["ok"] == 1 and out["refused"] == 1
        assert out["by_refusal"]["expired"] == 1
        assert "look healthier" in out["detail"]

    def test_a_call_that_never_got_a_warrant_is_still_recorded(self, log):
        """The kind an access review wants most, and the kind a warrant-keyed
        log would miss entirely because there is no warrant to key it to."""
        row = log.record_refusal(model_id="m-1", principal="svc/curious",
                                 declared_use="whatever", environment="prod",
                                 code="no_entitlement")
        assert row["warrant_id"] == "" and row["outcome"] == "refused"
        assert log.for_model("m-1")["refused"] == 1

    def test_a_model_never_called_says_so(self, log):
        assert log.for_model("m-nothing")["detail"] == "never invoked"


class TestLatency:
    def test_the_median_is_reported_rather_than_the_mean(self, log):
        """One cold start should not be what a reader takes away about how this
        model behaves."""
        for ms in (10.0, 11.0, 12.0, 13.0, 5000.0):
            log.record(warrant=_warrant(), outcome="ok", model_id="m-1",
                       latency_ms=ms)
        assert log.for_model("m-1")["p50_latency_ms"] == 12.0


class TestTheCatalogue:
    """FR-WARRANT-016. The last three columns could not be answered at all
    until invocations were recorded."""

    class _Warrants:
        def __init__(self, grants):
            self._grants = grants

        def every_grant(self):
            return self._grants

    class _Registry:
        def by_id(self, model_id):
            return {"id": model_id, "urn": f"maya://model/{model_id}",
                    "name": model_id, "tier": 2}

    def _log(self, repos, db, grants):
        from db import InvocationRepository
        return InvocationLog(InvocationRepository(db),
                             registry=self._Registry(),
                             warrants=self._Warrants(grants), idle_days=90)

    def test_a_grant_nobody_has_ever_used_is_named_and_put_first(self, repos, db):
        grants = [{"id": "g-used", "model_id": "m-1", "principal": "svc/a",
                   "declared_use": "u", "environment": "prod"},
                  {"id": "g-never", "model_id": "m-2", "principal": "svc/b",
                   "declared_use": "u", "environment": "prod"}]
        log = self._log(repos, db, grants)
        log.record(warrant=_warrant(principal="svc/a"), outcome="ok",
                   model_id="m-1")
        out = log.catalogue()
        assert out["never_used"] == 1
        assert out["grants"][0]["grant_id"] == "g-never", "worst read first"
        assert out["grants"][0]["never_used"] is True
        assert "carrying for no reason" in out["detail"]

    def test_never_used_and_idle_are_told_apart(self, repos, db):
        """They call for different actions: one is a withdrawal, the other is a
        conversation."""
        grants = [{"id": "g-idle", "model_id": "m-1", "principal": "svc/a",
                   "declared_use": "u", "environment": "prod"}]
        log = self._log(repos, db, grants)
        log.record(warrant=_warrant(principal="svc/a"), outcome="ok",
                   model_id="m-1", at=time.time() - 200 * DAY)
        entry = log.catalogue()["grants"][0]
        assert entry["never_used"] is False
        assert entry["withdrawable"] is True
        assert entry["idle_days"] > 90

    def test_a_grant_in_active_use_is_not_withdrawable(self, repos, db):
        grants = [{"id": "g-live", "model_id": "m-1", "principal": "svc/a",
                   "declared_use": "u", "environment": "prod"}]
        log = self._log(repos, db, grants)
        log.record(warrant=_warrant(principal="svc/a"), outcome="ok",
                   model_id="m-1")
        out = log.catalogue()
        assert out["withdrawable"] == 0
        assert "every one of them is in use" in out["detail"]

    def test_it_reports_what_each_grant_points_at(self, repos, db):
        grants = [{"id": "g", "model_id": "m-1", "principal": "svc/a",
                   "declared_use": "origination", "environment": "prod"}]
        entry = self._log(repos, db, grants).catalogue()["grants"][0]
        assert entry["urn"] == "maya://model/m-1" and entry["tier"] == 2
        assert entry["declared_use"] == "origination"

    def test_no_grants_says_so(self, repos, db):
        assert self._log(repos, db, []).catalogue()["detail"] == \
            "no standing grants exist"
