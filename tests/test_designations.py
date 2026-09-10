"""What a model is ALSO subject to, beside its tier.

A tier answers one question — how much rides on this model — and answers it
well. It does not answer the others. Two models can sit at the same tier while
one feeds a regulatory submission and the other does not, and no amount of
moving either up or down the lattice produces a reconciliation requirement.
"""
from __future__ import annotations

import pytest

from core.risk.designations import (DESIGNATION_CONTROLS, DESIGNATIONS,
                                    DesignationError, EXTRA_CONTROLS,
                                    explain, extra_controls, validate)
from core.risk.lattices import CONTROLS
from core.risk.tiering import TieringEngine
from tests.conftest import NAME, URN


class TestTheyAreOrthogonalToTheTier:
    """The separation is the thing preventing `L-5` from breaking quietly."""

    def test_designations_add_controls_without_moving_the_tier(self):
        plain = TieringEngine.required_controls(3)
        tagged = TieringEngine.required_controls(3, ["sox_relevant"])
        assert set(plain).issubset(set(tagged)), "additive, never subtractive"
        assert set(tagged) - set(plain) == set(EXTRA_CONTROLS["sox_relevant"])

    def test_the_galois_adjoint_reads_tier_controls_only(self):
        """An adjoint that also read designation controls would answer *which
        tier do these defend* from facts the tier lattice does not contain."""
        for tier in (1, 2, 3, 4):
            assert TieringEngine.supports_tier(list(CONTROLS[tier])) == tier

    def test_adding_a_designation_does_not_change_what_defends_a_tier(self):
        applied = list(CONTROLS[2]) + list(DESIGNATION_CONTROLS)
        assert TieringEngine.supports_tier(applied) == \
            TieringEngine.supports_tier(list(CONTROLS[2]))


class TestATagThatChangesNothingIsALabel:
    @pytest.mark.parametrize("designation", DESIGNATIONS)
    def test_every_designation_adds_at_least_one_control(self, designation):
        assert EXTRA_CONTROLS[designation], \
            "a designation nothing keys off is decoration"

    def test_the_extra_controls_are_all_waivable(self):
        """Or a bank that cannot yet meet one has nowhere to say so, and the
        requirement becomes something people meet on paper."""
        from core.waivers import WAIVABLE
        assert set(DESIGNATION_CONTROLS).issubset(set(WAIVABLE))

    def test_explain_says_which_control_came_from_which_designation(self):
        out = explain(["consumer_impacting"])
        assert out[0]["designation"] == "consumer_impacting"
        assert "adverse_action_reasons" in out[0]["adds"]
        assert out[0]["means"], "why, not only what"


class TestValidation:
    def test_an_unknown_designation_is_refused_by_name(self):
        with pytest.raises(DesignationError) as exc:
            validate(["important"])
        assert exc.value.code == "unknown_designation"
        assert "would change nothing" in exc.value.detail

    def test_the_answer_is_sorted_so_two_sets_compare_equal(self):
        assert validate(["safety_critical", "sox_relevant"]) == \
            validate(["sox_relevant", "safety_critical"])

    def test_duplicates_collapse(self):
        assert validate(["sox_relevant", "sox_relevant"]) == ["sox_relevant"]

    def test_no_designations_adds_no_controls(self):
        assert extra_controls([]) == []


class TestOverTheApi:
    def _registered(self, client, people):
        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "12-month PD"})
        return NAME

    def test_the_four_are_published_with_what_each_adds(self, client, people):
        r = client.get("/api/v1/designations", auth=people["d.raman"])
        assert r.status_code == 200, r.text
        got = {d["designation"] for d in r.json()["designations"]}
        assert got == set(DESIGNATIONS)
        assert all(d["adds"] for d in r.json()["designations"])

    def test_designating_a_model_reports_what_it_now_owes(self, client, people):
        name = self._registered(client, people)
        r = client.put(f"/api/v1/models/{name}/designations",
                       auth=people["j.okafor"],
                       json={"designations": ["regulatory_reporting"]})
        assert r.status_code == 200, r.text
        assert "reconciliation_to_submission" in r.json()["adds_controls"]

    def test_an_unknown_one_is_refused(self, client, people):
        name = self._registered(client, people)
        r = client.put(f"/api/v1/models/{name}/designations",
                       auth=people["j.okafor"],
                       json={"designations": ["important"]})
        assert r.status_code >= 400, r.text
        assert r.json()["error"] == "unknown_designation"

    def test_the_assessment_reads_them_off_the_model(self, client, people):
        """Not sent with the facts: a caller who could set them in an
        assessment could choose which controls it owes."""
        name = self._registered(client, people)
        client.post(f"/api/v1/models/{name}/versions", auth=people["d.raman"],
                    json={"semver": "1.0.0", "kernel": {
                        "runtime": "formula",
                        "parameter_kind": "estimated_coefficients",
                        "fit_procedure": "estimate", "deterministic": True,
                        "entry": {"expression": "w * x", "target": "y"},
                        "input_schema": [{"name": "x", "dtype": "numeric"}],
                        "parameter_schema": [{"name": "w", "dtype": "numeric"}],
                        "output_schema": [{"name": "y", "dtype": "numeric"}]}})
        client.put(f"/api/v1/models/{name}/designations", auth=people["j.okafor"],
                   json={"designations": ["consumer_impacting"]})
        r = client.post(f"/api/v1/models/{name}/assess", auth=people["j.okafor"],
                        json={"exposure": 0, "purpose_class": "credit_decision",
                              "feature_count": 4, "uses_alternative_data": False,
                              "interpretable": True})
        assert r.status_code == 200, r.text
        assert "adverse_action_reasons" in r.json()["required_controls"]

    def test_removing_a_designation_is_recorded_too(self, client, people):
        """A set that could only grow would record the day somebody decided a
        model reaches the financial statements and not the day they decided it
        no longer does."""
        name = self._registered(client, people)
        client.put(f"/api/v1/models/{name}/designations", auth=people["j.okafor"],
                   json={"designations": ["sox_relevant"]})
        r = client.put(f"/api/v1/models/{name}/designations",
                       auth=people["j.okafor"], json={"designations": []})
        assert r.status_code == 200, r.text
        assert r.json()["designations"] == []
        assert r.json()["adds_controls"] == []
