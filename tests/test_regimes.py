"""
MAYA — supervisory regimes as institutions.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

Regimes do not disagree only about requirements. They disagree about what words
mean. SR 26-2 asks whether something applies quantitative theory; the EU AI Act
asks what the system is for and whether a natural person is affected. Flattening
those into one set of compliance fields is how a scope determination becomes
indefensible.

TestTheSatisfactionCondition is the one that matters. It is the check that says
truth survives translation, and it earned its place during development by
catching a real error in the SR 26-2 encoding shipped here.
"""
import pytest

from core.regimes import (CORE, REGIMES, Interpretation, RegimeEngine, RegimeError,
                          Sentence, Signature, Translation, implies, requires,
                          satisfaction_condition)

GOVERNED = {
    "has_version": True, "has_owner": True, "has_declared_purpose": True,
    "tier": 1, "domain": "credit", "has_validation": True,
    "validation_independent": True, "has_monitoring": True,
    "has_documentation": True, "has_operating_contract": True,
    "has_warrants": True, "human_in_the_loop": True,
}
BARE = {"has_version": True, "tier": 1, "domain": "credit"}


# ================================================================ signatures
class TestSignatures:
    def test_a_regime_may_only_reason_in_its_own_vocabulary(self):
        sig = Signature.of("small", {"a", "b"})
        interp = Interpretation(sig, {"a": True})
        assert interp.get("a") is True
        with pytest.raises(KeyError, match="own vocabulary"):
            interp.get("c")

    def test_the_core_vocabulary_covers_what_the_platform_can_evaluate(self):
        for term in ("has_validation", "tier", "is_attested", "has_overlays"):
            assert CORE.contains(term)

    def test_each_shipped_regime_has_its_own_vocabulary(self):
        vocabularies = {k: r["signature"].terms for k, r in REGIMES.items()}
        assert vocabularies["sr-26-2"] != vocabularies["eu-ai-act"], \
            "different regimes carve up reality differently"
        assert "affects_natural_persons" in vocabularies["eu-ai-act"]
        assert "affects_natural_persons" not in vocabularies["sr-26-2"]


# ================================================== the satisfaction condition
class TestTheSatisfactionCondition:
    """M ⊨ σ(φ) ⟺ Mod(σ)(M) ⊨ φ — truth is invariant under change of notation."""

    @pytest.mark.parametrize("key", sorted(REGIMES))
    def test_every_shipped_regime_satisfies_it(self, regimes, key):
        report = regimes.check(key)
        assert report["holds"], report["detail"]
        assert report["checked"] > 0

    @pytest.mark.parametrize("key", sorted(REGIMES))
    def test_every_regime_term_has_a_translation(self, key):
        assert REGIMES[key]["translation"].missing() == [], \
            "a term with no translation is a term nothing can decide"

    def test_a_sentence_reading_an_undeclared_term_is_caught(self):
        """The error this check found in the shipped SR 26-2 encoding."""
        sig = Signature.of("demo", {"applies", "in_scope"})
        translation = Translation(sig, {"applies": lambda s: True,
                                        "in_scope": lambda s: True})
        # declares only 'applies' but reads 'in_scope'
        sloppy = Sentence("scope", "in scope", ("applies",),
                          lambda i: i.truthy("in_scope"))
        report = satisfaction_condition(translation, [sloppy], [{}])
        assert report["holds"] is False
        assert report["failures"][0]["reason"] == \
            "the sentence reads a term it did not declare"
        assert "in_scope" in report["failures"][0]["undeclared"]

    def test_declaring_the_term_fixes_it(self):
        sig = Signature.of("demo", {"applies", "in_scope"})
        translation = Translation(sig, {"applies": lambda s: True,
                                        "in_scope": lambda s: True})
        correct = Sentence("scope", "in scope", ("applies", "in_scope"),
                           lambda i: i.truthy("in_scope"))
        assert satisfaction_condition(translation, [correct], [{}])["holds"]

    def test_an_untranslated_term_is_reported_not_crashed_on(self):
        sig = Signature.of("demo", {"a", "b"})
        translation = Translation(sig, {"a": lambda s: True})
        sentence = requires("x", "needs b", "b")
        report = satisfaction_condition(translation, [sentence], [{}])
        assert report["holds"] is False
        assert "b" in report["untranslated_terms"]
        assert "no translation for b" in report["failures"][0]["reason"]


# ================================================================= activation
class TestActivation:
    def test_a_consistent_regime_activates(self, regimes):
        result = regimes.activate("sr-26-2")
        assert result["active"] is True
        assert result["satisfaction"]["holds"] is True
        assert "sr-26-2" in regimes.active()

    def test_activation_is_recorded_as_evidence(self, regimes, evidence):
        regimes.activate("ss1-23")
        assert "regime_activated" in [n["kind"] for n in evidence.repo.many()]

    def test_an_unknown_regime_is_refused_with_the_real_ones(self, regimes):
        with pytest.raises(RegimeError) as exc:
            regimes.activate("mars-central-bank")
        assert exc.value.code == "no_regime"
        assert "sr-26-2" in exc.value.remediation

    def test_an_inconsistent_encoding_cannot_be_activated(self, evidence):
        """A regime whose truth does not survive translation would produce
        determinations nobody can defend, so it never gets switched on."""
        sig = Signature.of("broken", {"a", "b"})
        broken = {"broken": {
            "signature": sig, "title": "Broken", "authority": "nobody",
            "sentences": (Sentence("s", "reads b", ("a",),
                                   lambda i: i.truthy("b")),),
            "translation": Translation(sig, {"a": lambda s: True,
                                             "b": lambda s: True})}}
        engine = RegimeEngine(evidence, broken)
        with pytest.raises(RegimeError) as exc:
            engine.activate("broken")
        assert exc.value.code == "satisfaction_condition_failed"
        assert "cannot be defended to an examiner" in exc.value.remediation

    def test_an_incomplete_translation_cannot_be_activated(self, evidence):
        sig = Signature.of("partial", {"a", "b"})
        partial = {"partial": {
            "signature": sig, "title": "Partial", "authority": "nobody",
            "sentences": (requires("s", "needs a", "a"),),
            "translation": Translation(sig, {"a": lambda s: True})}}
        with pytest.raises(RegimeError) as exc:
            RegimeEngine(evidence, partial).activate("partial")
        assert exc.value.code == "incomplete_translation"
        assert "nothing can decide it" in exc.value.remediation


# ============================================================== determinations
class TestDeterminations:
    def test_a_fully_governed_model_satisfies_sr_26_2(self, regimes):
        verdict = regimes.determine("sr-26-2", GOVERNED)
        assert verdict["compliant"] is True
        assert verdict["unmet"] == 0

    def test_a_bare_model_does_not(self, regimes):
        verdict = regimes.determine("sr-26-2", BARE)
        assert verdict["compliant"] is False
        unmet = {o["sentence"] for o in verdict["obligations"] if not o["satisfied"]}
        assert {"owner", "challenge", "monitoring"} <= unmet

    def test_every_obligation_carries_its_citation(self, regimes):
        verdict = regimes.determine("sr-26-2", GOVERNED)
        assert all(o["citation"] for o in verdict["obligations"])

    def test_a_determination_shows_what_it_read(self, regimes):
        """'The system said so' has never been an answer."""
        verdict = regimes.determine("sr-26-2", BARE)
        unmet = next(o for o in verdict["obligations"] if not o["satisfied"])
        assert unmet["read"], "the terms the obligation read must be visible"
        assert verdict["read_as"], "the whole regime-eye view must be visible"

    def test_the_eu_act_reasons_about_people_not_materiality(self, regimes):
        """A Tier 1 model outside a person-affecting domain is not high-risk here."""
        treasury = {**GOVERNED, "domain": "treasury"}
        assert regimes.determine("eu-ai-act", treasury)["read_as"]["high_risk_use"] \
            is False
        assert regimes.determine("eu-ai-act", GOVERNED)["read_as"]["high_risk_use"] \
            is True

    def test_ss1_23_asks_about_persistent_overlays(self, regimes):
        """Principle 5 is why the overlay register exists."""
        drifting = {**GOVERNED, "has_overlays": True, "overlay_persistent": True}
        verdict = regimes.determine("ss1-23", drifting)
        unmet = {o["sentence"] for o in verdict["obligations"] if not o["satisfied"]}
        assert "adjustments" in unmet


# ============================================================== several at once
class TestSeveralRegimes:
    def test_nothing_is_determined_before_a_regime_is_activated(self, regimes):
        assert regimes.determine_all(GOVERNED)["regimes"] == []

    def test_each_regime_is_evaluated_in_its_own_terms(self, regimes):
        for key in REGIMES:
            regimes.activate(key)
        result = regimes.determine_all(GOVERNED)
        assert len(result["regimes"]) == 3
        vocabularies = [set(v["vocabulary"]) for v in result["regimes"]]
        assert vocabularies[0] != vocabularies[1], "kept apart, not merged"

    def test_disagreement_is_reported_as_a_fact_not_a_defect(self, regimes):
        """In scope for one and out for another is something somebody needs to
        know, not an inconsistency to resolve away."""
        for key in REGIMES:
            regimes.activate(key)
        partial = {**GOVERNED, "has_monitoring": False}
        result = regimes.determine_all(partial)
        assert result["disagreement"] is True
        assert "fact about the estate rather than a defect" in result["detail"]

    def test_a_fully_governed_model_agrees_across_all_three(self, regimes):
        for key in REGIMES:
            regimes.activate(key)
        result = regimes.determine_all(GOVERNED)
        assert result["disagreement"] is False
        assert len(result["compliant_under"]) == 3


# ============================================================== core projection
class TestCoreProjection:
    def test_the_platform_state_projects_onto_the_core_vocabulary(self, regimes):
        state = regimes.core_state({
            "model": {"owner": "o", "purpose": "p", "tier": 2, "domain": "credit"},
            "versions": [{"trainability_class": "T3", "parameter_kind": "learned_weights",
                          "artifact_digest": "sha256:x", "contract": {"a": 1}}],
            "validations": [{"independence": {"independent": True}}],
            "monitoring": {"monitors": 2}, "documents": [{"id": "d"}],
            "lifecycle": {"attested_at": 1.0}, "warrants": [{"id": "w"}],
            "overlays": {"active": 1, "persistent": 0},
        })
        assert state["has_owner"] and state["validation_independent"]
        assert state["is_attested"] and state["has_overlays"]
        assert state["is_opaque"] is False and state["is_generative"] is False

    def test_an_empty_state_projects_to_nothing_present(self, regimes):
        state = regimes.core_state({})
        assert not any(v for k, v in state.items()
                       if k.startswith("has_") or k.startswith("is_"))

    def test_every_projected_term_is_in_the_core_vocabulary(self, regimes):
        for term in regimes.core_state({}):
            assert CORE.contains(term), f"{term} is outside the core signature"
