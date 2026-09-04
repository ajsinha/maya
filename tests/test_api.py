"""
MAYA — HTTP API and UI tests, exercised through the real application.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
import pytest
from fastapi.testclient import TestClient

from core.config import PropertiesConfigurator

URN = "maya://model/credit.pd.smallbiz"
NAME = "credit.pd.smallbiz"
KERNEL = {"parameter_kind": "estimated_coefficients", "fit_procedure": "estimate",
          "input_schema": [{"name": "dscr", "dtype": "float", "minimum": -5, "maximum": 20}],
          "output_schema": [{"name": "pd_12m", "dtype": "float"}]}
CONTRACT = {"assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
            "guarantees": [{"key": "gini", "minimum": 0.42}],
            "on_boundary_violation": "reject"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    cfg_file = tmp_path / "application.yaml"
    cfg_file.write_text(f"""
app: {{name: MAYA, version: "0.1.0", tagline: "Model & AI Lifecycle Assurance",
       slogan: "Evidence, not assertion."}}
server: {{host: 0.0.0.0, port: 5006}}
database: {{url: "sqlite:///{tmp_path}/data/sqlite/maya.db"}}
data: {{dir: "{tmp_path}/data", artifacts: "{tmp_path}/data/artifacts",
        attachments: "{tmp_path}/data/attachments",
        delta: {{dir: "{tmp_path}/data/delta", features: "{tmp_path}/data/delta/features",
                snapshots: "{tmp_path}/data/delta/snapshots",
                telemetry: "{tmp_path}/data/delta/telemetry",
                monitoring: "{tmp_path}/data/delta/monitoring"}}}}
risk:
  exposure_bands: {{negligible: 0, low: 1000000, moderate: 50000000,
                   material: 500000000, critical: 5000000000}}
  purpose_ranks: {{commercial: 1, risk_management: 2, financial_reporting: 3,
                  regulatory_capital: 4}}
  review_months: {{1: 12, 2: 18, 3: 24, 4: 36}}
warrants: {{jitter_pct: 0, signing_key_id: test-key,
         ttl_seconds: {{1: 60, 2: 300, 3: 3600, 4: 3600}},
         grace_seconds: {{1: 0, 2: 0, 3: 900, 4: 900}}}}
execution: {{captive: {{enabled: true, max_seconds: 5}}}}
logging: {{level: WARNING}}
""")
    PropertiesConfigurator.reset()
    from run_maya_web import create_app
    app = create_app(PropertiesConfigurator(str(cfg_file), reload_interval=0))
    with TestClient(app) as c:
        # Every API endpoint now requires an authenticated principal. The
        # bootstrap administrator is created on first start from configuration;
        # tests that care about authorisation override these credentials.
        c.auth = ("admin", "admin123")
        yield c


# Duties are separated in the fixtures because they are separated in the system.
# One account can no longer walk the whole path: the person who creates a version
# may not approve it, promote it, or conclude its validation.
PEOPLE = {
    "d.raman":  (["model_developer"],    "dev-pw"),
    "j.okafor": (["model_owner"],        "owner-pw"),
    "a.mehta":  (["validator"],          "val-pw"),
    "s.iqbal":  (["model_risk_manager"], "mrm-pw"),
}


@pytest.fixture
def people(client):
    """Create one principal per duty and return their credentials."""
    for username, (roles, password) in PEOPLE.items():
        r = client.post("/api/v1/principals", json={
            "username": username, "display_name": username, "roles": roles,
            "password": password})
        assert r.status_code == 201, r.text
    return {u: (u, pw) for u, (roles, pw) in PEOPLE.items()}


@pytest.fixture
def registered(client, people):
    """A model taken through the whole governed path by four different people."""
    owner, dev, mrm = people["j.okafor"], people["d.raman"], people["s.iqbal"]
    client.post("/api/v1/models", auth=owner, json={
        "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
        "domain": "credit", "owner": "person/j.okafor", "legal_entity": "LE-US-01",
        "purpose": "12-month PD at origination"})
    client.post(f"/api/v1/models/{NAME}/versions", auth=dev,
                json={"semver": "3.2.1", "kernel": KERNEL, "contract": CONTRACT,
                      "artifact_digest": "sha256:abc"})
    client.post(f"/api/v1/models/{NAME}/versions/3.2.1/approve", auth=mrm)
    client.post(f"/api/v1/models/{NAME}/assess", auth=owner,
                json={"exposure": 2e9, "purpose_class": "regulatory_capital"})
    client.put(f"/api/v1/models/{NAME}/aliases", auth=mrm,
               json={"environment": "prod", "alias": "champion", "semver": "3.2.1"})
    client.post("/api/v1/warrants", auth=owner, json={
        "urn": f"{URN}#champion", "environment": "prod",
        "principal": "svc/origination", "declared_use": "origination_decision"})
    return client


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
        registered.post(f"/api/v1/models/{NAME}/versions/3.3.0/approve", auth=mrm)
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


def _login(client, username="admin", password="admin123"):
    return client.post("/login", data={"username": username, "password": password,
                                       "next": "/dashboard"}, follow_redirects=False)


class TestPublicPages:
    def test_landing_is_public_and_carries_the_slogan(self, client):
        r = client.get("/")
        assert r.status_code == 200 and "Evidence, not assertion." in r.text

    def test_landing_explains_the_name(self, client):
        assert "m\u0101y\u0101" in client.get("/").text or "maya" in client.get("/").text.lower()

    def test_about_is_public(self, client):
        r = client.get("/about")
        assert r.status_code == 200 and "does not execute models" in r.text

    def test_help_lists_topic_cards_from_the_content_directory(self, client):
        body = client.get("/help").text
        assert "Documentation" in body
        # Cards, not a hard-coded walkthrough: the topics come from markdown on disk.
        assert "/help/quickstart" in body and "/help/registering-a-model" in body
        assert "Getting started" in body and "Reference" in body

    def test_a_help_topic_renders_its_markdown(self, client):
        body = client.get("/help/features-and-two-clocks").text
        assert body.count("<h2") >= 2, "headings should be rendered, not escaped"
        assert "<table>" in body, "markdown tables should render as tables"
        assert "content/help/" in body, "the source file is cited on the page"

    def test_an_unknown_help_topic_is_404(self, client):
        assert client.get("/help/no-such-topic").status_code == 404

    def test_help_is_reachable_without_signing_in(self, client):
        assert client.get("/help").status_code == 200
        assert client.get("/help/glossary").status_code == 200

    def test_about_carries_the_competitive_analysis(self, client):
        body = client.get("/about").text
        assert "Competitive analysis" in body
        assert "OpenPages" in body and "MLflow" in body
        assert "Where MAYA is weaker today" in body, "positioning must state weaknesses too"

    def test_landing_offers_sign_in_when_anonymous(self, client):
        assert "/login" in client.get("/").text


class TestAuthentication:
    def test_login_page_renders(self, client):
        assert client.get("/login").status_code == 200

    def test_valid_credentials_redirect_to_the_dashboard(self, client):
        r = _login(client)
        assert r.status_code == 303 and r.headers["location"] == "/dashboard"

    def test_invalid_password_is_rejected(self, client):
        r = _login(client, password="wrong")
        assert r.status_code == 401 and "not recognised" in r.text

    def test_invalid_username_is_rejected(self, client):
        assert _login(client, username="nobody").status_code == 401

    def test_dashboard_redirects_when_anonymous(self, client):
        r = client.get("/dashboard", follow_redirects=False)
        assert r.status_code == 303 and "/login" in r.headers["location"]

    def test_model_page_redirects_when_anonymous(self, client):
        r = client.get(f"/model/{NAME}", follow_redirects=False)
        assert r.status_code == 303

    def test_logout_clears_the_session(self, client):
        _login(client)
        client.get("/logout", follow_redirects=False)
        assert client.get("/dashboard", follow_redirects=False).status_code == 303


class TestAuthenticatedInterface:
    @pytest.fixture
    def signed_in(self, registered):
        _login(registered)
        return registered

    def test_dashboard_lists_a_registered_model(self, signed_in):
        assert "SB PD" in signed_in.get("/dashboard").text

    def test_model_page_renders(self, signed_in):
        html = signed_in.get(f"/model/{NAME}").text
        assert "SB PD" in html and "3.2.1" in html and "TIER" in html

    def test_unknown_model_page_is_404(self, signed_in):
        assert signed_in.get("/model/ghost").status_code == 404

    def test_no_cdn_references_anywhere(self, signed_in):
        """Every asset must be vendored: the UI has to work air-gapped."""
        for path in ("/", "/about", "/help", "/login", "/dashboard", f"/model/{NAME}"):
            html = signed_in.get(path).text
            for marker in ("cdn.", "//code.jquery", "googleapis", "jsdelivr", "unpkg"):
                assert marker not in html, f"{marker} referenced in {path}"

    def test_vendored_assets_are_served(self, client):
        for asset in ("/static/vendor/bootstrap/css/bootstrap.min.css",
                      "/static/vendor/jquery/jquery.min.js",
                      "/static/img/maya-mark-64.png"):
            assert client.get(asset).status_code == 200, asset


SCORED = {"left": [0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1, 1],
          "right": [0.02, 0.05, 0.09, 0.12, 0.18, 0.21, 0.24, 0.33,
                    0.41, 0.48, 0.52, 0.61, 0.70, 0.78, 0.85, 0.94]}


class TestValidationApi:
    def test_the_test_catalogue_is_published(self, client):
        body = client.get("/api/v1/tests").json()
        keys = {t["key"] for t in body["tests"]}
        assert "discrimination.gini" in keys and "stability.psi" in keys

    def test_open_record_and_conclude(self, registered):
        v = registered.post("/api/v1/validations", json={
            "urn": URN, "semver": "3.2.1", "validators": ["person/a.mehta"],
            "scope": ["discrimination"]})
        assert v.status_code == 201
        vid = v.json()["id"]

        r = registered.post(f"/api/v1/validations/{vid}/results",
                            json={"test_key": "discrimination.gini",
                                  "threshold": {"min": 0.3}, **SCORED})
        assert r.status_code == 201 and r.json()["passed"] is True

        done = registered.post(f"/api/v1/validations/{vid}/conclude",
                               json={"outcome": "approved"})
        assert done.status_code == 200 and done.json()["outcome"] == "approved"

    def test_the_builder_cannot_validate_their_own_version(self, registered, people):
        """The version was created by d.raman, so naming them as validator fails."""
        r = registered.post("/api/v1/validations", auth=people["a.mehta"], json={
            "urn": URN, "semver": "3.2.1", "validators": ["d.raman"]})
        assert r.status_code == 409
        assert "independence failed" in r.json()["detail"]
        assert "d.raman built this version" in r.json()["detail"]

    def test_approval_over_a_failed_test_is_refused_with_the_route_out(self, registered):
        vid = registered.post("/api/v1/validations", json={
            "urn": URN, "semver": "3.2.1", "validators": ["person/a.mehta"]}).json()["id"]
        registered.post(f"/api/v1/validations/{vid}/results",
                        json={"test_key": "discrimination.gini",
                              "threshold": {"min": 0.99}, **SCORED})
        r = registered.post(f"/api/v1/validations/{vid}/conclude",
                            json={"outcome": "approved"})
        assert r.status_code == 409
        assert "approved_with_conditions" in r.json()["detail"]

    def test_a_validation_reads_back_with_its_results_and_summary(self, registered):
        vid = registered.post("/api/v1/validations", json={
            "urn": URN, "semver": "3.2.1", "validators": ["person/a.mehta"]}).json()["id"]
        registered.post(f"/api/v1/validations/{vid}/results",
                        json={"test_key": "calibration.brier",
                              "threshold": {"max": 1.0}, **SCORED})
        body = registered.get(f"/api/v1/validations/{vid}").json()
        assert body["summary"]["tests_run"] == 1
        assert body["results"][0]["test_key"] == "calibration.brier"

    def test_an_unknown_validation_is_404(self, client):
        assert client.get("/api/v1/validations/nope").status_code == 404

    def test_replay_reproduces_over_the_api(self, registered):
        vid = registered.post("/api/v1/validations", json={
            "urn": URN, "semver": "3.2.1", "validators": ["person/a.mehta"]}).json()["id"]
        registered.post(f"/api/v1/validations/{vid}/results",
                        json={"test_key": "discrimination.gini",
                              "threshold": {"min": 0.3}, **SCORED})
        report = registered.post(
            f"/api/v1/validations/{vid}/replay",
            json={"data": {"discrimination.gini": [SCORED["left"], SCORED["right"]]}}).json()
        assert report["reproducible"] is True and report["reproduced"] == 1

    def test_replay_without_data_reports_skipped_not_reproduced(self, registered):
        vid = registered.post("/api/v1/validations", json={
            "urn": URN, "semver": "3.2.1", "validators": ["person/a.mehta"]}).json()["id"]
        registered.post(f"/api/v1/validations/{vid}/results",
                        json={"test_key": "discrimination.gini",
                              "threshold": {"min": 0.3}, **SCORED})
        report = registered.post(f"/api/v1/validations/{vid}/replay",
                                 json={"data": {}}).json()
        assert report["reproducible"] is False and len(report["skipped"]) == 1


class TestFindingsApi:
    def test_raise_and_read_back_a_finding(self, registered):
        r = registered.post("/api/v1/findings", json={
            "urn": URN, "severity": "Critical", "title": "Leakage in training set",
            "owner": "person/j.okafor"})
        assert r.status_code == 201 and r.json()["blocking"] is True

        body = registered.get("/api/v1/findings", params={"urn": URN}).json()
        assert body["summary"]["blocking"] == 1
        assert body["blocking"][0]["title"] == "Leakage in training set"

    def test_a_blocking_finding_refuses_warrant_resolution(self, registered):
        registered.post("/api/v1/findings", json={
            "urn": URN, "severity": "Critical", "title": "Leakage",
            "owner": "person/j.okafor"})
        r = registered.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination", "declared_use": "origination_decision"})
        assert r.status_code == 423
        assert r.json()["error"] == "blocked"
        assert r.json()["remediation"]

    def test_closing_the_finding_restores_service(self, registered):
        fid = registered.post("/api/v1/findings", json={
            "urn": URN, "severity": "Critical", "title": "Leakage",
            "owner": "person/j.okafor"}).json()["id"]
        registered.post(f"/api/v1/findings/{fid}/close",
                        json={"verified_by": "person/a.mehta", "evidence": {"pr": "1420"}})
        r = registered.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination", "declared_use": "origination_decision"})
        assert r.status_code == 200

    def test_the_owner_cannot_verify_their_own_closure_over_the_api(self, registered):
        fid = registered.post("/api/v1/findings", json={
            "urn": URN, "severity": "High", "title": "Docs stale",
            "owner": "person/j.okafor"}).json()["id"]
        r = registered.post(f"/api/v1/findings/{fid}/close",
                            json={"verified_by": "person/j.okafor",
                                  "evidence": {"pr": "1"}})
        assert r.status_code == 409 and "own closure" in r.json()["detail"]

    def test_an_unknown_severity_is_refused(self, registered):
        r = registered.post("/api/v1/findings", json={
            "urn": URN, "severity": "Catastrophic", "title": "x", "owner": "person/o"})
        assert r.status_code == 409


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


class TestLifecycleApi:
    def test_the_state_machine_is_published(self, client, people):
        body = client.get("/api/v1/lifecycle", auth=people["d.raman"]).json()
        assert {t["name"] for t in body["transitions"]} == {
            "submit", "return", "approve", "attest", "amend", "retire"}

    def test_the_whole_path_over_the_api(self, registered, people):
        owner, mrm = people["j.okafor"], people["s.iqbal"]
        assert registered.post(f"/api/v1/models/{NAME}/submit", auth=owner,
                               json={"note": "ready"}).status_code == 200
        assert registered.post(f"/api/v1/models/{NAME}/approve", auth=mrm,
                               json={"note": "sound"}).status_code == 200

        state = registered.get(f"/api/v1/models/{NAME}",
                               auth=owner).json()["lifecycle"]
        assert state["state"] == "approved" and not state["mutable"]
        assert state["open_attestation"]["outstanding_roles"] == [
            "model_owner", "model_risk_manager"]

        registered.post(f"/api/v1/models/{NAME}/attest", auth=owner,
                        json={"role": "model_owner", "statement": "controls operating"})
        r = registered.post(f"/api/v1/models/{NAME}/attest", auth=mrm,
                            json={"role": "model_risk_manager"})
        assert r.json()["state"] == "attested"

    def test_a_developer_cannot_approve_the_record(self, registered, people):
        registered.post(f"/api/v1/models/{NAME}/submit", auth=people["j.okafor"], json={})
        r = registered.post(f"/api/v1/models/{NAME}/approve", auth=people["d.raman"],
                            json={})
        assert r.status_code == 403

    def test_an_attested_model_refuses_a_new_version(self, registered, people):
        owner, mrm, dev = people["j.okafor"], people["s.iqbal"], people["d.raman"]
        registered.post(f"/api/v1/models/{NAME}/submit", auth=owner, json={})
        registered.post(f"/api/v1/models/{NAME}/approve", auth=mrm, json={})
        registered.post(f"/api/v1/models/{NAME}/attest", auth=owner,
                        json={"role": "model_owner"})
        registered.post(f"/api/v1/models/{NAME}/attest", auth=mrm,
                        json={"role": "model_risk_manager"})
        r = registered.post(f"/api/v1/models/{NAME}/versions", auth=dev,
                            json={"semver": "4.0.0", "kernel": KERNEL})
        assert r.status_code == 409
        assert "immutable" in r.json()["detail"]
        assert "amendment" in r.json()["detail"]

    def test_deletion_is_refused_for_everyone_but_an_administrator(self, registered,
                                                                   people):
        for who in (people["j.okafor"], people["s.iqbal"], people["d.raman"]):
            r = registered.request("DELETE", f"/api/v1/models/{NAME}",
                                   auth=who, params={"reason": "cleanup"})
            assert r.status_code == 403, f"{who[0]} must not be able to delete"

    def test_an_administrator_may_delete_and_the_evidence_remains(self, registered):
        before = registered.get("/api/v1/evidence/chain").json()["length"]
        r = registered.request("DELETE", f"/api/v1/models/{NAME}",
                               params={"reason": "registered in error"})
        assert r.status_code == 200 and r.json()["deleted"] is True
        chain = registered.get("/api/v1/evidence/chain").json()
        assert chain["valid"] is True and chain["length"] > before

    def test_the_workflow_renders_in_the_interface(self, registered, people):
        registered.post(f"/api/v1/models/{NAME}/submit", auth=people["j.okafor"], json={})
        registered.post("/login", data={"username": "admin", "password": "admin123",
                                        "next": "/dashboard"})
        body = registered.get(f"/model/{NAME}").text
        assert "Approval &amp; attestation" in body
        assert 'class="flow"' in body, "the stepper should render"
        assert "FROZEN" in body, "a submitted record is not open to change"

    def test_a_lifecycle_refusal_renders_in_the_standard_shape(self, registered, people):
        """Every refusal in the platform has the same three fields."""
        r = registered.post(f"/api/v1/models/{NAME}/approve", auth=people["s.iqbal"],
                            json={})
        assert r.status_code == 409
        body = r.json()
        assert body["error"] == "illegal_transition"
        assert "from here you may" in body["detail"]
        assert body["remediation"]

    def test_amending_reopens_an_attested_record(self, registered, people):
        owner, mrm, dev = people["j.okafor"], people["s.iqbal"], people["d.raman"]
        registered.post(f"/api/v1/models/{NAME}/submit", auth=owner, json={})
        registered.post(f"/api/v1/models/{NAME}/approve", auth=mrm, json={})
        registered.post(f"/api/v1/models/{NAME}/attest", auth=owner,
                        json={"role": "model_owner"})
        registered.post(f"/api/v1/models/{NAME}/attest", auth=mrm,
                        json={"role": "model_risk_manager"})

        r = registered.post(f"/api/v1/models/{NAME}/amend", auth=owner,
                            json={"reason": "recalibrate for the 2026 cycle",
                                  "scope": ["kernel"]})
        assert r.status_code == 200 and r.json()["status"] == "amending"
        assert registered.post(f"/api/v1/models/{NAME}/versions", auth=dev,
                               json={"semver": "4.0.0", "kernel": KERNEL}).status_code == 201


class TestMonitoringApi:
    def test_the_monitor_kinds_are_published_with_their_tests(self, client, people):
        body = client.get("/api/v1/monitor-kinds", auth=people["d.raman"]).json()
        kinds = {k["kind"]: k for k in body["kinds"]}
        assert kinds["input_drift"]["tests"] == ["stability.psi"]
        assert kinds["performance"]["needs_labels"] is True
        assert kinds["score_drift"]["needs_labels"] is False

    def test_define_and_evaluate_a_drift_monitor(self, registered, people):
        owner = people["j.okafor"]
        r = registered.post("/api/v1/monitors", auth=owner, json={
            "urn": URN, "name": "score drift", "kind": "score_drift",
            "test_key": "stability.psi", "threshold": {"max": 0.25},
            "owner": "person/j.okafor"})
        assert r.status_code == 201
        mid = r.json()["id"]

        reference = [i / 100 for i in range(100)]
        rows = [{"scored_at": 1.8e9, "score": i / 100} for i in range(100)]
        out = registered.post(f"/api/v1/monitors/{mid}/evaluate", auth=owner,
                              json={"rows": rows, "reference": reference,
                                    "now": 1.8e9}).json()
        assert out["observation"]["passed"] is True and out["breach"] is None

    def test_a_performance_monitor_refuses_an_immature_cohort(self, registered, people):
        owner = people["j.okafor"]
        mid = registered.post("/api/v1/monitors", auth=owner, json={
            "urn": URN, "name": "gini", "kind": "performance",
            "test_key": "discrimination.gini", "threshold": {"min": 0.4},
            "owner": "person/j.okafor", "label_delay_days": 365}).json()["id"]
        rows = [{"scored_at": 1.8e9, "score": i / 20, "label": i % 2}
                for i in range(20)]
        r = registered.post(f"/api/v1/monitors/{mid}/evaluate", auth=owner,
                            json={"rows": rows, "now": 1.8e9 + 86400})
        assert r.status_code == 409
        assert r.json()["error"] == "cohort_immature"
        assert "wait for the outcome window" in r.json()["remediation"]

    def test_a_breach_becomes_a_finding_visible_on_the_model(self, registered, people):
        owner = people["j.okafor"]
        mid = registered.post("/api/v1/monitors", auth=owner, json={
            "urn": URN, "name": "score drift", "kind": "score_drift",
            "test_key": "stability.psi", "threshold": {"max": 0.1},
            "owner": "person/j.okafor", "breach_severity": "Critical"}).json()["id"]
        registered.post(f"/api/v1/monitors/{mid}/evaluate", auth=owner, json={
            "rows": [{"scored_at": 1.8e9, "score": 0.99} for _ in range(100)],
            "reference": [i / 100 for i in range(100)], "now": 1.8e9})

        findings = registered.get("/api/v1/findings", params={"urn": URN}).json()
        assert findings["summary"]["blocking"] == 1
        assert findings["blocking"][0]["source"] == "monitoring"

        # ...and the model is now unservable.
        r = registered.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination", "declared_use": "origination_decision"})
        assert r.status_code == 423 and r.json()["error"] == "blocked"

    def test_a_developer_cannot_define_a_monitor(self, registered, people):
        r = registered.post("/api/v1/monitors", auth=people["d.raman"], json={
            "urn": URN, "name": "x", "kind": "score_drift",
            "test_key": "stability.psi", "threshold": {"max": 0.25}, "owner": "o"})
        assert r.status_code == 403

    def test_an_inadmissible_test_is_refused_at_definition(self, registered, people):
        r = registered.post("/api/v1/monitors", auth=people["j.okafor"], json={
            "urn": URN, "name": "x", "kind": "input_drift",
            "test_key": "discrimination.gini", "threshold": {"min": 0.4},
            "owner": "o"})
        assert r.status_code == 422
        assert r.json()["error"] == "test_not_admissible"

    def test_monitoring_renders_on_the_model_page(self, registered, people):
        registered.post("/api/v1/monitors", auth=people["j.okafor"], json={
            "urn": URN, "name": "score drift", "kind": "score_drift",
            "test_key": "stability.psi", "threshold": {"max": 0.25}, "owner": "o"})
        registered.post("/login", data={"username": "admin", "password": "admin123",
                                        "next": "/dashboard"})
        body = registered.get(f"/model/{NAME}").text
        assert "Monitoring" in body and "score drift" in body
        assert "stability.psi" in body


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


class TestTutorialsArea:
    def test_the_tutorials_index_renders_cards(self, client):
        body = client.get("/tutorials").text
        assert "Working through MAYA" in body
        assert "/tutorials/end-to-end" in body
        assert "/tutorials/warrants-by-family" in body

    def test_a_tutorial_renders_its_markdown(self, client):
        body = client.get("/tutorials/features-end-to-end").text
        assert "<table>" in body and body.count("<h2") >= 3

    def test_an_unknown_tutorial_is_404(self, client):
        assert client.get("/tutorials/nope").status_code == 404

    def test_tutorials_are_public(self, client):
        anon = TestClient(client.app)
        assert anon.get("/tutorials").status_code == 200
        assert anon.get("/tutorials/end-to-end").status_code == 200

    def test_help_still_works_alongside_tutorials(self, client):
        assert client.get("/help").status_code == 200
        assert client.get("/help/warrants").status_code == 200


class TestDocumentApi:
    def test_the_document_kinds_are_published(self, client, people):
        body = client.get("/api/v1/document-kinds", auth=people["d.raman"]).json()
        kinds = {k["kind"] for k in body["kinds"]}
        assert {"model_development_document", "validation_report", "model_card",
                "annex_iv"} == kinds
        assert all(k["purpose"] for k in body["kinds"])

    def test_compile_and_read_back(self, registered, people):
        r = registered.post("/api/v1/documents", auth=people["a.mehta"],
                            params={"urn": URN, "kind": "model_development_document"})
        assert r.status_code == 201
        doc = r.json()
        assert doc["citations"] and doc["sections"]

        full = registered.get(f"/api/v1/documents/{doc['id']}",
                              auth=people["a.mehta"]).json()
        assert full["citations_verified"]["sound"] is True
        assert full["staleness"]["stale"] is False

    def test_it_renders_as_markdown(self, registered, people):
        doc = registered.post("/api/v1/documents", auth=people["a.mehta"],
                              params={"urn": URN, "kind": "model_card"}).json()
        text = registered.get(f"/api/v1/documents/{doc['id']}/markdown",
                              auth=people["a.mehta"]).text
        assert text.startswith("# Model Card")
        assert "## Identity and ownership" in text

    def test_a_governance_event_makes_it_stale(self, registered, people):
        doc = registered.post("/api/v1/documents", auth=people["a.mehta"],
                              params={"urn": URN,
                                      "kind": "model_development_document"}).json()
        registered.post("/api/v1/findings", auth=people["a.mehta"], json={
            "urn": URN, "severity": "Medium", "title": "Docs stale",
            "owner": "person/j.okafor"})
        stale = registered.get(f"/api/v1/documents/{doc['id']}",
                               auth=people["a.mehta"]).json()["staleness"]
        assert stale["stale"] is True and "finding_raised" in stale["kinds_since"]

    def test_a_developer_cannot_compile(self, registered, people):
        r = registered.post("/api/v1/documents", auth=people["d.raman"],
                            params={"urn": URN, "kind": "model_card"})
        assert r.status_code == 403

    def test_an_unknown_kind_is_refused(self, registered, people):
        r = registered.post("/api/v1/documents", auth=people["a.mehta"],
                            params={"urn": URN, "kind": "poem"})
        assert r.status_code == 422 and r.json()["error"] == "unknown_document_kind"

    def test_the_document_renders_in_the_interface(self, registered, people):
        doc = registered.post("/api/v1/documents", auth=people["a.mehta"],
                              params={"urn": URN,
                                      "kind": "model_development_document"}).json()
        registered.post("/login", data={"username": "admin", "password": "admin123",
                                        "next": "/dashboard"})
        body = registered.get(f"/document/{doc['id']}").text
        assert "Model Development Document" in body
        assert "<h2" in body, "the markdown should be rendered, not escaped"
        assert "Required sections not filled" in body or "sections" in body

    def test_the_model_page_lists_documents(self, registered, people):
        registered.post("/api/v1/documents", auth=people["a.mehta"],
                        params={"urn": URN, "kind": "model_card"})
        registered.post("/login", data={"username": "admin", "password": "admin123",
                                        "next": "/dashboard"})
        body = registered.get(f"/model/{NAME}").text
        assert "Documentation" in body and "Model Card" in body
        assert 'id="compile-doc"' in body


class TestOverlayApi:
    def test_the_overlay_kinds_are_published(self, client, people):
        body = client.get("/api/v1/overlay-kinds", auth=people["j.okafor"]).json()
        assert {k["kind"] for k in body["kinds"]} == {
            "parameter", "output", "exclusion", "judgemental"}

    def test_propose_approve_measure_and_read(self, registered, people):
        owner, mrm = people["j.okafor"], people["s.iqbal"]
        r = registered.post("/api/v1/overlays", auth=owner, json={
            "urn": URN, "name": "SME sector uplift", "kind": "output",
            "rationale": "The model under-predicts hospitality default post-2025.",
            "owner": "person/j.okafor"})
        assert r.status_code == 201
        oid = r.json()["id"]

        assert registered.post(f"/api/v1/overlays/{oid}/approve",
                               auth=mrm).status_code == 200
        assert registered.post(f"/api/v1/overlays/{oid}/measure", auth=owner, json={
            "period": "2026-Q1", "base_value": 1000000.0,
            "adjusted_value": 1180000.0}).status_code == 201

        reading = registered.get(f"/api/v1/overlays/{oid}", auth=owner).json()
        assert reading["assessment"]["materiality"]["pct_of_base"] == pytest.approx(0.18)

    def test_the_proposer_cannot_approve_over_the_api(self, registered):
        """Admin holds both permissions and is still refused: the rule is about
        the person, not the role."""
        created = registered.post("/api/v1/overlays", json={
            "urn": URN, "name": "x", "kind": "output", "rationale": "because",
            "owner": "person/o"})
        assert created.status_code == 201, created.text
        r = registered.post(f"/api/v1/overlays/{created.json()['id']}/approve")
        assert r.status_code == 403 and r.json()["error"] == "self_approval"


    def test_renewal_without_a_measurement_is_refused(self, registered, people):
        oid = registered.post("/api/v1/overlays", auth=people["j.okafor"], json={
            "urn": URN, "name": "x", "kind": "output", "rationale": "because",
            "owner": "person/o"}).json()["id"]
        registered.post(f"/api/v1/overlays/{oid}/approve", auth=people["s.iqbal"])
        r = registered.post(f"/api/v1/overlays/{oid}/renew", auth=people["s.iqbal"])
        assert r.status_code == 409 and r.json()["error"] == "unmeasured"

    def test_a_persistent_overlay_raises_a_finding(self, registered, people):
        owner, mrm = people["j.okafor"], people["s.iqbal"]
        oid = registered.post("/api/v1/overlays", auth=owner, json={
            "urn": URN, "name": "SME uplift", "kind": "output",
            "rationale": "model under-predicts", "owner": "person/o"}).json()["id"]
        registered.post(f"/api/v1/overlays/{oid}/approve", auth=mrm)
        for period in ("2026-Q1", "2026-Q2", "2026-Q3"):
            registered.post(f"/api/v1/overlays/{oid}/measure", auth=owner, json={
                "period": period, "base_value": 1000.0, "adjusted_value": 1150.0})
            registered.post(f"/api/v1/overlays/{oid}/renew", auth=mrm,
                            params={"period": period})
        found = registered.get("/api/v1/findings", params={"urn": URN}).json()
        assert any("Persistent overlay" in f["title"] for f in found["open"])

    def test_the_portfolio_answers_how_much_is_the_model(self, registered, people):
        owner, mrm = people["j.okafor"], people["s.iqbal"]
        oid = registered.post("/api/v1/overlays", auth=owner, json={
            "urn": URN, "name": "uplift", "kind": "output", "rationale": "r",
            "owner": "person/o"}).json()["id"]
        registered.post(f"/api/v1/overlays/{oid}/approve", auth=mrm)
        registered.post(f"/api/v1/overlays/{oid}/measure", auth=owner, json={
            "period": "2026-Q1", "base_value": 1000000.0, "adjusted_value": 1180000.0})
        body = registered.get("/api/v1/overlays", params={"urn": URN},
                              auth=owner).json()
        assert body["aggregate_magnitude"] == pytest.approx(180000.0)
        assert "in aggregate" in body["detail"]

    def test_overlays_render_on_the_model_page(self, registered, people):
        registered.post("/api/v1/overlays", auth=people["j.okafor"], json={
            "urn": URN, "name": "SME sector uplift", "kind": "output",
            "rationale": "r", "owner": "person/o"})
        registered.post("/login", data={"username": "admin", "password": "admin123",
                                        "next": "/dashboard"})
        body = registered.get(f"/model/{NAME}").text
        assert "Post-model adjustments" in body and "SME sector uplift" in body

    def test_overlays_appear_in_a_compiled_document(self, registered, people):
        owner, mrm = people["j.okafor"], people["s.iqbal"]
        oid = registered.post("/api/v1/overlays", auth=owner, json={
            "urn": URN, "name": "SME uplift", "kind": "output", "rationale": "r",
            "owner": "person/o"}).json()["id"]
        registered.post(f"/api/v1/overlays/{oid}/approve", auth=mrm)
        doc = registered.post("/api/v1/documents", auth=people["a.mehta"],
                              params={"urn": URN,
                                      "kind": "model_development_document"}).json()
        text = registered.get(f"/api/v1/documents/{doc['id']}/markdown",
                              auth=people["a.mehta"]).text
        assert "## Post-model adjustments" in text
        assert "describes a model nobody runs" in text


class TestAssistApi:
    def test_the_tiers_and_oracles_are_published(self, client, people):
        body = client.get("/api/v1/assist/tiers", auth=people["d.raman"]).json()
        assert {t["tier"] for t in body["tiers"]} == {"A", "B"}
        assert body["oracles"] and "chat window" in body["note"]

    def test_register_a_grounded_capability_and_generate(self, registered, people):
        mrm, val = people["s.iqbal"], people["a.mehta"]
        r = registered.post("/api/v1/assist/capabilities", auth=mrm, json={
            "capability_key": "doc.draft", "description": "drafts doc sections",
            "tier": "B", "base_model": "claude-opus-5",
            "prompt_digest": "sha256:p", "owner": "person/a.mehta"})
        assert r.status_code == 201

        chain = registered.get("/api/v1/models/" + NAME).json()
        ids = [n["id"] for n in chain["evidence"]][:2]
        g = registered.post("/api/v1/assist/generations", auth=val, json={
            "capability_key": "doc.draft", "subject_type": "model",
            "subject_id": chain["model"]["id"],
            "claims": [{"id": "c1", "text": "Registered in 2026.",
                        "citations": ids[:1]},
                       {"id": "c2", "text": "Invented.", "citations": ["ghost"]}],
            "known_evidence": ids})
        assert g.status_code == 201
        body = g.json()
        assert body["output"]["grounding"]["rejected"] == 1
        assert "Invented." not in body["output"]["text"], \
            "an ungrounded claim must not reach the output"

    def test_tier_c_is_refused_over_the_api(self, registered, people):
        r = registered.post("/api/v1/assist/capabilities", auth=people["s.iqbal"],
                            json={"capability_key": "hunch", "description": "d",
                                  "tier": "C", "base_model": "m",
                                  "prompt_digest": "p", "owner": "o"})
        assert r.status_code == 422
        assert r.json()["error"] == "advisory_not_registrable"

    def test_tier_a_without_an_oracle_is_refused(self, registered, people):
        r = registered.post("/api/v1/assist/capabilities", auth=people["s.iqbal"],
                            json={"capability_key": "x", "description": "d",
                                  "tier": "A", "base_model": "m",
                                  "prompt_digest": "p", "owner": "o"})
        assert r.status_code == 422 and r.json()["error"] == "oracle_required"

    def test_the_requester_cannot_attest_their_own_generation(self, registered,
                                                              people):
        mrm, val = people["s.iqbal"], people["a.mehta"]
        registered.post("/api/v1/assist/capabilities", auth=mrm, json={
            "capability_key": "doc.draft", "description": "d", "tier": "B",
            "base_model": "m", "prompt_digest": "p", "owner": "o"})
        model = registered.get("/api/v1/models/" + NAME).json()
        ids = [n["id"] for n in model["evidence"]][:1]
        gid = registered.post("/api/v1/assist/generations", auth=val, json={
            "capability_key": "doc.draft", "subject_type": "model",
            "subject_id": model["model"]["id"],
            "claims": [{"id": "c", "text": "Registered.", "citations": ids}],
            "known_evidence": ids}).json()["id"]

        r = registered.post(f"/api/v1/assist/generations/{gid}/attest", auth=val,
                            json={"accept": True})
        assert r.status_code == 403 and r.json()["error"] == "self_attestation"

        ok = registered.post(f"/api/v1/assist/generations/{gid}/attest", auth=mrm,
                             json={"accept": True, "final_text": "Registered."})
        assert ok.status_code == 200 and ok.json()["state"] == "attested"

    def test_there_is_no_endpoint_that_decides_from_a_generation(self, client):
        """The absence is the control: a draft becomes consequential only when a
        person attests it."""
        paths = client.get("/api/v1/openapi.json").json()["paths"]
        assist = [p for p in paths if "/assist/" in p]
        assert assist, "the assistance surface should exist"
        for path in assist:
            assert "approve" not in path and "conclude" not in path


class TestBaselineApi:
    BATCH = [{"urn": "maya://model/legacy.pd.corporate", "name": "Corporate PD",
              "owner": "person/j.okafor", "legal_entity": "LE-US-01",
              "purpose": "PD for corporate lending", "domain": "credit", "tier": 1}]

    def test_the_gap_catalogue_is_published(self, client, people):
        body = client.get("/api/v1/baseline/gaps", auth=people["d.raman"]).json()
        keys = {g["key"] for g in body["gaps"]}
        assert {"owner", "version", "tier", "validation", "monitoring"} <= keys

    def test_import_a_batch_and_read_its_debt(self, client, people):
        mrm = people["s.iqbal"]
        r = client.post("/api/v1/baseline/imports", auth=mrm, json={
            "source": "legacy-inventory.csv", "models": self.BATCH})
        assert r.status_code == 201
        assert r.json()["models"] == 1 and r.json()["debt_items"] > 0
        assert "existing use is not blocked" in r.json()["detail"]

        debt = client.get("/api/v1/baseline/debt", auth=mrm,
                          params={"urn": self.BATCH[0]["urn"]}).json()
        assert debt["baselined"] is True and debt["debt_open"] > 0
        assert debt["breached"] == 0, "debt is not breach"

    def test_a_baselined_model_is_in_the_inventory(self, client, people):
        client.post("/api/v1/baseline/imports", auth=people["s.iqbal"], json={
            "source": "csv", "models": self.BATCH})
        listed = client.get("/api/v1/models", auth=people["s.iqbal"]).json()["models"]
        found = next(m for m in listed if m["urn"] == self.BATCH[0]["urn"])
        assert found["status"] == "baselined"

    def test_reconcile_closes_debt_when_the_evidence_arrives(self, client, people):
        mrm, dev = people["s.iqbal"], people["d.raman"]
        client.post("/api/v1/baseline/imports", auth=mrm, json={
            "source": "csv", "models": self.BATCH})
        urn = self.BATCH[0]["urn"]
        name = urn.rsplit("/", 1)[-1]
        before = client.get("/api/v1/baseline/debt", auth=mrm,
                            params={"urn": urn}).json()["debt_open"]

        client.post(f"/api/v1/models/{name}/versions", auth=dev, json={
            "semver": "1.0.0", "kernel": KERNEL, "contract": CONTRACT,
            "artifact_digest": "sha256:abc"})
        r = client.post("/api/v1/baseline/reconcile", auth=mrm, params={"urn": urn})
        assert r.status_code == 200 and r.json()["closed"]
        after = client.get("/api/v1/baseline/debt", auth=mrm,
                           params={"urn": urn}).json()["debt_open"]
        assert after < before

    def test_the_portfolio_reports_the_burn_down(self, client, people):
        client.post("/api/v1/baseline/imports", auth=people["s.iqbal"], json={
            "source": "csv", "models": self.BATCH})
        body = client.get("/api/v1/baseline", auth=people["s.iqbal"]).json()
        assert body["models_baselined"] == 1 and "burn_down" in body

    def test_a_developer_cannot_import(self, client, people):
        r = client.post("/api/v1/baseline/imports", auth=people["d.raman"], json={
            "source": "csv", "models": self.BATCH})
        assert r.status_code == 403


class TestRegimeApi:
    def test_the_regime_catalogue_is_published(self, client, people):
        body = client.get("/api/v1/regimes", auth=people["d.raman"]).json()
        keys = {r["key"] for r in body["regimes"]}
        assert {"sr-26-2", "ss1-23", "eu-ai-act"} <= keys
        sr = next(r for r in body["regimes"] if r["key"] == "sr-26-2")
        assert sr["active"] is True
        assert all(o["citation"] for o in sr["obligations"])

    def test_each_regime_publishes_its_own_vocabulary(self, client, people):
        body = client.get("/api/v1/regimes", auth=people["d.raman"]).json()
        by_key = {r["key"]: set(r["vocabulary"]) for r in body["regimes"]}
        assert "affects_natural_persons" in by_key["eu-ai-act"]
        assert "affects_natural_persons" not in by_key["sr-26-2"]

    def test_the_satisfaction_condition_is_checkable_over_the_api(self, client,
                                                                  people):
        r = client.get("/api/v1/regimes/sr-26-2/satisfaction",
                       auth=people["d.raman"]).json()
        assert r["holds"] is True and r["checked"] > 0
        assert "invariant under translation" in r["detail"]

    def test_an_unknown_regime_is_404(self, client, people):
        r = client.get("/api/v1/regimes/atlantis/satisfaction",
                       auth=people["d.raman"])
        assert r.status_code == 404 and r.json()["error"] == "no_regime"

    def test_determinations_are_returned_per_regime_with_their_derivation(
            self, registered, people):
        body = registered.get("/api/v1/regimes/determinations",
                              params={"urn": URN}, auth=people["d.raman"]).json()
        assert body["regimes"], "activated regimes should produce verdicts"
        first = body["regimes"][0]
        assert first["read_as"], "the regime-eye view of the model must be shown"
        assert all("citation" in o for o in first["obligations"])
        assert body["core_state"]["has_version"] is True

    def test_a_developer_cannot_activate_a_regime(self, client, people):
        r = client.post("/api/v1/regimes/ss1-23/activate", auth=people["d.raman"])
        assert r.status_code == 403

    def test_regimes_render_on_the_model_page(self, registered):
        registered.post("/login", data={"username": "admin", "password": "admin123",
                                        "next": "/dashboard"})
        body = registered.get(f"/model/{NAME}").text
        assert "Supervisory regimes" in body
        assert "sr-26-2" in body or "eu-ai-act" in body


class TestDashboardEstate:
    def test_the_dashboard_shows_the_estate_and_your_own_work(self, registered,
                                                              people):
        registered.post("/login", data={"username": "admin", "password": "admin123",
                                        "next": "/dashboard"})
        body = registered.get("/dashboard").text
        assert "models registered" in body
        assert "blocking findings" in body and "open breaches" in body
        assert "Outstanding for you" in body

    def test_an_outstanding_signature_reaches_the_person_who_can_sign(
            self, registered, people):
        owner, mrm = people["j.okafor"], people["s.iqbal"]
        r1 = registered.post(f"/api/v1/models/{NAME}/submit", auth=owner, json={})
        assert r1.status_code == 200, r1.text
        r2 = registered.post(f"/api/v1/models/{NAME}/approve", auth=mrm, json={})
        assert r2.status_code == 200, r2.text

        client = TestClient(registered.app)
        client.post("/login", data={"username": owner[0], "password": owner[1],
                                    "next": "/dashboard"})
        body = client.get("/dashboard").text
        assert "Attestation outstanding: model_owner" in body
        assert "Attestation outstanding: model_risk_manager" not in body, \
            "the owner is not shown somebody else's signature"

    def test_the_worklist_explains_that_it_cannot_go_stale(self, registered,
                                                           people):
        owner = people["j.okafor"]
        registered.post(f"/api/v1/models/{NAME}/submit", auth=owner, json={})
        client = TestClient(registered.app)
        val = people["a.mehta"]
        client.post("/login", data={"username": val[0], "password": val[1],
                                    "next": "/dashboard"})
        body = client.get("/dashboard").text
        assert "computed from the register rather than assigned" in body


class TestSchedulerApi:
    def test_the_job_catalogue_is_published_with_reasons(self, client, people):
        body = client.get("/api/v1/scheduler", auth=people["d.raman"]).json()
        keys = {j["job"] for j in body["jobs"]}
        assert {"attestation.lapsed", "monitoring.stalled", "overlays.expire",
                "debt.reconcile", "findings.overdue"} == keys
        assert all(j["what"] and j["why"] for j in body["jobs"])
        assert body["health"]["ever_run"] == 0

    def test_a_run_is_an_ordinary_authenticated_call(self, registered):
        """Cron, a CronJob, or a person — all the same endpoint."""
        r = registered.post("/api/v1/scheduler/run", json={})
        assert r.status_code == 200
        assert r.json()["ran"] == 5 and r.json()["failed"] == 0

    def test_running_the_same_job_twice_changes_nothing_more(self, registered):
        first = registered.post("/api/v1/scheduler/run",
                                json={"jobs": ["overlays.expire"]}).json()
        second = registered.post("/api/v1/scheduler/run",
                                 json={"jobs": ["overlays.expire"]}).json()
        assert first["results"][0]["outcome"] == second["results"][0]["outcome"]

    def test_an_unknown_job_is_refused(self, registered):
        r = registered.post("/api/v1/scheduler/run", json={"jobs": ["nonsense"]})
        assert r.status_code == 422 and r.json()["error"] == "unknown_job"

    def test_a_developer_cannot_run_the_schedule(self, registered, people):
        r = registered.post("/api/v1/scheduler/run", auth=people["d.raman"],
                            json={})
        assert r.status_code == 403

    def test_history_records_what_ran(self, registered):
        registered.post("/api/v1/scheduler/run", json={})
        runs = registered.get("/api/v1/scheduler/history").json()["runs"]
        assert len(runs) == 5 and all(r["ok"] for r in runs)

    def test_readiness_reports_the_scheduler_without_failing_on_it(self, client):
        """A stopped scheduler is worth knowing about and is not a reason to
        take the node out of service."""
        body = client.get("/health/ready")
        assert body.status_code == 200
        assert "scheduler" in body.json()
        assert body.json()["scheduler"]["detail"]

    def test_the_loop_is_off_unless_configured_on(self, client, people):
        body = client.get("/api/v1/scheduler", auth=people["d.raman"]).json()
        assert body["loop_running"] is False


# =========================================================== attached documents
class TestAttachedDocuments:
    """Uploading a document is the one place the API takes bytes rather than
    JSON, and the one place a second person's signature is on a file."""

    MDD = "# SB PD — Model Development Document\n\nLogistic regression.\n".encode()

    def _upload(self, client, auth, data=None, **fields):
        form = {"urn": URN, "kind": "model_development_document",
                "title": "SB PD MDD", **fields}
        return client.post("/api/v1/attachments", auth=auth, data=form,
                           files={"file": ("mdd.md", data or self.MDD,
                                           "text/markdown")})

    def test_an_owner_can_file_a_document(self, registered, people):
        r = self._upload(registered, people["j.okafor"])
        assert r.status_code == 201, r.text
        assert r.json()["state"] == "attached"
        assert r.json()["digest"].startswith("sha256:")

    def test_a_validator_may_not_file_one(self, registered, people):
        """Filing and accepting are different duties, held by different people."""
        assert self._upload(registered, people["a.mehta"]).status_code == 403

    def test_the_author_cannot_accept_their_own(self, registered, people):
        """Two independent lines. The role check already stops an owner, who
        holds no review permission; this asserts the register refuses even a
        principal whose role would otherwise let them through."""
        admin = ("admin", "admin123")
        attachment = self._upload(registered, admin).json()
        r = registered.post(f"/api/v1/attachments/{attachment['id']}/review",
                            auth=admin, json={"accept": True})
        assert r.status_code == 403 and r.json()["error"] == "self_review"

    def test_an_owner_holds_no_review_permission_at_all(self, registered, people):
        attachment = self._upload(registered, people["j.okafor"]).json()
        r = registered.post(f"/api/v1/attachments/{attachment['id']}/review",
                            auth=people["j.okafor"], json={"accept": True})
        assert r.status_code == 403 and r.json()["error"] == "forbidden"

    def test_a_reviewer_can_accept_it(self, registered, people):
        attachment = self._upload(registered, people["j.okafor"]).json()
        r = registered.post(f"/api/v1/attachments/{attachment['id']}/review",
                            auth=people["a.mehta"],
                            json={"accept": True, "note": "complete"})
        assert r.status_code == 200 and r.json()["state"] == "accepted"

    def test_rejecting_without_a_reason_is_refused(self, registered, people):
        attachment = self._upload(registered, people["j.okafor"]).json()
        r = registered.post(f"/api/v1/attachments/{attachment['id']}/review",
                            auth=people["a.mehta"], json={"accept": False})
        assert r.status_code == 422 and r.json()["error"] == "reason_required"

    def test_the_bytes_come_back_unchanged(self, registered, people):
        attachment = self._upload(registered, people["j.okafor"]).json()
        r = registered.get(f"/api/v1/attachments/{attachment['id']}/content")
        assert r.status_code == 200 and r.content == self.MDD
        assert "mdd.md" in r.headers["content-disposition"]

    def test_the_register_reports_what_is_on_file(self, registered, people):
        self._upload(registered, people["j.okafor"])
        body = registered.get(f"/api/v1/attachments?urn={URN}").json()
        assert body["attached"] == 1 and body["awaiting_review"] == 1
        assert body["attachments"][0]["title"] == "SB PD MDD"

    def test_an_unknown_kind_is_refused_with_the_list(self, registered, people):
        r = self._upload(registered, people["j.okafor"], kind="vibes")
        assert r.status_code == 422 and r.json()["error"] == "unknown_kind"

    def test_the_kinds_are_published_with_what_they_mean(self, registered):
        kinds = registered.get("/api/v1/attachment-kinds").json()["kinds"]
        assert any(k["kind"] == "validation_report" and k["means"] for k in kinds)

    def test_a_rejected_document_is_still_in_the_history(self, registered, people):
        attachment = self._upload(registered, people["j.okafor"]).json()
        registered.post(f"/api/v1/attachments/{attachment['id']}/review",
                        auth=people["a.mehta"],
                        json={"accept": False, "note": "no back-testing"})
        history = registered.get(
            f"/api/v1/attachments?urn={URN}&history=true").json()["attachments"]
        assert [a["state"] for a in history] == ["rejected"]

    def test_the_model_page_shows_the_register(self, registered, people):
        self._upload(registered, people["j.okafor"])
        _login(registered)
        page = registered.get(f"/model/{NAME}").text
        assert "SB PD MDD" in page and "awaiting review" in page


# ===================================================== featuresets and parameters
class TestFeaturesetsAndParameters:
    """The cycle: name a presentation of X, fit under a warrant, take delivery
    of a point in P, and have somebody else approve it before anything runs."""

    def _catalogue(self, client, auth):
        for name, dtype in [("living_area_sqft", "numeric"),
                            ("bedrooms", "integer"), ("sale_price", "numeric")]:
            client.post("/api/v1/features", auth=auth, json={
                "name": name, "entity": "property_id", "dtype": dtype,
                "description": f"NJ {name}", "owner": "person/j.okafor"})

    def _derived(self, client, auth, name="log_living_area",
                 expression="log(living_area_sqft)"):
        return client.post("/api/v1/derived-features", auth=auth, json={
            "name": name, "expression": expression, "dtype": "numeric",
            "description": "log of heated floor area"})

    def test_the_expression_language_is_published(self, registered):
        body = registered.get("/api/v1/expression-language").json()
        assert any(f["name"] == "log" for f in body["functions"])
        assert "external" in body["excluded"]

    def test_a_developer_can_declare_a_derived_feature(self, registered, people):
        self._catalogue(registered, people["d.raman"])
        r = self._derived(registered, people["d.raman"])
        assert r.status_code == 201, r.text
        assert r.json()["inputs"] == ["living_area_sqft"]

    def test_an_expression_outside_the_language_is_refused(self, registered, people):
        self._catalogue(registered, people["d.raman"])
        r = self._derived(registered, people["d.raman"], "evil",
                          "__import__('os').system('ls')")
        assert r.status_code == 409 and r.json()["error"] == "feature_refused"
        assert "not one of the functions" in r.json()["detail"]

    def test_lineage_answers_both_directions(self, registered, people):
        self._catalogue(registered, people["d.raman"])
        self._derived(registered, people["d.raman"])
        body = registered.get(
            "/api/v1/derived-features/log_living_area/lineage").json()
        assert body["rests_on"] == ["living_area_sqft"]
        assert registered.get(
            "/api/v1/derived-features/living_area_sqft/lineage"
        ).json()["depended_on_by"] == ["log_living_area"]

    def _featureset(self, client, auth):
        self._catalogue(client, auth)
        client.post("/api/v1/feature-views", auth=auth, json={
            "name": "nj_characteristics", "entity": "property_id",
            "owner": "person/j.okafor",
            "features": ["living_area_sqft", "bedrooms"]})
        client.post("/api/v1/feature-views/nj_characteristics/materialise",
                    auth=auth, json={"rows": [
                        {"entity_id": "P1", "event_ts": 1717200000.0,
                         "ingest_ts": 1717200000.0,
                         "living_area_sqft": 1800.0, "bedrooms": 3}]})
        return client.post("/api/v1/featuresets", auth=auth, json={
            "name": "nj_home_core", "entity": "property_id",
            "slots": {"living_area_sqft": "numeric", "bedrooms": "integer"}})

    def test_a_featureset_declares_a_schema_and_a_version_fills_it(
            self, registered, people):
        dev = people["d.raman"]
        assert self._featureset(registered, dev).status_code == 201
        r = registered.post("/api/v1/featuresets/nj_home_core/versions",
                            auth=dev, json={"bindings": {
                                "living_area_sqft": "living_area_sqft",
                                "bedrooms": "bedrooms"}})
        assert r.status_code == 201, r.text
        assert r.json()["version"] == 1
        assert r.json()["bindings"]["bedrooms"]["view_version"] == 1

    def test_a_binding_naming_no_slot_is_refused(self, registered, people):
        dev = people["d.raman"]
        self._featureset(registered, dev)
        r = registered.post("/api/v1/featuresets/nj_home_core/versions",
                            auth=dev, json={"bindings": {
                                "living_area_sqft": "living_area_sqft",
                                "bedrooms": "bedrooms",
                                "sale_price": "sale_price"}})
        assert r.status_code == 409
        assert "no declared slot" in r.json()["detail"]

    def test_the_plan_carries_the_namespaces_an_engine_reads(self, registered,
                                                             people):
        dev = people["d.raman"]
        self._featureset(registered, dev)
        registered.post("/api/v1/featuresets/nj_home_core/versions", auth=dev,
                        json={"bindings": {"living_area_sqft": "living_area_sqft",
                                           "bedrooms": "bedrooms"}})
        plan = registered.get("/api/v1/featuresets/nj_home_core/versions/1").json()
        assert plan["namespaces"] == ["features/property_id/nj_characteristics/v1"]
        assert "ingest_ts <= as_of" in plan["pit_rule"]

    def test_a_validator_may_not_publish_a_featureset(self, registered, people):
        self._featureset(registered, people["d.raman"])
        r = registered.post("/api/v1/featuresets/nj_home_core/versions",
                            auth=people["a.mehta"], json={"bindings": {}})
        assert r.status_code == 403

    # ------------------------------------------------------------- parameters
    def _warrant(self, client, auth):
        return client.post("/api/v1/warrants", auth=auth, json={
            "urn": URN, "environment": "lab", "principal": "svc/model-lab",
            "declared_use": "model_development"}).json()

    def _record(self, client, auth, **kw):
        body = {"urn": URN, "semver": "3.2.1", "name": "sb-pd-2025q1",
                "kind": "estimated_coefficients",
                "values": {"intercept": -1.4, "turnover": 0.31},
                "provenance": "declared"}
        body.update(kw)
        return client.post("/api/v1/parameters", auth=auth, json=body)

    def test_the_provenance_routes_are_published(self, registered):
        kinds = registered.get("/api/v1/parameter-provenance").json()["provenance"]
        assert {k["kind"] for k in kinds} == {"fitted", "calibrated", "declared"}

    def test_declared_parameters_are_recorded(self, registered, people):
        r = self._record(registered, people["d.raman"])
        assert r.status_code == 201, r.text
        assert r.json()["state"] == "proposed" and r.json()["cardinality"] == 2

    def test_a_fitted_set_without_a_warrant_is_refused(self, registered, people):
        r = self._record(registered, people["d.raman"], provenance="fitted")
        assert r.status_code == 422 and r.json()["error"] == "warrant_required"

    def test_a_fitted_set_names_the_warrant_and_the_featureset(self, registered,
                                                               people):
        dev = people["d.raman"]
        self._featureset(registered, dev)
        registered.post("/api/v1/featuresets/nj_home_core/versions", auth=dev,
                        json={"bindings": {"living_area_sqft": "living_area_sqft",
                                           "bedrooms": "bedrooms"}})
        grant = self._warrant(registered, people["j.okafor"])
        r = self._record(registered, dev, provenance="fitted",
                         warrant_id=grant["id"], featureset="nj_home_core",
                         featureset_version=1, as_of=1736899200.0)
        assert r.status_code == 201, r.text
        assert r.json()["featureset_version_id"]

    def test_whoever_recorded_them_cannot_approve_them(self, registered, people):
        """Two independent lines: the role grant stops a developer, who holds no
        approval permission, and the register stops even a principal whose role
        would let them through."""
        admin = ("admin", "admin123")
        recorded = self._record(registered, admin).json()
        r = registered.post(f"/api/v1/parameter-sets/{recorded['id']}/review",
                            auth=admin, json={"accept": True})
        assert r.status_code == 403 and r.json()["error"] == "self_approval"

    def test_a_validator_can_approve_them(self, registered, people):
        recorded = self._record(registered, people["d.raman"]).json()
        r = registered.post(f"/api/v1/parameter-sets/{recorded['id']}/review",
                            auth=people["a.mehta"],
                            json={"accept": True, "note": "residuals reviewed"})
        assert r.status_code == 200 and r.json()["state"] == "approved"

    def test_an_owner_holds_no_approval_permission(self, registered, people):
        recorded = self._record(registered, people["d.raman"]).json()
        r = registered.post(f"/api/v1/parameter-sets/{recorded['id']}/review",
                            auth=people["j.okafor"], json={"accept": True})
        assert r.status_code == 403 and r.json()["error"] == "forbidden"

    def test_the_status_says_whether_the_kernel_is_ready(self, registered, people):
        body = registered.get(
            f"/api/v1/parameters?urn={URN}&semver=3.2.1").json()
        assert body["ready"] is False
        assert "cannot be run until" in body["detail"]

        recorded = self._record(registered, people["d.raman"]).json()
        registered.post(f"/api/v1/parameter-sets/{recorded['id']}/review",
                        auth=people["a.mehta"], json={"accept": True})
        after = registered.get(
            f"/api/v1/parameters?urn={URN}&semver=3.2.1").json()
        assert after["ready"] and after["approved"] == 1

    def test_the_model_page_shows_what_it_runs_on(self, registered, people):
        recorded = self._record(registered, people["d.raman"]).json()
        registered.post(f"/api/v1/parameter-sets/{recorded['id']}/review",
                        auth=people["a.mehta"], json={"accept": True})
        _login(registered)
        page = registered.get(f"/model/{NAME}").text
        assert "sb-pd-2025q1" in page and "declared" in page


class TestTheFitWarrantChecksTheSchema:
    """L-W10. A featureset a warrant names must provide what the kernel reads.
    Left unchecked this is a claim, and the model is fitted over a different X
    than the one its version declares."""

    def _fittable_version(self, client, people):
        """A version MAYA can locate. L-W6 refuses to fit a descriptor-only
        model, and the shared fixture registers one — correctly."""
        # The runtime is what makes a version locatable; without one the
        # builder emits descriptor_only and L-W6 refuses to fit it, correctly.
        kernel = {**KERNEL, "runtime": "python.callable",
                  "entry": {"module": "sb.estimators", "attr": "ols_fit"}}
        client.post(f"/api/v1/models/{NAME}/versions", auth=people["d.raman"],
                    json={"semver": "3.3.0", "kernel": kernel,
                          "contract": CONTRACT,
                          "artifact_digest": "sha256:" + "d" * 64,
                          "artifact_uri": "file://sb_pd_3.3.0.onnx"})
        client.post(f"/api/v1/models/{NAME}/versions/3.3.0/approve",
                    auth=people["s.iqbal"])
        client.put(f"/api/v1/models/{NAME}/aliases", auth=people["s.iqbal"],
                   json={"environment": "prod", "alias": "champion",
                         "semver": "3.3.0"})

    def _setup(self, client, auth, slots, bindings):
        for name, dtype in [("dscr", "float"), ("turnover", "float")]:
            client.post("/api/v1/features", auth=auth, json={
                "name": name, "entity": "borrower_id", "dtype": dtype,
                "description": name, "owner": "person/j.okafor"})
        client.post("/api/v1/feature-views", auth=auth, json={
            "name": "sb_credit", "entity": "borrower_id",
            "owner": "person/j.okafor", "features": ["dscr", "turnover"]})
        client.post("/api/v1/feature-views/sb_credit/materialise", auth=auth,
                    json={"rows": [{"entity_id": "B1", "event_ts": 1717200000.0,
                                    "ingest_ts": 1717200000.0,
                                    "dscr": 1.4, "turnover": 250000.0}]})
        client.post("/api/v1/featuresets", auth=auth, json={
            "name": "sb_set", "entity": "borrower_id", "slots": slots})
        return client.post("/api/v1/featuresets/sb_set/versions", auth=auth,
                           json={"bindings": bindings})

    def _fit(self, client, auth):
        # resolve_fit reads a standing grant, exactly as resolve() does: a fit is
        # an entitlement like any other, not a side door around one.
        client.post("/api/v1/warrants", auth=auth, json={
            "urn": URN, "environment": "prod", "principal": "svc/model-lab",
            "declared_use": "model_development"})
        return client.post("/api/v1/fit-warrants", auth=auth, json={
            "urn": URN, "environment": "prod", "principal": "svc/model-lab",
            "featureset": "sb_set", "featureset_version": 1,
            "window": {"from": 1546300800.0, "to": 1735603200.0},
            "as_of": 1736899200.0})

    def test_a_covering_featureset_yields_a_signed_descriptor(self, registered,
                                                              people):
        """The fixture kernel declares it reads dscr."""
        dev, owner = people["d.raman"], people["j.okafor"]
        self._fittable_version(registered, people)
        self._setup(registered, dev, {"dscr": "float"}, {"dscr": "dscr"})
        r = self._fit(registered, owner)
        assert r.status_code == 201, r.text
        doc = r.json()
        assert doc["operation"]["verb"] == "fit"
        assert doc["parameters"]["source"]["binding"] == "to_be_fitted"
        assert doc["data"]["inputs"][0]["featureset"] == "sb_set"
        assert doc["data"]["outputs"][0]["sink"] == "parameter_object"

    def test_a_featureset_missing_what_the_kernel_reads_is_refused(
            self, registered, people):
        dev, owner = people["d.raman"], people["j.okafor"]
        self._setup(registered, dev, {"turnover": "float"},
                    {"turnover": "turnover"})
        r = self._fit(registered, owner)
        assert r.status_code == 409, r.text
        assert r.json()["error"] == "schema_not_satisfied"
        assert "dscr" in r.json()["detail"]
        assert "model change, not a data change" in r.json()["remediation"]

    def test_the_descriptor_carries_the_pinned_namespaces(self, registered,
                                                          people):
        dev, owner = people["d.raman"], people["j.okafor"]
        self._fittable_version(registered, people)
        self._setup(registered, dev, {"dscr": "float"}, {"dscr": "dscr"})
        binding = self._fit(registered, owner).json()["data"]["inputs"][0]
        assert binding["namespaces"] == ["features/borrower_id/sb_credit/v1"]
        assert "ingest_ts <= as_of" in binding["pit_rule"]


class TestTheEngineBoundaryIsPublished:
    def test_it_says_what_the_isolation_does_not_cover(self, registered):
        body = registered.get("/api/v1/engine").json()
        assert body["captive_engine"] == "enabled"
        assert body["does_not_protect_against"]
