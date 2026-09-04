"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Asking a model, and refusing to believe the answer.

The generation log could always gate a draft. Nothing ever asked for one, so
every control around it -- the oracle, the grounding gate, attestation, the
automation-bias sample -- had only ever been exercised against claims a test
wrote by hand. These run the real path with a provider at the end of it.
"""
from __future__ import annotations

import pytest

from core.assist import AssistError, DraftingService, providers


@pytest.fixture
def subject(evidence):
    """Three evidence nodes about one model, which is what a draft may cite."""
    for kind, payload in (("model_registered", {"name": "SB PD"}),
                          ("risk_assessed", {"tier": 1}),
                          ("version_approved", {"semver": "3.2.1"})):
        evidence.append(kind, "model", "m-1", payload, actor="person/j.okafor")
    return "m-1"


@pytest.fixture
def capability(capabilities):
    return capabilities.register(
        "validation_summary", "Draft a validation summary from the record",
        "B", "mock-1", "sha256:prompt", "person/a.mehta",
        review_sample=0.0)


@pytest.fixture
def drafting(generations, capabilities, evidence):
    return DraftingService(generations, capabilities, evidence,
                           providers.build("mock"))


class TestTheProviderPort:
    def test_one_provider_works_and_the_rest_refuse_by_name(self):
        """A stub returning plausible prose into a governance register is worse
        than no provider: the first reader has no way to tell."""
        rows = {r["provider"]: r for r in providers.describe()}
        assert rows["mock"]["usable"] is True
        for key in ("anthropic", "openai", "self_hosted"):
            assert rows[key]["usable"] is False
            assert rows[key]["why_not"], f"{key} refuses without saying why"

    def test_an_unwired_provider_raises_rather_than_returning_something(self):
        with pytest.raises(AssistError) as exc:
            providers.build("anthropic").draft("draft it", base_model="claude")
        assert exc.value.code == "provider_unavailable"
        assert exc.value.remediation

    def test_an_unknown_provider_names_the_ones_that_exist(self):
        with pytest.raises(AssistError) as exc:
            providers.build("wishful")
        assert exc.value.code == "unknown_provider"
        assert "mock" in exc.value.remediation

    def test_the_mock_is_deterministic(self):
        """A mock that varied would make every test touching it flaky, and a
        demonstration nobody could repeat would demonstrate nothing."""
        a = providers.build("mock").draft("same prompt", base_model="m",
                                          evidence_ids=("e1", "e2"), context={})
        b = providers.build("mock").draft("same prompt", base_model="m",
                                          evidence_ids=("e1", "e2"), context={})
        assert a.claims == b.claims and a.text == b.text


class TestDraftingRunsTheRealGate:
    def test_a_draft_is_grounded_in_the_record_and_lands_drafted(
            self, drafting, capability, subject):
        out = drafting.draft("validation_summary", "model", subject,
                             actor="person/a.mehta")
        assert out["state"] == "drafted", "a draft is never evidence yet"
        assert len(out["claims"]) == 3
        assert out["output"]["grounding"]["rejected"] == 0

    def test_what_the_model_may_cite_is_fixed_before_it_is_asked(
            self, drafting, capability, subject, evidence):
        """The bound that makes the rest safe. A provider cannot introduce a
        fact, only a candidate that has to land on evidence already held."""
        known = {n["id"] for n in evidence.for_subject(subject)}
        out = drafting.draft("validation_summary", "model", subject,
                             actor="person/a.mehta")
        for claim in out["claims"]:
            assert set(claim["citations"]) <= known

    def test_a_fabricated_citation_is_dropped_before_anybody_reads_it(
            self, generations, capabilities, evidence, capability, subject):
        """The control that actually matters. A provider that only ever cited
        real evidence would leave this untested, and the first ungrounded claim
        anybody saw would be in production."""
        liar = DraftingService(generations, capabilities, evidence,
                               providers.build("mock", fabricate=True))
        out = liar.draft("validation_summary", "model", subject,
                         actor="person/a.mehta")
        assert out["output"]["grounding"]["rejected"] == 1
        assert len(out["claims"]) == 3, "only the grounded claims survive"
        assert len(out["rejected_claims"]) == 1
        # And the fabrication is nowhere in what a reader is shown.
        assert "not in the record" not in out["output"]["text"]

    def test_the_provider_prose_is_kept_but_is_not_the_answer(
            self, generations, capabilities, evidence, capability, subject):
        """What a reader sees is assembled from claims that survived, so the
        rejected sentence is on the record without being in the output."""
        liar = DraftingService(generations, capabilities, evidence,
                               providers.build("mock", fabricate=True))
        out = liar.draft("validation_summary", "model", subject,
                         actor="person/a.mehta")
        assert "not in the record" in out["output"]["as_drafted"]

    def test_a_subject_with_no_record_is_refused(self, drafting, capability):
        with pytest.raises(AssistError) as exc:
            drafting.draft("validation_summary", "model", "never-heard-of-it",
                           actor="person/a.mehta")
        assert exc.value.code == "nothing_to_ground"

    def test_the_prompt_is_recorded_by_digest(self, drafting, capability,
                                              subject):
        """'What was it asked' needs an answer that survives the model moving
        on, and the prompt itself is too large to keep in the row."""
        out = drafting.draft("validation_summary", "model", subject,
                             actor="person/a.mehta")
        assert out["output"]["prompt_digest"].startswith("sha256:")

    def test_a_suspended_capability_cannot_draft(self, drafting, capabilities,
                                                 capability, subject):
        capabilities.suspend("validation_summary", "under review",
                             actor="person/s.iqbal")
        with pytest.raises(AssistError) as exc:
            drafting.draft("validation_summary", "model", subject,
                           actor="person/a.mehta")
        assert exc.value.code == "capability_inactive"

    def test_a_draft_still_needs_a_person_to_attest_it(self, drafting,
                                                       generations, capability,
                                                       subject):
        """The machine drafts; a person signs. Nothing about adding a provider
        changes which of those two is the control."""
        out = drafting.draft("validation_summary", "model", subject,
                             actor="person/a.mehta")
        attested = generations.attest(out["id"], "person/s.iqbal",
                                      final_text=out["output"]["text"])
        assert attested["state"] == "attested"
        assert attested["attested_by"] == "person/s.iqbal"
