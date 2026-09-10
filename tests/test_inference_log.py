"""What a model was asked, and what it answered.

The invocation log records the shape of a call — who, what for, which version,
how long, how it ended — and deliberately holds no content, because content
carries personal data. This is the other half, and everything about it is
arranged so the retention problem is one somebody *did* decide to take on.
"""
from __future__ import annotations


import pytest

from core.execution.inference import (ALWAYS, DAY, DEFAULT_RETAIN_DAYS,
                                      REASONS, RETAIN_DAYS, SAMPLE_BY_TIER,
                                      InferenceLog)
from tests.conftest import URN

FEATURES = {"dscr": 1.4, "postcode": "SW1A", "age": 42}


@pytest.fixture
def log(db, registry):
    from db import InferenceRepository
    return InferenceLog(InferenceRepository(db), registry,
                        key="a-configured-key", sampler=lambda: 0.0)


@pytest.fixture
def never(db, registry):
    """A sampler that never selects, so only the always-kept rows land."""
    from db import InferenceRepository
    return InferenceLog(InferenceRepository(db), registry,
                        key="a-configured-key", sampler=lambda: 1.0)


def _tiered(registry, tier):
    registry.set_tier(registry.require(URN)["id"], tier)


class TestTheDigestIsTheDefault:
    def test_a_logged_call_carries_digests_and_no_content(self, log, a_model):
        row = log.record(URN, principal="svc/pricer", features=FEATURES,
                         prediction=0.031)
        assert row["feature_digest"] and row["prediction_digest"]
        assert row["features"] is None and row["prediction"] is None

    def test_the_digest_is_keyed(self, log, a_model, db, registry):
        """An unkeyed digest of a small feature vector is a lookup table
        anybody with the same hash function can enumerate."""
        from db import InferenceRepository
        unkeyed = InferenceLog(InferenceRepository(db), registry, key="",
                               sampler=lambda: 0.0)
        assert log.digest(FEATURES).startswith("hmac:")
        assert log.digest(FEATURES) != unkeyed.digest(FEATURES)

    def test_two_different_keys_give_different_digests(self, db, registry,
                                                       a_model):
        from db import InferenceRepository
        a = InferenceLog(InferenceRepository(db), registry, key="one")
        b = InferenceLog(InferenceRepository(db), registry, key="two")
        assert a.digest(FEATURES) != b.digest(FEATURES)

    def test_the_same_input_digests_the_same(self, log):
        assert log.digest(FEATURES) == log.digest(dict(reversed(
            list(FEATURES.items()))))

    def test_content_is_held_only_where_somebody_decided_to(self, log,
                                                            a_model):
        row = log.record(URN, principal="svc/pricer", features=FEATURES,
                         prediction=0.031, retain_content=True)
        assert row["features"] == FEATURES
        assert row["prediction"] == {"value": 0.031}
        assert row["reason"] == "always"


class TestSamplingByTier:
    def test_a_tier_one_model_keeps_everything(self, db, registry, a_model):
        from db import InferenceRepository
        _tiered(registry, 1)
        # A sampler at the very top of the range still lands inside 1.0.
        log = InferenceLog(InferenceRepository(db), registry, key="k",
                           sampler=lambda: 0.999)
        assert log.record(URN, principal="p") is not None

    def test_a_tier_four_model_keeps_a_fraction(self, never, registry,
                                                a_model):
        _tiered(registry, 4)
        assert never.record(URN, principal="p") is None

    def test_the_rate_falls_with_the_tier(self):
        assert (SAMPLE_BY_TIER[1] > SAMPLE_BY_TIER[2] > SAMPLE_BY_TIER[3]
                > SAMPLE_BY_TIER[4])

    def test_a_refusal_is_never_sampled_out(self, never, registry, a_model):
        """The sample exists to make the rare thing visible, and sampling out
        the rare thing is exactly backwards."""
        _tiered(registry, 4)
        row = never.record(URN, principal="p", outcome="refused")
        assert row is not None and row["reason"] == "refused"

    def test_an_error_is_never_sampled_out(self, never, registry, a_model):
        _tiered(registry, 4)
        assert never.record(URN, principal="p", outcome="error")["reason"] == (
            "error")

    def test_a_boundary_violation_is_never_sampled_out(self, never, registry,
                                                       a_model):
        _tiered(registry, 4)
        row = never.record(URN, principal="p", boundary_ok=False)
        assert row is not None and row["reason"] == "boundary"

    def test_the_interesting_reason_beats_the_sampler(self, log, registry,
                                                      a_model):
        """A refusal the sampler happened to select must not be recorded as
        `sampled`, or a reader counting refusals is counting a coincidence."""
        _tiered(registry, 1)
        row = log.record(URN, principal="p", outcome="refused")
        assert row["reason"] == "refused"

    def test_every_reason_says_why_the_row_is_there(self):
        assert set(REASONS) == {"sampled", "refused", "boundary", "error",
                                "always"}
        assert all(v for v in REASONS.values())
        assert set(ALWAYS) <= set(REASONS)


class TestRetentionRunsTheOtherWay:
    """The instinct is that important data should be kept longer; the
    obligation is that data you should not be holding is held for less time."""

    def test_restricted_is_kept_for_the_shortest_time(self):
        assert RETAIN_DAYS["restricted"] < RETAIN_DAYS["confidential"]
        assert RETAIN_DAYS["confidential"] < RETAIN_DAYS["internal"]
        assert RETAIN_DAYS["internal"] < RETAIN_DAYS["public"]

    def test_the_retention_comes_from_the_models_classification(
            self, db, registry, features, a_model):
        from core.classification import Classification
        from db import InferenceRepository
        features.catalogue.define("cust.ssn", "customer", "float", "d",
                                  "person/d.raman", sensitivity="restricted")
        log = InferenceLog(InferenceRepository(db), registry,
                           classification=Classification(registry, features),
                           key="k", sampler=lambda: 0.0)
        row = log.record(URN, principal="p", now=1000.0)
        # No version binds that feature yet, so the model traces to nothing and
        # takes the default — which the row records rather than guessing at.
        assert row["classification"] in RETAIN_DAYS
        assert row["retain_until"] == pytest.approx(
            1000.0 + RETAIN_DAYS[row["classification"]] * DAY)

    def test_without_a_classification_service_the_default_applies(self, log,
                                                                  a_model):
        row = log.record(URN, principal="p", now=0.0)
        assert row["classification"] == "internal"
        assert row["retain_until"] == pytest.approx(
            RETAIN_DAYS["internal"] * DAY)

    def test_expired_rows_are_deleted_not_marked(self, log, a_model):
        """A retention period enforced by a column somebody could select
        around is not a retention period."""
        log.record(URN, principal="p", now=0.0)
        out = log.expire_due(now=DEFAULT_RETAIN_DAYS * DAY * 10)
        assert out["dropped"] == 1
        assert log.repo.many() == []
        assert "Deleted rather than marked" in out["detail"]

    def test_rows_inside_their_window_are_kept(self, log, a_model):
        log.record(URN, principal="p")
        assert log.expire_due()["dropped"] == 0


class TestWhatTheInstanceIsHolding:
    def test_the_posture_names_an_unkeyed_instance(self, db, registry,
                                                   a_model):
        from db import InferenceRepository
        log = InferenceLog(InferenceRepository(db), registry, key="",
                           sampler=lambda: 0.0)
        log.record(URN, principal="p")
        out = log.posture()
        assert out["keyed_digests"] is False
        assert "lookup table" in out["detail"]

    def test_a_keyed_instance_says_nothing_about_it(self, log, a_model):
        log.record(URN, principal="p")
        assert log.posture()["keyed_digests"] is True
        assert "lookup table" not in log.posture()["detail"]

    def test_rows_past_retention_mean_the_batch_has_not_run(self, log,
                                                            a_model):
        log.record(URN, principal="p", now=0.0)
        out = log.posture(now=DEFAULT_RETAIN_DAYS * DAY * 10)
        assert out["past_retention"] == 1
        assert "a policy document" in out["detail"]

    def test_it_names_which_models_hold_content(self, log, a_model):
        log.record(URN, principal="p", features=FEATURES, retain_content=True)
        held = log.retained()
        assert held and held[0]["urn"] == URN and held[0]["records"] == 1

    def test_an_empty_log_distinguishes_two_different_facts(self, log,
                                                            a_model):
        """Not called, and not sampled, are different things."""
        out = log.for_model(URN)
        assert out["count"] == 0
        assert "those are different facts" in out["detail"]


class TestOverHttp:
    def test_the_posture_is_served(self, client, people):
        r = client.get("/api/v1/inference-posture", auth=people["d.raman"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert "keyed_digests" in body and "retention_days" in body
        assert body["retention_days"]["restricted"] < (
            body["retention_days"]["public"]), "retention runs the other way"

    def test_an_uncalled_model_says_which_fact_it_means(self, client, people):
        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "12-month PD"})
        r = client.get("/api/v1/inference", auth=people["d.raman"],
                       params={"urn": URN})
        assert r.status_code == 200, r.text
        assert "those are different facts" in r.json()["detail"]

    def test_the_screen_says_which_way_retention_runs(self, client, people):
        client.post("/login", data={"username": "admin",
                                    "password": "maya-admin-dev",
                                    "next": "/classification"})
        body = client.get("/classification").text
        assert "kept for the <em>shortest</em> time" in body
        assert "sampling out the rare thing is" in body
