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
