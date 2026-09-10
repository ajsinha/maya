"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Shared vocabulary for the waiver register.
"""
from __future__ import annotations

from typing import Dict, Tuple

DAY = 86400.0

#: The longest a single waiver may run before somebody has to decide again.
#: Ninety days rather than a year, because the decision this bounds is *should
#: this control still be relaxed*, and a year is long enough for the people who
#: took it to have moved on.
DEFAULT_MAX_DAYS = 90

#: How many renewals before the register stops treating it as temporary. Three
#: renewals of a ninety-day waiver is a year of not doing something.
DEFAULT_RENEWAL_LIMIT = 3

PROPOSED = "proposed"
STATUSES: Tuple[str, ...] = (PROPOSED, "active", "expired", "revoked")

STATUS_MEANING: Dict[str, str] = {
    PROPOSED: "asked for, and not yet signed by enough people for this tier",
    "active": "in force — this control is currently not being met, on purpose",
    "expired": "the window ended. The control applies again, whether or not "
               "anybody has started meeting it",
    "revoked": "ended early, either because the control is met again or "
               "because the exception was withdrawn",
}


class WaiverError(RuntimeError):
    """A waiver operation was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}
