"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The waiver register: controls a model is not meeting, and who said that was
acceptable, until when, and what is being done instead.
"""
from core.waivers.common import (DEFAULT_MAX_DAYS, DEFAULT_RENEWAL_LIMIT,
                                 STATUS_MEANING, STATUSES, WaiverError)
from core.waivers.register import QUORUM_BY_TIER, WAIVABLE, WaiverRegister

__all__ = ["DEFAULT_MAX_DAYS", "DEFAULT_RENEWAL_LIMIT", "QUORUM_BY_TIER",
           "STATUSES", "STATUS_MEANING", "WAIVABLE", "WaiverError",
           "WaiverRegister"]
