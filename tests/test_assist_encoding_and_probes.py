"""Proposing an encoding, and probes over a declared domain.

Two boundaries: no predicate crosses into the regime library, and no probe is
run by the platform that proposed it.
"""
from __future__ import annotations

import pytest

from core.assist.common import AssistError
from core.assist.encoding import (AMBIGUOUS, CUES, FORBIDS, FORMS, IMPLIES,
                                  MODALS, REQUIRES, RegimeEncodingAssistant,
                                  _build)
from core.assist.probes import (AT_BOUND, INTERIOR, KINDS, MISSING, OUTSIDE,
                                THIN_BELOW, WHY, WRONG_TYPE, ProbeSets)
from core.regimes.signature import CORE_TERMS
from tests.conftest import URN

TEXT = ("A firm must ensure that every model in use has an identified owner "
        "accountable for its performance. The firm shall carry out independent "
        "validation of each model in use. Ongoing monitoring shall be performed "
        "for every model in use. A firm may not deploy a model that is a black "
        "box without recorded limitations describing its conditions of use.")


@pytest.fixture
def assistant():
    return RegimeEncodingAssistant()


class _Encoding:
    """A provider that proposes an encoding — including things it should not."""

    key = "stub"

    def __init__(self, sentences):
        self.sentences = sentences

    def available(self):
        return None

    def propose_encoding(self, text, forms=None, core_terms=None):
        return self.sentences


# --------------------------------------------------------- no code crosses
class TestNoPredicateCrossesTheBoundary:
    def test_a_proposal_carrying_an_expression_loses_it(self, assistant):
        out = assistant.propose("draft", TEXT)
        assistant.provider = _Encoding([{
            "key": "sneaky", "form": REQUIRES, "text": "t",
            "terms": ["has_owner"],
            "predicate": "lambda i: True",
            "expression": "os.system('rm -rf /')"}])
        out = assistant.propose("draft", TEXT)
        sentence = out["sentences"][0]
        assert "predicate" not in sentence and "expression" not in sentence
        assert set(sentence["discarded"]) == {"predicate", "expression"}

    def test_an_unpublished_form_is_dropped_not_interpreted(self, assistant):
        assistant.provider = _Encoding([{"key": "k", "form": "whenever",
                                         "text": "t", "terms": ["has_owner"]}])
        out = assistant.propose("draft", TEXT)
        assert out["check"]["unbuildable"] == ["k"]
        assert "a proposal, not an encoding" in out["check"]["detail"]

    def test_every_form_maps_to_a_real_constructor(self):
        for form in FORMS:
            built = _build({"key": "k", "form": form, "text": "t",
                            "terms": ["has_owner", "has_version"][
                                :1 if form == FORBIDS else 2]})
            assert built is not None, form

    def test_nothing_is_ever_activated(self, assistant):
        out = assistant.propose("draft", TEXT)
        assert out["activatable"] is False
        assert RegimeEncodingAssistant.describe()["activates"] is False
        assert "no standing to set them" in RegimeEncodingAssistant.describe()["detail"]


class TestObligationsAreReadFromModalVerbs:
    def test_a_shall_becomes_an_obligation(self, assistant):
        out = assistant.propose("draft", TEXT)
        assert out["sentences"]
        assert any("has_owner" in s["terms"] for s in out["sentences"])

    def test_a_scoped_obligation_is_an_implication_not_a_requirement(
            self, assistant):
        """Encoded flat, 'an in-scope model must have an owner' obliges every
        model in the estate — including the ones the regulation does not reach."""
        out = assistant.propose("draft", TEXT)
        assert out["sentences"][0]["form"] == IMPLIES

    def test_a_may_not_becomes_a_prohibition(self, assistant):
        out = assistant.propose("draft", TEXT)
        assert any(s["form"] == FORBIDS for s in out["sentences"])

    def test_a_cue_split_across_a_line_break_is_still_found(self, assistant):
        """Regulatory text arrives pasted out of a PDF, and about half of it
        breaks a cue across a line."""
        wrapped = ("A firm may not deploy a model that is a black\nbox without "
                   "recorded limitations describing its conditions of\nuse.")
        assert assistant.propose("draft", wrapped)["sentences"]

    def test_a_passage_with_no_modal_is_reported_unread(self, assistant):
        out = assistant.propose("draft", TEXT + " This section explains the "
                                "background to the requirements set out above.")
        assert out["unread_sentences"]
        assert "most important line in a gap analysis" in out["detail"]

    def test_every_modal_maps_to_a_published_form(self):
        assert all(form in FORMS for _, form in MODALS)

    def test_every_cue_term_is_in_the_core_vocabulary(self):
        """A cue mapping to a term nothing can evaluate would propose an
        encoding nothing could decide."""
        assert set(CUES) <= CORE_TERMS


class TestAnUncertainReadingSaysSo:
    def test_a_without_clause_is_flagged_rather_than_corrected(self, assistant):
        out = assistant.propose("draft", TEXT)
        flagged = [s for s in out["sentences"] if s["uncertain"]]
        assert flagged
        assert "forbids the thing the regulation actually requires" in \
            flagged[0]["uncertain"][0]

    def test_the_flag_reaches_the_summary(self, assistant):
        assert "flagged uncertain" in assistant.propose("draft", TEXT)["detail"]

    def test_surplus_terms_are_named_not_dropped_silently(self, assistant):
        out = assistant.propose(
            "draft", "A firm must ensure that every model in use has an "
                     "identified owner and independent validation and ongoing "
                     "monitoring and full documentation.")
        assert out["sentences"][0]["terms_dropped"]
        assert "silently dropped half an obligation" in out["detail"]

    def test_every_ambiguity_gives_a_reason(self):
        assert all(why.strip() for _, why in AMBIGUOUS)


class TestTheProposalIsCheckedBeforeAnybodyReadsIt:
    def test_the_satisfaction_condition_runs(self, assistant):
        out = assistant.propose("draft", TEXT)
        assert out["check"]["checked"] > 0

    def test_a_contradictory_proposal_is_reported_rather_than_withheld(
            self, assistant):
        assistant.provider = _Encoding([
            {"key": "a", "form": REQUIRES, "text": "t", "terms": ["has_owner"]},
            {"key": "b", "form": FORBIDS, "text": "t", "terms": ["has_owner"]}])
        out = assistant.propose("draft", TEXT)
        assert out["check"]["holds"] is False
        assert out["check"]["conflicts"]
        assert out["sentences"]           # shown, not withheld

    def test_a_term_outside_the_core_vocabulary_is_named_never_translated(
            self, assistant):
        assistant.provider = _Encoding([{"key": "k", "form": REQUIRES,
                                         "text": "t",
                                         "terms": ["board_has_discussed_it"]}])
        out = assistant.propose("draft", TEXT)
        assert out["untranslatable"] == ["board_has_discussed_it"]
        assert "expert judgement this must not make" in out["detail"]

    def test_holding_is_only_a_claim_of_self_consistency(self, assistant):
        out = assistant.propose("draft", TEXT)
        assert "far weaker claim than that it reads the regulation correctly" \
            in out["check"]["detail"]

    def test_an_empty_text_is_refused(self, assistant):
        with pytest.raises(AssistError) as e:
            assistant.propose("draft", "short")
        assert e.value.code == "text_too_short"

    def test_an_unnamed_regime_is_refused(self, assistant):
        with pytest.raises(AssistError) as e:
            assistant.propose("  ", TEXT)
        assert e.value.code == "name_required"


# ----------------------------------------------------------------- probes
@pytest.fixture
def probes(registry, a_model, kernel_spec, contract_spec):
    registry.create_version(URN, "1.0.0", kernel_spec, contract_spec,
                            artifact_digest="sha256:" + "a" * 64)
    return ProbeSets(registry)


class TestProbesAreDerivedNotSampled:
    def test_each_declared_bound_gets_three_probes(self, probes):
        out = probes.propose(URN, "1.0.0")
        at_bound = [p for p in out["probes"]
                    if p["kind"] == AT_BOUND and p["field"] == "dscr"]
        assert len(at_bound) == 2                # minimum and maximum
        assert out["by_kind"][OUTSIDE] >= 2

    def test_a_missing_value_probe_always_exists(self, probes):
        out = probes.propose(URN, "1.0.0")
        assert any(p["kind"] == MISSING for p in out["probes"])
        assert "reads as zero and another refuses" in WHY[MISSING]

    def test_a_wrong_type_probe_exists_where_a_dtype_is_declared(self, probes):
        out = probes.propose(URN, "1.0.0")
        wrong = next(p for p in out["probes"] if p["kind"] == WRONG_TYPE)
        assert not isinstance(wrong["value"], (int, float))

    def test_the_interior_is_present_and_is_not_the_point(self, probes):
        out = probes.propose(URN, "1.0.0")
        assert out["by_kind"][INTERIOR] == 1
        assert "only kind a hand-written probe set usually has" in WHY[INTERIOR]

    def test_maya_does_not_run_them(self, probes):
        out = probes.propose(URN, "1.0.0")
        assert out["runs_them"] is False
        assert "only witness to its own model's behaviour" in out["detail"]

    def test_a_version_with_no_declared_domain_is_refused(self, registry,
                                                          a_model):
        registry.create_version(
            URN, "2.0.0",
            {"parameter_kind": "estimated_coefficients",
             "fit_procedure": "estimate", "input_schema": [],
             "output_schema": [{"name": "y", "dtype": "float"}]},
            {"assumptions": [], "guarantees": [],
             "on_boundary_violation": "reject"},
            artifact_digest="sha256:" + "b" * 64)
        with pytest.raises(AssistError) as e:
            ProbeSets(registry).propose(URN, "2.0.0")
        assert e.value.code == "no_declared_domain"

    def test_every_probe_says_what_it_is_for(self, probes):
        for probe in probes.propose(URN, "1.0.0")["probes"]:
            assert probe["kind"] in KINDS and probe["why"]


class TestCoverageIsOverTheDeclaration:
    def test_the_derived_set_covers_its_own_declaration(self, probes):
        out = probes.propose(URN, "1.0.0")
        graded = probes.grade(URN, "1.0.0", out["probes"])
        assert graded["coverage"] == 1.0 and graded["thin"] is False

    def test_an_interior_only_set_is_a_deficiency_not_a_result(self, probes):
        """The failure this module exists for: ten thousand ordinary rows show
        two artifacts agreeing to six decimal places and say nothing."""
        graded = probes.grade(URN, "1.0.0",
                              [{"field": "dscr", "value": 3.0}] * 10_000)
        assert graded["thin"] and graded["deficiency"]["kind"] == "thin_probe_set"
        assert "not a result about the model" in \
            graded["deficiency"]["statement"]

    def test_the_count_of_probes_is_not_the_coverage(self, probes):
        many = probes.grade(URN, "1.0.0",
                            [{"field": "dscr", "value": 3.0}] * 10_000)
        assert many["probes"] == 10_000 and many["coverage"] < THIN_BELOW
        assert "only the first is easy to count" in many["detail"]

    def test_unexercised_constraints_are_named(self, probes):
        graded = probes.grade(URN, "1.0.0", [])
        assert "dscr.minimum" in graded["unexercised"]

    def test_the_contract_and_the_schema_are_both_read(self, probes):
        """A probe set built from one of them misses whatever lives in the
        other."""
        out = probes.propose(URN, "1.0.0")
        sources = {tuple(c["declared_in"]) for c in out["constraints"]}
        assert any("contract" in s for s in sources)
