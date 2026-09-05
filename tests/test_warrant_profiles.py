"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Templating the request, and the three laws that differ by how P is inhabited.

The ask was "warrants should be templated per kind of model". The half of it
that is right is the request: the same verb and the same ceiling retyped for
every warrant of a shape. The half that is wrong is the document, and these
tests are mostly about holding that line — a profile cannot select on a category
somebody attached, cannot widen authority, and cannot carry an obligation.

The laws are the other half of the answer. Warrants DO differ by kind of model;
they differ as refusals over one document rather than as different documents,
and each of the three here is keyed on a fact the platform derives.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from core.execution.grammar import validate
from core.execution.profiles import (ProfileError, WarrantProfileRegister,
                                     facts_for)

EXAMPLES = pathlib.Path(__file__).resolve().parent.parent / "examples" / "warrants"


def load(stem):
    doc = json.loads((EXAMPLES / f"{stem}.json").read_text())
    doc.pop("_comment", None)
    return doc


@pytest.fixture
def profiles(db, evidence):
    from db import WarrantProfileRepository
    return WarrantProfileRegister(WarrantProfileRepository(db), evidence)


# ---------------------------------------------------------------------------
# The laws
# ---------------------------------------------------------------------------
class TestACalibrationMustSayWhatItWasCalibratedAsOf:
    """L-W11. Staleness is silent unless the stamp is there to be read."""

    def test_a_calibrated_score_without_an_as_of_is_refused(self):
        doc = load("10-var-backtest")
        doc["parameters"]["source"].pop("as_of", None)
        problem = next(p for p in validate(doc).problems if p.law == "L-W11")
        assert "stale" in problem.detail

    def test_with_the_stamp_it_is_admissible(self):
        assert validate(load("10-var-backtest")).valid

    def test_a_fit_needs_none_because_it_is_producing_them(self):
        """The calibration being solved for cannot state when it was solved."""
        doc = load("02-quantlib-hullwhite-calibrate")
        assert doc["operation"]["verb"] == "fit"
        assert validate(doc).valid

    def test_estimated_coefficients_are_not_caught_by_it(self):
        """A regression's coefficients summarise a history rather than reproduce
        a market, so the day they were fitted is provenance rather than meaning."""
        doc = load("12-nj-linear-score-on-parameters")
        assert doc["parameters"]["kind"] == "estimated_coefficients"
        assert not [p for p in validate(doc).problems if p.law == "L-W11"]


class TestParametersInsideAnArtifactNeedItDigested:
    """L-W12. 'Which numbers ran' and 'which bytes loaded' are one question."""

    def test_an_undigested_artifact_binding_is_refused(self):
        doc = load("03-gbm-pd-score")
        doc["realisation"]["artifact"].pop("digest", None)
        doc["parameters"].pop("digest", None)
        problem = next(p for p in validate(doc).problems if p.law == "L-W12")
        assert "what it loaded is what was approved" in problem.detail

    def test_the_law_is_not_keyed_on_the_class(self):
        """A PMML scorecard is T3 and has exactly the same exposure as a T4
        network. Keying this on the trainability class would have missed it."""
        doc = load("05-logistic-scorecard-score")
        assert doc["subject"]["trainability_class"] != "T4"
        doc["parameters"]["source"] = {"binding": "artifact",
                                       "uri": "s3://x/scorecard.pmml"}
        doc["realisation"]["artifact"] = {"uri": "s3://x/scorecard.pmml"}
        assert [p for p in validate(doc).problems if p.law == "L-W12"]

    def test_a_parameter_set_binding_is_untouched_by_it(self):
        """Registered parameters carry their own digest; the artifact is not
        where those numbers live."""
        doc = load("12-nj-linear-score-on-parameters")
        assert doc["parameters"]["source"]["binding"] == "parameter_set"
        assert not [p for p in validate(doc).problems if p.law == "L-W12"]


class TestAGenerativeRuntimeMustPinTheBuild:
    """L-W13. A family name is not a build, and the weights move underneath it."""

    def test_a_base_model_name_alone_is_refused(self):
        doc = load("06-llm-kyc-summarise")
        doc["realisation"]["entry"].pop("base_model_version")
        problem = next(p for p in validate(doc).problems if p.law == "L-W13")
        assert "family of weights rather than a build" in problem.detail

    def test_a_pinned_build_is_admissible(self):
        assert validate(load("06-llm-kyc-summarise")).valid

    def test_an_agent_is_held_to_the_same_pin(self):
        doc = load("07-llm-agent-credit-memo")
        doc["realisation"]["entry"].pop("base_model_version")
        assert [p for p in validate(doc).problems if p.law == "L-W13"]

    def test_a_non_generative_runtime_is_not_asked_for_one(self):
        """An ONNX graph IS the build. There is nothing to pin that the digest
        does not already pin."""
        assert not [p for p in validate(load("03-gbm-pd-score")).problems
                    if p.law == "L-W13"]


# ---------------------------------------------------------------------------
# The profiles
# ---------------------------------------------------------------------------
class TestAProfileSelectsOnFactsThePlatformDerives:
    def test_a_predicate_over_derived_facts_is_accepted(self, profiles):
        row = profiles.create("trained_artifact", {"trainability_class": ["T4"]},
                              {"verb": "score", "max_seconds": 5})
        assert row["specificity"] == 1 and row["version"] == 1

    def test_a_category_somebody_attached_is_refused(self, profiles):
        """The whole point. A declared taxonomy beside a derived one is two
        answers to one question, and nothing decides which wins."""
        with pytest.raises(ProfileError) as exc:
            profiles.create("nn", {"model_category": ["neural_network"]},
                            {"verb": "score"})
        assert exc.value.code == "unknown_profile_fact"
        assert "DERIVES" in exc.value.remediation

    def test_a_predicate_that_allows_nothing_is_refused(self, profiles):
        with pytest.raises(ProfileError) as exc:
            profiles.create("dead", {"trainability_class": []}, {"verb": "score"})
        assert exc.value.code == "empty_predicate"

    def test_versions_accumulate_rather_than_overwrite(self, profiles):
        profiles.create("base", {}, {"max_seconds": 5})
        second = profiles.create("base", {}, {"max_seconds": 10})
        assert second["version"] == 2
        assert profiles.current("base")["defaults"]["max_seconds"] == 10


class TestAProfileCannotWidenAuthority:
    @pytest.mark.parametrize("key", ["principal", "declared_use", "environment",
                                     "ttl_seconds", "binding_kind"])
    def test_authority_keys_are_refused_at_creation(self, profiles, key):
        """Checked when the profile is written, because a check performed then
        is one nobody can forget to perform at use."""
        with pytest.raises(ProfileError) as exc:
            profiles.create("sneaky", {}, {key: "anything"})
        assert exc.value.code == "authority_not_defaultable"
        assert "warrant:resolve" in exc.value.remediation

    def test_an_obligation_is_pointed_at_the_policy_gate(self, profiles):
        """A default is something you can drop, so an obligation cannot be one."""
        with pytest.raises(ProfileError) as exc:
            profiles.create("must", {}, {"requires_digest": True})
        assert exc.value.code == "not_defaultable"

    def test_a_profile_that_changes_nothing_is_refused(self, profiles):
        with pytest.raises(ProfileError) as exc:
            profiles.create("empty", {"tier": [1]}, {})
        assert exc.value.code == "empty_profile"
        assert "reads as a control that ran" in exc.value.remediation


class TestTheFold:
    @pytest.fixture
    def stack(self, profiles):
        profiles.create("everything", {}, {"max_seconds": 30, "verb": "score"})
        profiles.create("trained", {"trainability_class": ["T4"]},
                        {"max_seconds": 10})
        profiles.create("trained_in_prod",
                        {"trainability_class": ["T4"], "environment": ["prod"]},
                        {"max_seconds": 3})
        return profiles

    def test_the_most_specific_speaks_last(self, stack):
        out = stack.apply({"trainability_class": "T4", "environment": "prod"})
        assert out["request"]["max_seconds"] == 3
        assert out["applied"]["max_seconds"] == "trained_in_prod@1"

    def test_a_less_specific_default_still_fills_a_hole(self, stack):
        """Rightmost wins per KEY, not per profile: the general profile still
        supplies the verb the specific one says nothing about."""
        out = stack.apply({"trainability_class": "T4", "environment": "prod"})
        assert out["request"]["verb"] == "score"
        assert out["applied"]["verb"] == "everything@1"

    def test_an_empty_predicate_is_the_identity(self, stack):
        out = stack.apply({"trainability_class": "T0", "environment": "dev"})
        assert [p["name"] for p in out["profiles"]] == ["everything"]
        assert out["request"]["max_seconds"] == 30

    def test_the_caller_is_never_overridden(self, stack):
        out = stack.apply({"trainability_class": "T4", "environment": "prod"},
                          {"max_seconds": 120})
        assert out["request"]["max_seconds"] == 120
        assert "max_seconds" not in out["applied"]

    def test_nothing_matching_leaves_the_request_alone(self, profiles):
        profiles.create("t4", {"trainability_class": ["T4"]}, {"max_seconds": 5})
        out = profiles.apply({"trainability_class": "T0"}, {"verb": "score"})
        assert out["request"] == {"verb": "score"} and out["profiles"] == []
        assert "no profile matches" in out["detail"]

    def test_the_derivation_names_where_each_value_came_from(self, stack):
        out = stack.apply({"trainability_class": "T4", "environment": "prod"})
        assert set(out["applied"]) == {"max_seconds", "verb"}
        assert all("@" in origin for origin in out["applied"].values())

    def test_retiring_one_stops_it_applying(self, stack):
        stack.retire("trained_in_prod")
        out = stack.apply({"trainability_class": "T4", "environment": "prod"})
        assert out["request"]["max_seconds"] == 10


class TestTheFactsAreDerivedFromTheVersion:
    def test_every_fact_comes_from_the_kernel_or_the_record(self):
        facts = facts_for(
            {"tier": 1, "domain": "credit", "model_class": "credit.pd.scorecard"},
            {"trainability_class": "T4", "parameter_kind": "learned_weights",
             "fit_procedure": "train",
             "manifest": {"kernel": {"runtime": "onnx",
                                     "artifact_format": "onnx"}}},
            "prod")
        assert facts["trainability_class"] == "T4"
        assert facts["runtime"] == "onnx" and facts["artifact_format"] == "onnx"
        assert facts["tier"] == 1 and facts["environment"] == "prod"

    def test_a_version_with_no_runtime_reads_as_descriptor_only(self):
        facts = facts_for({}, {"manifest": {}}, "prod")
        assert facts["runtime"] == "descriptor_only"


class TestOverTheApi:
    def test_the_vocabulary_is_published(self, client):
        body = client.get("/api/v1/warrant-profile-vocabulary").json()
        assert "trainability_class" in body["selectable_facts"]
        assert "verb" in body["defaultable"]
        assert "principal" in body["never_defaultable"]

    def test_a_profile_can_be_created_and_listed(self, client):
        r = client.post("/api/v1/warrant-profiles", json={
            "name": "trained_artifact", "when": {"trainability_class": ["T4"]},
            "defaults": {"verb": "score", "max_seconds": 5}})
        assert r.status_code == 201, r.text
        names = [p["name"] for p in
                 client.get("/api/v1/warrant-profiles").json()["profiles"]]
        assert "trained_artifact" in names

    def test_authority_is_refused_with_a_status_that_says_who_must_act(self, client):
        r = client.post("/api/v1/warrant-profiles", json={
            "name": "sneaky", "when": {}, "defaults": {"principal": "svc/anyone"}})
        assert r.status_code == 403
        problem = r.json()
        assert problem["error"] == "authority_not_defaultable"
        assert "warrant:resolve" in problem["remediation"]
