"""
MAYA — validation episodes, the findings register, and the gates they drive.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

The register is only a control if something refuses to proceed because of it, so
the tests that matter most here are the ones asserting that an alias move and a
warrant resolution both fail while a blocking finding is open, and both recover the
moment it is properly closed.
"""
import time

import pytest

from core.execution import WarrantError, WarrantService
from core.registry import RegistryError
from core.validation import ValidationError
from tests.conftest import URN


# ============================================================== test catalogue
class TestCatalogueBehaviour:
    def test_every_registered_test_is_described(self, catalogue):
        described = {d["key"] for d in catalogue.describe()}
        assert described == set(catalogue.keys())
        assert "discrimination.gini" in described

    def test_an_unknown_test_is_refused_and_lists_what_exists(self, catalogue):
        with pytest.raises(ValidationError) as exc:
            catalogue.definition("discrimination.made_up")
        assert "discrimination.gini" in str(exc.value), "the refusal must be actionable"

    def test_misaligned_series_are_refused(self, catalogue):
        with pytest.raises(ValidationError, match="must align"):
            catalogue.run("discrimination.auc", [0, 1, 1], [0.2, 0.9])

    def test_a_minimum_threshold_passes_when_met(self, catalogue, scored):
        out = catalogue.run("discrimination.gini", *scored, {"min": 0.3})
        assert out.passed and "meets the minimum" in out.detail

    def test_a_minimum_threshold_fails_when_missed(self, catalogue, scored):
        out = catalogue.run("discrimination.gini", *scored, {"min": 0.99})
        assert not out.passed and "is below the minimum" in out.detail

    def test_a_maximum_threshold_bounds_from_above(self, catalogue, scored):
        assert catalogue.run("calibration.brier", *scored, {"max": 1.0}).passed
        assert not catalogue.run("calibration.brier", *scored, {"max": 0.0}).passed

    def test_a_target_threshold_uses_its_tolerance(self, catalogue):
        within = catalogue.run("calibration.expected_vs_actual", [0, 0, 1, 1], [0.5] * 4,
                               {"target": 1.0, "tolerance": 0.05})
        outside = catalogue.run("calibration.expected_vs_actual", [0, 0, 0, 1], [0.5] * 4,
                                {"target": 1.0, "tolerance": 0.05})
        assert within.passed and not outside.passed
        assert "outside" in outside.detail

    def test_no_threshold_records_the_measurement_and_passes(self, catalogue, scored):
        """An exploratory number should not have to invent a limit to be recorded."""
        out = catalogue.run("discrimination.ks", *scored)
        assert out.passed and "no threshold declared" in out.detail

    def test_a_threshold_declaring_no_comparison_is_refused(self, catalogue, scored):
        with pytest.raises(ValidationError, match="min.*max.*target"):
            catalogue.run("discrimination.gini", *scored, {"roughly": 0.4})

    def test_a_value_that_cannot_be_computed_does_not_pass(self, catalogue):
        """Absent evidence is not evidence of compliance."""
        out = catalogue.run("discrimination.auc", [1, 1, 1], [0.1, 0.2, 0.3], {"min": 0.5})
        assert out.value is None and not out.passed
        assert "not computable" in out.detail

    def test_a_two_sample_test_takes_reference_and_current(self, catalogue):
        out = catalogue.run("stability.psi", list(range(100)), list(range(100)), {"max": 0.1})
        assert out.passed and out.value == pytest.approx(0.0, abs=1e-9)


class TestResultDigest:
    def test_the_same_run_produces_the_same_digest(self, catalogue, scored):
        a = catalogue.run("discrimination.gini", *scored, {"min": 0.3})
        b = catalogue.run("discrimination.gini", *scored, {"min": 0.3})
        assert a.digest() == b.digest()

    def test_a_changed_value_changes_the_digest(self, catalogue, scored):
        labels, scores = scored
        a = catalogue.run("discrimination.gini", labels, scores, {"min": 0.3})
        b = catalogue.run("discrimination.gini", labels, list(reversed(scores)), {"min": 0.3})
        assert a.digest() != b.digest()

    def test_a_threshold_moved_after_the_fact_changes_the_digest(self, catalogue, scored):
        """The value is identical; only the bar moved. Replay must still catch it."""
        a = catalogue.run("discrimination.gini", *scored, {"min": 0.30})
        b = catalogue.run("discrimination.gini", *scored, {"min": 0.05})
        assert a.value == b.value and a.digest() != b.digest()

    def test_a_changed_slice_changes_the_digest(self, catalogue, scored):
        a = catalogue.run("discrimination.gini", *scored, {"min": 0.3}, slice_={"region": "US"})
        b = catalogue.run("discrimination.gini", *scored, {"min": 0.3}, slice_={"region": "EU"})
        assert a.digest() != b.digest()


# =============================================================== the register
class TestRaisingFindings:
    def test_a_finding_is_recorded_with_a_due_date_from_its_severity(self, findings, a_model):
        f = findings.raise_finding(a_model["id"], "High", "PD calibration drifted",
                                   "person/j.okafor")
        assert f["status"] == "open"
        assert f["due_at"] - f["raised_at"] == pytest.approx(90 * 86400.0, rel=1e-6)

    def test_critical_findings_block_by_default(self, findings, a_model):
        f = findings.raise_finding(a_model["id"], "Critical", "Leakage in training set",
                                   "person/j.okafor")
        assert f["blocking"] is True

    def test_lesser_findings_do_not_block_by_default(self, findings, a_model):
        f = findings.raise_finding(a_model["id"], "Medium", "Documentation stale",
                                   "person/j.okafor")
        assert f["blocking"] is False

    def test_blocking_can_be_forced_on_a_lesser_finding(self, findings, a_model):
        f = findings.raise_finding(a_model["id"], "Low", "Owner unassigned",
                                   "person/j.okafor", blocking=True)
        assert f["blocking"] is True

    def test_an_unknown_severity_is_refused(self, findings, a_model):
        with pytest.raises(ValidationError, match="unknown severity"):
            findings.raise_finding(a_model["id"], "Catastrophic", "x", "person/j.okafor")

    def test_an_unknown_source_is_refused(self, findings, a_model):
        with pytest.raises(ValidationError, match="unknown finding source"):
            findings.raise_finding(a_model["id"], "High", "x", "person/j.okafor",
                                   source="a_hunch")

    def test_a_finding_with_no_owner_is_refused(self, findings, a_model):
        with pytest.raises(ValidationError, match="nobody will fix"):
            findings.raise_finding(a_model["id"], "High", "x", "")


class TestClosingFindings:
    @pytest.fixture
    def raised(self, findings, a_model):
        return findings.raise_finding(a_model["id"], "Critical", "Leakage",
                                      "person/j.okafor")

    def test_closure_records_the_verifier_and_the_evidence(self, findings, raised):
        closed = findings.close(raised["id"], "person/a.mehta", {"pr": "1420"})
        assert closed["status"] == "closed"
        assert closed["closure_verified_by"] == "person/a.mehta"
        assert closed["closure_evidence"] == {"pr": "1420"}

    def test_the_owner_cannot_verify_their_own_closure(self, findings, raised):
        """The person with the strongest reason to declare it done."""
        with pytest.raises(ValidationError, match="cannot verify its own closure"):
            findings.close(raised["id"], "person/j.okafor", {"pr": "1420"})

    def test_closure_without_evidence_is_refused(self, findings, raised):
        with pytest.raises(ValidationError, match="closure evidence"):
            findings.close(raised["id"], "person/a.mehta", {})

    def test_closure_without_a_verifier_is_refused(self, findings, raised):
        with pytest.raises(ValidationError, match="requires a verifier"):
            findings.close(raised["id"], "", {"pr": "1420"})

    def test_closing_twice_is_refused(self, findings, raised):
        findings.close(raised["id"], "person/a.mehta", {"pr": "1420"})
        with pytest.raises(ValidationError, match="already closed"):
            findings.close(raised["id"], "person/a.mehta", {"pr": "1420"})

    def test_status_may_advance_without_closing(self, findings, raised):
        moved = findings.set_status(raised["id"], "in_remediation")
        assert moved["status"] == "in_remediation"
        assert moved in findings.open_for(moved["model_id"])

    def test_status_cannot_be_used_to_close_around_the_checks(self, findings, raised):
        with pytest.raises(ValidationError, match="use close"):
            findings.set_status(raised["id"], "closed")


class TestRegisterQueries:
    def test_summary_counts_open_blocking_and_worst_severity(self, findings, a_model):
        findings.raise_finding(a_model["id"], "Critical", "A", "person/o")
        findings.raise_finding(a_model["id"], "Medium", "B", "person/o")
        low = findings.raise_finding(a_model["id"], "Low", "C", "person/o")
        findings.close(low["id"], "person/v", {"note": "fixed"})
        s = findings.summary(a_model["id"])
        assert s["open"] == 2 and s["blocking"] == 1
        assert s["worst_severity"] == "Critical"
        assert s["by_severity"] == {"Critical": 1, "Medium": 1}

    def test_summary_of_a_clean_model_reports_nothing_open(self, findings, a_model):
        s = findings.summary(a_model["id"])
        assert s["open"] == 0 and s["blocking"] == 0 and s["worst_severity"] is None

    def test_overdue_uses_the_due_date(self, findings, a_model):
        findings.raise_finding(a_model["id"], "Critical", "A", "person/o")
        assert findings.overdue(a_model["id"]) == []
        later = time.time() + 400 * 86400
        assert len(findings.overdue(a_model["id"], now=later)) == 1

    def test_findings_are_scoped_to_their_model(self, findings, registry, a_model):
        registry.register("maya://model/other", "Other", "c", "credit", "o", "LE", "p")
        other = registry.get("maya://model/other")
        findings.raise_finding(a_model["id"], "Critical", "A", "person/o")
        assert len(findings.open_for(a_model["id"])) == 1
        assert findings.open_for(other["id"]) == []


# ================================================================ the gates
class TestBlockingGate:
    """The point of the register: something refuses to proceed."""

    def test_an_alias_move_is_refused_while_a_blocking_finding_is_open(
            self, gated_registry, findings, kernel_spec, contract_spec):
        gated_registry.register(URN, "SB PD", "c", "credit", "o", "LE", "p")
        model = gated_registry.get(URN)
        gated_registry.create_version(URN, "1.0.0", kernel_spec, contract_spec)
        gated_registry.approve_version(URN, "1.0.0")
        findings.raise_finding(model["id"], "Critical", "Leakage in training set",
                               "person/j.okafor")

        with pytest.raises(RegistryError) as exc:
            gated_registry.move_alias(URN, "prod", "champion", "1.0.0")
        assert "blocking finding" in str(exc.value)
        assert "Leakage in training set" in str(exc.value), "name what is blocking"

    def test_closing_the_finding_releases_the_gate(
            self, gated_registry, findings, kernel_spec, contract_spec):
        gated_registry.register(URN, "SB PD", "c", "credit", "o", "LE", "p")
        model = gated_registry.get(URN)
        gated_registry.create_version(URN, "1.0.0", kernel_spec, contract_spec)
        gated_registry.approve_version(URN, "1.0.0")
        f = findings.raise_finding(model["id"], "Critical", "Leakage", "person/j.okafor")

        findings.close(f["id"], "person/a.mehta", {"pr": "1420"})
        moved = gated_registry.move_alias(URN, "prod", "champion", "1.0.0")
        assert moved["version"] == "1.0.0"

    def test_a_non_blocking_finding_does_not_stop_a_move(
            self, gated_registry, findings, kernel_spec, contract_spec):
        gated_registry.register(URN, "SB PD", "c", "credit", "o", "LE", "p")
        model = gated_registry.get(URN)
        gated_registry.create_version(URN, "1.0.0", kernel_spec, contract_spec)
        gated_registry.approve_version(URN, "1.0.0")
        findings.raise_finding(model["id"], "Medium", "Docs stale", "person/j.okafor")
        assert gated_registry.move_alias(URN, "prod", "champion", "1.0.0")

    def test_warrant_resolution_fails_closed_on_a_blocking_finding(
            self, repos, registry, evidence, findings, a_model, approved_version):
        warrants = WarrantService(repos["warrants"], registry, evidence, jitter_pct=0,
                            blocking=findings)
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        warrants.issue(URN, "prod", "svc/pricing", "origination_decision")
        assert warrants.resolve(URN, "prod", "svc/pricing", "origination_decision")

        findings.raise_finding(a_model["id"], "Critical", "Leakage", "person/j.okafor")
        with pytest.raises(WarrantError) as exc:
            warrants.resolve(URN, "prod", "svc/pricing", "origination_decision")
        assert exc.value.code == "blocked"
        assert exc.value.remediation, "a refusal must say what to do about it"

    def test_resolution_recovers_once_the_finding_is_closed(
            self, repos, registry, evidence, findings, a_model, approved_version):
        warrants = WarrantService(repos["warrants"], registry, evidence, jitter_pct=0,
                            blocking=findings)
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        warrants.issue(URN, "prod", "svc/pricing", "origination_decision")
        f = findings.raise_finding(a_model["id"], "Critical", "Leakage", "person/j.okafor")
        findings.close(f["id"], "person/a.mehta", {"pr": "1"})
        assert warrants.resolve(URN, "prod", "svc/pricing", "origination_decision")

    def test_without_a_register_wired_in_nothing_blocks(
            self, warrants, registry, a_model, approved_version):
        """The gate is optional by construction, so the core stays independent."""
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        warrants.issue(URN, "prod", "svc/pricing", "origination_decision")
        assert warrants.resolve(URN, "prod", "svc/pricing", "origination_decision")
