"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

`fitted` is the strongest claim the register offers: estimated from data, under
a warrant MAYA issued. It was refused for exactly two parameter kinds — `none`
(nothing to fit) and `opaque` (somebody else's) — and allowed for every other,
including three that no fit can produce.
"""
from __future__ import annotations

import pytest


def _kernel(kind: str, fit: str) -> dict:
    return {"runtime": "formula", "parameter_kind": kind, "fit_procedure": fit,
            "deterministic": True,
            "entry": {"expression": "w * x", "target": "y"},
            "input_schema": [{"name": "x", "dtype": "numeric"}],
            "parameter_schema": [{"name": "w", "dtype": "numeric"}],
            "output_schema": [{"name": "y", "dtype": "numeric"}]}


def _versioned(client, people, kind: str, fit: str) -> tuple:
    from tests.conftest import NAME, URN
    client.post("/api/v1/models", auth=people["j.okafor"], json={
        "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
        "domain": "credit", "owner": "person/j.okafor",
        "legal_entity": "LE-US-01", "purpose": "12-month PD"})
    made = client.post(f"/api/v1/models/{NAME}/versions", auth=people["d.raman"],
                       json={"semver": "1.0.0", "kernel": _kernel(kind, fit)})
    assert made.status_code == 201, made.text
    return NAME, URN


class TestAJudgmentCannotClaimToHaveBeenFitted:
    """A rule set is authored, a generative assembly is configured, and elicited
    weights come out of a panel. Recording any of them as `fitted` launders an
    opinion into a measurement — and the diagnostics that make an elicitation
    reviewable (the panel, the questions, the dissent) are exactly what nobody
    goes looking for once the row says the numbers came from data.
    """

    @pytest.mark.parametrize("kind,fit", [
        ("elicited_weights", "elicit"),
        ("rule_set", "author"),
        ("llm_configuration", "configure"),
    ])
    def test_it_is_refused_and_the_refusal_names_the_honest_word(
            self, client, people, kind, fit):
        _name, urn = _versioned(client, people, kind, fit)
        r = client.post("/api/v1/parameters", auth=people["d.raman"], json={
            "urn": urn, "semver": "1.0.0", "name": "p", "kind": kind,
            "values": {"w": 0.5}, "provenance": "fitted"})
        assert r.status_code >= 400, r.text
        body = r.json()
        assert body["error"] == "not_obtained_from_data", body
        assert kind in body["detail"], "name the kind that cannot be fitted"
        assert "declared" in body["remediation"], "name the honest word"

    def test_declared_is_accepted_for_the_same_version(self, client, people):
        """The refusal is about the CLAIM, not about the numbers. The same
        values arrive under the honest word and are taken."""
        _name, urn = _versioned(client, people, "elicited_weights", "elicit")
        r = client.post("/api/v1/parameters", auth=people["d.raman"], json={
            "urn": urn, "semver": "1.0.0", "name": "p",
            "kind": "elicited_weights", "values": {"w": 0.5},
            "provenance": "declared"})
        assert r.status_code == 201, r.text

    @pytest.mark.parametrize("kind,fit", [
        ("elicited_weights", "elicit"),
        ("rule_set", "author"),
        ("llm_configuration", "configure"),
    ])
    def test_calibrated_is_refused_for_the_same_set(self, client, people,
                                                    kind, fit):
        """`calibrated` is the lesser lie and still a lie.

        It means solved against market data under an approved procedure. A
        panel is not that, an author is not that, and a system prompt is not
        that. Guarding `fitted` alone left the middle claim open.
        """
        _name, urn = _versioned(client, people, kind, fit)
        r = client.post("/api/v1/parameters", auth=people["d.raman"], json={
            "urn": urn, "semver": "1.0.0", "name": "p", "kind": kind,
            "values": {"w": 0.5}, "provenance": "calibrated"})
        assert r.status_code >= 400, r.text
        assert r.json()["error"] == "not_obtained_from_data", r.text

    def test_a_calibration_set_may_still_be_calibrated(self, client, people):
        """The guard must not fire on the kind calibration genuinely produces."""
        _name, urn = _versioned(client, people, "calibration_set", "calibrate")
        r = client.post("/api/v1/parameters", auth=people["d.raman"], json={
            "urn": urn, "semver": "1.0.0", "name": "p",
            "kind": "calibration_set", "values": {"w": 0.5},
            "provenance": "calibrated"})
        assert r.status_code == 201, r.text

    def test_estimated_coefficients_may_still_be_fitted(self, client, people):
        """The guard must not fire on the kinds a fit genuinely produces."""
        _name, urn = _versioned(client, people, "estimated_coefficients",
                                "estimate")
        r = client.post("/api/v1/parameters", auth=people["d.raman"], json={
            "urn": urn, "semver": "1.0.0", "name": "p",
            "kind": "estimated_coefficients", "values": {"w": 0.5},
            "provenance": "fitted"})
        # It may be refused for wanting a warrant — which is a different and
        # correct refusal — but never for the kind it inhabits.
        if r.status_code >= 400:
            assert r.json()["error"] != "not_obtained_from_data", r.text
