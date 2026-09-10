"""What a model of this class, at this tier, should be watched for.

Four monitor kinds existed and nothing said which of them any given model
needed, so every monitor in the estate was one somebody had thought to create.
That produces two failures and only one is visible: the model with no monitors,
which a coverage screen finds, and the model with three monitors that could
never have answered anything about it — which reads as coverage and is worse.
"""
from __future__ import annotations

import pytest

from core.monitoring import MonitorError
from core.monitoring.common import KINDS
from core.monitoring.defaults import (CADENCE_DAYS, DEFAULT_LABEL_DELAY_DAYS,
                                      DEFAULT_TEST, MonitoringDefaults)
from tests.conftest import NAME, URN


def _kernel(kind: str, fit: str) -> dict:
    return {"runtime": "formula", "parameter_kind": kind, "fit_procedure": fit,
            "deterministic": True,
            "entry": {"expression": "w * x", "target": "y"},
            "input_schema": [{"name": "x", "dtype": "numeric"}],
            "parameter_schema": [{"name": "w", "dtype": "numeric"}],
            "output_schema": [{"name": "y", "dtype": "numeric"}]}


def _registered(client, people, *, kind="estimated_coefficients",
                fit="estimate", exposure=2e9, purpose="regulatory_capital"):
    client.post("/api/v1/models", auth=people["j.okafor"], json={
        "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
        "domain": "credit", "owner": "person/j.okafor",
        "legal_entity": "LE-US-01", "purpose": "12-month PD"})
    client.post(f"/api/v1/models/{NAME}/versions", auth=people["d.raman"],
                json={"semver": "1.0.0", "kernel": _kernel(kind, fit)})
    client.post(f"/api/v1/models/{NAME}/assess", auth=people["j.okafor"],
                json={"exposure": exposure, "purpose_class": purpose,
                      "feature_count": 12, "uses_alternative_data": False,
                      "interpretable": True})
    return NAME


class TestTheDefaultsAreDerivedNotDeclared:
    def test_every_default_test_is_admissible_for_its_own_kind(self):
        """A default that failed the platform's own admissibility rule would be
        refused by `define()` the moment anybody seeded it."""
        from core.monitoring.common import ADMISSIBLE_TESTS
        for kind, test in DEFAULT_TEST.items():
            assert test in ADMISSIBLE_TESTS[kind], (kind, test)

    def test_a_t0_model_is_told_what_it_cannot_be_asked(self, client, people):
        """T0 has no parameters and no fitted relationship, so performance and
        calibration are not questions about it. That is a property of the
        model, not a gap in its coverage, and the answer says so."""
        _registered(client, people, kind="none", fit="none")
        r = client.get("/api/v1/monitor-defaults", auth=people["d.raman"],
                       params={"urn": URN})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["trainability_class"] == "T0"
        declined = {d["kind"] for d in body["declined"]}
        assert "performance" in declined and "calibration" in declined
        assert all(d["is_a_gap"] is False for d in body["declined"])
        assert "property of the model and not a gap" in body["detail"]

    def test_a_t2_model_admits_more_than_a_t0_one(self, client, people):
        _registered(client, people)
        body = client.get("/api/v1/monitor-defaults", auth=people["d.raman"],
                          params={"urn": URN}).json()
        assert body["trainability_class"] == "T2"
        proposed = {p["kind"] for p in body["propose"]}
        assert proposed == set(KINDS), "T2 can be asked all four"

    def test_the_declined_reason_quotes_what_the_class_CAN_answer(
            self, client, people):
        _registered(client, people, kind="none", fit="none")
        body = client.get("/api/v1/monitor-defaults", auth=people["d.raman"],
                          params={"urn": URN}).json()
        reason = next(d["reason"] for d in body["declined"]
                      if d["kind"] == "performance")
        assert "what it can answer is" in reason


class TestCadenceComesFromTheTier:
    """How closely a model is watched depends on what rides on it, not only on
    what it is — so a Tier 1 rulebook and a Tier 4 one are not watched alike."""

    def test_a_tier_one_model_is_watched_daily(self, client, people):
        _registered(client, people, exposure=2e10)
        body = client.get("/api/v1/monitor-defaults", auth=people["d.raman"],
                          params={"urn": URN}).json()
        assert body["tier"] == 1
        assert all(p["cadence_days"] == CADENCE_DAYS[1] for p in body["propose"])
        assert all(p["breach_severity"] == "High" for p in body["propose"])

    def test_a_low_tier_model_is_watched_less_often(self, client, people):
        _registered(client, people, exposure=0, purpose="commercial")
        body = client.get("/api/v1/monitor-defaults", auth=people["d.raman"],
                          params={"urn": URN}).json()
        assert body["tier"] == 4
        assert all(p["cadence_days"] == CADENCE_DAYS[4] for p in body["propose"])


class TestTheFieldPeopleLeaveAtZero:
    """`label_delay_days` at zero evaluates a performance monitor over a cohort
    whose outcomes have not matured, which measures the maturity of the cohort
    and not the model. Defaulting it to zero would have shipped that mistake as
    the default."""

    def test_label_dependent_kinds_get_a_non_zero_delay(self, client, people):
        _registered(client, people)
        body = client.get("/api/v1/monitor-defaults", auth=people["d.raman"],
                          params={"urn": URN}).json()
        for proposal in body["propose"]:
            if proposal["kind"] in ("performance", "calibration"):
                assert proposal["label_delay_days"] == DEFAULT_LABEL_DELAY_DAYS
                assert "maturity of the cohort" in proposal["note"]
            else:
                assert proposal["label_delay_days"] == 0.0


class TestSeeding:
    def test_it_creates_what_it_proposed_and_nothing_else(self, client, people):
        _registered(client, people)
        r = client.post("/api/v1/monitor-defaults", auth=people["j.okafor"],
                        params={"urn": URN})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["created_count"] == 4, "T2 admits all four"
        seeded = {m["kind"] for m in body["created"]}
        assert seeded == set(KINDS), "all four, one per admitted kind"

    def test_a_t0_model_is_seeded_only_with_what_it_can_answer(
            self, client, people):
        _registered(client, people, kind="none", fit="none")
        body = client.post("/api/v1/monitor-defaults", auth=people["j.okafor"],
                           params={"urn": URN}).json()
        assert body["created_count"] == 1, "input drift, and nothing else"
        assert body["created"][0]["kind"] == "input_drift"

    def test_seeding_twice_creates_nothing_the_second_time(self, client, people):
        """A defaults helper that duplicated its own work is one nobody would
        dare run on an estate."""
        _registered(client, people)
        client.post("/api/v1/monitor-defaults", auth=people["j.okafor"],
                    params={"urn": URN})
        again = client.post("/api/v1/monitor-defaults", auth=people["j.okafor"],
                            params={"urn": URN}).json()
        assert again["created_count"] == 0
        assert again["already_defined"] == 4
        assert "already defined" in again["detail"]


class TestItRefusesRatherThanGuessing:
    def test_a_model_with_no_version_has_no_class_to_read(self, client, people):
        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": URN, "name": "SB PD", "model_class": "c", "domain": "credit",
            "owner": "person/j.okafor", "legal_entity": "LE-US-01",
            "purpose": "p"})
        r = client.get("/api/v1/monitor-defaults", auth=people["d.raman"],
                       params={"urn": URN})
        assert r.status_code >= 400, r.text
        assert r.json()["error"] == "no_class"

    def test_an_unassessed_model_has_no_cadence(self, client, people, repos, db,
                                                registry, evidence):
        """Cadence comes from the tier, so an untiered model cannot be given
        one — and guessing a cadence is choosing how closely to watch it."""
        from core.fibres import FibreRegistry

        defaults = MonitoringDefaults(
            monitors=None, fibres=FibreRegistry(),
            class_of=lambda urn: "T2", tier_of=lambda urn: None)
        with pytest.raises(MonitorError) as exc:
            defaults.propose(URN, "any-id")
        assert exc.value.code == "no_tier"
        assert "rides on it" in exc.value.remediation
