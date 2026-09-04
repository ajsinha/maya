"""
MAYA — validation episodes, conclusion rules, and reproducibility replay.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

Three rules carry the weight: a validator may not be the builder, a validation
with a failed test cannot conclude 'approved', and results are immutable once it
does conclude. The replay tests exist to check the fourth thing — that a recorded
result can be shown to be reproducible, and that "we could not check" never reads
as "we checked and it matched".
"""
import pytest

from core.validation import ValidationError
from tests.conftest import URN


@pytest.fixture
def opened(validation, a_model, approved_version):
    return validation.open(URN, "3.2.1", "initial", ["person/a.mehta"])


# ================================================================== opening
class TestOpeningAValidation:
    def test_an_episode_records_its_scope_validators_and_plan(self, validation,
                                                              a_model, approved_version):
        v = validation.open(URN, "3.2.1", "initial", ["person/a.mehta"],
                            scope=["discrimination", "calibration"],
                            plan={"sample": "2025H2 out-of-time"})
        assert v["status"] == "in_progress"
        assert v["validators"] == ["person/a.mehta"]
        assert v["scope"] == ["discrimination", "calibration"]
        assert v["plan"]["sample"] == "2025H2 out-of-time"

    def test_independence_is_attested_on_the_record(self, opened):
        assert opened["independence"]["independent"] is True
        assert "no validator built this version" in opened["independence"]["reason"]

    def test_the_builder_cannot_validate_their_own_version(self, validation, registry,
                                                           a_model, kernel_spec):
        """Effective challenge, in the only form a system can actually check."""
        registry.create_version(URN, "9.0.0", kernel_spec, actor="person/d.raman")
        registry.approve_version(URN, "9.0.0")
        with pytest.raises(ValidationError) as exc:
            validation.open(URN, "9.0.0", "initial", ["person/d.raman"])
        assert "independence failed" in str(exc.value)
        assert "person/d.raman built this version" in str(exc.value)

    def test_an_independent_validator_alongside_the_builder_is_still_refused(
            self, validation, registry, a_model, kernel_spec):
        registry.create_version(URN, "9.0.0", kernel_spec, actor="person/d.raman")
        registry.approve_version(URN, "9.0.0")
        with pytest.raises(ValidationError, match="independence failed"):
            validation.open(URN, "9.0.0", "initial",
                            ["person/a.mehta", "person/d.raman"])

    def test_a_validation_needs_at_least_one_validator(self, validation, a_model,
                                                       approved_version):
        with pytest.raises(ValidationError, match="at least one named validator"):
            validation.open(URN, "3.2.1", "initial", [])

    def test_an_unknown_kind_is_refused(self, validation, a_model, approved_version):
        with pytest.raises(ValidationError, match="unknown validation kind"):
            validation.open(URN, "3.2.1", "vibes", ["person/a.mehta"])

    def test_a_missing_version_is_refused(self, validation, a_model):
        with pytest.raises(ValidationError, match="no version 0.0.1"):
            validation.open(URN, "0.0.1", "initial", ["person/a.mehta"])

    def test_an_unregistered_model_is_refused(self, validation):
        from core.registry import RegistryError
        with pytest.raises(RegistryError):
            validation.open("maya://model/ghost", "1.0.0", "initial", ["person/a"])


# ================================================================= recording
class TestRecordingResults:
    def test_a_result_is_stored_with_its_verdict_and_digest(self, validation, opened, scored):
        r = validation.record(opened["id"], "discrimination.gini", *scored,
                              threshold={"min": 0.3})
        assert r["passed"] is True
        assert r["test_key"] == "discrimination.gini"
        assert r["digest"] and r["value"] > 0.3

    def test_a_failing_result_is_stored_rather_than_rejected(self, validation, opened, scored):
        """A validation records what it found. Refusing to store a failure is how
        a register becomes a list of successes."""
        r = validation.record(opened["id"], "discrimination.gini", *scored,
                              threshold={"min": 0.99})
        assert r["passed"] is False

    def test_results_carry_their_slice(self, validation, opened, scored):
        r = validation.record(opened["id"], "discrimination.gini", *scored,
                              threshold={"min": 0.3}, slice_={"region": "EMEA"})
        assert r["slice"] == {"region": "EMEA"}

    def test_recording_against_an_unknown_validation_is_refused(self, validation, scored):
        with pytest.raises(ValidationError, match="no validation"):
            validation.record("nope", "discrimination.gini", *scored)

    def test_results_are_immutable_once_the_episode_concludes(self, validation, opened,
                                                              scored):
        validation.record(opened["id"], "discrimination.gini", *scored, threshold={"min": 0.3})
        validation.conclude(opened["id"], "approved")
        with pytest.raises(ValidationError, match="immutable"):
            validation.record(opened["id"], "discrimination.ks", *scored)


# ================================================================ concluding
class TestConcluding:
    def test_a_clean_validation_can_be_approved(self, validation, opened, scored):
        validation.record(opened["id"], "discrimination.gini", *scored, threshold={"min": 0.3})
        v = validation.conclude(opened["id"], "approved")
        assert v["outcome"] == "approved" and v["status"] == "completed"
        assert v["completed_at"] is not None

    def test_approval_is_refused_when_a_test_failed(self, validation, opened, scored):
        validation.record(opened["id"], "discrimination.gini", *scored, threshold={"min": 0.99})
        with pytest.raises(ValidationError) as exc:
            validation.conclude(opened["id"], "approved")
        assert "cannot approve" in str(exc.value)
        assert "discrimination.gini" in str(exc.value), "name the test that failed"
        assert "approved_with_conditions" in str(exc.value), "offer the legitimate route"

    def test_a_failed_validation_may_conclude_with_conditions(self, validation, opened,
                                                              scored):
        validation.record(opened["id"], "discrimination.gini", *scored, threshold={"min": 0.99})
        v = validation.conclude(opened["id"], "approved_with_conditions",
                                ["retrain before 2027Q1", "monthly Gini reporting"])
        assert v["outcome"] == "approved_with_conditions"
        assert len(v["conditions"]) == 2

    def test_a_failed_validation_may_be_rejected(self, validation, opened, scored):
        validation.record(opened["id"], "discrimination.gini", *scored, threshold={"min": 0.99})
        assert validation.conclude(opened["id"], "rejected")["outcome"] == "rejected"

    def test_approval_is_refused_while_a_blocking_finding_is_open(
            self, validation, findings, opened, a_model, scored):
        validation.record(opened["id"], "discrimination.gini", *scored, threshold={"min": 0.3})
        findings.raise_finding(a_model["id"], "Critical", "Leakage", "person/j.okafor")
        with pytest.raises(ValidationError) as exc:
            validation.conclude(opened["id"], "approved")
        assert "blocking finding" in str(exc.value) and "Leakage" in str(exc.value)

    def test_an_unknown_outcome_is_refused(self, validation, opened):
        with pytest.raises(ValidationError, match="unknown outcome"):
            validation.conclude(opened["id"], "probably_fine")

    def test_concluding_twice_is_refused(self, validation, opened):
        validation.conclude(opened["id"], "deferred")
        with pytest.raises(ValidationError, match="already concluded"):
            validation.conclude(opened["id"], "approved")

    def test_summary_reports_what_ran_and_what_failed(self, validation, opened, scored):
        validation.record(opened["id"], "discrimination.gini", *scored, threshold={"min": 0.3})
        validation.record(opened["id"], "calibration.brier", *scored, threshold={"max": 0.01})
        s = validation.summary(opened["id"])
        assert s["tests_run"] == 2 and s["tests_failed"] == 1
        assert s["failed_keys"] == ["calibration.brier"]
        assert s["independent"] is True

    def test_validations_are_listed_per_model(self, validation, opened):
        assert [v["id"] for v in validation.for_model(URN)] == [opened["id"]]


# ==================================================================== replay
class TestReproducibilityReplay:
    @pytest.fixture
    def recorded(self, validation, opened, scored):
        validation.record(opened["id"], "discrimination.gini", *scored,
                          threshold={"min": 0.3})
        validation.record(opened["id"], "calibration.brier", *scored, threshold={"max": 1.0})
        return opened["id"]

    def test_the_same_data_reproduces_every_result(self, replayer, recorded, scored):
        report = replayer.replay(recorded, lambda key, sl: scored)
        assert report["reproducible"] is True
        assert report["reproduced"] == 2 and report["mismatched"] == []
        assert "reproduced exactly" in report["detail"]

    def test_different_data_is_caught_as_a_mismatch(self, replayer, recorded, scored):
        labels, scores = scored
        tampered = (labels, list(reversed(scores)))
        report = replayer.replay(recorded, lambda key, sl: tampered)
        assert report["reproducible"] is False
        assert len(report["mismatched"]) >= 1
        first = report["mismatched"][0]
        assert first["stored_value"] != first["replayed_value"]
        assert first["stored_digest"] != first["replayed_digest"]

    def test_data_that_cannot_be_supplied_is_skipped_not_reproduced(self, replayer,
                                                                    recorded, scored):
        """'We could not check' must never read as 'we checked and it matched'."""
        def only_gini(key, _slice):
            return scored if key == "discrimination.gini" else None
        report = replayer.replay(recorded, only_gini)
        assert report["reproducible"] is False
        assert report["reproduced"] == 1 and len(report["skipped"]) == 1
        assert report["skipped"][0]["test_key"] == "calibration.brier"
        assert "could not be checked" in report["detail"]

    def test_a_validation_with_no_results_is_not_reproducible(self, replayer, opened):
        report = replayer.replay(opened["id"], lambda key, sl: None)
        assert report["reproducible"] is False and report["total"] == 0
        assert report["detail"] == "no results to replay"
