"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The estate view.

What needs doing, and how the whole population is faring. Both are derived from
the same state everything else reads: there is no task table and no summary
table, because either would be a second source of truth that goes wrong within a
week — and a stale worklist is worse than none, since somebody will act on it.
"""
from core.estate.summary import EstateSummary
from core.estate.worklist import HORIZON_DAYS, Item, WorkList

__all__ = ["WorkList", "EstateSummary", "Item", "HORIZON_DAYS"]
