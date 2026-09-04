"""
MAYA — machine assistance.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

The organising question is not whether the model is good enough. It is whether a
human can check the output more cheaply than producing it — because where such a
check exists an LLM can be wrong loudly and cheaply, and where it does not, it is
wrong quietly.

TestTheGroundingGate and TestAdvisoryIsNotRegistrable are the two that carry the
design. The first because rejected claims are REMOVED rather than flagged; the
second because a capability that can be neither checked nor grounded has no
business in a registry that things get wired into.
"""
import pytest

from core.assist import AssistError, grounding, oracles
from core.assist.common import TIER_A, TIER_B


@pytest.fixture
def tier_b(capabilities):
    return capabilities.register(
        "doc.draft", "Drafts model documentation sections from evidence",
        TIER_B, "claude-opus-5", "sha256:prompt-a1", "person/a.mehta")


@pytest.fixture
def tier_a(capabilities):
    return capabilities.register(
        "warrant.draft", "Drafts an execution warrant for a registered version",
        TIER_A, "claude-opus-5", "sha256:prompt-b2", "person/a.mehta",
        oracle_key="warrant.conforms")


CLAIMS = [
    {"id": "c1", "text": "The model is a T2 logistic scorecard.",
     "citations": ["ev-1"]},
    {"id": "c2", "text": "It was validated in January 2026.",
     "citations": ["ev-2", "ev-3"]},
]
KNOWN = ["ev-1", "ev-2", "ev-3"]


# ==================================================================== oracles
class TestOracles:
    def test_the_oracle_list_is_short_and_each_rests_on_something(self):
        described = oracles.describe()
        assert 3 <= len(described) <= 8, "the honest list is short"
        assert all(o["rests_on"].startswith("core.") for o in described), \
            "an oracle written specially to bless AI output is one nobody trusts"

    def test_a_registered_test_key_passes_and_an_invented_one_fails(self):
        check = oracles.get("test.registered").check
        assert check({"test_key": "discrimination.gini"}).passed is True
        assert check({"test_key": "discrimination.vibes"}).passed is False

    def test_citation_soundness_is_boolean(self):
        check = oracles.get("citations.resolve").check
        assert check({"citations": ["a"], "known_evidence": ["a", "b"]}).passed
        assert not check({"citations": ["z"], "known_evidence": ["a"]}).passed

    def test_citing_nothing_is_not_support(self):
        verdict = oracles.get("citations.resolve").check(
            {"citations": [], "known_evidence": ["a"]})
        assert verdict.passed is False and "nothing is supported" in verdict.detail

    def test_a_conforming_warrant_passes_its_oracle(self):
        import json, pathlib
        path = (pathlib.Path(__file__).resolve().parent.parent / "examples" /
                "warrants" / "03-gbm-pd-score.json")
        doc = json.loads(path.read_text()); doc.pop("_comment", None)
        assert oracles.get("warrant.conforms").check({"warrant": doc}).passed


# ============================================== advisory is not a platform thing
class TestAdvisoryIsNotRegistrable:
    def test_tier_c_is_refused(self, capabilities):
        with pytest.raises(AssistError) as exc:
            capabilities.register("hunch", "summarises things", "C",
                                  "claude-opus-5", "sha256:x", "person/o")
        assert exc.value.code == "advisory_not_registrable"
        assert "chat window" in exc.value.detail
        assert "Tier A" in exc.value.remediation and "Tier B" in exc.value.remediation

    def test_tier_a_must_name_its_oracle(self, capabilities):
        """'We validate the output' without naming the check is the sentence
        that precedes every AI incident."""
        with pytest.raises(AssistError) as exc:
            capabilities.register("x", "does things", TIER_A, "claude-opus-5",
                                  "sha256:x", "person/o")
        assert exc.value.code == "oracle_required"
        assert "name the check" in exc.value.detail

    def test_an_unknown_oracle_is_refused_with_the_real_ones(self, capabilities):
        with pytest.raises(AssistError) as exc:
            capabilities.register("x", "does things", TIER_A, "claude-opus-5",
                                  "sha256:x", "person/o", oracle_key="vibes.check")
        assert "warrant.conforms" in exc.value.remediation

    def test_tier_b_needs_no_oracle(self, tier_b):
        assert tier_b["tier"] == TIER_B and tier_b["oracle_key"] is None

    def test_duplicate_capability_keys_are_refused(self, capabilities, tier_b):
        with pytest.raises(AssistError, match="already registered"):
            capabilities.register("doc.draft", "again", TIER_B, "m", "d", "o")


# =========================================================== the grounding gate
class TestTheGroundingGate:
    def test_supported_claims_are_kept(self):
        kept, rejected = grounding.gate(CLAIMS, KNOWN)
        assert len(kept) == 2 and rejected == []

    def test_a_claim_citing_nothing_is_rejected(self):
        """Uncited prose in a governance document is exactly what this stops,
        however true it happens to be."""
        kept, rejected = grounding.gate(
            [{"id": "c", "text": "The model is excellent.", "citations": []}], KNOWN)
        assert kept == [] and rejected[0]["reason"].startswith("the claim cites nothing")

    def test_a_claim_citing_something_that_does_not_exist_is_rejected(self):
        kept, rejected = grounding.gate(
            [{"id": "c", "text": "It was approved.", "citations": ["ev-99"]}], KNOWN)
        assert kept == []
        assert "do not resolve" in rejected[0]["reason"] and "ev-99" in rejected[0]["reason"]

    def test_rejected_claims_are_removed_from_the_output_not_flagged(self):
        """A document where unsupported sentences are marked is a document where
        the marks get skimmed past."""
        claims = CLAIMS + [{"id": "c3", "text": "It is the best model in the bank.",
                            "citations": ["ev-99"]}]
        kept, rejected = grounding.gate(claims, KNOWN)
        text = grounding.assemble(kept)
        assert "best model in the bank" not in text
        assert len(rejected) == 1

    def test_the_rejected_list_is_kept_for_the_reviewer(self):
        """It is the list of places the model was making things up."""
        _, rejected = grounding.gate(
            CLAIMS + [{"id": "c3", "text": "Invented.", "citations": []}], KNOWN)
        assert rejected[0]["text"] == "Invented."

    def test_the_report_counts_what_survived(self):
        kept, rejected = grounding.gate(
            CLAIMS + [{"id": "c3", "text": "x", "citations": []}], KNOWN)
        report = grounding.report(kept, rejected)
        assert report["claims"] == 3 and report["grounded"] == 2
        assert report["passed"] is False
        assert "removed from the output" in report["detail"]


# ================================================================= generations
class TestGenerations:
    def test_a_grounded_generation_is_recorded_as_a_draft(self, generations, tier_b):
        g = generations.record("doc.draft", "model", "m-1", CLAIMS, KNOWN,
                               actor="a.mehta")
        assert g["state"] == "drafted"
        assert g["output"]["grounding"]["grounded"] == 2

    def test_a_generation_with_nothing_grounded_is_refused_outright(
            self, generations, tier_b):
        with pytest.raises(AssistError) as exc:
            generations.record("doc.draft", "model", "m-1",
                               [{"id": "c", "text": "x", "citations": []}], KNOWN)
        assert exc.value.code == "nothing_grounded"

    def test_a_tier_a_generation_is_refused_when_its_oracle_fails(
            self, generations, tier_a):
        """The check is the control; nothing is recorded when it fails."""
        with pytest.raises(AssistError) as exc:
            generations.record("warrant.draft", "version", "v-1", CLAIMS, KNOWN,
                               oracle_payload={"warrant": {"maya_warrant": "1.0"}})
        assert exc.value.code == "oracle_failed"
        assert "nothing is recorded when it fails" in exc.value.remediation

    def test_a_tier_a_generation_passing_its_oracle_is_recorded(
            self, generations, tier_a):
        import json, pathlib
        path = (pathlib.Path(__file__).resolve().parent.parent / "examples" /
                "warrants" / "03-gbm-pd-score.json")
        doc = json.loads(path.read_text()); doc.pop("_comment", None)
        g = generations.record("warrant.draft", "version", "v-1", CLAIMS, KNOWN,
                               oracle_payload={"warrant": doc})
        assert g["oracle_verdict"]["passed"] is True

    def test_a_suspended_capability_cannot_generate(self, generations, capabilities,
                                                    tier_b):
        capabilities.suspend("doc.draft", "prompt regression")
        with pytest.raises(AssistError, match="suspended"):
            generations.record("doc.draft", "model", "m-1", CLAIMS, KNOWN)


# ================================================================= attestation
class TestAttestation:
    @pytest.fixture
    def drafted(self, generations, tier_b):
        return generations.record("doc.draft", "model", "m-1", CLAIMS, KNOWN,
                                  actor="d.raman")

    def test_a_draft_carries_no_weight_until_attested(self, drafted):
        assert drafted["state"] == "drafted"
        assert drafted["attested_by"] is None

    def test_a_person_takes_responsibility_for_it(self, generations, drafted):
        done = generations.attest(drafted["id"], "a.mehta",
                                  final_text="The model is a T2 logistic scorecard.")
        assert done["state"] == "attested" and done["attested_by"] == "a.mehta"

    def test_whoever_asked_for_it_cannot_attest_it(self, generations, drafted):
        with pytest.raises(AssistError) as exc:
            generations.attest(drafted["id"], "d.raman")
        assert exc.value.code == "self_attestation"
        assert "taking responsibility for machine output" in exc.value.remediation

    def test_it_can_be_rejected(self, generations, drafted):
        done = generations.attest(drafted["id"], "a.mehta", accept=False,
                                  note="conclusions do not follow")
        assert done["state"] == "rejected"

    def test_deciding_twice_is_refused(self, generations, drafted):
        generations.attest(drafted["id"], "a.mehta")
        with pytest.raises(AssistError, match="already"):
            generations.attest(drafted["id"], "s.iqbal")

    def test_edit_distance_records_how_much_was_changed(self, generations):
        assert generations.edit_distance("a b c d", "a b c d") == 0.0
        assert generations.edit_distance("a b c d", "w x y z") == 1.0
        assert 0.0 < generations.edit_distance("a b c d", "a b y z") < 1.0


# ============================================================ automation bias
class TestAutomationBias:
    """A reviewer who has approved forty correct drafts is not reviewing the
    forty-first, and no amount of telling them to will change that."""

    def _attest_series(self, generations, tier_b, distances):
        for i, d in enumerate(distances):
            g = generations.record("doc.draft", "model", f"m-{i}", CLAIMS, KNOWN,
                                   actor="system")
            generations.generations.set(
                {"state": "attested", "attested_by": "a.mehta",
                 "edit_distance": d}, id=g["id"])

    def test_too_few_attestations_is_not_a_trend(self, generations, tier_b):
        self._attest_series(generations, tier_b, [0.4, 0.3])
        assert generations.automation_bias("a.mehta")["known"] is False

    def test_a_falling_edit_distance_is_flagged(self, generations, tier_b):
        self._attest_series(generations, tier_b, [0.5, 0.45, 0.05, 0.02])
        report = generations.automation_bias("a.mehta")
        assert report["falling"] is True
        assert "may have stopped reading" in report["detail"]

    def test_a_steady_reviewer_is_not_flagged(self, generations, tier_b):
        self._attest_series(generations, tier_b, [0.30, 0.28, 0.31, 0.29])
        assert generations.automation_bias("a.mehta")["falling"] is False
