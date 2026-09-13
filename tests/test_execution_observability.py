"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Two columns nobody selected, and the limitation neither of them repairs.

C-6 said `descriptor_only` warrants make governance depend on client honesty,
and §4.7 found four of its five mitigations unbuilt. `warrant.flavour` was
written at every issue and read by nothing; `TelemetryCollector.estate()`
classified every version as silent, never or sending and no job consumed it.

The most important assertion in this file is
`test_it_does_not_claim_to_have_observed_an_engine`. MAYA does not run models.
Nothing here detects an engine ignoring its operating boundary, and a module
that counted unobserved execution and then read as though it had observed
something would be worse than the gap it closes.
"""
from __future__ import annotations

import pytest

from core.execution.observability import (ESCALATE_AT_OR_ABOVE, UNOBSERVED,
                                          ExecutionObservability)
from db.schema.metadata import METADATA


def _warrant(db, wid, model_id, flavour, principal="svc-pricing",
             revoked=0, environment="production"):
    row = {"id": wid, "model_id": model_id, "flavour": flavour,
           "principal": principal, "revoked": revoked,
           "environment": environment}
    for col in METADATA.tables["warrant"].columns:
        if col.name in row or col.nullable or col.server_default is not None:
            continue
        row[col.name] = 0.0 if str(col.type).upper().startswith(
            ("DOUBLE", "FLOAT", "INTEGER")) else f"{col.name}-x"
    db.execute(f"INSERT INTO warrant ({', '.join(row)}) VALUES "
               f"({', '.join(':' + c for c in row)})", row)


class FakeRegistry:
    def __init__(self, models):
        self._models = models

    def list(self):
        return list(self._models)

    def get(self, urn):
        return next((m for m in self._models if m["urn"] == urn), None)


@pytest.fixture()
def estate():
    return [
        {"id": "m-1", "urn": "urn:maya:model:pd", "name": "pd", "tier": 1},
        {"id": "m-2", "urn": "urn:maya:model:lgd", "name": "lgd", "tier": 4},
    ]


@pytest.fixture()
def obs(db, estate):
    return ExecutionObservability(db, FakeRegistry(estate))


class TestTheColumnNobodyRead:
    def test_it_counts_live_warrants_by_flavour(self, obs, db, estate):
        _warrant(db, "w-1", "m-1", UNOBSERVED)
        _warrant(db, "w-2", "m-2", "python.callable")
        posture = obs.posture(estate)
        assert posture["live_warrants"] == 2
        assert posture["unobserved"] == 1
        assert posture["share_unobserved"] == 0.5

    def test_a_revoked_warrant_is_not_live(self, obs, db, estate):
        _warrant(db, "w-1", "m-1", UNOBSERVED, revoked=1)
        assert obs.posture(estate)["live_warrants"] == 0

    def test_a_missing_flavour_counts_as_unobserved(self, obs, db, estate):
        """The honest default. A warrant whose flavour nobody set is not a
        warrant over an engine somebody can see into."""
        _warrant(db, "w-1", "m-1", "")
        assert obs.posture(estate)["unobserved"] == 1

    def test_tier_one_on_an_opaque_engine_is_singled_out(self, obs, db, estate):
        """Not every tier. A Tier 4 model on an opaque engine is a normal
        arrangement, and raising it would bury the Tier 1 case."""
        _warrant(db, "w-1", "m-1", UNOBSERVED)          # tier 1
        _warrant(db, "w-2", "m-2", UNOBSERVED)          # tier 4
        escalating = obs.posture(estate)["unobserved_at_tier"]
        assert [e["urn"] for e in escalating] == ["urn:maya:model:pd"]
        assert ESCALATE_AT_OR_ABOVE == 2

    def test_an_estate_with_no_warrants_says_so(self, obs, estate):
        assert "nothing is being executed" in obs.posture(estate)["detail"]


class TestWhatItRefusesToClaim:
    def test_it_does_not_claim_to_have_observed_an_engine(self, obs, db, estate):
        """The assertion this whole module is measured against.

        MAYA does not run models. Counting how much of the estate is governed
        by a document is useful; letting that count read as though something
        had been observed would be worse than not counting at all.
        """
        _warrant(db, "w-1", "m-1", UNOBSERVED)
        posture = obs.posture(estate)
        assert "does_not_prove" in posture
        assert "does not run models" in posture["does_not_prove"]

    def test_silence_is_reported_with_what_it_cannot_distinguish(self, db,
                                                                 estate):
        class Quiet:
            @staticmethod
            def estate(models, now=None):
                return {"versions": [{"model": "urn:maya:model:pd",
                                      "semver": "1.0.0",
                                      "never": True, "silent": False}]}
        obs = ExecutionObservability(db, FakeRegistry(estate), Quiet())
        _warrant(db, "w-1", "m-1", UNOBSERVED)
        found = obs.authorised_and_silent(estate)
        assert len(found) == 1
        assert "cannot tell those apart" in found[0]["explanation_absent"]

    def test_a_model_that_is_reporting_raises_nothing(self, db, estate):
        class Busy:
            @staticmethod
            def estate(models, now=None):
                return {"versions": [{"model": "urn:maya:model:pd",
                                      "semver": "1.0.0",
                                      "never": False, "silent": False}]}
        obs = ExecutionObservability(db, FakeRegistry(estate), Busy())
        _warrant(db, "w-1", "m-1", UNOBSERVED)
        assert obs.authorised_and_silent(estate) == []

    def test_with_no_telemetry_wired_it_returns_nothing_rather_than_guessing(
            self, obs, db, estate):
        _warrant(db, "w-1", "m-1", UNOBSERVED)
        assert obs.authorised_and_silent(estate) == []


class TestTheJobThatConsumesIt:
    def test_the_job_is_registered(self):
        from core.scheduler.jobs import JOBS
        assert "execution.unreported" in JOBS

    def test_it_raises_advisory_rather_than_blocking(self):
        """Against the grain of `attestation.lapsed`, and deliberately.

        Silence has an innocent reading MAYA cannot rule out. Blocking on a
        condition the platform admits it cannot diagnose trains people to
        override it, and an override performed weekly is not a control.
        """
        import inspect
        from core.scheduler.jobs import authorised_and_reporting_nothing
        src = inspect.getsource(authorised_and_reporting_nothing)
        assert "blocking=False" in src

    def test_it_skips_cleanly_when_nothing_is_wired(self):
        from core.scheduler.jobs import (JobContext,
                                         authorised_and_reporting_nothing)
        ctx = JobContext(registry=FakeRegistry([]), now=0.0)
        assert "skipped" in authorised_and_reporting_nothing(ctx)
