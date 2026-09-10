"""What each lifecycle move costs, over HTTP.

One state graph and several sets of obligations. The class says which evidence
kinds must be on file before a record can be attested, the tier says how many
signatures the move takes and how long it may sit before somebody should ask.

The stalled-record endpoint is the one nothing else in the platform could
answer: submission succeeded, every gate passed, and no control watches the
clock.
"""
from __future__ import annotations

from tests.conftest import CONTRACT, KERNEL, NAME, URN


def _model_with_a_version(client, people):
    client.post("/api/v1/models", auth=people["j.okafor"], json={
        "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
        "domain": "credit", "owner": "person/j.okafor",
        "legal_entity": "LE-US-01", "purpose": "12-month PD"})
    client.post(f"/api/v1/models/{NAME}/versions", auth=people["d.raman"],
                json={"semver": "3.2.1", "kernel": KERNEL,
                      "contract": CONTRACT,
                      "artifact_digest": "sha256:" + "a" * 64})
    return NAME


class TestTheReferenceLifecycles:
    def test_every_class_has_one(self, client, people):
        """FR-LC-002: T0 through T8."""
        r = client.get("/api/v1/lifecycle-profiles", auth=people["d.raman"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 9
        assert [row["trainability_class"] for row in body["lifecycles"]] == [
            f"T{i}" for i in range(9)]

    def test_the_obligations_differ_and_the_graph_does_not(self, client,
                                                           people):
        body = client.get("/api/v1/lifecycle-profiles",
                          auth=people["d.raman"]).json()
        assert body["distinct_evidence_sets"] > 1
        graphs = {tuple(row["states"]) for row in body["lifecycles"]}
        assert len(graphs) == 1, "nine graphs would mean nine reachability proofs"

    def test_one_class_at_one_tier(self, client, people):
        r = client.get("/api/v1/lifecycle-profiles/T3",
                       auth=people["d.raman"], params={"tier": 1})
        assert r.status_code == 200, r.text
        body = r.json()
        attest = next(m for m in body["transitions"]
                      if m["transition"] == "attest")
        assert attest["signatures"] == 2
        assert "independent_review" in attest["required_evidence"]

    def test_an_unknown_class_is_refused_by_name(self, client, people):
        r = client.get("/api/v1/lifecycle-profiles/T99",
                       auth=people["d.raman"])
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "no_fibre"


class TestReadiness:
    def test_it_names_what_this_model_does_not_hold(self, client, people):
        _model_with_a_version(client, people)
        r = client.get("/api/v1/lifecycle-readiness",
                       auth=people["d.raman"], params={"urn": URN})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["transition"] == "attest"
        assert body["ready"] is False
        assert body["missing_evidence"], "a fresh model holds no documents"
        assert body["trainability_class"]

    def test_a_move_with_no_evidence_guard_says_so(self, client, people):
        _model_with_a_version(client, people)
        r = client.get("/api/v1/lifecycle-readiness", auth=people["d.raman"],
                       params={"urn": URN, "transition": "submit"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["required_evidence"] == []
        assert "authority, not documents" in body["detail"]

    def test_an_unknown_transition_is_refused(self, client, people):
        _model_with_a_version(client, people)
        r = client.get("/api/v1/lifecycle-readiness", auth=people["d.raman"],
                       params={"urn": URN, "transition": "unsubmit"})
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "unknown_transition"
        assert "attest" in r.json()["remediation"], "name what does exist"


class TestTheQueueNobodyIsWatching:
    def test_a_fresh_register_has_nothing_stuck(self, client, people):
        r = client.get("/api/v1/lifecycle-stalled", auth=people["d.raman"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 0
        assert body["stalled"] == []

    def test_a_submitted_record_is_measured_and_not_yet_late(self, client,
                                                             people):
        """A record that has just been submitted is in the queue and inside its
        window — which is a different answer from *we cannot tell*."""
        name = _model_with_a_version(client, people)
        client.post(f"/api/v1/models/{name}/assess", auth=people["j.okafor"],
                    json={"exposure": 2e9,
                          "purpose_class": "regulatory_capital",
                          "feature_count": 12,
                          "uses_alternative_data": False,
                          "interpretable": True})
        submitted = client.post(f"/api/v1/models/{name}/submit",
                                auth=people["j.okafor"],
                                json={"note": "ready for review"})
        assert submitted.status_code == 200, submitted.text
        body = client.get("/api/v1/lifecycle-stalled",
                          auth=people["d.raman"]).json()
        assert body["count"] == 0
        assert body["not_measurable"] == [], (
            "the chain recorded the submission, so this is measurable")
