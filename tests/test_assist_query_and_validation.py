"""A question that becomes a query, and three pieces of a validator's work.

The boundary that makes both safe: the model produces a query and never a
number, and nothing here concludes a validation.
"""
from __future__ import annotations

import inspect

import pytest

from core.assist.common import AssistError
from core.assist.nlquery import (PHRASES, PROVIDER, VOCABULARY,
                                 NaturalLanguageQuery, catalogue_prompt)
from core.assist.validation_aid import (COMPARABLE_ON, DERIVED, EXACT,
                                        NOT_A_QUESTION, RETRIEVED,
                                        ValidationAssistant)
from core.authz.scope import Scope
from core.reporting.semantics import ENTITIES, SemanticLayer
from tests.conftest import URN


@pytest.fixture
def semantics(db, registry, findings, monitoring):
    return SemanticLayer(db, registry, findings=findings, monitoring=monitoring)


@pytest.fixture
def ask(semantics):
    return NaturalLanguageQuery(semantics)


class _Proposing:
    """A provider that proposes a query. The point is that it never sees rows."""

    key = "stub"
    seen = None

    def __init__(self, proposal):
        self.proposal = proposal

    def available(self):
        return None

    def propose_query(self, question, catalogue=None):
        _Proposing.seen = catalogue
        return self.proposal


# ----------------------------------------------------------- the translation
class TestAQuestionBecomesAQuery:
    def test_a_tier_is_read_as_a_comparison(self, ask, a_model):
        out = ask.translate("show me every model with tier 1")
        assert out["understood"]
        assert out["proposed"]["where"] == [
            {"field": "tier", "operator": "eq", "value": 1.0}]

    def test_a_value_before_the_field_is_still_found(self, ask, a_model):
        """'the credit domain' and 'domain is credit' are the same request, and
        a matcher reading only forwards answers the first with no filter."""
        out = ask.translate("models in the credit domain")
        assert out["proposed"]["where"][0]["value"] == "credit"

    def test_a_phrase_before_the_field_still_sets_the_operator(self, ask,
                                                               a_model):
        """Reading only forwards turns a 'greater than' into an 'equals' — a
        query that runs, returns a plausible number and answers nothing asked."""
        out = ask.translate("models with more than 2 open findings")
        assert out["proposed"]["where"][0]["operator"] == "gt"

    def test_a_quoted_value_keeps_its_case(self, ask, a_model):
        """'Critical' is a value in the register and 'critical' is not; a
        lower-cased one produces a query that matches nothing and reads as an
        answer of zero."""
        out = ask.translate("findings with severity 'Critical'")
        assert out["proposed"]["where"][0]["value"] == "Critical"

    def test_the_first_entity_named_is_the_one_answered(self, ask, a_model):
        """'how many models have more than two open findings' names both, and
        the thing being counted is the one the question opens with."""
        out = ask.translate("how many models have more than 2 open findings")
        assert out["proposed"]["entity"] == "model"
        assert "finding" in out["also_named"]

    def test_a_field_with_nothing_asked_of_it_is_not_a_filter(self, ask,
                                                              a_model):
        out = ask.translate("show me the tier")
        assert out["proposed"]["where"] == []

    def test_words_it_did_not_use_are_reported(self, ask, a_model):
        out = ask.translate("models that somebody worried about")
        assert "worried" in out["ignored"]
        assert "silently drops half a question" in out["detail"]

    def test_an_empty_question_is_refused(self, ask):
        with pytest.raises(AssistError) as e:
            ask.translate("   ")
        assert e.value.code == "question_required"

    def test_every_phrase_maps_to_a_real_operator(self):
        from core.reporting.semantics import OPERATORS
        assert all(op in OPERATORS for _, op in PHRASES)

    def test_no_phrase_is_shadowed_by_an_earlier_shorter_one(self):
        """'at least' must not be read as 'least', and 'is not' must not be
        read as 'is'. The list is scanned in order, so a phrase containing an
        earlier one would never be reached."""
        seen = []
        for phrase, _ in PHRASES:
            assert not any(earlier in phrase for earlier in seen), phrase
            seen.append(phrase)


class TestNothingReachesTheRegisterUnvalidated:
    def test_a_proposal_naming_an_unknown_field_is_refused_not_retried(
            self, semantics, a_model):
        asker = NaturalLanguageQuery(
            semantics, provider=_Proposing({"entity": "model",
                                            "where": [{"field": "colour",
                                                       "operator": "eq",
                                                       "value": "blue"}]}))
        out = asker.ask("what colour are my models", scope=Scope())
        assert out["understood"] is False and out["result"] is None
        assert out["refusal"]["error"] == "unknown_field"
        assert "rather than retried" in out["detail"]

    def test_a_proposal_naming_an_unknown_entity_is_refused(self, semantics,
                                                           a_model):
        asker = NaturalLanguageQuery(
            semantics, provider=_Proposing({"entity": "customers"}))
        assert asker.translate("how many customers")["refusal"]["error"] \
            == "unknown_entity"

    def test_the_provider_is_told_the_catalogue_and_nothing_else(
            self, semantics, a_model):
        asker = NaturalLanguageQuery(
            semantics, provider=_Proposing({"entity": "model"}))
        asker.translate("models")
        assert "entities" in _Proposing.seen and "rows" not in _Proposing.seen

    def test_which_translator_ran_is_reported(self, semantics, a_model):
        assert NaturalLanguageQuery(semantics).translate(
            "models")["translated_by"] == VOCABULARY
        assert NaturalLanguageQuery(
            semantics, provider=_Proposing({"entity": "model"})).translate(
                "models")["translated_by"] == PROVIDER

    def test_the_prompt_a_provider_sees_is_inspectable(self, semantics):
        """A prompt nobody can read is a place an instruction lives unexamined."""
        text = catalogue_prompt(semantics.describe())
        assert "You are producing a" in text and "model (" in text


class TestTheQueryIsAlwaysShown:
    def test_the_proposal_travels_with_the_rows(self, ask, a_model):
        out = ask.ask("models with tier 1", scope=Scope())
        assert out["proposed"] and out["result"]["returned"] == 1

    def test_the_rows_are_the_registers_under_the_callers_scope(
            self, ask, registry, a_model):
        registry.register("urn:maya:model:other", "Other", "x.y", "markets",
                          "person/j.okafor", "LE-UK-01", "p")
        out = ask.ask("every model", scope=Scope(legal_entities=("LE-US-01",)))
        assert out["result"]["outside_scope"] == 1

    def test_no_number_in_the_answer_came_from_the_translator(self, ask,
                                                              a_model):
        out = ask.ask("models with tier 1", scope=Scope())
        assert "produced a query and never a number" in out["detail"]

    def test_the_vocabulary_is_published_before_anybody_asks(self, ask):
        out = ask.vocabulary()
        assert {e["entity"] for e in out["entities"]} == set(ENTITIES)
        assert out["translated_by"] == VOCABULARY


# ------------------------------------------------- assistance for a validator
@pytest.fixture
def aid(registry, findings, assumptions, monitoring):
    return ValidationAssistant(registry, findings=findings,
                               assumptions=assumptions, monitoring=monitoring)


@pytest.fixture
def assumptions(db, registry, evidence, monitoring):
    from core.assumptions.register import AssumptionRegister
    from db import AssumptionRepository
    return AssumptionRegister(AssumptionRepository(db), registry, evidence,
                              monitors=monitoring.registry)


class TestItNeverConcludes:
    def test_there_is_no_method_that_concludes(self):
        """The absence is the control, and an absence nothing checks is one
        somebody adds a method to."""
        methods = {n for n, _ in inspect.getmembers(
            ValidationAssistant, inspect.isfunction) if not n.startswith("_")}
        assert not (methods & {"conclude", "decide", "approve", "sign",
                               "validate", "record"})

    def test_no_method_takes_an_outcome(self):
        for name, fn in inspect.getmembers(ValidationAssistant,
                                           inspect.isfunction):
            params = set(inspect.signature(fn).parameters)
            assert not (params & {"outcome", "conclusion", "verdict"}), name

    def test_it_says_so_itself(self, aid):
        assert aid.describe()["never"] == "concludes"


class TestChallengeQuestionsCarryTheirProvenance:
    def test_a_finding_on_a_comparable_model_becomes_a_question(
            self, aid, registry, findings, a_model):
        peer = registry.register("urn:maya:model:peer", "Peer", "x.y", "credit",
                                 "person/j.okafor", "LE-US-01", "p")
        findings.raise_finding(peer["id"], "High", "PD calibration drifted",
                               "person/j.okafor")
        out = aid.challenge_questions(URN)
        assert out["questions"][0]["from_model"] == "urn:maya:model:peer"
        assert out["questions"][0]["from_finding"]
        assert "domain" in out["questions"][0]["comparable_on"]

    def test_nothing_is_invented(self, aid, registry, a_model):
        registry.register("urn:maya:model:peer", "Peer", "x.y", "credit",
                          "person/j.okafor", "LE-US-01", "p")
        out = aid.challenge_questions(URN)
        assert out["questions"] == []
        assert "fact about the challenge those models received" in out["detail"]

    def test_no_comparable_model_is_not_a_clean_bill(self, aid, registry,
                                                     a_model):
        registry.register("urn:maya:model:elsewhere", "E", "x.y", "markets",
                          "person/j.okafor", "LE-US-01", "p")
        out = aid.challenge_questions(URN)
        assert out["comparable_models"] == []
        assert "nobody else has met yet" in out["detail"]

    def test_a_finding_about_a_missed_date_is_not_a_question(
            self, aid, registry, findings, a_model):
        peer = registry.register("urn:maya:model:peer", "Peer", "x.y", "credit",
                                 "person/j.okafor", "LE-US-01", "p")
        findings.raise_finding(peer["id"], "High", "Remediation overdue: x",
                               "person/j.okafor", category="remediation_sla")
        assert aid.challenge_questions(URN)["questions"] == []
        assert "remediation_sla" in NOT_A_QUESTION

    def test_the_basis_is_labelled_derived(self, aid, a_model):
        assert aid.challenge_questions(URN)["basis"] == DERIVED

    def test_comparability_is_a_published_list(self):
        assert "domain" in COMPARABLE_ON and "trainability_class" in COMPARABLE_ON


class TestUntestedAssumptionsAreExact:
    def test_an_unmonitored_assumption_is_reported(self, aid, registry,
                                                   assumptions, a_model,
                                                   kernel_spec, contract_spec):
        registry.create_version(URN, "1.0.0", kernel_spec, contract_spec,
                                artifact_digest="sha256:" + "a" * 64)
        assumptions.record(URN, "1.0.0", "data",
                           "the book resembles the development sample",
                           basis="developer judgement", owner="person/j.okafor",
                           materiality="material")
        out = aid.untested_assumptions(URN)
        assert out["count"] == 1 and out["material_and_unmitigated"] == 1
        assert out["basis"] == EXACT

    def test_no_language_model_is_involved_and_it_says_so(self, aid, registry,
                                                          assumptions, a_model,
                                                          kernel_spec,
                                                          contract_spec):
        registry.create_version(URN, "1.0.0", kernel_spec, contract_spec,
                                artifact_digest="sha256:" + "a" * 64)
        assumptions.record(URN, "1.0.0", "data", "x", basis="b",
                           owner="person/j.okafor")
        assert "exact" in aid.untested_assumptions(URN)["detail"]

    def test_a_fully_monitored_estate_is_not_celebrated(self, aid, a_model):
        assert "rarer than it sounds" in aid.untested_assumptions()["detail"]

    def test_the_three_bases_are_distinct(self, aid):
        assert len({EXACT, RETRIEVED, DERIVED}) == 3
        assert {o["basis"] for o in aid.describe()["offers"]} == {
            EXACT, RETRIEVED, DERIVED}


class TestVendorCoverageIsRetrievalNotSummary:
    def test_without_document_search_it_refuses_rather_than_paraphrasing(
            self, aid, a_model):
        with pytest.raises(AssistError) as e:
            aid.vendor_coverage(URN)
        assert e.value.code == "no_document_search"

    def test_every_checklist_item_is_asked_about(self, registry, findings,
                                                 a_model, attachments):
        from core.docs.search import DocumentSearch
        from core.validation.vendor import CHECKLIST
        assistant = ValidationAssistant(
            registry, findings=findings,
            search=DocumentSearch(attachments, registry))
        out = assistant.vendor_coverage(URN)
        assert {i["item"] for i in out["items"]} == set(CHECKLIST)
        assert out["basis"] == RETRIEVED

    def test_it_names_the_items_no_document_mentions(self, registry, findings,
                                                     a_model, attachments):
        from core.docs.search import DocumentSearch
        assistant = ValidationAssistant(
            registry, findings=findings,
            search=DocumentSearch(attachments, registry))
        out = assistant.vendor_coverage(URN)
        assert out["no_document_mentions"]
        assert "second document that says something the vendor did not" \
            in out["detail"]
