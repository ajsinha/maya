"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — reading a findings register: ageing and escalation.

Nothing here is stored, which is the property worth testing: every number is
computed from the finding row and the append-only acts against it, so there is
no status table that can disagree with the register. That makes the boundaries
testable as arithmetic — exactly seven days past a date, exactly five days
unaccepted — without waiting a week for the clock.

The cases pass an explicit `now` for that reason. A case that used the wall
clock would be testing whichever side of a boundary the test happened to run
on.
"""
from __future__ import annotations

from core.validation import ageing
from core.validation.common import (DAY, DEFAULT_ACKNOWLEDGE_DAYS,
                                    DEFAULT_ESCALATE_DAYS, ESCALATION_ROLE)
from qa.regression_suite.scenarios.common import (FAIL, PASS, Ctx,
                                                  Result, case)

NOW = 1_800_000_000.0
F = "/api/v1/findings"


def _finding(**over) -> dict:
    """A finding row shaped as the register stores it."""
    return {"id": over.pop("id", "fnd-qa"), "model_id": "mdl-qa",
            "severity": "High", "status": "open", "blocking": False,
            "owner": "person/owner", "title": "A QA finding",
            "raised_at": NOW - 10 * DAY, "due_at": NOW + 30 * DAY,
            "closed_at": None, **over}


def _acknowledged(at: float) -> list:
    return [{"finding_id": "fnd-qa", "model_id": "mdl-qa",
             "act": "acknowledged", "actor": "person/owner",
             "from_owner": None, "to_owner": None, "reason": "", "plan": "p",
             "committed_at": NOW + 20 * DAY, "due_before": None,
             "due_after": None, "acted_at": at}]


@case("QA-AM-123",
      "Ageing over a model with one finding open four years and nine opened "
      "last week")
def am_123(ctx: Ctx) -> Result:
    """The reason the buckets exist. A mean over this register reads as
    roughly five months, which describes none of the ten findings."""
    rows = [_finding(id="fnd-old", raised_at=NOW - 4 * 365 * DAY)]
    rows += [_finding(id=f"fnd-{i}", raised_at=NOW - 5 * DAY) for i in range(9)]
    got = ageing.profile(rows, {r["id"]: [] for r in rows}, NOW)
    if "by_age" not in got:
        return FAIL, "the profile carries no distribution, only totals"
    buckets = got["by_age"]
    if buckets.get("over 180 days") != 1 or buckets.get("0-30 days") != 9:
        return FAIL, (f"the distribution does not separate the four-year "
                      f"finding from the nine fresh ones: {buckets}")
    if "mean_age_days" not in got:
        return FAIL, "the mean is absent, so a reader cannot see it is misleading"
    mean = got["mean_age_days"]
    if not 140 < mean < 160:
        return FAIL, f"the mean is {mean}, which is not the arithmetic mean"
    if (got.get("oldest") or {}).get("finding_id") != "fnd-old":
        return FAIL, "the oldest finding is not named beside the distribution"
    return PASS, (f"{buckets}, mean {mean} days shown beside it rather than "
                  f"instead of it")


@case("QA-AM-124", "Ageing where every finding is closed")
def am_124(ctx: Ctx) -> Result:
    """A register whose findings are all closed is a good register, and it
    must not read as an empty one or as a broken one."""
    rows = [_finding(id=f"fnd-{i}", status="closed", closed_at=NOW - DAY)
            for i in range(3)]
    got = ageing.profile(rows, {r["id"]: [] for r in rows}, NOW)
    if got.get("open") != 0:
        return FAIL, f"open reads {got.get('open')} with everything closed"
    if got.get("closed") != 3:
        return FAIL, f"closed reads {got.get('closed')} rather than 3"
    if got.get("worst_severity") is not None:
        return FAIL, (f"worst_severity is '{got.get('worst_severity')}' with "
                      f"nothing open, so a closed register reports a severity "
                      f"nobody has to act on")
    if got.get("detail") != "nothing is open":
        return FAIL, f"the detail reads '{got.get('detail')}'"
    return PASS, "open 0, closed 3, no worst severity, 'nothing is open'"


@case("QA-AM-125", "Age of a closed finding stops at its closure")
def am_125(ctx: Ctx) -> Result:
    """A closed finding that goes on ageing makes every historical pack
    disagree with the one printed after it."""
    row = _finding(status="closed", raised_at=NOW - 100 * DAY,
                   closed_at=NOW - 40 * DAY)
    first = ageing.age_days(row, NOW)
    later = ageing.age_days(row, NOW + 365 * DAY)
    if round(first, 1) != 60.0:
        return FAIL, f"age reads {first} rather than the 60 days it was open"
    if round(later, 1) != round(first, 1):
        return FAIL, (f"a closed finding aged from {first} to {later} over a "
                      f"year in which nothing happened to it")
    return PASS, f"frozen at {first} days — closed_at minus raised_at"


@case("QA-AM-126", "`days_overdue` for a finding that is not overdue")
def am_126(ctx: Ctx) -> Result:
    """Reported as 0.0, never negative. "Not overdue" is not a quantity, and
    a negative one nets off against a real overdue elsewhere in a sum."""
    row = _finding(due_at=NOW + 30 * DAY)
    late = ageing.days_overdue(row, NOW)
    if late != 0.0:
        return FAIL, (f"a finding due in 30 days reports {late} days overdue; "
                      f"summed across a register that cancels real lateness")
    reading = ageing.reading(row, [], NOW)
    if reading.get("overdue"):
        return FAIL, "flagged overdue 30 days before its date"
    if reading.get("days_overdue") != 0.0:
        return FAIL, f"the reading says {reading.get('days_overdue')}"
    return PASS, "0.0, not -30.0"


@case("QA-AM-127", "Escalation at exactly seven days past the date")
def am_127(ctx: Ctx) -> Result:
    """The boundary is `>` and not `>=`, so the seventh day is still the
    owner's. A boundary nobody decided is a boundary that moves when the
    comparison is rewritten."""
    at_limit = _finding(due_at=NOW - DEFAULT_ESCALATE_DAYS * DAY,
                        raised_at=NOW - 60 * DAY)
    acts = _acknowledged(NOW - 59 * DAY)
    got = ageing.escalation(at_limit, acts, NOW)
    if got["escalate"]:
        return FAIL, (f"escalated at exactly {DEFAULT_ESCALATE_DAYS} days: "
                      f"{got['reasons']}")
    past = _finding(due_at=NOW - (DEFAULT_ESCALATE_DAYS * DAY) - 3600,
                    raised_at=NOW - 60 * DAY)
    beyond = ageing.escalation(past, acts, NOW)
    if not beyond["escalate"]:
        return FAIL, ("an hour past the boundary still does not escalate, so "
                      "the threshold is not where it is documented")
    if beyond["to_role"] != ESCALATION_ROLE:
        return FAIL, (f"escalated to '{beyond['to_role']}' rather than the "
                      f"role the platform names everywhere else")
    return PASS, ("not at 7 days, escalated at 7 days and an hour, to "
                  "the model risk manager")


@case("QA-AM-128", "A blocking finding one hour past its date")
def am_128(ctx: Ctx) -> Result:
    """A blocking finding does not get the seven-day grace the others get:
    while it is open and past its date the model cannot be served at all, so
    lateness is already somebody else's problem."""
    row = _finding(blocking=True, due_at=NOW - 3600, raised_at=NOW - 60 * DAY)
    got = ageing.escalation(row, _acknowledged(NOW - 59 * DAY), NOW)
    if not got["escalate"]:
        return FAIL, ("a blocking finding an hour past its date is not "
                      "escalated, so a model withheld from service is nobody's "
                      "problem for another week")
    if not any("blocking" in r for r in got["reasons"]):
        return FAIL, (f"escalated without saying it is because the finding "
                      f"blocks: {got['reasons']}")
    plain = _finding(due_at=NOW - 3600, raised_at=NOW - 60 * DAY)
    if ageing.escalation(plain, _acknowledged(NOW - 59 * DAY),
                         NOW)["escalate"]:
        return FAIL, ("a non-blocking finding an hour late also escalates, so "
                      "'blocking' is not the thing making the difference")
    return PASS, f"escalated: {got['reasons'][0][:60]}"


@case("QA-AM-129", "A finding unaccepted at exactly five days")
def am_129(ctx: Ctx) -> Result:
    """A finding nobody has accepted looks identical on every dashboard to
    one being worked on. The acknowledge window is what tells them apart, and
    its boundary is `>` like the other one."""
    row = _finding(raised_at=NOW - DEFAULT_ACKNOWLEDGE_DAYS * DAY,
                   due_at=NOW + 30 * DAY)
    at_limit = ageing.escalation(row, [], NOW)
    if at_limit["escalate"]:
        return FAIL, (f"escalated at exactly {DEFAULT_ACKNOWLEDGE_DAYS} days "
                      f"unaccepted: {at_limit['reasons']}")
    beyond = ageing.escalation(row, [], NOW + 3600)
    if not beyond["escalate"]:
        return FAIL, "an hour past the acknowledge window still does not escalate"
    if not any("accepted" in r for r in beyond["reasons"]):
        return FAIL, f"escalated for some other reason: {beyond['reasons']}"
    accepted = ageing.escalation(row, _acknowledged(NOW - 4 * DAY),
                                 NOW + 3600)
    if accepted["escalate"]:
        return FAIL, ("an acknowledged finding still escalates on the "
                      "acknowledge window, so accepting one changes nothing")
    return PASS, "not at 5 days, escalated at 5 days and an hour, silent once accepted"
