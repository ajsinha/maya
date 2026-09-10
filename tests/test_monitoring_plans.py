"""What a model will be watched for, written down before it goes anywhere.

*A monitoring plan* and *a monitored model* are different statements, and the
gap between them is where estates actually fail. The plan is written at
development time, argued over in validation, approved — and then somebody else,
months later, creates whatever monitors seem reasonable. Nothing ever compares
the two, and every party is doing their job.
"""
from __future__ import annotations


from tests.conftest import NAME, URN

KERNEL = {"runtime": "formula", "parameter_kind": "estimated_coefficients",
          "fit_procedure": "estimate", "deterministic": True,
          "entry": {"expression": "w * x", "target": "y"},
          "input_schema": [{"name": "x", "dtype": "numeric"}],
          "parameter_schema": [{"name": "w", "dtype": "numeric"}],
          "output_schema": [{"name": "y", "dtype": "numeric"}]}


def _registered(client, people, *, exposure=2e9):
    client.post("/api/v1/models", auth=people["j.okafor"], json={
        "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
        "domain": "credit", "owner": "person/j.okafor",
        "legal_entity": "LE-US-01", "purpose": "12-month PD"})
    client.post(f"/api/v1/models/{NAME}/versions", auth=people["d.raman"],
                json={"semver": "1.0.0", "kernel": KERNEL})
    client.post(f"/api/v1/models/{NAME}/assess", auth=people["j.okafor"],
                json={"exposure": exposure, "purpose_class": "regulatory_capital",
                      "feature_count": 12, "uses_alternative_data": False,
                      "interpretable": True})
    return NAME


class TestAuthoringOne:
    def test_an_empty_plan_takes_the_class_aware_defaults(self, client, people):
        """Not a convenience. A blank form produces either a plan copied from
        the last model or a plan with one monitor on it."""
        _registered(client, people)
        r = client.post("/api/v1/monitoring-plans", auth=people["j.okafor"],
                        json={"urn": URN, "semver": "1.0.0"})
        assert r.status_code == 201, r.text
        assert len(r.json()["items"]) == 4, "T2 admits all four kinds"

    def test_an_explicit_plan_is_taken_as_given(self, client, people):
        _registered(client, people)
        r = client.post("/api/v1/monitoring-plans", auth=people["j.okafor"],
                        json={"urn": URN, "semver": "1.0.0",
                              "items": [{"kind": "input_drift",
                                         "test_key": "stability.psi",
                                         "threshold": {"max": 0.2}}],
                              "rationale": "the score is not the risk here"})
        assert r.status_code == 201, r.text
        assert len(r.json()["items"]) == 1

    def test_a_plan_the_platform_could_never_honour_is_refused_at_authoring(
            self, client, people):
        """A plan that cannot be honoured is worse than no plan: it is
        reviewed, approved, and fails silently at the one moment nobody is
        watching it."""
        _registered(client, people)
        r = client.post("/api/v1/monitoring-plans", auth=people["j.okafor"],
                        json={"urn": URN, "semver": "1.0.0",
                              "items": [{"kind": "input_drift",
                                         "test_key": "discrimination.gini"}]})
        assert r.status_code >= 400, r.text
        assert r.json()["error"] == "test_not_admissible"

    def test_a_second_plan_for_one_version_is_refused(self, client, people):
        _registered(client, people)
        client.post("/api/v1/monitoring-plans", auth=people["j.okafor"],
                    json={"urn": URN, "semver": "1.0.0"})
        again = client.post("/api/v1/monitoring-plans", auth=people["j.okafor"],
                            json={"urn": URN, "semver": "1.0.0"})
        assert again.status_code >= 400
        assert again.json()["error"] == "plan_exists"


class TestTheColumnThatCarriesThePoint:
    """`inherited_at` null means this model has a monitoring plan and is not
    monitored."""

    def test_a_fresh_plan_says_it_is_not_monitored(self, client, people):
        _registered(client, people)
        client.post("/api/v1/monitoring-plans", auth=people["j.okafor"],
                    json={"urn": URN, "semver": "1.0.0"})
        out = client.get("/api/v1/monitoring-plans", auth=people["d.raman"],
                         params={"urn": URN, "semver": "1.0.0"}).json()
        assert out["inherited"] is False
        assert "has a monitoring plan and is not monitored" in out["detail"]

    def test_inheriting_creates_the_monitors_it_describes(self, client, people):
        _registered(client, people)
        client.post("/api/v1/monitoring-plans", auth=people["j.okafor"],
                    json={"urn": URN, "semver": "1.0.0"})
        r = client.post("/api/v1/monitoring-plans/inherit",
                        auth=people["j.okafor"],
                        params={"urn": URN, "semver": "1.0.0"})
        assert r.status_code == 200, r.text
        assert len(r.json()["monitor_ids"]) == 4
        live = client.get("/api/v1/monitors", auth=people["d.raman"],
                          params={"urn": URN}).json()
        assert live["monitors"], "the plan became actual monitors"

    def test_inheriting_twice_is_refused(self, client, people):
        _registered(client, people)
        client.post("/api/v1/monitoring-plans", auth=people["j.okafor"],
                    json={"urn": URN, "semver": "1.0.0"})
        client.post("/api/v1/monitoring-plans/inherit", auth=people["j.okafor"],
                    params={"urn": URN, "semver": "1.0.0"})
        again = client.post("/api/v1/monitoring-plans/inherit",
                            auth=people["j.okafor"],
                            params={"urn": URN, "semver": "1.0.0"})
        assert again.status_code >= 400
        assert again.json()["error"] == "already_inherited"
        assert "where the change is recorded" in again.json()["remediation"]


class TestTheOutstandingReport:
    def test_an_uninherited_plan_appears_on_it(self, client, people):
        _registered(client, people)
        client.post("/api/v1/monitoring-plans", auth=people["j.okafor"],
                    json={"urn": URN, "semver": "1.0.0"})
        out = client.get("/api/v1/monitoring-plans",
                         auth=people["s.iqbal"]).json()
        assert out["count"] == 1
        assert out["plans"][0]["urn"] == URN
        assert "different statements" in out["detail"]

    def test_inheriting_takes_it_off(self, client, people):
        _registered(client, people)
        client.post("/api/v1/monitoring-plans", auth=people["j.okafor"],
                    json={"urn": URN, "semver": "1.0.0"})
        client.post("/api/v1/monitoring-plans/inherit", auth=people["j.okafor"],
                    params={"urn": URN, "semver": "1.0.0"})
        out = client.get("/api/v1/monitoring-plans",
                         auth=people["s.iqbal"]).json()
        assert out["count"] == 0
        assert "every authored monitoring plan has been inherited" in out["detail"]

    def test_a_version_with_no_plan_is_a_404_naming_the_decision(self, client,
                                                                 people):
        _registered(client, people)
        r = client.get("/api/v1/monitoring-plans", auth=people["d.raman"],
                       params={"urn": URN, "semver": "1.0.0"})
        assert r.status_code == 404
        assert "development-time decision" in r.json()["remediation"]

    def test_a_urn_without_a_semver_is_refused(self, client, people):
        _registered(client, people)
        r = client.get("/api/v1/monitoring-plans", auth=people["d.raman"],
                       params={"urn": URN})
        assert r.status_code == 422
        assert r.json()["error"] == "semver_required"
