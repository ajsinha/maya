"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The overlay vocabulary.

An overlay is a human adjustment applied on top of a model's output: a
management add-on to an IFRS 9 provision, a haircut on a valuation, an
exclusion of a segment the model handles badly, an expert uplift for a risk the
model does not see.

Every bank has them. Almost none can answer three questions about them in
aggregate: how large are they, how long have they been running, and which of
them have quietly become permanent.

That third question is what this package exists for. **An overlay renewed again
and again is evidence that the model is wrong**, not that the overlay is needed —
and the point at which that becomes true should be a threshold in a register
rather than a judgement nobody is asked to make.
"""
from __future__ import annotations

from typing import Dict, Tuple

DAY = 86400.0

# What is being adjusted.
PARAMETER = "parameter"       # an input or coefficient is overridden
OUTPUT = "output"             # the model's answer is adjusted after the fact
EXCLUSION = "exclusion"       # a population the model is not trusted on
JUDGEMENTAL = "judgemental"   # an expert addition for a risk the model cannot see

KINDS: Tuple[str, ...] = (PARAMETER, OUTPUT, EXCLUSION, JUDGEMENTAL)

KIND_MEANING: Dict[str, str] = {
    PARAMETER: "an input or coefficient is overridden before the model runs",
    OUTPUT: "the model's answer is adjusted after it has produced one",
    EXCLUSION: "a population the model is not trusted on is carved out",
    JUDGEMENTAL: "an expert addition for a risk the model cannot see",
}

DIRECTIONS: Tuple[str, ...] = ("increase", "decrease", "either")
STATUSES: Tuple[str, ...] = ("proposed", "active", "expired", "withdrawn", "absorbed")

# Defaults, all overridable by configuration, because how long an overlay may
# run before it stops being temporary is a policy question.
DEFAULT_MAX_DAYS = 180
DEFAULT_RENEWAL_LIMIT = 2      # renewals before the register raises a finding
DEFAULT_MATERIAL_PCT = 0.05    # 5% of base is material enough to escalate


class OverlayError(RuntimeError):
    """An overlay operation was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}
