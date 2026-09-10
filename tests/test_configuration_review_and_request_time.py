"""The platform configuring itself, a document under review, and the inputs the
caller brings.

Three failure modes: a gate changed by a pull request, a compiled document
edited into untraceability, and an assurance gap nobody declared.
"""
from __future__ import annotations

import pytest

from core.docs.common import DocumentError
from core.docs.review import ASKS, NEEDS_SOMEBODY_ELSE, DocumentReview
from core.features.common import FeatureError
from core.features.request_time import GUARANTEES, RequestTimeInputs
from core.platform.configuration import (CONFIGURABLE, FORMAT, LOOSENS,
                                         NOT_CONFIGURABLE, TIGHTENS,
                                         Configuration, ConfigurationError)
from tests.conftest import URN


# ------------------------------------------------------------ configuration
@pytest.fixture
def configuration(evidence, policies, appetite, registry):
    return Configuration(evidence, policies=policies, appetite=appetite,
                         registry=registry)


@pytest.fixture
def appetite(db, evidence):
    from core.reporting.appetite import AppetiteRegister
    from db import RiskAppetiteRepository
    return AppetiteRegister(RiskAppetiteRepository(db), evidence)


class TestTheLineDoesNotMove:
    def test_what_is_code_is_published_with_its_reason(self):
        out = Configuration.boundary()
        keys = {r["section"] for r in out["not_configurable"]}
        assert "lifecycle_states" in keys and "tier_lattice" in keys
        assert all(r["why"].strip() for r in out["not_configurable"])

    def test_exporting_something_that_is_code_is_refused(self, configuration):
        with pytest.raises(ConfigurationError) as e:
            configuration.export(sections=["lifecycle_states"])
        assert e.value.code == "not_configurable"
        assert "the argument is what the platform is" in e.value.remediation

    def test_the_two_lists_do_not_overlap(self):
        assert not (set(CONFIGURABLE) & set(NOT_CONFIGURABLE))

    def test_it_says_why_naive_config_as_code_defeats_a_platform(self):
        assert "whoever is on shift" in Configuration.boundary()["detail"]

    def test_export_reads_the_registers_not_a_file(self, configuration):
        out = configuration.export()
        assert out["read_from"] == "the registers in force, never a file"
        assert "somebody's intentions" in out["detail"]


class TestAPlanSeparatesLooseningFromTightening:
    def test_a_matching_document_is_a_no_op(self, configuration):
        current = configuration.export(sections=["appetite"])
        out = configuration.plan({"format": FORMAT,
                                  "configuration": current["configuration"]})
        assert out["count"] == 0
        assert "a no-op plan is the only proof" in out["detail"]

    def test_a_raised_limit_loosens(self, configuration, appetite, evidence):
        appetite.declare(metric="blocking_findings", limit=5.0,
                         rationale="the board's tolerance",
                         actor="person/s.iqbal")
        out = configuration.plan({"format": FORMAT, "configuration": {
            "appetite": [{"metric": "blocking_findings", "limit": 50.0,
                          "amber": None, "scope": {},
                          "rationale": "the board's tolerance"}]}})
        assert out["loosens"] and out["loosens"][0]["direction"] == LOOSENS
        assert "let something through that is refused today" in out["detail"]

    def test_a_lowered_limit_tightens(self, configuration, appetite):
        appetite.declare(metric="blocking_findings", limit=50.0,
                         rationale="r", actor="person/s.iqbal")
        out = configuration.plan({"format": FORMAT, "configuration": {
            "appetite": [{"metric": "blocking_findings", "limit": 5.0,
                          "amber": None, "scope": {}, "rationale": "r"}]}})
        assert out["tightens"] and out["tightens"][0]["direction"] == TIGHTENS

    def test_a_direction_it_cannot_read_is_neutral_not_guessed(self,
                                                               configuration,
                                                               appetite):
        appetite.declare(metric="blocking_findings", limit=5.0,
                         rationale="r", actor="person/s.iqbal")
        out = configuration.plan({"format": FORMAT, "configuration": {
            "appetite": [{"metric": "blocking_findings", "limit": 5.0,
                          "amber": None, "scope": {},
                          "rationale": "a different reason"}]}})
        assert out["changes"][0]["direction"] == "neutral"

    def test_an_unknown_format_is_refused(self, configuration):
        with pytest.raises(ConfigurationError) as e:
            configuration.plan({"format": "terraform",
                                "configuration": {"appetite": []}})
        assert e.value.code == "unknown_format"

    def test_an_empty_configuration_is_refused(self, configuration):
        with pytest.raises(ConfigurationError) as e:
            configuration.plan({"format": FORMAT, "configuration": {}})
        assert e.value.code == "empty_configuration"
        assert "would look like a successful no-op" in e.value.remediation


class TestApplyingIsAGovernanceAct:
    def test_a_loosening_plan_needs_a_named_approver(self, configuration,
                                                     appetite):
        appetite.declare(metric="blocking_findings", limit=5.0,
                         rationale="r", actor="person/s.iqbal")
        with pytest.raises(ConfigurationError) as e:
            configuration.apply({"format": FORMAT, "configuration": {
                "appetite": [{"metric": "blocking_findings",
                              "limit": 50.0, "amber": None, "scope": {},
                              "rationale": "r"}]}}, rationale="widening")
        assert e.value.code == "loosening_needs_an_approver"
        assert "travel in the same pull request" in e.value.remediation

    def test_a_tightening_plan_does_not(self, configuration, appetite):
        appetite.declare(metric="blocking_findings", limit=50.0,
                         rationale="r", actor="person/s.iqbal")
        out = configuration.apply({"format": FORMAT, "configuration": {
            "appetite": [{"metric": "blocking_findings", "limit": 5.0,
                          "amber": None, "scope": {}, "rationale": "r"}]}},
            rationale="tightening after the review", actor="person/s.iqbal")
        assert out["applied"] is True

    def test_it_reaches_the_evidence_chain(self, configuration, appetite,
                                           evidence):
        appetite.declare(metric="blocking_findings", limit=50.0,
                         rationale="r", actor="person/s.iqbal")
        configuration.apply({"format": FORMAT, "configuration": {
            "appetite": [{"metric": "blocking_findings", "limit": 5.0,
                          "amber": None, "scope": {}, "rationale": "r"}]}},
            rationale="tightening", actor="person/s.iqbal")
        kinds = {n["kind"] for n in evidence.for_subject("configuration")}
        assert "configuration_applied" in kinds

    def test_a_rationale_is_required(self, configuration, appetite):
        appetite.declare(metric="blocking_findings", limit=50.0,
                         rationale="r", actor="person/s.iqbal")
        with pytest.raises(ConfigurationError) as e:
            configuration.apply({"format": FORMAT, "configuration": {
                "appetite": [{"metric": "blocking_findings", "limit": 5.0,
                              "amber": None, "scope": {},
                              "rationale": "r"}]}}, rationale="  ")
        assert e.value.code == "rationale_required"

    def test_a_no_op_is_refused_rather_than_recorded(self, configuration):
        current = configuration.export(sections=["appetite"])
        with pytest.raises(ConfigurationError) as e:
            configuration.apply({"format": FORMAT,
                                 "configuration": current["configuration"]},
                                rationale="nothing")
        assert e.value.code == "nothing_to_apply"
        assert "says something happened when nothing did" in \
            e.value.remediation


# ------------------------------------------------------------ document review
@pytest.fixture
def review(db, evidence):
    from db import DocumentCommentRepository, DocumentRepository
    return DocumentReview(DocumentCommentRepository(db),
                          DocumentRepository(db), evidence)


@pytest.fixture
def a_document(db, a_model):
    from db import DocumentRepository
    repo = DocumentRepository(db)
    row = {"model_id": a_model["id"], "model_version_id": None,
           "subject_type": "model", "subject_id": a_model["id"],
           "kind": "model_development", "title": "SB PD development",
           "sections": [{"key": "purpose", "title": "Purpose"},
                        {"key": "data", "title": "Data"}],
           "citations": {}, "coverage": {}, "digest": "sha256:v1",
           "subjects": [], "evidence_head": "sha256:head", "status": "compiled",
           "compiled_at": 0.0, "compiled_by": "person/j.okafor"}
    repo.add(row)
    return repo.one(id=row["id"])


class TestACompiledDocumentIsNotEditable:
    def test_it_says_so(self, review, a_document):
        out = review.read(a_document["id"])
        assert out["editable"] is False
        assert "no longer traceable to anything" in out["detail"]

    def test_there_is_no_edit_method(self):
        import inspect
        methods = {n for n, _ in inspect.getmembers(DocumentReview,
                                                    inspect.isfunction)}
        assert not (methods & {"edit", "amend", "rewrite", "replace"})

    def test_a_comment_names_a_real_section(self, review, a_document):
        with pytest.raises(DocumentError) as e:
            review.comment(a_document["id"], section="conclusions",
                           body="wrong")
        assert e.value.code == "unknown_section"
        assert "cannot be resolved by changing anything" in e.value.remediation

    def test_the_ask_comes_from_a_closed_list(self, review, a_document):
        with pytest.raises(DocumentError) as e:
            review.comment(a_document["id"], section="purpose", body="b",
                           asks_for="please-fix")
        assert e.value.code == "unknown_ask"
        assert "makes them the same one" in e.value.remediation

    def test_every_ask_explains_what_is_owed(self):
        assert all(v.strip() for v in ASKS.values())
        assert set(NEEDS_SOMEBODY_ELSE) <= set(ASKS)


class TestCommentsAttachToADigest:
    def test_a_comment_is_on_the_version_that_was_read(self, review,
                                                       a_document, db):
        review.comment(a_document["id"], section="purpose", body="unclear",
                       asks_for="clarification", actor="person/a.mehta")
        assert review.read(a_document["id"])["open"] == 1

    def test_a_recompilation_starts_with_no_open_comments(self, review,
                                                          a_document, db):
        """A comment carried onto a recompilation is a remark about text that
        may no longer be there — and worse, one that looks answered."""
        from db import DocumentRepository
        review.comment(a_document["id"], section="purpose", body="unclear",
                       asks_for="clarification", actor="person/a.mehta")
        DocumentRepository(db).set({"digest": "sha256:v2"},
                                   id=a_document["id"])
        out = review.read(a_document["id"])
        assert out["open"] == 0
        assert out["raised_against_an_earlier_version"] == 1
        assert "one that looks answered" in out["detail"]


class TestResolvingSaysWhatWasDone:
    def test_a_resolution_is_required(self, review, a_document):
        review.comment(a_document["id"], section="purpose", body="b",
                       actor="person/a.mehta")
        comment = review.read(a_document["id"])["comments"][0]
        with pytest.raises(DocumentError) as e:
            review.resolve(comment["id"], "  ")
        assert e.value.code == "resolution_required"
        assert "the second is a legitimate resolution" in e.value.remediation

    def test_a_factual_comment_cannot_be_closed_by_its_raiser(self, review,
                                                              a_document):
        review.comment(a_document["id"], section="data",
                       body="the register does not say this",
                       asks_for="factual", actor="person/a.mehta")
        comment = review.read(a_document["id"])["comments"][0]
        with pytest.raises(DocumentError) as e:
            review.resolve(comment["id"], "fixed", actor="person/a.mehta")
        assert e.value.code == "raiser_may_not_close"
        assert "a disagreement that never happened" in e.value.remediation

    def test_a_fix_to_the_record_names_the_node(self, review, a_document,
                                                evidence):
        review.comment(a_document["id"], section="data", body="wrong",
                       asks_for="factual", actor="person/a.mehta")
        comment = review.read(a_document["id"])["comments"][0]
        review.resolve(comment["id"], "the limitation was recorded",
                       evidence_id="node-1", actor="person/j.okafor")
        node = next(n for n in evidence.for_subject(a_document["id"])
                    if n["kind"] == "document_comment_resolved")
        assert node["payload"]["changed_the_record"] is True

    def test_only_the_raiser_may_withdraw(self, review, a_document):
        review.comment(a_document["id"], section="purpose", body="b",
                       actor="person/a.mehta")
        comment = review.read(a_document["id"])["comments"][0]
        with pytest.raises(DocumentError) as e:
            review.withdraw(comment["id"], "never mind",
                            actor="person/j.okafor")
        assert e.value.code == "not_your_comment"

    def test_an_unresolved_objection_makes_a_document_contested(self, review,
                                                                a_document):
        review.comment(a_document["id"], section="data", body="I do not accept",
                       asks_for="objection", actor="person/a.mehta")
        assert a_document["id"] in review.across_the_estate()["contested"]

    def test_an_empty_register_says_what_that_means(self, review):
        assert "a review that happens in email" in \
            review.across_the_estate()["detail"]


# --------------------------------------------------------- request-time inputs
@pytest.fixture
def request_time(registry, features, a_model):
    return RequestTimeInputs(registry, features)


@pytest.fixture
def with_request_inputs(registry, a_model, kernel_spec, contract_spec):
    kernel_spec["input_schema"] = [
        {"name": "dscr", "dtype": "float", "minimum": -5, "maximum": 20},
        {"name": "requested_amount", "dtype": "float", "minimum": 0,
         "maximum": 5_000_000, "at_request": True},
        {"name": "channel", "dtype": "string", "at_request": True},
    ]
    registry.create_version(URN, "1.0.0", kernel_spec, contract_spec,
                            artifact_digest="sha256:" + "a" * 64)
    return registry


class TestTheGuaranteesStopAtTheRequest:
    def test_the_gap_is_a_published_table(self):
        assert GUARANTEES["point_in_time"]["holds"] is False
        assert GUARANTEES["bounded_at_serve"]["holds"] is True
        assert all(v["why"].strip() for v in GUARANTEES.values())

    def test_a_version_reports_which_inputs_the_caller_brings(self,
                                                              request_time,
                                                              with_request_inputs):
        out = request_time.posture(URN, "1.0.0")
        assert out["count"] == 2 and out["inputs"] == 3
        assert "the training/serving skew check is blind to them" in \
            out["detail"]

    def test_the_skew_silence_is_named(self, request_time,
                                       with_request_inputs):
        assert "reads on a screen exactly like finding no skew" in \
            request_time.posture(URN, "1.0.0")["detail"]

    def test_an_unbounded_input_is_named(self, request_time,
                                         with_request_inputs):
        out = request_time.posture(URN, "1.0.0")
        assert out["unbounded"] == ["channel"]
        assert "a caller may send anything" in out["detail"]

    def test_a_version_with_none_says_every_guarantee_applies(
            self, request_time, registry, a_model, kernel_spec, contract_spec):
        registry.create_version(URN, "2.0.0", kernel_spec, contract_spec,
                                artifact_digest="sha256:" + "b" * 64)
        assert "every guarantee it gives applies" in \
            request_time.posture(URN, "2.0.0")["detail"]


class TestTheCollisionIsRefused:
    def test_a_name_that_is_also_a_catalogued_feature(self, request_time,
                                                      registry, features,
                                                      a_model, kernel_spec,
                                                      contract_spec, sb_view):
        """The model was fitted on the stored value and would be served the
        caller's, and nothing anywhere distinguishes them."""
        kernel_spec["input_schema"] = [
            {"name": "dscr", "dtype": "float", "at_request": True}]
        registry.create_version(URN, "3.0.0", kernel_spec, contract_spec,
                                artifact_digest="sha256:" + "c" * 64)
        with pytest.raises(FeatureError) as e:
            request_time.declare(URN, "3.0.0")
        assert "looks like model degradation" in str(e.value)


class TestValidationAtServeTime:
    def test_an_in_range_payload_is_admissible(self, request_time,
                                               with_request_inputs):
        out = request_time.check(URN, "1.0.0",
                                 {"requested_amount": 250_000.0,
                                  "channel": "broker"})
        assert out["admissible"] is True

    def test_every_violation_is_named_not_the_first(self, request_time,
                                                    with_request_inputs):
        out = request_time.check(URN, "1.0.0",
                                 {"requested_amount": -1.0,
                                  "channel": "broker"})
        assert out["violations"]
        assert "told about one fixes it, retries and is told about the next" \
            in out["detail"]

    def test_a_missing_request_time_value_is_not_a_null(self, request_time,
                                                        with_request_inputs):
        out = request_time.check(URN, "1.0.0", {"channel": "broker"})
        assert out["absent"] == ["requested_amount"]
        assert "there is nothing to fall back to" in out["detail"]

    def test_an_undeclared_field_is_reported_not_refused(self, request_time,
                                                         with_request_inputs):
        out = request_time.check(URN, "1.0.0",
                                 {"requested_amount": 1.0, "channel": "b",
                                  "extra": 1})
        assert out["unexpected"] == ["extra"]
        assert "a caller who sends a superset for two models" in out["detail"]

    def test_the_estate_sorts_by_exposure(self, request_time,
                                          with_request_inputs):
        out = request_time.across_the_estate()
        assert out["count"] == 1
        assert f"{URN}@1.0.0" in out["with_unbounded_inputs"]
