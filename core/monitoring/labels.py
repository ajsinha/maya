"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Delayed labels: the reason most performance monitoring is wrong.

A 12-month PD model scores a borrower today. Whether they default is not known
for twelve months. So a performance number computed on this month's cohort is
computed from the outcomes that arrived early — and the outcomes that arrive
early are the fast defaults. The result is not noisy, it is **biased**, and it is
biased towards looking worse or better than reality depending on which tail
matures first. Either way it is not a measurement.

The fix is not statistical, it is bookkeeping. A cohort has a **maturity date**:
the moment by which its outcomes are known. Until then the cohort is not
measurable, and MAYA says so rather than producing a figure.

    scored_at ────────── label_delay ──────────▶ matures_at
                                                      │
                        immature: refuse              ▼  measurable
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.monitoring.common import DAY


@dataclass(frozen=True)
class OutcomeWindow:
    """When a cohort's labels can be trusted to be complete."""
    label_delay_days: float

    @property
    def delay_seconds(self) -> float:
        return self.label_delay_days * DAY

    def matures_at(self, scored_at: float) -> float:
        return scored_at + self.delay_seconds

    def is_mature(self, scored_at: float, now: Optional[float] = None) -> bool:
        moment = now if now is not None else time.time()
        return moment >= self.matures_at(scored_at)

    def split(self, rows: Sequence[Dict[str, Any]],
              now: Optional[float] = None) -> Tuple[List[Dict[str, Any]],
                                                    List[Dict[str, Any]]]:
        """(mature, immature) by each row's own scored_at.

        Split per row rather than per batch: a monitoring window usually spans
        several days, and the older end of it may be measurable while the newer
        end is not. Discarding the whole window because part of it is immature
        throws away the only data that could have been used.
        """
        moment = now if now is not None else time.time()
        mature, immature = [], []
        for row in rows:
            target = mature if self.is_mature(row.get("scored_at", 0.0), moment) else immature
            target.append(row)
        return mature, immature

    def report(self, rows: Sequence[Dict[str, Any]],
               now: Optional[float] = None) -> Dict[str, Any]:
        """What is measurable here, and when the rest becomes measurable."""
        moment = now if now is not None else time.time()
        mature, immature = self.split(rows, moment)
        next_maturity = min((self.matures_at(r.get("scored_at", 0.0))
                             for r in immature), default=None)
        return {
            "measurable": len(mature), "waiting": len(immature),
            "label_delay_days": self.label_delay_days,
            "next_maturity_at": next_maturity,
            "detail": (f"{len(mature)} of {len(rows)} rows have matured "
                       f"({self.label_delay_days:g} day outcome window)"),
        }


def labelled(rows: Sequence[Dict[str, Any]]) -> Tuple[List[int], List[float]]:
    """Split matured rows into (labels, scores) for the catalogue tests."""
    pairs = [(r["label"], r["score"]) for r in rows
             if r.get("label") is not None and r.get("score") is not None]
    return [p[0] for p in pairs], [p[1] for p in pairs]
