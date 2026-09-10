"""What one grant may spend, checked before the descriptor is signed.

Three limits, and they are not three sizes of the same thing. A rate limit
protects the downstream system from a loop. A quota protects the authorisation
from being used more than anybody intended — a grant issued for a nightly batch
and exercised forty thousand times a day is being used for something nobody
approved, and no rate limit would notice because none of it is fast. A cost
budget is the only one whose unit is not calls, which is why it is the one that
matters for a token-metered model.
"""
from __future__ import annotations

import time

import pytest

from core.execution.errors import WarrantError
from core.execution.quotas import LIMITS, MINUTE, WARN_AT, GrantQuotas
from tests.conftest import URN


@pytest.fixture
def invocations(db):
    from core.execution.invocations import InvocationLog
    from db import InvocationRepository
    return InvocationLog(InvocationRepository(db))


@pytest.fixture
def quotas(warrants, invocations, evidence):
    return GrantQuotas(warrants, invocations, evidence)


@pytest.fixture
def grant(warrants, attested_model):
    return warrants.grants.issue(URN, "prod", "svc/pricer", "origination",
                                 actor="s.iqbal")


def _called(invocations, grant, n=1, outcome="ok", cost=None, at=None):
    for _ in range(n):
        invocations.repo.add({
            "warrant_id": grant["id"], "model_id": grant["model_id"],
            "model_version_id": None, "semver": None,
            "principal": grant["principal"],
            "declared_use": grant["declared_use"],
            "environment": grant["environment"], "verb": "score",
            "outcome": outcome, "refusal_code": None, "latency_ms": 5.0,
            "cost": cost, "boundary_ok": True, "request_id": None,
            "at": at if at is not None else time.time()})


class TestThreeDifferentLimits:
    def test_each_says_what_it_protects(self):
        assert set(LIMITS) == {"rate", "quota", "cost"}
        assert all(v for v in LIMITS.values())

    def test_a_grant_starts_unlimited_on_every_axis(self, quotas, grant):
        """Inventing a limit would refuse work nobody agreed to refuse, and
        pretending an absent limit is a decision would be worse."""
        out = quotas.of(grant["id"])
        assert set(out["unlimited"]) == set(LIMITS)
        assert out["within_limits"] is True
        assert "a decision nobody has taken" in out["detail"]

    def test_limits_are_recorded_and_read_back(self, quotas, grant):
        out = quotas.set(grant["id"], rate=60, quota=1000, cost=25.0,
                         window_hours=12)
        ceilings = {line["limit"]: line["ceiling"] for line in out["limits"]}
        assert ceilings == {"rate": 60, "quota": 1000, "cost": 25.0}
        assert out["window_hours"] == 12.0
        assert out["unlimited"] == []

    def test_a_zero_limit_is_a_revocation_written_as_a_number(self, quotas,
                                                              grant):
        with pytest.raises(WarrantError) as caught:
            quotas.set(grant["id"], quota=0)
        assert caught.value.code == "limit_not_positive"
        assert "revoke the grant instead" in caught.value.remediation

    def test_setting_nothing_records_a_decision_nobody_made(self, quotas,
                                                            grant):
        with pytest.raises(WarrantError) as caught:
            quotas.set(grant["id"])
        assert caught.value.code == "nothing_to_set"

    def test_it_lands_on_the_evidence_chain(self, quotas, grant, evidence):
        quotas.set(grant["id"], quota=100)
        kinds = [n["kind"] for n in evidence.for_subject(grant["id"])]
        assert "warrant_limits_set" in kinds


class TestAQuotaIsNotARateLimit:
    def test_a_slow_flood_passes_the_rate_and_exhausts_the_quota(
            self, quotas, grant, invocations):
        """A grant issued for a nightly batch and exercised forty thousand
        times a day is being used for something nobody approved, and no rate
        limit would notice because none of it is fast."""
        quotas.set(grant["id"], rate=60, quota=10)
        now = time.time()
        for i in range(10):
            _called(invocations, grant, at=now - (i + 1) * MINUTE * 5)
        out = quotas.of(grant["id"], now=now)
        assert out["exhausted"] == ["quota"]
        rate = next(x for x in out["limits"] if x["limit"] == "rate")
        assert rate["spent"] == 0.0, "none of it was in the last minute"

    def test_a_burst_exhausts_the_rate_and_not_the_quota(self, quotas, grant,
                                                         invocations):
        quotas.set(grant["id"], rate=5, quota=10_000)
        _called(invocations, grant, n=5)
        out = quotas.of(grant["id"])
        assert out["exhausted"] == ["rate"]

    def test_the_rate_window_slides(self, quotas, grant, invocations):
        """A fixed bucket permits twice the limit across a boundary, and the
        whole point of a rate limit is the burst."""
        quotas.set(grant["id"], rate=5)
        now = time.time()
        _called(invocations, grant, n=5, at=now - MINUTE - 1)
        assert quotas.of(grant["id"], now=now)["within_limits"] is True

    def test_ten_expensive_calls_exhaust_a_cost_budget_ten_thousand_cheap_ones_do_not(
            self, quotas, grant, invocations):
        """The only limit whose unit is not calls, which is why it is the one
        that matters for a token-metered model."""
        quotas.set(grant["id"], quota=100_000, cost=10.0)
        _called(invocations, grant, n=10, cost=1.5)
        out = quotas.of(grant["id"])
        assert out["exhausted"] == ["cost"]
        quota = next(x for x in out["limits"] if x["limit"] == "quota")
        assert quota["share"] < 0.001

    def test_a_call_with_no_reported_cost_is_not_free(self, quotas, grant,
                                                      invocations):
        """Null means not reported. A cost budget over a column that silently
        read zero would never be reached."""
        quotas.set(grant["id"], cost=10.0)
        _called(invocations, grant, n=5, cost=None)
        out = quotas.of(grant["id"])
        cost = next(x for x in out["limits"] if x["limit"] == "cost")
        assert cost["spent"] == 0.0
        assert out["calls_in_window"] == 5


class TestRefusalsDoNotSpend:
    def test_a_retry_loop_cannot_keep_a_grant_exhausted(self, quotas, grant,
                                                        invocations):
        """Otherwise the retries consume the allowance the retries are waiting
        for, and the grant is dead until the window rolls despite never having
        been used successfully."""
        quotas.set(grant["id"], quota=5)
        _called(invocations, grant, n=50, outcome="refused")
        out = quotas.of(grant["id"])
        assert out["within_limits"] is True
        assert out["calls_in_window"] == 0

    def test_refusals_are_still_reported(self, quotas, grant, invocations):
        """The invocation log keeps them, which is what makes *who is hammering
        this* answerable."""
        quotas.set(grant["id"], quota=5)
        _called(invocations, grant, n=50, outcome="refused")
        out = quotas.of(grant["id"])
        assert out["refused_in_window"] == 50
        assert "were refused" in out["detail"]


class TestTheCheck:
    def test_a_grant_within_its_limits_passes(self, quotas, grant):
        assert quotas.check(grant["id"])["within_limits"] is True

    def test_an_exhausted_grant_is_refused_naming_which_limit(self, quotas,
                                                              grant,
                                                              invocations):
        quotas.set(grant["id"], quota=2)
        _called(invocations, grant, n=2)
        with pytest.raises(WarrantError) as caught:
            quotas.check(grant["id"])
        assert caught.value.code == "quota_limit_reached"
        assert "does not itself count against the limit" in (
            caught.value.remediation)

    def test_resolution_is_refused_before_a_descriptor_is_signed(
            self, warrants, quotas, grant, invocations, attested_model):
        """A signed descriptor IS an authorisation. Handing one out and then
        declining to honour it leaves the caller holding a warrant the platform
        does not intend to let it use."""
        quotas.set(grant["id"], quota=1)
        _called(invocations, grant, n=1)
        warrants.quotas = quotas
        with pytest.raises(WarrantError) as caught:
            warrants.resolve(URN, "prod", "svc/pricer", "origination")
        assert caught.value.code == "quota_limit_reached"

    def test_without_quotas_wired_the_limit_never_refuses(self, warrants,
                                                          quotas, grant,
                                                          invocations,
                                                          attested_model):
        """An instance that has set no limits still issues warrants, and this
        one is over its quota: whatever refuses it, it is not the quota."""
        quotas.set(grant["id"], quota=1)
        _called(invocations, grant, n=5)
        warrants.quotas = None
        with pytest.raises(WarrantError) as caught:
            warrants.resolve(URN, "prod", "svc/pricer", "origination")
        assert caught.value.code != "quota_limit_reached"


class TestTheEstate:
    def test_it_counts_the_wholly_unlimited(self, quotas, grant):
        out = quotas.across_the_estate()
        assert out["count"] == 1 and out["unlimited"] == 1
        assert "a decision nobody has taken" in out["detail"]

    def test_a_revoked_grant_is_not_listed(self, quotas, warrants, grant):
        warrants.grants.revoke(grant["id"], "no longer needed",
                               actor="s.iqbal")
        assert quotas.across_the_estate()["count"] == 0

    def test_the_closest_to_a_limit_is_first(self, quotas, grant, invocations,
                                             warrants, attested_model):
        second = warrants.grants.issue(URN, "uat", "svc/other", "testing",
                                       actor="s.iqbal")
        quotas.set(grant["id"], quota=100)
        quotas.set(second["id"], quota=10)
        _called(invocations, second, n=9)
        out = quotas.across_the_estate()
        assert out["grants"][0]["warrant_id"] == second["id"]

    def test_a_grant_near_a_limit_says_so_before_it_stops(self, quotas, grant,
                                                          invocations):
        quotas.set(grant["id"], quota=10)
        _called(invocations, grant, n=int(10 * WARN_AT))
        out = quotas.of(grant["id"])
        assert out["within_limits"] is True
        assert any(line["near"] for line in out["limits"])
        assert "before the work stops" in out["detail"]

    def test_an_unknown_grant_is_refused(self, quotas):
        with pytest.raises(WarrantError) as caught:
            quotas.of("no-such-grant")
        assert caught.value.code == "no_grant"


class TestOverHttp:
    def _granted(self, client, people):
        """The register's own path: the `registered` fixture takes a model all
        the way through, and a warrant needs one to point at."""
        r = client.post("/api/v1/warrants", auth=people["j.okafor"], json={
            "urn": URN, "environment": "prod", "principal": "svc/pricer",
            "declared_use": "origination"})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def test_limits_are_set_and_read_back(self, registered, people):
        client = registered
        warrant_id = self._granted(client, people)
        put = client.put(f"/api/v1/grant-limits/{warrant_id}",
                         auth=people["j.okafor"],
                         json={"rate": 60, "quota": 1000, "cost": 25.0})
        assert put.status_code == 200, put.text
        ceilings = {line["limit"]: line["ceiling"]
                    for line in put.json()["limits"]}
        assert ceilings == {"rate": 60, "quota": 1000, "cost": 25.0}

    def test_a_zero_limit_is_refused_by_name(self, registered, people):
        client = registered
        warrant_id = self._granted(client, people)
        r = client.put(f"/api/v1/grant-limits/{warrant_id}",
                       auth=people["j.okafor"], json={"quota": 0})
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "limit_not_positive"

    def test_the_estate_counts_the_unlimited(self, registered, people):
        client = registered
        before = client.get("/api/v1/grant-limits",
                            auth=people["s.iqbal"]).json()["unlimited"]
        self._granted(client, people)
        r = client.get("/api/v1/grant-limits", auth=people["s.iqbal"])
        assert r.status_code == 200, r.text
        # The `registered` fixture already issues one, so this is relative:
        # a fresh grant is unlimited on every axis until somebody says.
        assert r.json()["unlimited"] == before + 1

    def test_the_screen_explains_which_limit_is_which(self, client, people):
        client.post("/login", data={"username": "admin",
                                    "password": "maya-admin-dev",
                                    "next": "/warrants/estate"})
        body = client.get("/warrants/estate").text
        assert "not three sizes of the same thing" in body
        assert "does not count against the quota" in body
