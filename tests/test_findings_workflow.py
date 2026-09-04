"""
MAYA — the workflow around a finding.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

Findings were raised, tracked and closed, and nothing happened in between. A
finding could be handed quietly between three people, sit for a year with nobody
having agreed it was theirs, and have its date moved as often as anybody liked by
the one person with a reason to move it.

TestExtensionIsNotSilent carries the design: an extension is legitimate, needs a
reason, may not be granted by the person whose deadline it is, is counted, and
past the limit becomes a finding in its own right — the overlay register's answer
to the same shape of problem.

TestNothingIsStoredTwice carries the other half: none of ageing, overdue-ness,
acceptance or escalation is written down anywhere. All of it is computed from the
acts, so there is no second record to disagree with the register.
"""
import time

import pytest

from core.validation import ageing
from core.validation.common import (DAY, ESCALATION_ROLE, FindingWorkflowError,
                                    same_person)

NOW = 1_800_000_000.0


@pytest.fixture
def raised(findings, a_model):
    """A High finding: a 90-day window, and it does not block."""
    return findings.raise_finding(a_model["id"], "High", "Segment drift unexplained",
                                  "person/j.okafor", category="performance",
                                  actor="a.mehta")


@pytest.fixture
def accepted(finding_workflow, raised):
    """Accepted by its owner, with a plan, which is the normal path."""
    finding_workflow.acknowledge(raised["id"], "person/j.okafor",
                                 plan="Re-fit on the 2026 sample by 30 June")
    return raised


# ================================================================== assignment
class TestAssignment:
    def test_a_finding_can_be_handed_to_somebody_else(self, finding_workflow,
                                                      raised):
        moved = finding_workflow.assign(raised["id"], "person/d.raman",
                                        "the re-fit is the development team's work",
                                        actor="j.okafor")
        assert moved["owner"] == "person/d.raman"

    def test_the_handover_is_on_the_record(self, finding_workflow, raised):
        """A finding passed quietly between three people is a finding nobody
        owned; the register has to be able to say who gave it up and why."""
        finding_workflow.assign(raised["id"], "person/d.raman", "development work",
                                actor="j.okafor")
        handover = finding_workflow.reading(raised["id"])["handovers"][0]
        assert handover["from"] == "person/j.okafor"
        assert handover["to"] == "person/d.raman"
        assert handover["reason"] == "development work"
        assert handover["by"] == "j.okafor"

    def test_a_handover_without_a_reason_is_refused(self, finding_workflow, raised):
        with pytest.raises(FindingWorkflowError) as exc:
            finding_workflow.assign(raised["id"], "person/d.raman", "   ")
        assert exc.value.code == "reason_required"
        assert "explains nothing" in exc.value.remediation

    def test_handing_it_to_nobody_is_refused(self, finding_workflow, raised):
        with pytest.raises(FindingWorkflowError) as exc:
            finding_workflow.assign(raised["id"], "  ", "because")
        assert exc.value.code == "owner_required"

    def test_handing_it_to_its_current_owner_is_refused(self, finding_workflow,
                                                        raised):
        """Not pedantry: a no-op handover in the record reads as a real one."""
        with pytest.raises(FindingWorkflowError) as exc:
            finding_workflow.assign(raised["id"], "person/j.okafor", "because")
        assert exc.value.code == "already_owned"

    def test_a_handover_withdraws_the_previous_owners_acceptance(
            self, finding_workflow, accepted):
        """The new owner has not agreed to the date the last one named, and
        treating the old acknowledgement as current is how a reassignment
        launders an unaccepted commitment into an accepted one."""
        assert finding_workflow.reading(accepted["id"])[
            "acknowledgement"]["acknowledged"] is True
        finding_workflow.assign(accepted["id"], "person/d.raman", "handover",
                                actor="j.okafor")
        state = finding_workflow.reading(accepted["id"])["acknowledgement"]
        assert state["acknowledged"] is False
        assert "reassigned" in state["detail"]

    def test_who_raised_it_never_changes(self, finding_workflow, raised, evidence,
                                         a_model):
        """Ownership moves; authorship does not. The raiser is who the
        segregation check reads to decide who may close it."""
        finding_workflow.assign(raised["id"], "person/d.raman", "handover",
                                actor="j.okafor")
        raiser = [n for n in evidence.for_subject(a_model["id"])
                  if n["kind"] == "finding_raised"]
        assert raiser[0]["recorded_by"] == "a.mehta"

    def test_a_closed_findings_workflow_has_ended(self, finding_workflow, findings,
                                                  raised):
        findings.close(raised["id"], "person/a.mehta", {"pr": "1420"})
        with pytest.raises(FindingWorkflowError) as exc:
            finding_workflow.assign(raised["id"], "person/d.raman", "because")
        assert exc.value.code == "finding_closed"
        assert "raise a new one" in exc.value.remediation

    def test_a_finding_that_does_not_exist_says_so(self, finding_workflow):
        with pytest.raises(FindingWorkflowError) as exc:
            finding_workflow.assign("no-such-finding", "person/x", "because")
        assert exc.value.code == "no_finding"


# ============================================================== acknowledgement
class TestAcknowledgement:
    def test_the_owner_accepts_it_and_names_a_date(self, finding_workflow, raised):
        state = finding_workflow.acknowledge(raised["id"], "person/j.okafor",
                                             plan="Re-fit on the 2026 sample")
        assert state["acknowledgement"]["acknowledged"] is True
        assert state["acknowledgement"]["committed_at"] == raised["due_at"]

    def test_nobody_may_accept_a_finding_on_somebody_elses_behalf(
            self, finding_workflow, raised):
        """An acknowledgement recorded for you is the paperwork of a commitment
        without the commitment."""
        with pytest.raises(FindingWorkflowError) as exc:
            finding_workflow.acknowledge(raised["id"], "s.iqbal", plan="a plan")
        assert exc.value.code == "not_the_owner"
        assert "reassign it first" in exc.value.remediation

    def test_the_owner_is_recognised_however_their_identity_is_written(
            self, finding_workflow, raised):
        """The register writes an owner as `person/j.okafor` and authenticates
        the same human as `j.okafor`. A check that compared the two as strings
        would be one anybody could step around by dropping the prefix."""
        state = finding_workflow.acknowledge(raised["id"], "j.okafor",
                                             plan="Re-fit on the 2026 sample")
        assert state["acknowledgement"]["acknowledged"] is True

    def test_acceptance_without_a_plan_is_a_receipt_not_a_commitment(
            self, finding_workflow, raised):
        with pytest.raises(FindingWorkflowError) as exc:
            finding_workflow.acknowledge(raised["id"], "person/j.okafor")
        assert exc.value.code == "plan_required"
        assert "receipt, not a commitment" in exc.value.detail

    def test_an_existing_plan_is_enough_to_acknowledge_against(
            self, finding_workflow, raised):
        finding_workflow.plan_for(raised["id"], "Re-fit by 30 June", "j.okafor")
        state = finding_workflow.acknowledge(raised["id"], "person/j.okafor")
        assert state["acknowledgement"]["acknowledged"]

    def test_the_owner_cannot_commit_to_a_date_after_the_due_date(
            self, finding_workflow, raised):
        """The hole this closes: an owner who could accept to any date they liked
        would have an extension mechanism needing nobody's agreement, leaving no
        count and no reason."""
        with pytest.raises(FindingWorkflowError) as exc:
            finding_workflow.acknowledge(raised["id"], "person/j.okafor",
                                         days=200, plan="eventually")
        assert exc.value.code == "beyond_the_due_date"
        assert "an extension is counted and needs a reason" in exc.value.remediation

    def test_a_date_that_has_already_passed_is_refused(self, finding_workflow,
                                                       raised):
        with pytest.raises(FindingWorkflowError) as exc:
            finding_workflow.acknowledge(raised["id"], "person/j.okafor",
                                         committed_at=time.time() - DAY,
                                         plan="a plan")
        assert exc.value.code == "date_in_the_past"

    def test_acceptance_moves_the_finding_into_remediation(self, finding_workflow,
                                                           findings, raised):
        """The status column ends up agreeing with what was actually done. It is
        a summary of the acts, never a substitute for them."""
        assert findings.get(raised["id"])["status"] == "open"
        finding_workflow.acknowledge(raised["id"], "person/j.okafor",
                                     plan="Re-fit by 30 June")
        assert findings.get(raised["id"])["status"] == "in_remediation"

    def test_acceptance_is_witnessed(self, finding_workflow, evidence, a_model,
                                     raised):
        finding_workflow.acknowledge(raised["id"], "person/j.okafor", plan="a plan")
        kinds = [n["kind"] for n in evidence.for_subject(a_model["id"])]
        assert "finding_acknowledged" in kinds
        assert "finding_planned" in kinds


# ======================================================================= plan
class TestThePlan:
    def test_a_plan_says_what_will_be_done(self, finding_workflow, raised):
        finding_workflow.plan_for(raised["id"], "Re-fit on the 2026 sample by "
                                                "30 June, revalidate in July",
                                  "j.okafor")
        state = finding_workflow.reading(raised["id"])["plan"]
        assert state["planned"] and "30 June" in state["plan"]

    def test_an_empty_plan_is_refused(self, finding_workflow, raised):
        """The same refusal, and the same word, the compliance debt register
        uses — one idiom for one idea."""
        with pytest.raises(FindingWorkflowError) as exc:
            finding_workflow.plan_for(raised["id"], "   ")
        assert exc.value.code == "plan_required"
        assert "'will fix' is not a plan" in exc.value.remediation

    def test_replanning_keeps_every_earlier_plan(self, finding_workflow, raised):
        """A finding re-planned three times is a fact about the remediation, and
        overwriting the plan in place is how that fact disappears."""
        finding_workflow.plan_for(raised["id"], "Re-fit by March", "j.okafor")
        finding_workflow.plan_for(raised["id"], "Re-fit by June", "j.okafor")
        state = finding_workflow.reading(raised["id"])["plan"]
        assert state["plan"] == "Re-fit by June"
        assert state["revisions"] == 2
        assert "revised 1 time(s)" in state["detail"]


# ======================================================== the point of it all
class TestExtensionIsNotSilent:
    """Dates move for good reasons. What must not happen is a date moving with
    no reason, at the discretion of the person it constrains, and uncounted."""

    def test_an_extension_moves_the_date_and_says_who_and_why(
            self, finding_workflow, accepted):
        state = finding_workflow.extend(accepted["id"], "s.iqbal",
                                        "the 2026 sample does not close until Q3",
                                        days=30)
        assert state["due_at"] == pytest.approx(accepted["due_at"] + 30 * DAY)
        assert state["extensions"]["count"] == 1
        moved = state["extensions"]["history"][0]
        assert moved["by"] == "s.iqbal" and "2026 sample" in moved["reason"]

    def test_an_extension_without_a_reason_is_refused(self, finding_workflow,
                                                      accepted):
        with pytest.raises(FindingWorkflowError) as exc:
            finding_workflow.extend(accepted["id"], "s.iqbal", "  ", days=30)
        assert exc.value.code == "reason_required"

    def test_the_owner_cannot_extend_their_own_deadline(self, finding_workflow,
                                                        accepted):
        """The obvious hole, and the overlay register's answer to it: the person
        with the deadline is the last person who should be able to move it."""
        with pytest.raises(FindingWorkflowError) as exc:
            finding_workflow.extend(accepted["id"], "person/j.okafor",
                                    "need more time", days=30)
        assert exc.value.code == "self_extension"
        assert "somebody independent" in exc.value.remediation

    def test_the_owner_cannot_extend_under_a_shorter_name_either(
            self, finding_workflow, accepted):
        with pytest.raises(FindingWorkflowError) as exc:
            finding_workflow.extend(accepted["id"], "j.okafor", "need more time",
                                    days=30)
        assert exc.value.code == "self_extension"

    def test_extending_a_finding_nobody_accepted_is_refused(self, finding_workflow,
                                                            raised):
        """Overlays refuse renewal without a measurement, for the same reason:
        extending a date nobody agreed to moves a number, not a commitment."""
        with pytest.raises(FindingWorkflowError) as exc:
            finding_workflow.extend(raised["id"], "s.iqbal", "more time", days=30)
        assert exc.value.code == "not_acknowledged"
        assert "acknowledge it with a plan first" in exc.value.remediation

    def test_a_date_brought_forward_is_not_an_extension(self, finding_workflow,
                                                        accepted):
        with pytest.raises(FindingWorkflowError) as exc:
            finding_workflow.extend(accepted["id"], "s.iqbal", "sooner",
                                    due_at=accepted["due_at"] - DAY)
        assert exc.value.code == "not_an_extension"

    def test_an_extension_longer_than_the_original_window_is_refused(
            self, finding_workflow, accepted):
        """A High finding gets 90 days. An extension of 200 is not an extension,
        it is a new remediation date nobody has justified."""
        with pytest.raises(FindingWorkflowError) as exc:
            finding_workflow.extend(accepted["id"], "s.iqbal", "a long time",
                                    days=200)
        assert exc.value.code == "extension_too_long"
        assert "90-day remediation window" in exc.value.detail

    def test_extensions_are_counted_and_totalled(self, finding_workflow, accepted):
        for i in range(2):
            finding_workflow.extend(accepted["id"], "s.iqbal", f"reason {i}",
                                    days=10)
        counted = finding_workflow.reading(accepted["id"])["extensions"]
        assert counted["count"] == 2 and counted["days_added"] == pytest.approx(20.0)
        assert counted["over_limit"] is False

    def test_past_the_limit_the_extension_itself_becomes_a_finding(
            self, finding_workflow, findings, a_model, accepted):
        """A date moved often enough is not a date, and that is a governance
        failure distinct from whatever the original finding was about."""
        for i in range(3):
            finding_workflow.extend(accepted["id"], "s.iqbal", f"reason {i}",
                                    days=10)
        raised = [f for f in findings.open_for(a_model["id"])
                  if f["category"] == "remediation_extension"]
        assert len(raised) == 1
        assert "moved repeatedly" in raised[0]["title"]
        assert "no longer means anything" in raised[0]["description"]

    def test_the_escalation_is_raised_once_not_on_every_extension(
            self, finding_workflow, findings, a_model, accepted):
        for i in range(5):
            finding_workflow.extend(accepted["id"], "s.iqbal", f"reason {i}",
                                    days=10)
        assert len([f for f in findings.open_for(a_model["id"])
                    if f["category"] == "remediation_extension"]) == 1

    def test_within_the_limit_nothing_is_escalated(self, finding_workflow, findings,
                                                   a_model, accepted):
        finding_workflow.extend(accepted["id"], "s.iqbal", "one good reason",
                                days=10)
        assert not [f for f in findings.open_for(a_model["id"])
                    if f["category"] == "remediation_extension"]

    def test_an_extension_is_witnessed(self, finding_workflow, evidence, a_model,
                                       accepted):
        finding_workflow.extend(accepted["id"], "s.iqbal", "sample timing", days=10)
        moved = [n for n in evidence.for_subject(a_model["id"])
                 if n["kind"] == "finding_extended"]
        assert moved and moved[0]["payload"]["reason"] == "sample timing"


# =================================================================== escalation
class TestEscalation:
    def test_a_finding_within_its_window_is_not_escalated(self, finding_workflow,
                                                          accepted):
        reading = finding_workflow.reading(accepted["id"])
        assert reading["escalation"]["escalate"] is False
        assert "within its window" in reading["escalation"]["detail"]

    def test_a_long_overdue_finding_stops_being_only_its_owners_problem(
            self, finding_workflow, findings, accepted):
        findings.findings.set({"due_at": time.time() - 30 * DAY}, id=accepted["id"])
        escalation = finding_workflow.reading(accepted["id"])["escalation"]
        assert escalation["escalate"] is True
        assert "past its remediation date" in escalation["reasons"][0]

    def test_a_finding_nobody_accepted_escalates_on_its_own(self, finding_workflow,
                                                            findings, raised):
        """The failure this catches: silence looks exactly like progress."""
        findings.findings.set({"raised_at": time.time() - 10 * DAY},
                              id=raised["id"])
        escalation = finding_workflow.reading(raised["id"])["escalation"]
        assert escalation["escalate"] is True
        assert "nobody has accepted it" in escalation["reasons"][0]

    def test_a_blocking_finding_escalates_the_day_it_is_late(
            self, finding_workflow, findings, a_model):
        """It is stopping the model being served at all; one day past its date is
        not the same as one day past a Low finding's date."""
        blocker = findings.raise_finding(a_model["id"], "Critical", "Leakage",
                                         "person/j.okafor")
        finding_workflow.acknowledge(blocker["id"], "person/j.okafor",
                                     plan="rebuild the sample")
        findings.findings.set({"due_at": time.time() - DAY}, id=blocker["id"])
        reasons = finding_workflow.reading(blocker["id"])["escalation"]["reasons"]
        assert any("it is blocking" in r for r in reasons)

    def test_escalation_names_a_role_and_not_a_person(self, finding_workflow,
                                                      findings, accepted):
        """MAYA does not know who reports to whom and should not pretend to."""
        findings.findings.set({"due_at": time.time() - 30 * DAY}, id=accepted["id"])
        escalation = finding_workflow.reading(accepted["id"])["escalation"]
        assert escalation["to_role"] == ESCALATION_ROLE
        assert "model risk manager" in escalation["detail"]

    def test_it_is_the_same_role_notification_escalates_to(self):
        """Two escalation paths that disagree about who is told is worse than
        one that is wrong, because nobody can say which is operating."""
        from core.notify.common import ESCALATION_ROLE as NOTIFY_ROLE
        assert ESCALATION_ROLE == NOTIFY_ROLE

    def test_a_closed_finding_escalates_to_nobody(self, finding_workflow, findings,
                                                  accepted):
        findings.findings.set({"due_at": time.time() - 90 * DAY}, id=accepted["id"])
        findings.close(accepted["id"], "person/a.mehta", {"pr": "1"})
        assert finding_workflow.reading(accepted["id"])[
            "escalation"]["escalate"] is False

    def test_the_model_reports_what_is_escalated(self, finding_workflow, findings,
                                                 a_model, accepted):
        findings.findings.set({"due_at": time.time() - 30 * DAY}, id=accepted["id"])
        escalated = finding_workflow.escalated(a_model["id"])
        assert len(escalated) == 1
        assert escalated[0]["title"] == "Segment drift unexplained"


# ============================================================= derived, not kept
class TestNothingIsStoredTwice:
    """No status table that can disagree with the register."""

    def test_ageing_is_computed_from_when_it_was_raised(self, findings, a_model):
        row = findings.raise_finding(a_model["id"], "Low", "Typo", "person/o")
        findings.findings.set({"raised_at": NOW - 45 * DAY}, id=row["id"])
        assert ageing.age_days(findings.get(row["id"]), NOW) == pytest.approx(45.0)

    def test_a_closed_finding_stops_ageing_when_it_closed(self):
        closed = {"raised_at": NOW - 100 * DAY, "closed_at": NOW - 60 * DAY,
                  "status": "closed", "due_at": NOW}
        assert ageing.age_days(closed, NOW) == pytest.approx(40.0)

    def test_not_overdue_is_not_a_negative_quantity(self):
        """Reporting 'minus twelve days overdue' puts a misleading number into
        every sum it reaches."""
        assert ageing.days_overdue({"due_at": NOW + 12 * DAY, "status": "open"},
                                   NOW) == 0.0

    def test_age_is_reported_as_a_distribution(self):
        """One finding open for four years and nine opened last week average to
        something reassuring."""
        assert ageing.bucket(10) == "0-30 days"
        assert ageing.bucket(200) == "over 180 days"

    def test_the_extension_count_is_derived_from_the_acts(self, finding_workflow,
                                                          accepted):
        """A counter and a log can disagree, and when they do it is the counter
        that gets believed and the log that is right."""
        finding_workflow.extend(accepted["id"], "s.iqbal", "reason", days=10)
        acts = finding_workflow.actions_for(accepted["id"])
        assert ageing.extensions(acts)["count"] == 1
        assert len([a for a in acts if a["act"] == "extended"]) == 1

    def test_closing_a_finding_by_another_route_leaves_nothing_stale(
            self, finding_workflow, findings, a_model, accepted):
        """There is no task row to orphan: the register is the only thing that
        has to be right."""
        findings.close(accepted["id"], "person/a.mehta", {"pr": "1"})
        assert finding_workflow.escalated(a_model["id"]) == []
        assert finding_workflow.ageing(a_model["id"])["open"] == 0

    def test_identity_comparison_ignores_the_namespace_but_not_the_person(self):
        assert same_person("person/j.okafor", "j.okafor")
        assert same_person("svc/batch", "batch")
        assert not same_person("person/j.okafor", "person/d.raman")
        assert not same_person("", "person/j.okafor")


# ============================================================ the reporting cycle
class TestTheAgeingProfile:
    """What a risk committee asks for about a findings register and rarely gets."""

    def test_it_counts_by_severity_and_by_age(self, finding_workflow, findings,
                                              a_model):
        for severity, age in (("Critical", 5), ("High", 45), ("High", 200)):
            row = findings.raise_finding(a_model["id"], severity, f"{severity}{age}",
                                         "person/o")
            findings.findings.set({"raised_at": time.time() - age * DAY},
                                  id=row["id"])
        profile = finding_workflow.ageing(a_model["id"])
        assert profile["open"] == 3
        assert profile["by_severity"]["High"]["open"] == 2
        assert profile["by_age"]["0-30 days"] == 1
        assert profile["by_age"]["over 180 days"] == 1

    def test_it_counts_what_is_past_its_date(self, finding_workflow, findings,
                                             a_model, raised):
        findings.findings.set({"due_at": time.time() - DAY}, id=raised["id"])
        assert finding_workflow.ageing(a_model["id"])["overdue"] == 1

    def test_it_counts_how_many_have_been_extended_and_how_often(
            self, finding_workflow, a_model, accepted):
        for i in range(2):
            finding_workflow.extend(accepted["id"], "s.iqbal", f"reason {i}",
                                    days=10)
        extended = finding_workflow.ageing(a_model["id"])["extended"]
        assert extended["findings"] == 1 and extended["extensions"] == 2
        assert extended["most_extended"] == 2
        assert extended["days_added"] == pytest.approx(20.0)

    def test_it_counts_what_nobody_has_accepted(self, finding_workflow, a_model,
                                                raised):
        assert finding_workflow.ageing(a_model["id"])["unacknowledged"] == 1
        finding_workflow.acknowledge(raised["id"], "person/j.okafor", plan="a plan")
        assert finding_workflow.ageing(a_model["id"])["unacknowledged"] == 0

    def test_it_names_the_oldest_and_the_worst(self, finding_workflow, findings,
                                               a_model, raised):
        old = findings.raise_finding(a_model["id"], "Critical", "Leakage",
                                     "person/o")
        findings.findings.set({"raised_at": time.time() - 400 * DAY}, id=old["id"])
        profile = finding_workflow.ageing(a_model["id"])
        assert profile["worst_severity"] == "Critical"
        assert profile["oldest"]["finding_id"] == old["id"]
        assert profile["oldest"]["age_days"] == pytest.approx(400.0, abs=1.0)

    def test_a_closed_finding_leaves_the_open_count_and_joins_the_closed_one(
            self, finding_workflow, findings, a_model, raised):
        findings.close(raised["id"], "person/a.mehta", {"pr": "1"})
        profile = finding_workflow.ageing(a_model["id"])
        assert profile["open"] == 0 and profile["closed"] == 1
        assert profile["detail"] == "nothing is open"

    def test_the_estate_profile_spans_models(self, finding_workflow, findings,
                                             registry, a_model):
        registry.register("maya://model/other.x", "Other", "credit.pd.scorecard",
                          "credit", "person/o", "LE-US-01", "another")
        other = registry.get("maya://model/other.x")
        findings.raise_finding(a_model["id"], "High", "one", "person/o")
        findings.raise_finding(other["id"], "Low", "two", "person/o")
        across = finding_workflow.across([a_model["id"], other["id"]])
        assert across["models"] == 2 and across["open"] == 2

    def test_the_detail_reads_as_a_sentence(self, finding_workflow, findings,
                                            a_model, accepted):
        findings.findings.set({"due_at": time.time() - 30 * DAY}, id=accepted["id"])
        finding_workflow.extend(accepted["id"], "s.iqbal", "reason", days=10)
        detail = finding_workflow.ageing(a_model["id"])["detail"]
        assert "1 open" in detail and "extended" in detail


# ================================================================== the worklist
class TestItReachesSomebody:
    def test_an_unaccepted_finding_appears_on_the_worklist(self, worklist, findings,
                                                           a_model):
        """Derived like everything else on the list, so it clears itself the
        moment the owner accepts it rather than waiting for a task to be ticked."""
        row = findings.raise_finding(a_model["id"], "High", "Drift", "person/j.okafor")
        findings.findings.set({"raised_at": time.time() - 10 * DAY}, id=row["id"])
        items = [i for i in worklist.for_model(a_model)
                 if i.kind == "finding_acknowledgement"]
        assert len(items) == 1
        assert items[0].permission == "finding:acknowledge"
        assert "Accept it with a plan" in items[0].detail

    def test_accepting_it_clears_the_item(self, worklist, finding_workflow,
                                          findings, a_model):
        row = findings.raise_finding(a_model["id"], "High", "Drift", "person/j.okafor")
        findings.findings.set({"raised_at": time.time() - 10 * DAY}, id=row["id"])
        finding_workflow.acknowledge(row["id"], "person/j.okafor", plan="a plan")
        assert not [i for i in worklist.for_model(a_model)
                    if i.kind == "finding_acknowledgement"]

    def test_a_fresh_finding_is_not_yet_noise(self, worklist, findings, a_model):
        """An owner has a few days to accept a finding before the silence is
        itself the problem; a list that complains on day zero is a list people
        learn to ignore."""
        findings.raise_finding(a_model["id"], "High", "Drift", "person/j.okafor")
        assert not [i for i in worklist.for_model(a_model)
                    if i.kind == "finding_acknowledgement"]


# ================================================================== the scheduler
class TestTheReminderCycleIsRecorded:
    def test_an_unaccepted_finding_eventually_becomes_a_finding(
            self, scheduler, findings, a_model):
        """Reminders that are ignored have to end somewhere other than in more
        reminders."""
        row = findings.raise_finding(a_model["id"], "High", "Drift", "person/j.okafor")
        findings.findings.set({"raised_at": time.time() - 30 * DAY}, id=row["id"])
        scheduler.run(["findings.unacknowledged"])
        raised = [f for f in findings.open_for(a_model["id"])
                  if f["category"] == "remediation_acknowledgement"]
        assert len(raised) == 1
        assert "never accepted" in raised[0]["title"]
        assert "nobody has agreed to fix it" in raised[0]["description"]

    def test_running_it_twice_changes_nothing(self, scheduler, findings, a_model):
        """A schedule that must not be run twice is a schedule that will be, and
        the first duplicate run will be at three in the morning."""
        row = findings.raise_finding(a_model["id"], "High", "Drift", "person/j.okafor")
        findings.findings.set({"raised_at": time.time() - 30 * DAY}, id=row["id"])
        scheduler.run(["findings.unacknowledged"])
        scheduler.run(["findings.unacknowledged"])
        assert len([f for f in findings.open_for(a_model["id"])
                    if f["category"] == "remediation_acknowledgement"]) == 1

    def test_it_does_not_escalate_its_own_escalations(self, scheduler, findings,
                                                      a_model):
        """Otherwise every sweep raises a finding about the finding it raised
        last time, for ever."""
        row = findings.raise_finding(a_model["id"], "High", "Drift", "person/j.okafor")
        findings.findings.set({"raised_at": time.time() - 30 * DAY}, id=row["id"])
        scheduler.run(["findings.unacknowledged"])
        for f in findings.open_for(a_model["id"]):
            findings.findings.set({"raised_at": time.time() - 30 * DAY}, id=f["id"])
        scheduler.run(["findings.unacknowledged"])
        assert len(findings.open_for(a_model["id"])) == 2

    def test_an_accepted_finding_is_left_alone(self, scheduler, finding_workflow,
                                               findings, a_model):
        row = findings.raise_finding(a_model["id"], "High", "Drift", "person/j.okafor")
        findings.findings.set({"raised_at": time.time() - 30 * DAY}, id=row["id"])
        finding_workflow.acknowledge(row["id"], "person/j.okafor", plan="a plan")
        scheduler.run(["findings.unacknowledged"])
        assert len(findings.open_for(a_model["id"])) == 1

    def test_the_job_is_published_with_its_reason(self, scheduler):
        entry = next(j for j in scheduler.catalogue()
                     if j["job"] == "findings.unacknowledged")
        assert "looks identical" in entry["why"]


# =============================================================== authorisation
class TestWhoMayDoWhat:
    def test_the_first_line_may_accept_and_plan_but_never_extend(self):
        """An owner who can extend their own deadline has no deadline, and the
        permission set should say so before the register has to."""
        from core.authz.roles import permissions_for
        owner = permissions_for(["model_owner"])
        assert {"finding:acknowledge", "finding:plan", "finding:assign"} <= owner
        assert "finding:extend" not in owner

    def test_the_second_line_holds_extension(self):
        from core.authz.roles import permissions_for
        assert "finding:extend" in permissions_for(["validator"])
        assert "finding:extend" in permissions_for(["model_risk_manager"])

    def test_the_third_line_remediates_nothing(self):
        from core.authz.roles import permissions_for
        auditor = permissions_for(["auditor"])
        assert "finding:raise" in auditor
        assert not {"finding:acknowledge", "finding:plan", "finding:assign",
                    "finding:extend"} & auditor

    def test_whoever_accepted_a_finding_may_not_extend_it(self, segregation,
                                                          evidence):
        """Enforced from the evidence chain as well as in the register, because
        one person wearing two hats defeats a role check and does not defeat a
        record of what they already did."""
        from core.authz import AuthzError
        evidence.append("finding_acknowledged", "model", "m-1",
                        {"finding_id": "f-1"}, actor="j.okafor")
        with pytest.raises(AuthzError) as exc:
            segregation.check("j.okafor", "finding:extend", "m-1", about="f-1")
        assert exc.value.code == "segregation_of_duties"
        assert "may not move the date they accepted" in str(exc.value)

    def test_accepting_one_finding_does_not_disqualify_them_from_another(
            self, segregation, evidence):
        evidence.append("finding_acknowledged", "model", "m-1",
                        {"finding_id": "f-1"}, actor="j.okafor")
        segregation.check("j.okafor", "finding:extend", "m-1", about="f-2")
