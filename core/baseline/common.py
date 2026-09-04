"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The baseline vocabulary.

The distinction this package exists to preserve: **debt is not breach**. A Tier 1
model that arrived last week with no validation history and a Tier 1 model that
missed its scheduled validation are completely different situations, and a
register that renders them the same colour is one the model risk office stops
believing within a month.

Debt is dated. It becomes a breach when it passes its expiry, and not before.
"""
from __future__ import annotations

from typing import Dict, Tuple

DAY = 86400.0

STATUSES: Tuple[str, ...] = ("open", "closed", "breached")

# Board-approved debt expiry by tier: how long a baselined model may carry a gap
# before it stops being debt and becomes a breach. Configuration, because it is
# a board decision and not ours.
DEFAULT_EXPIRY_MONTHS: Dict[int, int] = {1: 18, 2: 30, 3: 36, 4: 36}


class BaselineError(RuntimeError):
    """A baseline operation was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}
