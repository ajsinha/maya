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
        assert "/help/quickstart" in body and "/help/trainability-classes" in body
        assert "Getting started" in body and "Reference" in body

    def test_a_help_topic_renders_its_markdown(self, client):
        body = client.get("/help/point-in-time-assembly").text
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
        assert client.get("/help/warrant-grammar").status_code == 200


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
