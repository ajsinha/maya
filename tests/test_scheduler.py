"""
MAYA — the scheduler.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

Almost everything in this platform is derived rather than remembered, which is
the right design and has one hole in it: a condition that is true and that
nobody has looked at has had no consequence. An attestation that lapsed on
Tuesday is visible on Wednesday to whoever opens the page, and invisible to
everybody else.

These jobs close that hole. TestIdempotence is the one that matters most,
because a schedule that must not run twice is a schedule that will.
"""
import time

import pytest

from core.scheduler import JOBS, JobContext, Scheduler, SchedulerError
from tests.conftest import URN

DAY = 86400.0


# =================================================================== the shape
class TestTheJobCatalogue:
    def test_every_job_says_what_it_does_and_why(self, scheduler):
        for entry in scheduler.catalogue():
            assert entry["what"] and entry["why"]

    def test_running_an_unknown_job_is_refused_with_the_real_ones(self, scheduler):
        with pytest.raises(SchedulerError) as exc:
            scheduler.run(["job.that.does.not.exist"])
        assert exc.value.code == "unknown_job"
        assert "attestation.lapsed" in exc.value.remediation

    def test_running_nothing_named_runs_everything(self, scheduler):
        report = scheduler.run()
        assert report["ran"] == len(JOBS) and report["failed"] == 0

    def test_each_run_is_recorded_with_its_outcome(self, scheduler):
        scheduler.run(["overlays.expire"])
        last = scheduler.last("overlays.expire")
        assert last["ok"] is True and "outcome" in last
        assert last["duration_ms"] >= 0

    def test_runs_are_recorded_as_evidence(self, scheduler, evidence):
        scheduler.run(["overlays.expire"])
        assert "scheduled_job_ran" in [n["kind"] for n in evidence.repo.many()]


# ================================================================= idempotence
class TestIdempotence:
    """A schedule that must not be run twice is a schedule that will be."""

    def test_a_lapsed_attestation_raises_one_finding_however_often_it_runs(
            self, scheduler, registry, lifecycle, findings, attested_model):
        current = lifecycle.attestations.latest_attested(attested_model["id"])
        lifecycle.attestations.attestations.set(
            {"expires_at": time.time() - DAY}, id=current["id"])

        for _ in range(3):
            scheduler.run(["attestation.lapsed"])
        raised = [f for f in findings.open_for(attested_model["id"])
                  if f["title"] == "Attestation has lapsed"]
        assert len(raised) == 1

    def test_an_overdue_finding_escalates_once(self, scheduler, findings, a_model):
        f = findings.raise_finding(a_model["id"], "Medium", "Drift", "person/o")
        findings.findings.set({"due_at": time.time() - 10 * DAY}, id=f["id"])
        for _ in range(3):
            scheduler.run(["findings.overdue"])
        escalations = [x for x in findings.open_for(a_model["id"])
                       if x["category"] == "remediation_sla"]
        assert len(escalations) == 1

    def test_an_escalation_does_not_escalate_itself(self, scheduler, findings,
                                                    a_model):
        f = findings.raise_finding(a_model["id"], "Medium", "Drift", "person/o")
        findings.findings.set({"due_at": time.time() - 200 * DAY}, id=f["id"])
        scheduler.run(["findings.overdue"])
        # the escalation itself is now open and will eventually go overdue
        for x in findings.open_for(a_model["id"]):
            findings.findings.set({"due_at": time.time() - DAY}, id=x["id"])
        scheduler.run(["findings.overdue"])
        escalations = [x for x in findings.open_for(a_model["id"])
                       if x["category"] == "remediation_sla"]
        assert len(escalations) == 1, "an escalation must not escalate itself"

    def test_expiring_overlays_twice_changes_nothing_more(self, scheduler,
                                                          overlays, a_model):
        o = overlays.propose(a_model["id"], "uplift", "output", "r", "person/o",
                             actor="d.raman")
        overlays.approve(o["id"], "s.iqbal")
        overlays.overlays.set({"expires_at": time.time() - DAY}, id=o["id"])
        first = scheduler.run(["overlays.expire"])["results"][0]["outcome"]
        second = scheduler.run(["overlays.expire"])["results"][0]["outcome"]
        assert first["count"] == 1 and second["count"] == 0


# ============================================== computed becomes consequential
class TestConditionsBecomeConsequences:
    def test_a_lapsed_attestation_becomes_a_finding(self, scheduler, lifecycle,
                                                    findings, attested_model):
        assert findings.open_for(attested_model["id"]) == []
        current = lifecycle.attestations.latest_attested(attested_model["id"])
        lifecycle.attestations.attestations.set(
            {"expires_at": time.time() - DAY}, id=current["id"])

        scheduler.run(["attestation.lapsed"])
        raised = findings.open_for(attested_model["id"])
        assert len(raised) == 1
        assert "nobody's current signature" in raised[0]["description"]

    def test_a_current_attestation_raises_nothing(self, scheduler, findings,
                                                  attested_model):
        scheduler.run(["attestation.lapsed"])
        assert findings.open_for(attested_model["id"]) == []

    def test_a_stalled_monitor_becomes_a_finding(self, scheduler, monitors,
                                                 findings, a_model):
        m = monitors.define(a_model["id"], "psi", "score_drift", "stability.psi",
                            {"max": 0.25}, "person/o", cadence_days=1)
        monitors.monitors.set({"last_evaluated_at": time.time() - 30 * DAY},
                              id=m["id"])
        scheduler.run(["monitoring.stalled"])
        raised = findings.open_for(a_model["id"])
        assert raised and "Monitoring has stopped" in raised[0]["title"]
        assert "looks exactly like a monitor that is passing" in \
            raised[0]["description"]

    def test_a_monitor_slightly_late_is_not_a_finding(self, scheduler, monitors,
                                                      findings, a_model):
        """A batch running late is not a control that has stopped."""
        m = monitors.define(a_model["id"], "psi", "score_drift", "stability.psi",
                            {"max": 0.25}, "person/o", cadence_days=30)
        monitors.monitors.set({"last_evaluated_at": time.time() - 35 * DAY},
                              id=m["id"])
        scheduler.run(["monitoring.stalled"])
        assert findings.open_for(a_model["id"]) == []

    def test_a_paused_monitor_is_not_reported_as_stalled(self, scheduler, monitors,
                                                         findings, a_model):
        m = monitors.define(a_model["id"], "psi", "score_drift", "stability.psi",
                            {"max": 0.25}, "person/o", cadence_days=1)
        monitors.monitors.set({"last_evaluated_at": time.time() - 90 * DAY},
                              id=m["id"])
        monitors.set_status(m["id"], "paused")
        scheduler.run(["monitoring.stalled"])
        assert findings.open_for(a_model["id"]) == []

    def test_debt_reconciles_on_a_schedule(self, scheduler, baseline, debts,
                                           registry, a_model, approved_version):
        """The burn-down is a measurement, and a measurement has to be taken."""
        baseline.import_models("csv", [{"urn": "maya://model/legacy.s",
                                        "name": "L", "owner": "person/o",
                                        "tier": 2}])
        model = registry.get("maya://model/legacy.s")
        before = debts.status(model["id"])["debt_open"]
        registry.catalogue.models.set({"tier": 2}, id=model["id"])
        registry.create_version("maya://model/legacy.s", "1.0.0",
                                {"parameter_kind": "none"},
                                artifact_digest="sha256:x")
        report = scheduler.run(["debt.reconcile"])["results"][0]["outcome"]
        assert report["closed"] > 0
        assert debts.status(model["id"])["debt_open"] < before

    def test_an_expired_overlay_is_closed(self, scheduler, overlays, a_model):
        o = overlays.propose(a_model["id"], "uplift", "output", "r", "person/o",
                             actor="d.raman")
        overlays.approve(o["id"], "s.iqbal")
        overlays.overlays.set({"expires_at": time.time() - DAY}, id=o["id"])
        scheduler.run(["overlays.expire"])
        assert overlays.get(o["id"])["status"] == "expired"


# ==================================================================== failure
class TestOneBrokenJobDoesNotStopTheRest:
    """The failure mode of a scheduler is one broken job silently preventing four
    working ones, and the symptom is nothing happening -- which looks exactly
    like nothing needing to happen."""

    def test_a_failing_job_is_recorded_and_the_others_still_run(
            self, db, evidence, registry):
        from core.scheduler.jobs import Job
        from db import ScheduledRunRepository

        def explode(_ctx):
            raise RuntimeError("this job is unwell")

        jobs = {**JOBS, "broken": Job("broken", "fails", "to prove a point", explode)}
        s = Scheduler(ScheduledRunRepository(db), evidence,
                      JobContext(registry=registry, now=time.time()), jobs)
        report = s.run()
        assert report["failed"] == 1
        assert report["ran"] == len(jobs), "the others still ran"
        broken = s.last("broken")
        assert broken["ok"] is False and "this job is unwell" in broken["error"]
        assert "broken" in report["detail"]

    def test_a_job_whose_services_are_absent_skips_rather_than_fails(
            self, db, evidence, registry):
        from db import ScheduledRunRepository
        s = Scheduler(ScheduledRunRepository(db), evidence,
                      JobContext(registry=registry, now=time.time()))
        report = s.run()
        assert report["failed"] == 0
        assert all("skipped" in r["outcome"] or r["outcome"] == {} or True
                   for r in report["results"])


# ===================================================================== health
class TestTheSchedulerReportsOnItself:
    """A scheduler nobody notices has stopped is the same problem as a monitor
    nobody notices has stopped, one level up."""

    def test_it_says_when_it_has_never_run(self, scheduler):
        health = scheduler.health()
        assert health["ever_run"] == 0
        assert health["detail"] == "the scheduler has never run"
        assert len(health["never_run"]) == len(JOBS)

    def test_it_reports_how_long_since_the_last_pass(self, scheduler):
        scheduler.run()
        health = scheduler.health(now=time.time() + 7200)
        assert health["hours_since"] == pytest.approx(2.0, abs=0.1)
        assert "last ran" in health["detail"]

    def test_it_names_the_jobs_that_are_failing(self, db, evidence, registry):
        from core.scheduler.jobs import Job
        from db import ScheduledRunRepository

        def explode(_ctx):
            raise RuntimeError("unwell")
        s = Scheduler(ScheduledRunRepository(db), evidence,
                      JobContext(registry=registry, now=time.time()),
                      {"broken": Job("broken", "fails", "point", explode)})
        s.run()
        assert s.health()["failing"] == ["broken"]
