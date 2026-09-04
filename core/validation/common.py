"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The vocabulary validation shares.

Severity is an ordered scale, not a label set, because the register has to answer
"what is the worst thing still open against this model" — and that question needs
a total order. Remediation windows are attached to severity here so that a due
date is derived from how bad something is rather than negotiated per finding.
"""
from __future__ import annotations

DAY = 86400.0

# Worst first. Index doubles as the ordering.
SEVERITIES = ("Critical", "High", "Medium", "Low", "Observation")
OUTCOMES = ("approved", "approved_with_conditions", "rejected", "deferred")
KINDS = ("initial", "periodic", "targeted", "change", "vendor",
         "annual_review", "tier_review")
SOURCES = ("validation", "monitoring", "audit", "regulator", "self_identified")
STATUSES = ("open", "in_remediation", "resolved", "closed")

# Remediation window by severity. A Critical finding is not a diary entry.
REMEDIATION_DAYS = {"Critical": 30, "High": 90, "Medium": 180,
                    "Low": 365, "Observation": 365}

# Which severities block by default when raised. Overridable per finding, but
# the default matters: it is what happens when nobody makes a decision.
BLOCKING_BY_DEFAULT = ("Critical",)


class ValidationError(RuntimeError):
    """A validation operation was refused. The message always says why."""


def severity_rank(severity: str) -> int:
    """Lower is worse. Unknown severities sort last rather than crashing a list."""
    return SEVERITIES.index(severity) if severity in SEVERITIES else len(SEVERITIES)


def worst(severities) -> str:
    """The most severe of a collection, or 'Observation' if it is empty."""
    return min(severities, key=severity_rank, default="Observation")


# ---------------------------------------------------------------------------
# The workflow around a finding: assignment, acknowledgement, plan, extension.
# ---------------------------------------------------------------------------
# A finding is raised with an owner and a date derived from its severity, and
# closed by somebody who does not own it. Everything between those two acts is
# recorded as an ACT rather than as a status, because a status column can
# disagree with what happened and an append-only act cannot.

ASSIGNED, ACKNOWLEDGED, PLANNED, EXTENDED = (
    "assigned", "acknowledged", "planned", "extended")
ACTS = (ASSIGNED, ACKNOWLEDGED, PLANNED, EXTENDED)

ACT_MEANING = {
    ASSIGNED: "ownership was handed from one person to another, with a reason",
    ACKNOWLEDGED: "the owner accepted the finding as theirs and named a date",
    PLANNED: "what will be done to close it was written down",
    EXTENDED: "the due date was moved, by somebody who does not own it",
}

# How long an owner has to accept a finding before the silence is itself the
# problem. A finding nobody has accepted looks exactly like one being worked on.
DEFAULT_ACKNOWLEDGE_DAYS = 5.0

# Extensions before the extension itself becomes a finding. The overlay
# register's renewal limit is the same shape of answer to the same shape of
# problem: a date moved often enough is not a date.
DEFAULT_EXTENSION_LIMIT = 2

# An overdue finding this old has stopped being only its owner's problem.
DEFAULT_ESCALATE_DAYS = 7.0

# Escalation is BY ROLE, not by hierarchy: MAYA does not know who reports to
# whom and should not pretend to. Deliberately the same role notification
# escalates to (``core.notify.common.ESCALATION_ROLE``); a test pins the two
# together so the platform cannot grow two different escalation paths.
ESCALATION_ROLE = "model_risk_manager"

# Ageing buckets. A committee asks "how long have these been open", and the
# answer has to be a distribution rather than a mean, because one finding open
# for four years and nine opened last week average to something reassuring.
AGE_BUCKETS = ((30.0, "0-30 days"), (60.0, "31-60 days"), (90.0, "61-90 days"),
               (180.0, "91-180 days"), (None, "over 180 days"))


class FindingWorkflowError(ValidationError):
    """A workflow act was refused, in the coded form the route layer maps.

    A subclass of ValidationError so that anything already catching a validation
    refusal keeps working, but carrying ``code``/``detail``/``remediation``
    because "policy violation" tells nobody what to do instead.
    """

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self):
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


def same_person(a: str, b: str) -> bool:
    """Whether two identities name the same person.

    The platform writes an owner as ``person/j.okafor`` and authenticates the
    same human as ``j.okafor``. A duties check that compares the two with ``==``
    is one anybody can step around by dropping seven characters, which is the
    whole value of it gone.
    """
    def bare(who: str) -> str:
        return (who or "").strip().rsplit("/", 1)[-1].casefold()

    return bool(a) and bool(b) and bare(a) == bare(b)
