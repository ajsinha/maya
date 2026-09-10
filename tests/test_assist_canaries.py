"""Noticing that the model moved underneath its own version string.

A capability records a `base_model` and everybody reads that string as though it
identified something. It does not: a hosted model is re-trained, quantised and
rolled forward while the string stays the same, and every piece of evidence this
platform holds about that capability's quality was gathered against the weights
it had then.
"""
from __future__ import annotations

import pytest

from core.assist import CanaryRegister, providers
from core.assist.canaries import (PROBES, REPEATS, UNFINGERPRINTABLE, measure)
from core.assist.providers.common import Draft


class Drifted:
    """The same provider after somebody rolled the weights forward."""

    key = "mock"

    def __init__(self, claims=2):
        self.claims = claims

    def available(self):
        return None

    def draft(self, prompt, *, base_model="mock-1", evidence_ids=(),
              context=None):
        return Draft(text="x" * self.claims, model=base_model, provider="mock",
                     claims=[{"text": "t", "citations": []}] * self.claims)


class Stochastic:
    """A provider that will not answer the same question the same way twice."""

    key = "mock"

    def __init__(self):
        self.n = 0

    def available(self):
        return None

    def draft(self, prompt, *, base_model="mock-1", evidence_ids=(),
              context=None):
        self.n += 1
        return Draft(text="x" * self.n, model=base_model, provider="mock",
                     claims=[])


@pytest.fixture
def capability(capabilities):
    return capabilities.register(
        "validation_summary", "Draft a validation summary from the record",
        "B", "mock-1", "sha256:prompt", "person/a.mehta", review_sample=0.1)


@pytest.fixture
def canaries(capabilities, evidence):
    return CanaryRegister(capabilities, providers.build("mock"), evidence)


class TestTakingABaseline:
    def test_a_deterministic_model_fingerprints(self, canaries, capability):
        out = canaries.take("validation_summary")
        assert out["fingerprintable"] is True
        assert out["digest"] != UNFINGERPRINTABLE
        assert set(out["stable_probes"]) == {k for k, _ in PROBES}

    def test_it_is_recorded_on_the_capability(self, canaries, capability,
                                              capabilities):
        out = canaries.take("validation_summary")
        row = capabilities.require("validation_summary")
        assert row["canary_digest"] == out["digest"]
        assert row["canary_taken_at"]
        assert set(row["canary_probes"]) == set(out["stable_probes"])

    def test_it_lands_on_the_evidence_chain(self, canaries, capability,
                                            evidence):
        canaries.take("validation_summary")
        kinds = [n["kind"] for n in evidence.for_subject(capability["id"])]
        assert "ai_canary_taken" in kinds

    def test_per_probe_digests_are_kept_not_just_the_combined_one(
            self, canaries, capability, capabilities):
        """Which probe moved is most of the diagnostic value: the refusal probe
        moving and the counting probe moving say different things."""
        canaries.take("validation_summary")
        probes = capabilities.require("validation_summary")["canary_probes"]
        assert isinstance(probes, dict) and len(probes) == len(PROBES)


class TestAStochasticModelHasNoFingerprint:
    def test_an_unstable_probe_is_excluded_by_name(self):
        measured = measure(Stochastic(), "mock-1", repeats=REPEATS)
        assert measured["fingerprintable"] is False
        assert set(measured["unstable"]) == {k for k, _ in PROBES}

    def test_a_capability_with_no_stable_probe_is_unfingerprintable(
            self, capabilities, capability, evidence):
        register = CanaryRegister(capabilities, Stochastic(), evidence)
        out = register.take("validation_summary")
        assert out["digest"] == UNFINGERPRINTABLE
        assert "cries wolf" in out["detail"] or "consume exactly the attention" \
            in out["detail"] or "attention a real change" in out["detail"]

    def test_the_check_then_says_it_can_say_nothing(self, capabilities,
                                                    capability, evidence):
        """Better than a digest that changes on every check and teaches
        everybody to ignore the alarm."""
        register = CanaryRegister(capabilities, Stochastic(), evidence)
        register.take("validation_summary")
        out = register.check("validation_summary")
        assert out["checked"] is False and out["changed"] is False
        assert "cannot be fingerprinted" in out["detail"]

    def test_only_the_stable_probes_are_asked_at_check_time(self,
                                                            capabilities,
                                                            capability,
                                                            evidence):
        """Asking the others would be comparing against a number known to be
        noise."""
        register = CanaryRegister(capabilities, providers.build("mock"),
                                  evidence)
        register.take("validation_summary")
        capabilities.capabilities.set(
            {"canary_probes": {"echo": "sha256:whatever"}},
            id=capability["id"])
        assert register.check("validation_summary")["probes"] == ["echo"]


class TestNoticingAChange:
    def test_an_unchanged_model_reads_as_unchanged(self, canaries, capability):
        canaries.take("validation_summary")
        out = canaries.check("validation_summary")
        assert out["checked"] is True and out["changed"] is False
        assert "is not proof of it" in out["detail"]

    def test_a_changed_model_is_detected_and_the_probe_named(
            self, capabilities, capability, evidence):
        canaries = CanaryRegister(capabilities, providers.build("mock"),
                                  evidence)
        canaries.take("validation_summary")
        moved = CanaryRegister(capabilities, Drifted(claims=7), evidence)
        out = moved.check("validation_summary")
        assert out["changed"] is True
        assert out["differing_probes"], "say WHICH probe moved"
        assert out["observed_digest"] != out["recorded_digest"]

    def test_it_is_a_trigger_and_not_a_verdict(self, capabilities, capability,
                                               evidence):
        canaries = CanaryRegister(capabilities, providers.build("mock"),
                                  evidence)
        canaries.take("validation_summary")
        CanaryRegister(capabilities, Drifted(claims=7),
                       evidence).check("validation_summary")
        assert capabilities.require("validation_summary")["status"] == "active"

    def test_the_review_sample_goes_back_to_one(self, capabilities, capability,
                                                evidence):
        """What "re-run the eval gate" means for a platform whose gate is a
        sampling rate. Every accepted draft and every clean sample was measured
        against weights that have apparently moved — that evidence is not
        wrong, it is about something else."""
        canaries = CanaryRegister(capabilities, providers.build("mock"),
                                  evidence)
        canaries.take("validation_summary")
        assert capabilities.require("validation_summary")["review_sample"] == 0.1
        out = CanaryRegister(capabilities, Drifted(claims=7),
                             evidence).check("validation_summary")
        assert out["review_sample_was"] == 0.1
        assert capabilities.require("validation_summary")["review_sample"] == 1.0
        assert "about something else" in out["detail"]

    def test_it_rebaselines_so_it_does_not_fire_forever(self, capabilities,
                                                        capability, evidence):
        moved = CanaryRegister(capabilities, Drifted(claims=7), evidence)
        CanaryRegister(capabilities, providers.build("mock"),
                       evidence).take("validation_summary")
        assert moved.check("validation_summary")["changed"] is True
        assert moved.check("validation_summary")["changed"] is False

    def test_the_change_lands_on_the_evidence_chain(self, capabilities,
                                                    capability, evidence):
        CanaryRegister(capabilities, providers.build("mock"),
                       evidence).take("validation_summary")
        CanaryRegister(capabilities, Drifted(claims=7),
                       evidence).check("validation_summary")
        kinds = [n["kind"] for n in evidence.for_subject(capability["id"])]
        assert "ai_base_model_changed" in kinds


class TestNoBaselineIsNotACleanBillOfHealth:
    def test_a_capability_never_baselined_says_so(self, canaries, capability):
        out = canaries.check("validation_summary")
        assert out["checked"] is False and out["changed"] is False
        assert "the absence of one" in out["detail"]

    def test_the_estate_counts_them_apart(self, canaries, capabilities,
                                          capability):
        capabilities.register("probe_generation", "Propose probes", "B",
                              "mock-1", "sha256:p2", "person/d.raman")
        canaries.take("validation_summary")
        out = canaries.across_the_estate()
        assert out["count"] == 2
        assert out["without_a_baseline"] == 1
        assert out["checked"] == 1
        assert "absence of a clean bill of health" in out["detail"]


class TestTheProbesThemselves:
    def test_they_are_boring_on_purpose(self):
        """A canary whose output is interesting is one somebody starts relying
        on for its content, and then changing it becomes a decision."""
        for _, text in PROBES:
            assert len(text) < 90

    def test_there_is_an_empty_one(self):
        """The cheapest probe there is, and the one most likely to move when a
        provider changes how it handles a degenerate input."""
        assert "" in {text for _, text in PROBES}


class TestOverHttp:
    def _capability(self, client, people):
        r = client.post("/api/v1/assist/capabilities", auth=people["s.iqbal"],
                        json={"capability_key": "validation_summary",
                              "description": "Draft a summary", "tier": "B",
                              "base_model": "mock-1",
                              "prompt_digest": "sha256:prompt",
                              "owner": "person/a.mehta", "review_sample": 0.1})
        assert r.status_code == 201, r.text
        return "validation_summary"

    def test_a_baseline_is_taken_and_checked(self, client, people):
        key = self._capability(client, people)
        took = client.post(f"/api/v1/assist/canaries/{key}",
                           auth=people["s.iqbal"])
        assert took.status_code == 201, took.text
        assert took.json()["fingerprintable"] is True

        checked = client.get(f"/api/v1/assist/canaries/{key}",
                             auth=people["d.raman"])
        assert checked.status_code == 200, checked.text
        assert checked.json()["changed"] is False

    def test_the_estate_view_is_served(self, client, people):
        self._capability(client, people)
        r = client.get("/api/v1/assist/canaries", auth=people["d.raman"])
        assert r.status_code == 200, r.text
        assert r.json()["without_a_baseline"] == 1
