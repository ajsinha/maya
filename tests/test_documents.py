"""
MAYA — the document compiler.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

A model development document is the artifact a supervisor reads, and in most
banks it is the artifact that has drifted furthest from the model. Three
properties are what a compiled document has and a written one cannot:
citations that resolve, staleness that is computed rather than remembered, and
gaps that say what is absent instead of leaving a blank heading.

TestStaleness and TestGapsAreVisible are the ones that matter.
"""
import pytest

from core.docs import ANNEX_IV, KINDS, MODEL_CARD, MODEL_DEVELOPMENT, DocumentError
from core.docs.templates import TEMPLATES
from tests.conftest import URN


@pytest.fixture
def documented(compiler, registry, a_model, approved_version, lifecycle):
    return compiler.compile(MODEL_DEVELOPMENT, URN, actor="a.mehta")


# ================================================================== compiling
class TestCompiling:
    def test_a_document_is_compiled_from_the_register(self, documented):
        assert documented["kind"] == MODEL_DEVELOPMENT
        assert documented["title"].startswith("Model Development Document")
        assert documented["sections"], "a document with no sections is not a document"

    def test_it_carries_the_identity_of_the_model(self, documented):
        identity = next(s for s in documented["sections"] if s["key"] == "identity")
        assert URN in identity["body"]
        assert "person/j.okafor" in identity["body"]

    def test_it_explains_the_derived_classification(self, documented):
        section = next(s for s in documented["sections"] if s["key"] == "classification")
        assert "T2" in section["body"]
        assert "derived" in section["body"], "say that the class was not declared"

    def test_it_states_the_assumptions_the_guarantees_rest_on(self, documented):
        section = next(s for s in documented["sections"] if s["key"] == "assumptions")
        assert "dscr" in section["body"] and "gini" in section["body"]
        assert "guarantee is void" in section["body"]

    def test_every_kind_compiles(self, compiler, a_model, approved_version, lifecycle):
        for kind in KINDS:
            doc = compiler.compile(kind, URN)
            assert doc["sections"], kind

    def test_a_model_card_is_deliberately_short(self, compiler, a_model,
                                                approved_version, lifecycle):
        card = compiler.compile(MODEL_CARD, URN)
        mdd = compiler.compile(MODEL_DEVELOPMENT, URN)
        assert len(card["sections"]) < len(mdd["sections"])

    def test_an_unknown_kind_is_refused(self, compiler, a_model):
        with pytest.raises(DocumentError) as exc:
            compiler.compile("interpretive_dance", URN)
        assert exc.value.code == "unknown_document_kind"
        assert MODEL_CARD in exc.value.remediation

    def test_compilation_is_itself_recorded(self, compiler, evidence, documented):
        kinds = [n["kind"] for n in evidence.repo.many()]
        assert "document_compiled" in kinds

    def test_the_digest_covers_the_content(self, compiler, registry, a_model,
                                           approved_version, lifecycle):
        first = compiler.compile(MODEL_DEVELOPMENT, URN)
        registry.update(URN, {"description": "materially different"})
        second = compiler.compile(MODEL_DEVELOPMENT, URN)
        assert first["digest"] != second["digest"]


# ============================================================ gaps are visible
class TestGapsAreVisible:
    """A blank heading and 'nothing has been recorded' are different findings."""

    def test_an_unfilled_required_section_says_so(self, compiler, a_model,
                                                  approved_version, lifecycle):
        doc = compiler.compile(MODEL_DEVELOPMENT, URN)
        validation = next(s for s in doc["sections"] if s["key"] == "validation")
        assert validation["filled"] is False
        assert "required and could not be filled" in validation["body"]
        assert "statement about the model's evidence" in validation["body"]

    def test_coverage_counts_what_is_missing(self, compiler, a_model,
                                             approved_version, lifecycle):
        doc = compiler.compile(MODEL_DEVELOPMENT, URN)
        coverage = doc["coverage"]
        assert coverage["sections"] > coverage["filled"]
        assert "validation" in coverage["missing_required"]
        assert coverage["complete"] is False

    def test_a_document_becomes_complete_as_the_evidence_arrives(
            self, compiler, validation, findings, monitors, a_model,
            approved_version, lifecycle, features, registry, scored):
        before = compiler.compile(MODEL_DEVELOPMENT, URN)["coverage"]

        episode = validation.open(URN, "3.2.1", "initial", ["a.mehta"])
        validation.record(episode["id"], "discrimination.gini", *scored,
                          threshold={"min": 0.3})
        validation.conclude(episode["id"], "approved")
        monitors.define(a_model["id"], "psi", "score_drift", "stability.psi",
                        {"max": 0.25}, "person/j.okafor")

        after = compiler.compile(MODEL_DEVELOPMENT, URN)["coverage"]
        assert after["filled"] > before["filled"]
        assert "validation" not in after["missing_required"]

    def test_an_optional_section_reports_differently(self, compiler, a_model,
                                                     approved_version, lifecycle):
        card = compiler.compile(MODEL_CARD, URN)
        optional_gap = next(s for s in card["sections"]
                            if not s["filled"] and not s["required"])
        assert "Not applicable" in optional_gap["body"]


# =================================================================== staleness
class TestStaleness:
    """Computed from the chain, so a document cannot be stale unnoticed."""

    def test_a_fresh_document_is_not_stale(self, compiler, documented):
        report = compiler.staleness(documented["id"])
        assert report["stale"] is False
        assert "nothing has been recorded" in report["detail"]

    def test_any_governance_event_makes_it_stale(self, compiler, registry,
                                                 documented):
        registry.update(URN, {"description": "changed after compilation"})
        report = compiler.staleness(documented["id"])
        assert report["stale"] is True
        assert "model_updated" in report["kinds_since"]
        assert report["events_since"] >= 1

    def test_a_finding_makes_the_document_stale(self, compiler, findings,
                                                a_model, documented):
        findings.raise_finding(a_model["id"], "High", "Drift observed",
                               "person/j.okafor")
        assert compiler.staleness(documented["id"])["stale"] is True

    def test_recompiling_clears_staleness(self, compiler, registry, documented):
        registry.update(URN, {"description": "changed"})
        assert compiler.staleness(documented["id"])["stale"] is True
        fresh = compiler.compile(MODEL_DEVELOPMENT, URN)
        assert compiler.staleness(fresh["id"])["stale"] is False

    def test_compiling_another_document_does_not_make_this_one_stale(
            self, compiler, documented):
        """Otherwise every document would be stale the moment a second existed."""
        compiler.compile(MODEL_CARD, URN)
        assert compiler.staleness(documented["id"])["stale"] is False


# =================================================================== citations
class TestCitations:
    def test_sections_cite_the_evidence_they_rest_on(self, documented):
        assert documented["citations"], "a document resting on nothing is visible"

    def test_citations_resolve_to_real_evidence(self, compiler, documented):
        report = compiler.verify_citations(documented["id"])
        assert report["sound"] is True and report["dangling"] == []
        assert report["cited"] == len(documented["citations"])

    def test_a_dangling_citation_is_detected(self, compiler, documented):
        """Citation soundness reduces to Boolean evaluation over the graph."""
        compiler.documents.set({"citations": documented["citations"] + ["ghost"]},
                               id=documented["id"])
        report = compiler.verify_citations(documented["id"])
        assert report["sound"] is False and report["dangling"] == ["ghost"]


# ===================================================================== render
class TestRendering:
    def test_it_renders_as_markdown(self, compiler, documented):
        text = compiler.markdown(documented)
        assert text.startswith("# Model Development Document")
        assert "## Identity and ownership" in text
        assert "citations" in text and "digest" in text

    def test_every_section_appears_in_the_rendering(self, compiler, documented):
        text = compiler.markdown(documented)
        for section in documented["sections"]:
            assert f"## {section['heading']}" in text


# ================================================================== templates
class TestTemplates:
    def test_every_kind_has_a_template(self):
        assert set(TEMPLATES) == set(KINDS)

    def test_annex_iv_requires_everything_the_mdd_requires(self):
        """An Annex IV pack that omits monitoring is not an Annex IV pack."""
        mdd = {l.key for l in TEMPLATES[MODEL_DEVELOPMENT] if l.required}
        annex = {l.key for l in TEMPLATES[ANNEX_IV] if l.required}
        assert mdd <= annex

    def test_no_template_names_a_lens_twice(self):
        for kind, lenses in TEMPLATES.items():
            keys = [l.key for l in lenses]
            assert len(keys) == len(set(keys)), kind


class TestRegimeSection:
    """A compiled document states which supervisors apply. That is what an
    examiner reads it for."""

    def test_the_document_names_each_activated_regime(self, compiler, a_model,
                                                      approved_version, lifecycle):
        doc = compiler.compile(MODEL_DEVELOPMENT, URN)
        section = next(s for s in doc["sections"] if s["key"] == "regimes")
        assert section["filled"] is True
        assert "SR 26-2" in section["body"] and "EU AI Act" in section["body"]

    def test_outstanding_obligations_are_listed_with_their_citations(
            self, compiler, a_model, approved_version, lifecycle):
        doc = compiler.compile(MODEL_DEVELOPMENT, URN)
        body = next(s for s in doc["sections"] if s["key"] == "regimes")["body"]
        assert "outstanding" in body
        assert "SR 26-2 §" in body, "each unmet obligation cites its source"

    def test_it_explains_why_regimes_are_kept_apart(self, compiler, a_model,
                                                    approved_version, lifecycle):
        body = next(s for s in compiler.compile(MODEL_DEVELOPMENT, URN)["sections"]
                    if s["key"] == "regimes")["body"]
        assert "own vocabulary" in body and "indefensible" in body

    def test_an_annex_iv_pack_requires_the_regime_section(self):
        required = {l.key for l in TEMPLATES[ANNEX_IV] if l.required}
        assert "regimes" in required
