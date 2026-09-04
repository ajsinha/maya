"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The vocabulary of notification.
"""
from __future__ import annotations

from typing import Dict, Tuple

LOG, WEBHOOK, EMAIL = "log", "webhook", "email"
CHANNELS: Tuple[str, ...] = (LOG, WEBHOOK, EMAIL)

CHANNEL_MEANING: Dict[str, str] = {
    LOG: "written to the platform log; always available, and the honest default "
         "for an instance with nowhere to send",
    WEBHOOK: "posted to a URL — Slack, Teams, a ticketing system, anything that "
             "accepts JSON",
    EMAIL: "sent through a configured SMTP relay",
}

SENT, FAILED, SUPPRESSED = "sent", "failed", "suppressed"
STATES: Tuple[str, ...] = (SENT, FAILED, SUPPRESSED)

# How long an unchanged worklist stays quiet. Nothing is more certain to be
# ignored than a daily message that says exactly what yesterday's said.
DEFAULT_QUIET_HOURS = 24.0

# An overdue item this old is escalated to the second line as well as to whoever
# owns it. Not a hierarchy — the platform does not have one — but a role.
DEFAULT_ESCALATE_DAYS = 7.0
ESCALATION_ROLE = "model_risk_manager"


class NotifyError(RuntimeError):
    """A notification was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}
