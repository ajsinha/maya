"""
MAYA — HTTP API tests: the core surface.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

Health, the model register, warrants, the execution boundary and the
warrant grammar -- the endpoints everything else is built on.

The application, the four principals and a registered model come from
``conftest``; ``quorum_approve`` and ``login`` from ``api_helpers``. Everything
here runs against the real app over HTTP, because an interface tested through a
shortcut is an interface nobody has tested.
"""
import json

from fastapi.testclient import TestClient

from tests.api_helpers import quorum_approve as _quorum_approve
from tests.conftest import CONTRACT, KERNEL, NAME, URN


class TestHealth:
    def test_health(self, client):
        assert client.get("/health").json()["status"] == "healthy"

    def test_liveness(self, client):
        assert client.get("/health/live").status_code == 200

    def test_readiness_includes_the_evidence_chain(self, client):
        body = client.get("/health/ready").json()
        assert body["status"] == "ready" and body["evidence_chain"]["valid"] is True

    def test_openapi_is_published(self, client):
        assert "paths" in client.get("/api/v1/openapi.json").json()

class TestModelApi:
    def test_empty_inventory(self, client):
        assert client.get("/api/v1/models").json() == {"models": []}

    def test_create_and_read(self, client):
        r = client.post("/api/v1/models", json={
            "urn": URN, "name": "SB PD", "model_class": "c", "domain": "credit",
            "owner": "p", "legal_entity": "LE", "purpose": "x"})
        assert r.status_code == 201 and r.json()["urn"] == URN
        assert client.get(f"/api/v1/models/{NAME}").json()["model"]["urn"] == URN

    def test_duplicate_is_refused_with_a_reason(self, client):
        body = {"urn": URN, "name": "a", "model_class": "c", "domain": "d",
                "owner": "o", "legal_entity": "l", "purpose": "p"}
        client.post("/api/v1/models", json=body)
        r = client.post("/api/v1/models", json=body)
        assert r.status_code == 409 and "already registered" in r.json()["detail"]

    def test_unknown_model_is_404(self, client):
        assert client.get("/api/v1/models/ghost").status_code == 404

    def test_invalid_payload_is_422(self, client):
        assert client.post("/api/v1/models", json={"urn": URN}).status_code == 422

    def test_version_derives_the_trainability_class(self, registered):
        v = registered.get(f"/api/v1/models/{NAME}").json()["versions"][0]
        assert v["trainability_class"] == "T2"

    def test_assessment_returns_its_rationale(self, registered):
        r = registered.post(f"/api/v1/models/{NAME}/assess",
                            json={"exposure": 1e10, "purpose_class": "regulatory_capital"})
        b = r.json()
        assert b["tier"] == 1 and "materiality=" in b["rationale"] and b["required_controls"]

    def test_filters(self, registered):
        assert len(registered.get("/api/v1/models?domain=credit").json()["models"]) == 1
        assert registered.get("/api/v1/models?domain=markets").json()["models"] == []

    def test_alias_move_is_refused_when_incompatible(self, registered, people):
        dev, mrm = people["d.raman"], people["s.iqbal"]
        weak = {**CONTRACT, "guarantees": [{"key": "gini", "minimum": 0.10}]}
        registered.post(f"/api/v1/models/{NAME}/versions", auth=dev,
                        json={"semver": "3.3.0", "kernel": KERNEL, "contract": weak})
        _quorum_approve(registered, people, "3.3.0")
        r = registered.put(f"/api/v1/models/{NAME}/aliases", auth=mrm,
                           json={"environment": "prod", "alias": "champion", "semver": "3.3.0"})
        assert r.status_code == 409 and "gini" in r.json()["detail"], \
            "the refusal must be about the contract, not about who asked"

    def test_evidence_chain_endpoint(self, registered):
        assert registered.get("/api/v1/evidence/chain").json()["valid"] is True

class TestWarrantApi:
    def test_resolve_returns_a_signed_descriptor(self, registered):
        r = registered.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination", "declared_use": "origination_decision"})
        d = r.json()
        assert d["subject"]["version"] == "3.2.1" and d["signature"]

    def test_unentitled_principal_gets_403_with_remediation(self, registered):
        r = registered.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/marketing", "declared_use": "origination_decision"})
        assert r.status_code == 403
        assert r.json()["error"] == "no_entitlement" and r.json()["remediation"]

    def test_wrong_use_is_refused(self, registered):
        r = registered.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination", "declared_use": "marketing_targeting"})
        assert r.status_code == 403 and r.json()["error"] == "use_not_approved"

    def test_unknown_model_is_404(self, registered):
        r = registered.post("/api/v1/resolve", json={
            "urn": "maya://model/ghost#champion", "environment": "prod",
            "principal": "svc/origination", "declared_use": "x"})
        assert r.status_code == 404

    def test_malformed_urn_is_422(self, registered):
        r = registered.post("/api/v1/resolve", json={
            "urn": "not-a-urn", "environment": "prod",
            "principal": "svc/origination", "declared_use": "x"})
        assert r.status_code == 422

    def test_revocation_then_resolution_fails_closed(self, registered):
        assert registered.post("/api/v1/warrants/revoke",
                               json={"urn": URN, "reason": "critical finding"}).json()["revoked"] == 1
        r = registered.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination", "declared_use": "origination_decision"})
        assert r.status_code == 410 and r.json()["error"] == "revoked"

class TestExecutionBoundary:
    """MAYA issues warrants. The captive engine is one consumer of that contract."""

    def test_execute_without_a_runtime_reports_not_implemented(self, registered):
        r = registered.post("/api/v1/execute", json={
            "urn": f"{URN}#champion", "environment": "prod", "principal": "svc/origination",
            "declared_use": "origination_decision", "inputs": {"dscr": 1.2}})
        assert r.status_code == 501 and r.json()["error"] == "no_runtime"

    def test_every_refusal_shares_one_shape(self, registered):
        """DR-6/DR-7: one error body shape, whichever route raised it."""
        cases = [("/api/v1/resolve", {"urn": f"{URN}#champion", "environment": "prod",
                                      "principal": "svc/nobody", "declared_use": "x"}),
                 ("/api/v1/training-sets", {"name": "b", "spine": [], "views": [],
                                            "as_of": 1.0, "valid_time_bound": False})]
        for path, payload in cases:
            body = registered.post(path, json=payload).json()
            assert {"error", "detail"} <= set(body), f"{path} returned {body}"

    def test_execution_still_enforces_entitlement(self, registered):
        r = registered.post("/api/v1/execute", json={
            "urn": f"{URN}#champion", "environment": "prod", "principal": "svc/nobody",
            "declared_use": "origination_decision", "inputs": {"dscr": 1.2}})
        assert r.status_code == 403

    def test_execution_after_revocation_is_refused(self, registered):
        registered.post("/api/v1/warrants/revoke", json={"urn": URN, "reason": "stop"})
        r = registered.post("/api/v1/execute", json={
            "urn": f"{URN}#champion", "environment": "prod", "principal": "svc/origination",
            "declared_use": "origination_decision", "inputs": {"dscr": 1.2}})
        assert r.status_code == 410

class TestGrammarApi:
    def test_the_grammar_is_published(self, client, people):
        v = client.get("/api/v1/grammar", auth=people["d.raman"]).json()
        assert v["warrant_version"] == "1.0"
        assert len(v["operations"]) == 10 and len(v["runtimes"]) >= 15
        assert "fit" not in v["admissibility"]["by_trainability_class"]["T0"]

    def test_the_json_schema_is_published(self, client, people):
        s = client.get("/api/v1/grammar/schema", auth=people["d.raman"]).json()
        assert s["$schema"].startswith("https://json-schema.org/")
        assert "subject" in s["properties"] and "signature" in s["properties"]

    def test_a_document_can_be_checked_before_it_is_acted_on(self, client, people):
        r = client.post("/api/v1/grammar/validate", auth=people["d.raman"],
                        json={"maya_warrant": "1.0"}).json()
        assert r["valid"] is False and r["problem_count"] == 10
        assert all(p["remediation"] for p in r["problems"])

    def test_a_shipped_example_validates_over_the_api(self, client, people):
        import json, pathlib
        path = (pathlib.Path(__file__).resolve().parent.parent / "examples" /
                "warrants" / "01-quantlib-swaption-price.json")
        r = client.post("/api/v1/grammar/validate", auth=people["d.raman"],
                        json=json.loads(path.read_text())).json()
        assert r["valid"] is True

    def test_a_resolved_warrant_conforms_to_the_published_grammar(self, registered):
        """The strongest check: what MAYA hands out passes its own grammar."""
        from core.execution.grammar import validate
        warrant = registered.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination",
            "declared_use": "origination_decision"}).json()
        assert validate(warrant).valid, validate(warrant).as_dict()["detail"]

    def test_the_verb_is_carried_through_to_the_warrant(self, registered):
        warrant = registered.post("/api/v1/resolve?verb=explain", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination",
            "declared_use": "origination_decision"}).json()
        assert warrant["operation"]["verb"] == "explain"

    def test_an_inadmissible_verb_is_refused_at_issue(self, registered):
        """A T2 scorecard registered without a locatable artifact is
        descriptor-only, and a descriptor-only model cannot be warranted to fit."""
        r = registered.post("/api/v1/resolve?verb=fit", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination", "declared_use": "origination_decision"})
        assert r.status_code == 422
        assert r.json()["error"] == "grammar_violation"

    def test_the_generate_button_is_on_the_model_page(self, registered):
        registered.post("/login", data={"username": "admin", "password": "admin123",
                                        "next": "/dashboard"})
        body = registered.get(f"/model/{NAME}").text
        assert 'id="gen-warrant"' in body and "RESOLVED WARRANT" in body

class TestTheEngineBoundaryIsPublished:
    def test_it_says_what_the_isolation_does_not_cover(self, registered):
        body = registered.get("/api/v1/engine").json()
        assert body["captive_engine"] == "enabled"
        assert body["does_not_protect_against"]

class TestAuthorisationApi:
    def test_an_unauthenticated_call_is_401_with_a_challenge(self, client):
        anon = TestClient(client.app)
        r = anon.get("/api/v1/models")
        assert r.status_code == 401
        assert r.json()["error"] == "unauthenticated"
        assert "Basic" in r.headers.get("www-authenticate", "")

    def test_public_pages_stay_open(self, client):
        anon = TestClient(client.app)
        for path in ("/", "/about", "/help", "/health", "/login"):
            assert anon.get(path).status_code == 200, path

    def test_me_reports_roles_permissions_and_scope(self, client, people):
        body = client.get("/api/v1/me", auth=people["a.mehta"]).json()
        assert body["roles"] == ["validator"]
        assert "validation:conclude" in body["permissions"]
        assert "version:approve" not in body["permissions"]

    def test_the_role_catalogue_is_published(self, client, people):
        body = client.get("/api/v1/roles", auth=people["d.raman"]).json()
        names = {r["name"] for r in body["roles"]}
        assert {"model_developer", "validator", "model_risk_manager", "auditor"} <= names
        assert body["incompatible"] and body["segregation"]

    def test_a_developer_cannot_approve_a_version(self, registered, people):
        r = registered.post(f"/api/v1/models/{NAME}/versions/3.2.1/approve",
                            auth=people["d.raman"])
        assert r.status_code == 403 and r.json()["error"] == "forbidden"
        assert "model_developer" in r.json()["detail"]

    def test_a_validator_cannot_create_a_version(self, registered, people):
        r = registered.post(f"/api/v1/models/{NAME}/versions", auth=people["a.mehta"],
                            json={"semver": "9.9.9", "kernel": KERNEL})
        assert r.status_code == 403

    def test_the_builder_cannot_approve_their_own_version(self, client, people):
        """Segregation catches what role separation alone cannot.

        A small firm grants one person both hats as a documented exception. Role
        checks then pass for both acts -- and segregation still refuses, because
        it reads the evidence chain rather than the role list.
        """
        client.post("/api/v1/principals", json={
            "username": "solo", "display_name": "Solo", "password": "pw",
            "roles": ["model_developer", "model_risk_manager"],
            "allow_conflicts": True})
        solo = ("solo", "pw")
        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": "maya://model/sod.demo", "name": "SoD", "model_class": "c",
            "domain": "credit", "owner": "person/o", "legal_entity": "LE-US-01",
            "purpose": "p"})
        # Tier 4, so a single signature is the correct control depth here and
        # the test stays about segregation rather than about the quorum.
        client.post("/api/v1/models/sod.demo/assess", auth=people["j.okafor"],
                    json={"exposure": 1e5, "purpose_class": "commercial"})
        r = client.post("/api/v1/models/sod.demo/versions", auth=solo,
                        json={"semver": "1.0.0", "kernel": KERNEL})
        assert r.status_code == 201, "both roles are held, so creation is permitted"

        r = client.post("/api/v1/models/sod.demo/versions/1.0.0/approve", auth=solo)
        assert r.status_code == 403
        assert r.json()["error"] == "segregation_of_duties"
        assert "evidence #" in r.json()["detail"], "cite the record that disqualifies them"

        # And somebody else can, which is the remediation the refusal names.
        assert client.post("/api/v1/models/sod.demo/versions/1.0.0/approve",
                           auth=people["s.iqbal"]).status_code == 200

    def test_the_inventory_is_filtered_by_entity_scope(self, registered, client):
        client.post("/api/v1/principals", json={
            "username": "uk.auditor", "display_name": "UK", "roles": ["auditor"],
            "password": "pw", "legal_entities": ["LE-UK-02"]})
        body = registered.get("/api/v1/models", auth=("uk.auditor", "pw")).json()
        assert body["models"] == [], "a US model must not be visible to a UK-scoped auditor"

    def test_a_model_out_of_scope_is_refused_by_name_too(self, registered, client):
        client.post("/api/v1/principals", json={
            "username": "uk.auditor", "display_name": "UK", "roles": ["auditor"],
            "password": "pw", "legal_entities": ["LE-UK-02"]})
        r = registered.get(f"/api/v1/models/{NAME}", auth=("uk.auditor", "pw"))
        assert r.status_code == 403 and r.json()["error"] == "out_of_scope"

    def test_creating_a_principal_needs_principal_manage(self, client, people):
        r = client.post("/api/v1/principals", auth=people["s.iqbal"], json={
            "username": "x", "display_name": "X", "roles": ["auditor"]})
        assert r.status_code == 403

    def test_incompatible_roles_are_refused_over_the_api(self, client):
        r = client.post("/api/v1/principals", json={
            "username": "x", "display_name": "X",
            "roles": ["model_developer", "model_risk_manager"], "password": "pw"})
        assert r.status_code == 409 and r.json()["error"] == "incompatible_roles"

    def test_a_suspended_principal_loses_access_immediately(self, client, people):
        assert client.get("/api/v1/me", auth=people["a.mehta"]).status_code == 200
        client.post("/api/v1/principals/a.mehta/suspend")
        assert client.get("/api/v1/me", auth=people["a.mehta"]).status_code == 401

    def test_acts_are_attributed_to_the_principal_not_to_system(self, registered, people):
        chain = registered.get("/api/v1/evidence/chain").json()
        assert chain["valid"] is True
        body = registered.get(f"/api/v1/models/{NAME}").json()
        actors = {n["recorded_by"] for n in body["evidence"]}
        assert "j.okafor" in actors, "registration must be attributed to whoever did it"
        assert "system" not in actors
