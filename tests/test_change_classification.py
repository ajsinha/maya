"""Whether a proposed change is material, decided from what actually changed.

Every institution has this rule and almost none can apply it consistently,
because "material" is asked of a person looking at a pull request who has an
opinion about how much work revalidation is. The answer drifts toward
non-material over a career.
"""
from __future__ import annotations

import pytest

from core.lifecycle.changes import (CLASS_CHANGE, MATERIAL, NON_MATERIAL,
                                    VERDICTS, classify)


def _version(**over):
    base = {"trainability_class": "T2", "runtime": "formula",
            "input_schema": [{"name": "dscr"}, {"name": "turnover"}],
            "output_schema": [{"name": "pd_12m"}],
            "contract": {"assumptions": [{"key": "dscr", "minimum": -5,
                                          "maximum": 20}],
                         "guarantees": [{"key": "pd_12m", "minimum": 0,
                                         "maximum": 1}]},
            "artifact_digest": None}
    return {**base, **over}


class TestNothingChanged:
    def test_an_identical_version_is_non_material(self):
        out = classify(_version(), _version())
        assert out["verdict"] == NON_MATERIAL
        assert out["triggers_revalidation"] is False
        assert "still covers it" in out["detail"]


class TestTheThirdVerdict:
    """Material and non-material are the requirement's words. `class_change` is
    the one it does not have and needs."""

    def test_a_changed_parameter_kind_is_not_merely_material(self):
        out = classify(_version(trainability_class="T2"),
                       _version(trainability_class="T3"))
        assert out["verdict"] == CLASS_CHANGE
        assert out["triggers_revalidation"] is False, \
            "the answer is a separate registration, not a heavier review"
        assert "different model" in out["means"]

    def test_it_outranks_a_material_change_found_alongside_it(self):
        out = classify(_version(trainability_class="T2"),
                       _version(trainability_class="T3",
                                output_schema=[{"name": "something_else"}]))
        assert out["verdict"] == CLASS_CHANGE
        assert "review of the wrong thing" in out["detail"]


class TestSchemas:
    def test_adding_a_regressor_is_material(self):
        out = classify(_version(),
                       _version(input_schema=[{"name": "dscr"},
                                              {"name": "turnover"},
                                              {"name": "sector"}]))
        assert out["verdict"] == MATERIAL
        reason = next(r for r in out["reasons"] if "added" in r["what"])
        assert "not a data change" in reason["why"]

    def test_removing_an_input_is_material_and_says_why_contravariance_matters(self):
        out = classify(_version(), _version(input_schema=[{"name": "dscr"}]))
        reason = next(r for r in out["reasons"] if "removed" in r["what"])
        assert "contravariant" in reason["why"]

    def test_changing_the_output_is_material(self):
        out = classify(_version(), _version(output_schema=[{"name": "pd_24m"}]))
        assert out["verdict"] == MATERIAL
        assert any("covariant" in r["why"] for r in out["reasons"])


class TestTheContract:
    """Both directions are material, and for opposite reasons — which is why
    they are reported as two things rather than 'the contract changed'."""

    def test_widening_a_bound_is_material(self):
        out = classify(_version(),
                       _version(contract={"assumptions": [
                           {"key": "dscr", "minimum": -50, "maximum": 200}]}))
        assert out["verdict"] == MATERIAL
        assert any("opposite reasons" in r["why"] for r in out["reasons"])

    def test_narrowing_a_bound_is_also_material(self):
        out = classify(_version(),
                       _version(contract={"assumptions": [
                           {"key": "dscr", "minimum": 0, "maximum": 1}]}))
        assert out["verdict"] == MATERIAL

    def test_removing_a_bound_says_what_it_was_for(self):
        out = classify(_version(), _version(contract={}))
        reason = next(r for r in out["reasons"] if "removed" in r["what"])
        assert "the reason it was safe to" in reason["why"]

    def test_adding_a_bound_is_material_because_it_refuses_old_calls(self):
        out = classify(_version(contract={}), _version())
        assert out["verdict"] == MATERIAL
        assert any("used to be answered" in r["why"] for r in out["reasons"])


class TestTheArtifact:
    def test_different_bytes_are_a_different_model(self):
        out = classify(_version(artifact_digest="sha256:" + "a" * 64),
                       _version(artifact_digest="sha256:" + "b" * 64))
        assert out["verdict"] == MATERIAL
        reason = next(r for r in out["reasons"] if "artifact" in r["what"])
        assert "no description distinguishes" in reason["why"]

    def test_gaining_an_artifact_where_there_was_none_is_material(self):
        out = classify(_version(),
                       _version(artifact_digest="sha256:" + "a" * 64))
        assert out["verdict"] == MATERIAL


class TestTheOverride:
    """A classifier somebody may override is the right design; an override with
    no reason and no author is how the rule stops existing."""

    @pytest.fixture
    def classifier(self, registry, evidence):
        from core.lifecycle.changes import ChangeClassifier
        from tests.conftest import URN

        kernel = {"parameter_kind": "estimated_coefficients",
                  "fit_procedure": "estimate", "runtime": "formula",
                  "entry": {"expression": "a * dscr", "target": "pd_12m"},
                  "input_schema": [{"name": "dscr", "dtype": "numeric"}],
                  "parameter_schema": [{"name": "a", "dtype": "numeric"}],
                  "output_schema": [{"name": "pd_12m", "dtype": "numeric"}]}
        registry.register(URN, "SB PD", "credit.pd", "credit", "person/o",
                          "LE-US-01", "p")
        registry.create_version(URN, "1.0.0", dict(kernel), {})
        registry.create_version(URN, "1.1.0", dict(kernel), {})
        return ChangeClassifier(registry, evidence), URN

    def test_an_override_keeps_both_answers(self, classifier):
        classify_, urn = classifier
        out = classify_.override(urn, "1.0.0", "1.1.0", MATERIAL,
                                 "the change is technically nothing, but this "
                                 "model now feeds a regulatory submission")
        assert out["computed_verdict"] == NON_MATERIAL
        assert out["verdict"] == MATERIAL and out["overridden"] is True
        assert out["triggers_revalidation"] is True

    def test_an_override_without_a_reason_is_refused(self, classifier):
        classify_, urn = classifier
        from core.registry.common import RegistryError
        with pytest.raises(RegistryError) as exc:
            classify_.override(urn, "1.0.0", "1.1.0", MATERIAL, "  ")
        assert "did not want to revalidate" in str(exc.value)

    def test_an_unknown_verdict_is_refused(self, classifier):
        classify_, urn = classifier
        from core.registry.common import RegistryError
        with pytest.raises(RegistryError, match="the three are"):
            classify_.override(urn, "1.0.0", "1.1.0", "probably fine", "r")

    def test_the_override_is_on_the_evidence_chain(self, classifier, evidence,
                                                   registry):
        classify_, urn = classifier
        classify_.override(urn, "1.0.0", "1.1.0", MATERIAL, "it feeds a return")
        model = registry.require(urn)
        entries = [e for e in evidence.for_subjects([model["id"]])
                   if e["kind"] == "change_classified"]
        assert entries
        payload = entries[-1]["payload"]
        assert payload["computed"] == NON_MATERIAL
        assert payload["recorded"] == MATERIAL and payload["overridden"] is True

    def test_agreeing_with_the_classifier_is_not_an_override(self, classifier):
        classify_, urn = classifier
        out = classify_.override(urn, "1.0.0", "1.1.0", NON_MATERIAL,
                                 "reviewed and agreed")
        assert out["overridden"] is False


class TestTheVocabulary:
    def test_there_are_three_verdicts_and_each_means_something_different(self):
        from core.lifecycle.changes import VERDICT_MEANING
        assert set(VERDICTS) == set(VERDICT_MEANING)
        assert len({VERDICT_MEANING[v] for v in VERDICTS}) == 3
