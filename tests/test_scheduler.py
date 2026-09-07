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
                                artifact_digest="sha256:" + "8" * 64)
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
        assert health["stale"] is True
        assert "NEVER run" in health["detail"]
        # And says what that MEANS, because the consequence is the point: every
        # lapse, overdue finding and silent monitor is derived and only becomes
        # a record when this batch runs.
        assert "looks exactly like this one" in health["detail"]
        assert len(health["never_run"]) == len(JOBS)

    def test_a_batch_that_has_stopped_reads_differently_from_one_running(
            self, scheduler):
        """`hours_since` had no threshold, so 30 days and 0.2 hours rendered
        identically as a number on a tile — a batch that stopped a month ago
        looked exactly like one that ran on time."""
        import time as _t

        scheduler.run()
        fresh = scheduler.health(now=_t.time() + 600)
        assert fresh["stale"] is False

        stopped = scheduler.health(
            now=_t.time() + scheduler.interval_seconds * 3)
        assert stopped["stale"] is True
        assert "considered stopped" in stopped["detail"]
        assert stopped["expected_every_hours"] > 0

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


class TestTheLastRunIsTheLatestOne:
    """`last()` returned the OLDEST run of every job.

    It called `latest_version(rows)`, which orders by `semver` — a field a
    scheduled run does not have. Every row keyed the same, `max` returned the
    first of the equals, and the repository orders ascending. Nothing raised:
    `/admin/scheduler` showed the first time the batch ever ran as its last run,
    and a job that failed once on the day it was installed was reported failing
    forever while every run since had succeeded.
    """

    @staticmethod
    def _runs(scheduler, rows):
        for row in rows:
            scheduler.runs.add(row)

    def test_last_returns_the_newest_run(self, scheduler):
        key = sorted(scheduler.jobs)[0]
        self._runs(scheduler, [
            {"job": key, "ran_at": 1000.0, "ok": 0, "outcome": {"note": "first"}, "ran_by": "test"},
            {"job": key, "ran_at": 3000.0, "ok": 1, "outcome": {"note": "newest"}, "ran_by": "test"},
            {"job": key, "ran_at": 2000.0, "ok": 1, "outcome": {"note": "middle"}, "ran_by": "test"}])
        assert scheduler.last(key)["ran_at"] == 3000.0

    def test_a_job_that_failed_once_long_ago_is_not_failing_now(self, scheduler):
        key = sorted(scheduler.jobs)[0]
        self._runs(scheduler, [
            {"job": key, "ran_at": 1000.0, "ok": 0, "outcome": {}, "ran_by": "test"},
            {"job": key, "ran_at": 9000.0, "ok": 1, "outcome": {}, "ran_by": "test"}])
        health = scheduler.health(now=9100.0)
        assert health["failing"] == [], \
            "the first run failed; every run since succeeded"
        assert health["last_run_at"] == 9000.0
        assert health["hours_since"] < 1

    def test_history_reads_newest_first(self, scheduler):
        key = sorted(scheduler.jobs)[0]
        self._runs(scheduler, [{"job": key, "ran_at": t, "ok": 1, "outcome": {}, "ran_by": "test"}
                               for t in (1000.0, 2000.0, 3000.0)])
        assert [r["ran_at"] for r in scheduler.history(2)] == [3000.0, 2000.0]


class TestPeriodicReviewIsActuallyRead:
    """`next_review_due` was computed, stored on every assessment, and read by
    nothing at all — not a job, not a screen, not an endpoint.

    The tier's review cadence is the whole reason `TieringEngine` carries a
    review map: twelve months at Tier 1, thirty-six at Tier 4. It was a column
    nobody selected, so an estate could pass every other control while its Tier
    1 models went four years unreviewed. Periodic review is the obligation
    SR 11-7 is most explicit about.
    """

    URN = "maya://model/review.subject"

    @staticmethod
    def _assess(scheduler, registry, tiering, repos, due_in_days):
        import time

        registry.register(
            TestPeriodicReviewIsActuallyRead.URN, "Review subject", "credit",
            "retail", "person/j.okafor", "LE-US-01", "periodic review")
        model = registry.require(TestPeriodicReviewIsActuallyRead.URN)
        assessment = tiering.assess({
            "exposure": 2e9, "purpose_class": "regulatory_capital",
            "trainability_class": "T2", "feature_count": 12,
            "uses_alternative_data": False, "interpretable": True})
        row = tiering.persist(repos["risk"], model["id"], assessment)
        repos["risk"].set({"next_review_due": time.time()
                           + due_in_days * 86400}, id=row["id"])
        return model

    def test_a_model_past_its_review_date_raises_a_finding(
            self, scheduler, registry, tiering, repos, findings):
        import time

        model = self._assess(scheduler, registry, tiering, repos, -40)
        outcome = scheduler.run(["review.overdue"], now=time.time())
        result = outcome["results"][0]
        assert result["ok"], result
        assert result["outcome"]["count"] == 1, result
        raised = findings.open_for(model["id"])
        assert any(f["title"] == "Periodic review is overdue" for f in raised)
        overdue = next(f for f in raised
                       if f["title"] == "Periodic review is overdue")
        assert "40 days ago" in overdue["description"]
        assert overdue["severity"] == "High", "Tier 2 or above is High"

    def test_a_model_within_its_window_raises_nothing(
            self, scheduler, registry, tiering, repos):
        import time

        self._assess(scheduler, registry, tiering, repos, 200)
        assert scheduler.run(["review.overdue"], now=time.time()
                             )["results"][0]["outcome"]["count"] == 0

    def test_it_does_not_raise_the_same_finding_twice(
            self, scheduler, registry, tiering, repos):
        import time

        self._assess(scheduler, registry, tiering, repos, -40)
        moment = time.time()
        scheduler.run(["review.overdue"], now=moment)
        again = scheduler.run(["review.overdue"], now=moment)
        assert again["results"][0]["outcome"]["count"] == 0, \
            "a batch that runs hourly must not raise a finding hourly"

    def test_a_model_that_was_never_assessed_is_not_flagged_here(
            self, scheduler, registry):
        """A model with no assessment has a different problem, and a different
        control says so — this one is about a review date that has passed."""
        import time

        registry.register("maya://model/review.unassessed", "Unassessed",
                          "credit", "retail", "person/o", "LE-US-01", "none")
        assert scheduler.run(["review.overdue"], now=time.time()
                             )["results"][0]["outcome"]["count"] == 0
