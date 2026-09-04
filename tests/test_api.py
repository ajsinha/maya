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
hooks: {{jitter_pct: 0, signing_key_id: test-key,
         ttl_seconds: {{1: 60, 2: 300, 3: 3600, 4: 3600}},
         grace_seconds: {{1: 0, 2: 0, 3: 900, 4: 900}}}}
execution: {{captive: {{enabled: true, max_seconds: 5}}}}
logging: {{level: WARNING}}
""")
    PropertiesConfigurator.reset()
    from run_maya_web import create_app
    app = create_app(PropertiesConfigurator(str(cfg_file), reload_interval=0))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def registered(client):
    client.post("/api/v1/models", json={
        "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
        "domain": "credit", "owner": "person/j.okafor", "legal_entity": "LE-US-01",
        "purpose": "12-month PD at origination"})
    client.post(f"/api/v1/models/{NAME}/versions",
                json={"semver": "3.2.1", "kernel": KERNEL, "contract": CONTRACT,
                      "artifact_digest": "sha256:abc"})
    client.post(f"/api/v1/models/{NAME}/versions/3.2.1/approve")
    client.post(f"/api/v1/models/{NAME}/assess",
                json={"exposure": 2e9, "purpose_class": "regulatory_capital"})
    client.put(f"/api/v1/models/{NAME}/aliases",
               json={"environment": "prod", "alias": "champion", "semver": "3.2.1"})
    client.post("/api/v1/hooks", json={
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

    def test_alias_move_is_refused_when_incompatible(self, registered):
        weak = {**CONTRACT, "guarantees": [{"key": "gini", "minimum": 0.10}]}
        registered.post(f"/api/v1/models/{NAME}/versions",
                        json={"semver": "3.3.0", "kernel": KERNEL, "contract": weak})
        registered.post(f"/api/v1/models/{NAME}/versions/3.3.0/approve")
        r = registered.put(f"/api/v1/models/{NAME}/aliases",
                           json={"environment": "prod", "alias": "champion", "semver": "3.3.0"})
        assert r.status_code == 409 and "gini" in r.json()["detail"]

    def test_evidence_chain_endpoint(self, registered):
        assert registered.get("/api/v1/evidence/chain").json()["valid"] is True


class TestHookApi:
    def test_resolve_returns_a_signed_descriptor(self, registered):
        r = registered.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination", "declared_use": "origination_decision"})
        d = r.json()
        assert d["resolved"]["version"] == "3.2.1" and d["signature"]

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
        assert registered.post("/api/v1/hooks/revoke",
                               json={"urn": URN, "reason": "critical finding"}).json()["revoked"] == 1
        r = registered.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination", "declared_use": "origination_decision"})
        assert r.status_code == 410 and r.json()["error"] == "revoked"


class TestExecutionBoundary:
    """MAYA issues hooks. The captive engine is one consumer of that contract."""

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
        registered.post("/api/v1/hooks/revoke", json={"urn": URN, "reason": "stop"})
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

    def test_help_is_public_and_shows_the_six_steps(self, client):
        html = client.get("/help").text
        assert "Register the model" in html and "Issue a hook" in html

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
