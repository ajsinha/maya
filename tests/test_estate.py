"""
MAYA — the estate view: what needs doing, and how the population is faring.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

The platform computes a great deal and, until this, surfaced almost none of it.
A control nobody is told about is a control that operates when somebody happens
to look.

TestWorkIsComputed carries the design: there is no task table, so the list cannot
go stale, cannot disagree with the register, and cannot accumulate orphans when
something is completed by another route.
"""
import time

import pytest

from core.estate import HORIZON_DAYS, WorkList
from tests.conftest import URN

DAY = 86400.0


# ============================================================ work is computed
class TestWorkIsComputed:
    def test_an_outstanding_signature_appears(self, worklist, registry, lifecycle,
                                              ready_model, owner, mrm):
        """The gap this whole module exists to close: nobody was ever told."""
        lifecycle.submit(ready_model, "j.okafor")
        lifecycle.approve(registry.get(URN), "s.iqbal")
        items = worklist.for_model(registry.get(URN))
        attestations = [i for i in items if i.kind == "attestation"]
        assert {i.role for i in attestations} == {"model_owner", "model_risk_manager"}
        assert "not in force until every required role has signed" in \
            attestations[0].detail

    def test_signing_removes_it_without_anyone_closing_a_task(
            self, worklist, registry, lifecycle, ready_model, owner, mrm):
        lifecycle.submit(ready_model, "j.okafor")
        lifecycle.approve(registry.get(URN), "s.iqbal")
        lifecycle.sign(registry.get(URN), owner, "model_owner")
        roles = {i.role for i in worklist.for_model(registry.get(URN))
                 if i.kind == "attestation"}
        assert roles == {"model_risk_manager"}, "the owner's item cleared itself"

    def test_a_submitted_model_shows_as_awaiting_approval(self, worklist, registry,
                                                          lifecycle, ready_model):
        lifecycle.submit(ready_model, "j.okafor")
        kinds = {i.kind for i in worklist.for_model(registry.get(URN))}
        assert "approval" in kinds

    def test_a_draft_with_no_version_says_so(self, worklist, a_model):
        items = worklist.for_model(a_model)
        assert any(i.kind == "draft" for i in items)

    def test_a_blocking_finding_is_always_surfaced(self, worklist, findings,
                                                   a_model):
        findings.raise_finding(a_model["id"], "Critical", "Leakage", "person/o")
        items = worklist.for_model(a_model)
        finding = next(i for i in items if i.kind == "finding")
        assert finding.urgency == "due"
        assert "refuses warrant resolution" in finding.detail

    def test_a_low_severity_finding_with_time_left_is_not_noise(self, worklist,
                                                                findings, a_model):
        findings.raise_finding(a_model["id"], "Low", "Docs untidy", "person/o")
        assert not any(i.kind == "finding" for i in worklist.for_model(a_model))

    def test_an_overdue_finding_is_overdue(self, worklist, findings, a_model):
        f = findings.raise_finding(a_model["id"], "Medium", "Drift", "person/o")
        findings.findings.set({"due_at": time.time() - DAY}, id=f["id"])
        item = next(i for i in worklist.for_model(a_model) if i.kind == "finding")
        assert item.urgency == "overdue"

    def test_a_due_monitor_appears(self, worklist, monitors, a_model):
        monitors.define(a_model["id"], "psi", "score_drift", "stability.psi",
                        {"max": 0.25}, "person/o", cadence_days=1)
        assert any(i.kind == "monitor" for i in worklist.for_model(a_model))

    def test_an_unmeasured_overlay_appears(self, worklist, overlays, a_model):
        o = overlays.propose(a_model["id"], "uplift", "output", "because",
                             "person/o", actor="d.raman")
        overlays.approve(o["id"], "s.iqbal")
        item = next(i for i in worklist.for_model(a_model) if i.kind == "overlay")
        assert "cannot be renewed" in item.detail

    def test_a_stale_document_appears(self, worklist, compiler, registry,
                                      a_model, approved_version, lifecycle):
        from core.docs import MODEL_DEVELOPMENT
        compiler.compile(MODEL_DEVELOPMENT, URN)
        registry.update(URN, {"description": "changed after compilation"})
        item = next(i for i in worklist.for_model(registry.get(URN))
                    if i.kind == "document")
        assert "no longer describes the model" in item.detail
        assert item.href.startswith("/document/")

    def test_baseline_debt_is_summarised_not_enumerated(self, worklist, baseline,
                                                        registry):
        """Eleven rows all saying 'this model arrived without its evidence'
        would bury every other kind of work."""
        baseline.import_models("csv", [{"urn": "maya://model/legacy.x",
                                        "name": "Legacy", "owner": "person/o",
                                        "tier": 1}])
        model = registry.get("maya://model/legacy.x")
        items = [i for i in worklist.for_model(model) if i.kind == "debt"]
        assert len(items) == 1, "one item per model, not one per gap"
        assert "item(s) outstanding" in items[0].title
        assert "without a dated plan" in items[0].detail
        assert "most material is" in items[0].detail

    def test_the_debt_item_names_the_worst_gap(self, worklist, baseline, registry):
        baseline.import_models("csv", [{"urn": "maya://model/legacy.z",
                                        "name": "Legacy", "owner": "", "tier": 1}])
        model = registry.get("maya://model/legacy.z")
        item = next(i for i in worklist.for_model(model) if i.kind == "debt")
        assert "Critical" in item.detail, "the most material gap leads"

    def test_a_subsystem_that_fails_does_not_blank_the_list(self, registry,
                                                            a_model):
        """One refusing service must not hide every other item."""
        class Exploding:
            def open_for(self, _):
                raise RuntimeError("this service is unwell")
        partial = WorkList(registry, findings=Exploding())
        items = partial.for_model(a_model)
        assert any(i.kind == "draft" for i in items), "other sources still ran"


# ================================================================ prioritising
class TestOrdering:
    def test_overdue_sorts_before_due_before_open(self, worklist, findings,
                                                  monitors, a_model):
        old = findings.raise_finding(a_model["id"], "Medium", "Old", "person/o")
        findings.findings.set({"due_at": time.time() - DAY}, id=old["id"])
        monitors.define(a_model["id"], "psi", "score_drift", "stability.psi",
                        {"max": 0.25}, "person/o", cadence_days=1)
        items = worklist.across([a_model])
        urgencies = [i.urgency for i in items]
        assert urgencies == sorted(urgencies,
                                   key=lambda u: {"overdue": 0, "due": 1, "open": 2}[u])


# ================================================================== filtering
class TestWhatIPersonallyCanDo:
    """A list of work somebody cannot act on is a list they learn to ignore."""

    def test_a_developer_is_not_shown_attestation_work(self, worklist, authz,
                                                       registry, lifecycle,
                                                       ready_model, staff):
        lifecycle.submit(ready_model, "j.okafor")
        lifecycle.approve(registry.get(URN), "s.iqbal")
        mine = worklist.mine(staff["d.raman"], authz, [registry.get(URN)])
        assert not any(i["kind"] == "attestation" for i in mine["items"])
        assert mine["others"] > 0

    def test_the_owner_is_shown_their_own_signature_and_not_the_others(
            self, worklist, authz, registry, lifecycle, ready_model, staff):
        lifecycle.submit(ready_model, "j.okafor")
        lifecycle.approve(registry.get(URN), "s.iqbal")
        mine = worklist.mine(staff["j.okafor"], authz, [registry.get(URN)])
        roles = {i["role"] for i in mine["items"] if i["kind"] == "attestation"}
        assert roles == {"model_owner"}, "not the risk manager's signature"

    def test_scope_filters_the_worklist_too(self, worklist, authz, principals,
                                            registry, a_model):
        principals.create("uk.owner", "UK", ["model_owner"], "pw",
                          legal_entities=["LE-UK-02"])
        mine = worklist.mine(principals.get("uk.owner"), authz, [a_model])
        assert mine["items"] == [], "a US model is outside a UK-scoped principal"

    def test_an_empty_list_says_so_plainly(self, worklist, authz, staff, registry,
                                           attested_model):
        mine = worklist.mine(staff["a.mehta"], authz, [registry.get(URN)])
        if not mine["items"]:
            assert "nothing is outstanding for you" in mine["detail"]


# ==================================================================== summary
class TestEstateSummary:
    def test_it_counts_the_population_by_tier_and_state(self, estate, a_model):
        summary = estate.of([a_model])
        assert summary["models"] == 1
        assert summary["by_tier"][1] == 1
        assert summary["by_state"]["draft"] == 1

    def test_it_separates_debt_from_breach(self, estate, baseline, registry):
        """The distinction preserved on every view."""
        baseline.import_models("csv", [{"urn": "maya://model/legacy.y",
                                        "name": "L", "owner": "o", "tier": 2}])
        summary = estate.of([registry.get("maya://model/legacy.y")])
        assert summary["cold_start"]["debt_open"] > 0
        assert summary["cold_start"]["debt_breached"] == 0
        assert summary["governance"]["blocking_findings"] == 0

    def test_it_reports_blocking_findings_across_the_estate(self, estate, findings,
                                                            a_model):
        findings.raise_finding(a_model["id"], "Critical", "Leakage", "person/o")
        assert estate.of([a_model])["governance"]["blocking_findings"] == 1

    def test_it_reports_what_is_unmonitored(self, estate, a_model):
        assert estate.of([a_model])["assurance"]["unmonitored"] == 1

    def test_it_aggregates_overlay_magnitude(self, estate, overlays, a_model):
        o = overlays.propose(a_model["id"], "uplift", "output", "r", "person/o",
                             actor="d.raman")
        overlays.approve(o["id"], "s.iqbal")
        overlays.measure(o["id"], "2026-Q1", 1_000_000.0, 1_180_000.0)
        adjustments = estate.of([a_model])["adjustments"]
        assert adjustments["aggregate_magnitude"] == pytest.approx(180_000.0)
        assert "in aggregate" in adjustments["detail"]

    def test_the_headline_reads_as_a_sentence(self, estate, a_model):
        assert "model(s) registered" in estate.of([a_model])["detail"]

    def test_an_empty_estate_does_not_divide_by_zero(self, estate):
        summary = estate.of([])
        assert summary["models"] == 0
        assert summary["adjustments"]["aggregate_magnitude"] == 0.0


class TestRowsReadWithoutClicking:
    def test_every_item_names_its_model(self, worklist, registry, lifecycle,
                                        ready_model, findings, a_model):
        lifecycle.submit(ready_model, "j.okafor")
        findings.raise_finding(a_model["id"], "Critical", "Leakage", "person/o")
        items = worklist.for_model(registry.get(URN))
        assert items
        for i in items:
            assert i.model == "SB PD", f"{i.kind} does not say which model"

    def test_the_name_survives_into_the_rendered_shape(self, worklist, a_model):
        item = worklist.for_model(a_model)[0].as_dict()
        assert item["model"] and item["href"].startswith("/model/")
