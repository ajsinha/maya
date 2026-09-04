"""
MAYA — the warrant grammar.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

The claim the grammar makes is that four independent vocabularies — how the
parameter object is inhabited, how the kernel is realised, what is asked of it,
and where its data comes from — cover every model a bank runs, as a *product*
rather than a union of special cases.

TestTheShippedExamples is where that claim is actually tested: ten worked
warrants spanning QuantLib pricing and calibration, gradient boosting scored and
refitted, a regression scorecard, an LLM summariser, an agent, a vendor black
box, a spreadsheet and a VaR backtest — all validated against one grammar with
no special cases and no exemptions.
"""
import copy
import json
import pathlib

import pytest

from core.execution.grammar import (RUNTIME_ENTRY, VERBS, admissible_verbs,
                                    json_schema, validate, vocabulary)

EXAMPLES = sorted((pathlib.Path(__file__).resolve().parent.parent
                   / "examples" / "warrants").glob("*.json"))


def load(name):
    for p in EXAMPLES:
        if p.name.startswith(name):
            doc = json.loads(p.read_text())
            doc.pop("_comment", None)
            return doc
    raise AssertionError(f"no example starting {name}")


@pytest.fixture
def score_warrant():
    return load("03-gbm-pd-score")


@pytest.fixture
def fit_warrant():
    return load("04-gbm-pd-fit")


# ================================================== the claim, tested directly
class TestTheShippedExamples:
    def test_there_are_examples_across_the_model_estate(self):
        assert len(EXAMPLES) >= 10

    @pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
    def test_every_example_conforms(self, path):
        doc = json.loads(path.read_text())
        doc.pop("_comment", None)
        report = validate(doc)
        assert report.valid, report.as_dict()["detail"]

    @pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
    def test_every_example_explains_itself(self, path):
        """Each is a teaching document as well as a test fixture."""
        doc = json.loads(path.read_text())
        assert doc.get("_comment"), f"{path.name} has no explanatory comment"

    def test_the_examples_span_the_four_axes(self):
        docs = [load(p.name[:2]) for p in EXAMPLES]
        assert {d["subject"]["trainability_class"] for d in docs} >= {"T0", "T1", "T2",
                                                                     "T3", "T5", "T6", "T8"}
        assert {d["operation"]["verb"] for d in docs} >= {"score", "fit", "generate",
                                                          "backtest"}
        assert {d["realisation"]["runtime"] for d in docs} >= {
            "quantlib", "onnx", "pmml", "llm.prompt", "llm.agent", "spreadsheet",
            "descriptor_only", "python.callable"}
        bindings = {b["binding"] for d in docs for b in d["data"]["inputs"]}
        assert bindings >= {"market_data", "feature_namespace", "dataset_snapshot",
                            "document_corpus", "request", "stream"}


# ==================================================================== shape
class TestShape:
    def test_a_missing_section_is_reported_by_name(self, score_warrant):
        del score_warrant["authority"]
        report = validate(score_warrant)
        assert not report.valid
        assert any(p.path == "authority" for p in report.problems)

    def test_all_missing_sections_are_reported_at_once(self):
        report = validate({"maya_warrant": "1.0"})
        assert len(report.problems) == 10, "report the whole list, not the first"

    def test_a_wrong_grammar_version_is_refused(self, score_warrant):
        score_warrant["maya_warrant"] = "0.9"
        assert not validate(score_warrant).valid

    def test_an_unknown_verb_is_refused_and_lists_the_real_ones(self, score_warrant):
        score_warrant["operation"]["verb"] = "teleport"
        report = validate(score_warrant)
        assert "score" in report.problems[0].remediation

    def test_an_unknown_runtime_is_refused(self, score_warrant):
        score_warrant["realisation"]["runtime"] = "wishful"
        assert not validate(score_warrant).valid

    def test_a_runtime_missing_its_entry_keys_is_refused(self, score_warrant):
        score_warrant["realisation"]["entry"] = {}
        report = validate(score_warrant)
        assert not report.valid
        assert "graph" in report.problems[0].detail, "name the key that is missing"

    def test_an_unknown_binding_is_refused(self, score_warrant):
        score_warrant["data"]["inputs"][0]["binding"] = "telepathy"
        assert not validate(score_warrant).valid

    def test_a_binding_missing_its_keys_is_refused(self, score_warrant):
        del score_warrant["data"]["inputs"][0]["namespace"]
        report = validate(score_warrant)
        assert not report.valid and "namespace" in report.problems[0].detail

    def test_an_unknown_sink_is_refused(self, score_warrant):
        score_warrant["data"]["outputs"][0]["sink"] = "the_void"
        assert not validate(score_warrant).valid

    def test_score_requires_inputs(self, score_warrant):
        score_warrant["data"]["inputs"] = []
        assert not validate(score_warrant).valid


# ============================================================= admissibility
class TestAdmissibility:
    def test_a_t0_model_cannot_be_fitted(self):
        """Its parameters come from theory. There is nothing to fit."""
        doc = load("01-quantlib-swaption-price")
        doc["operation"]["verb"] = "fit"
        report = validate(doc)
        assert not report.valid
        law = next(p for p in report.problems if p.law == "L-W1")
        assert "T0" in law.detail and "nothing to fit" in law.detail
        assert "parameter_kind" in law.remediation

    def test_a_t6_black_box_cannot_be_fitted(self):
        doc = load("08-vendor-blackbox-score")
        doc["operation"]["verb"] = "fit"
        problems = validate(doc).problems
        assert any(p.law in ("L-W1", "L-W6") for p in problems)

    def test_a_t1_calibration_can_be_fitted(self):
        """Same runtime as the T0 pricer; different coordinate on another axis."""
        assert validate(load("02-quantlib-hullwhite-calibrate")).valid

    def test_admissible_verbs_exclude_fit_only_for_t0_and_t6(self):
        for klass in ("T0", "T6"):
            assert "fit" not in admissible_verbs(klass)
        for klass in ("T1", "T2", "T3", "T4", "T5", "T7", "T8"):
            assert "fit" in admissible_verbs(klass)

    def test_generate_needs_a_generative_runtime(self, score_warrant):
        score_warrant["operation"]["verb"] = "generate"
        report = validate(score_warrant)
        law = next(p for p in report.problems if p.law == "L-W2")
        assert "llm.prompt" in law.remediation

    def test_training_from_a_non_bitemporal_source_is_refused(self, fit_warrant):
        """A source that cannot be read as-of cannot be shown not to have leaked."""
        fit_warrant["data"]["inputs"][0] = {"name": "t", "binding": "delta_table",
                                            "table": "raw/applications"}
        report = validate(fit_warrant)
        law = next(p for p in report.problems if p.law == "L-W3")
        assert "point-in-time" in law.detail
        assert "dataset_snapshot" in law.remediation

    def test_training_from_a_feature_namespace_is_allowed(self, fit_warrant):
        fit_warrant["data"]["inputs"][0] = {
            "name": "t", "binding": "feature_namespace",
            "namespace": "features/customer/sb_financials/v1"}
        assert validate(fit_warrant).valid

    def test_a_fit_must_say_where_its_parameters_go(self, fit_warrant):
        fit_warrant["data"]["outputs"] = [{"name": "metrics", "sink": "evidence"}]
        report = validate(fit_warrant)
        law = next(p for p in report.problems if p.law == "L-W4")
        assert "parameter_object" in law.remediation

    def test_claiming_determinism_from_a_stochastic_runtime_needs_a_seed(self):
        doc = load("06-llm-kyc-summarise")
        doc["operation"]["determinism"] = "deterministic"
        doc["operation"]["seed"] = None
        report = validate(doc)
        law = next(p for p in report.problems if p.law == "L-W5")
        assert "not deterministic unless it is pinned" in law.detail

    def test_a_pinned_seed_makes_the_claim_admissible(self):
        doc = load("06-llm-kyc-summarise")
        doc["operation"]["determinism"] = "deterministic"
        doc["operation"]["seed"] = 42
        assert validate(doc).valid

    def test_a_backtest_without_outcomes_is_refused(self):
        doc = load("10-var-backtest")
        doc["data"]["inputs"][0].pop("labels")
        doc["data"]["inputs"][0].pop("outcome_column")
        report = validate(doc)
        law = next(p for p in report.problems if p.law == "L-W7")
        assert "compares predictions against outcomes" in law.detail

    def test_a_descriptor_only_model_can_still_be_scored(self):
        """MAYA holds the governance; the engine holds the artifact."""
        assert validate(load("08-vendor-blackbox-score")).valid


# =================================================================== schema
class TestPublishedSchema:
    def test_the_schema_covers_every_section(self):
        props = json_schema()["properties"]
        for section in ("subject", "operation", "parameters", "realisation", "data",
                        "io_contract", "constraints", "authority", "governance",
                        "signature"):
            assert section in props

    def test_the_schema_enumerates_the_vocabularies(self):
        props = json_schema()["properties"]
        assert set(props["operation"]["properties"]["verb"]["enum"]) == set(VERBS)
        assert set(props["realisation"]["properties"]["runtime"]["enum"]) == set(RUNTIME_ENTRY)

    def test_the_schema_carries_per_runtime_entry_requirements(self):
        conditionals = json_schema()["properties"]["realisation"]["allOf"]
        quantlib = next(c for c in conditionals
                        if c["if"]["properties"]["runtime"]["const"] == "quantlib")
        assert set(quantlib["then"]["properties"]["entry"]["required"]) == {
            "instrument", "pricing_engine"}

    def test_annotations_do_not_break_the_schema(self):
        """`_comment` is a note to a reader; a warrant may carry one."""
        assert "^_" in json_schema()["patternProperties"]

    def test_the_vocabulary_publishes_admissibility_per_class(self):
        v = vocabulary()
        by_class = v["admissibility"]["by_trainability_class"]
        assert "fit" not in by_class["T0"] and "fit" in by_class["T3"]
        assert v["admissibility"]["non_fittable_classes"] == ["T0", "T6"]

    def test_every_verb_is_documented(self):
        v = vocabulary()
        assert {o["verb"] for o in v["operations"]} == set(VERBS)
        assert all(o["means"] for o in v["operations"])


class TestEveryRunSaysWhichPointInPItIsAt:
    """L-W8. Training does not change the kernel; it inhabits the parameter
    object. A run that will not say which inhabitant it is using produces a
    number attributable to nothing."""

    def test_a_score_naming_no_parameter_source_is_refused(self, score_warrant):
        score_warrant["parameters"]["source"] = {"binding": "to_be_fitted"}
        report = validate(score_warrant)
        assert not report.valid
        assert any("has to run at some point" in p.detail for p in report.problems)

    def test_a_fit_cannot_also_read_its_parameters_from_the_artifact(
            self, fit_warrant):
        """A fit writes the parameter object; declaring that it reads one
        describes the wrong direction."""
        fit_warrant["parameters"]["source"] = {"binding": "artifact"}
        report = validate(fit_warrant)
        assert not report.valid
        assert any("produces the parameter object" in p.detail
                   for p in report.problems)

    def test_a_run_may_name_a_registered_parameter_set(self, score_warrant):
        score_warrant["parameters"]["source"] = {
            "binding": "parameter_set", "parameter_set": "ps_01",
            "digest": "sha256:" + "c" * 64}
        assert validate(score_warrant).valid

    def test_naming_a_parameter_set_without_a_digest_is_refused(self, score_warrant):
        score_warrant["parameters"]["source"] = {"binding": "parameter_set",
                                                 "parameter_set": "ps_01"}
        report = validate(score_warrant)
        assert not report.valid
        assert any("needs digest" in p.detail for p in report.problems)

    def test_an_unknown_binding_is_refused_with_the_list(self, score_warrant):
        score_warrant["parameters"]["source"] = {"binding": "vibes"}
        report = validate(score_warrant)
        assert not report.valid
        assert any("not a known parameter source" in p.detail
                   for p in report.problems)

    def test_a_terminal_parameter_object_binds_nothing(self, score_warrant):
        """T0 carries its constants in the kernel; there is no point to name."""
        score_warrant["parameters"] = {"kind": "none", "source": {}}
        assert validate(score_warrant).valid


class TestAFeaturesetReadForFittingIsBounded:
    """L-W9. The featureset fixes the columns; the warrant fixes the period."""

    def _fit_from_featureset(self, fit_warrant, **binding):
        doc = copy.deepcopy(fit_warrant)
        doc["data"]["inputs"] = [{"name": "training_set", "binding": "featureset",
                                  "featureset": "nj_home_core", "version": 1,
                                  **binding}]
        return doc

    def test_a_bounded_read_is_admitted(self, fit_warrant):
        doc = self._fit_from_featureset(
            fit_warrant, as_of=1767139200.0,
            window={"from": 1546300800.0, "to": 1735603200.0})
        assert validate(doc).valid

    def test_a_read_with_no_as_of_is_refused(self, fit_warrant):
        doc = self._fit_from_featureset(
            fit_warrant, window={"from": 1546300800.0, "to": 1735603200.0})
        report = validate(doc)
        assert not report.valid
        assert any("as of when it is read" in p.detail for p in report.problems)

    def test_a_read_with_no_window_is_refused(self, fit_warrant):
        doc = self._fit_from_featureset(fit_warrant, as_of=1767139200.0)
        report = validate(doc)
        assert not report.valid
        assert any("bound the period" in p.detail for p in report.problems)

    def test_a_featureset_is_a_bitemporal_binding(self):
        """So L-W3 admits training from it at all."""
        from core.execution.grammar.vocabulary import BITEMPORAL_BINDINGS
        assert "featureset" in BITEMPORAL_BINDINGS
