"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What goes in the accounts about the part of the number that is not the model.

IFRS 9 requires disclosure of the significant judgements applied in measuring
expected credit losses, and every bank makes them: a management overlay for a
sector the model handles badly, a haircut for a shock the calibration window did
not contain. The number reported is almost always assembled in a spreadsheet at
period end, from a list somebody keeps.

The overlay register already holds the parts — magnitude against base, direction,
rationale, basis, renewals, expiry. This assembles the extract, and three things
about it are decisions rather than arithmetic.

**An unmeasured overlay cannot be disclosed and is named.** It is active, it is
changing the number, and nobody has recorded by how much. Leaving it out
understates the judgement component of the provision; putting it in at zero is
worse, because zero is a measurement. So it appears as an explicit hole in the
extract with the models it sits on — and the extract says it is incomplete.

**Movement is reported against the prior period, and a new overlay is separated
from a grown one.** Those are different disclosures: one is a judgement somebody
newly formed, the other is a judgement that got bigger, and the second is the one
an auditor asks about. A single "change in overlays" figure collapses them.

**An overlay renewed past its own limit is reported as structural.** A management
adjustment that has been continued five times is not a temporary judgement about
an unusual period; it is a permanent correction to a model that nobody has fixed,
and disclosing it beside genuine period judgements makes both harder to read.
That is the overlay register's own central rule — *a permanent adjustment is a
model defect* — arriving in the accounts.

MAYA produces an extract and not a disclosure note. The figures come from the
register; the words, the materiality judgement and the decision to file are the
firm's, and the extract says so in itself.
"""
from __future__ import annotations

import time
from itertools import pairwise
from typing import Any, Dict, List, Optional, Sequence

from core.log import get_logger
from core.overlays.common import OverlayError

logger = get_logger(__name__)

#: How many continuations make an adjustment structural rather than periodic.
#: The overlay register enforces a renewal limit already; this is the reading of
#: that fact for the accounts, and it is deliberately the same number so a firm
#: cannot be inside one and outside the other.
STRUCTURAL_AFTER = 3

NEW, GREW, SHRANK, UNCHANGED, ENDED = (
    "new", "grew", "shrank", "unchanged", "ended")
MOVEMENTS = (NEW, GREW, SHRANK, UNCHANGED, ENDED)


class Disclosure:
    """Assembles the post-model-adjustment extract for a reporting period."""

    def __init__(self, overlays, registry, renewal_limit: int = STRUCTURAL_AFTER):
        self.overlays, self.registry = overlays, registry
        self.renewal_limit = renewal_limit

    # ---------------------------------------------------------------- extract
    def extract(self, period: str, prior: str = "",
                now: Optional[float] = None) -> Dict[str, Any]:
        """The judgement component of the number, for one reporting period."""
        if not (period or "").strip():
            raise OverlayError(
                "period_required",
                "a disclosure extract is about a reporting period, and one "
                "without a period is a snapshot of today that will be filed as "
                "a quarter",
                "name the period the measurements were taken for")
        moment = now if now is not None else time.time()
        rows, unmeasured = [], []
        for model in self.registry.list():
            for overlay in self.overlays.for_model(model["id"]):
                measured = self._measured(overlay, period)
                before = self._measured(overlay, prior) if prior else None
                if measured is None:
                    if overlay["status"] == "active":
                        unmeasured.append({
                            "urn": model["urn"], "overlay": overlay["id"],
                            "name": overlay["name"], "kind": overlay["kind"],
                            "why": ("active in this period and never measured, "
                                    "so it is changing the number by an amount "
                                    "nobody has recorded")})
                    continue
                rows.append(self._row(model, overlay, measured, before, moment))

        by_model = self._by_model(rows)
        structural = [r for r in rows if r["structural"]]
        total = round(sum(r["magnitude"] for r in rows), 2)
        return {
            "period": period, "prior_period": prior or None,
            "extracted_at": moment,
            "overlays": rows, "count": len(rows),
            "by_model": by_model,
            "aggregate_magnitude": total,
            "movement": self._movement(rows),
            "structural": [r["overlay"] for r in structural],
            "structural_magnitude": round(
                sum(r["magnitude"] for r in structural), 2),
            "unmeasured": unmeasured,
            "complete": not unmeasured,
            "is_a_disclosure_note": False,
            "detail": self._detail(rows, unmeasured, structural, total, prior),
        }

    def _measured(self, overlay: Dict[str, Any],
                  period: str) -> Optional[Dict[str, Any]]:
        if not period:
            return None
        return next((m for m in self.overlays.measurements_for(overlay["id"])
                     if m["period"] == period), None)

    def _row(self, model, overlay, measured, before, moment) -> Dict[str, Any]:
        continuations = self.overlays.continuations(overlay)
        magnitude = float(measured.get("magnitude") or 0.0)
        prior_magnitude = (float(before.get("magnitude") or 0.0)
                           if before else None)
        return {
            "urn": model["urn"], "model": model.get("name"),
            "overlay": overlay["id"], "name": overlay["name"],
            "kind": overlay["kind"], "direction": overlay.get("direction"),
            "rationale": overlay.get("rationale"),
            "basis": overlay.get("basis"),
            "owner": overlay.get("owner"),
            "approved_by": overlay.get("approved_by"),
            "status": overlay["status"],
            "magnitude": round(magnitude, 2),
            "pct_of_base": measured.get("pct_of_base"),
            "prior_magnitude": (round(prior_magnitude, 2)
                                if prior_magnitude is not None else None),
            "movement": _movement_of(magnitude, prior_magnitude),
            "continuations": continuations,
            # The overlay register's own central rule, arriving in the
            # accounts: a permanent adjustment is a model defect.
            "structural": continuations >= self.renewal_limit,
            "expires_at": overlay.get("expires_at"),
            "expired": bool(overlay.get("expires_at")
                            and overlay["expires_at"] < moment
                            and overlay["status"] == "active"),
        }

    @staticmethod
    def _by_model(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            held = grouped.setdefault(row["urn"], {
                "urn": row["urn"], "model": row["model"], "overlays": 0,
                "magnitude": 0.0, "structural": 0})
            held["overlays"] += 1
            held["magnitude"] = round(held["magnitude"] + row["magnitude"], 2)
            held["structural"] += int(row["structural"])
        out = list(grouped.values())
        out.sort(key=lambda r: -abs(r["magnitude"]))
        return out

    @staticmethod
    def _movement(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        """New and grown separately. They are different disclosures."""
        buckets: Dict[str, Dict[str, Any]] = {
            m: {"count": 0, "magnitude": 0.0} for m in MOVEMENTS}
        for row in rows:
            bucket = buckets[row["movement"]]
            bucket["count"] += 1
            bucket["magnitude"] = round(
                bucket["magnitude"] + row["magnitude"], 2)
        return {m: b for m, b in buckets.items() if b["count"]}

    def _detail(self, rows, unmeasured, structural, total, prior) -> str:
        if not rows and not unmeasured:
            return ("no measured overlay in this period. Worth reading against "
                    "the overlay register rather than as an absence of "
                    "judgement: an adjustment nobody measured does not appear "
                    "here")
        out = (f"{len(rows)} measured overlay(s) adjusting the number by "
               f"{total:,.2f} in aggregate")
        if prior:
            out += (". New and grown are reported separately because they are "
                    "different disclosures: one is a judgement somebody newly "
                    "formed, the other is a judgement that got bigger, and the "
                    "second is the one an auditor asks about")
        if structural:
            out += (f". {len(structural)} have been continued "
                    f"{self.renewal_limit} times or more and are reported as "
                    f"**structural** — an adjustment renewed that often is not "
                    f"a temporary judgement about an unusual period, it is a "
                    f"permanent correction to a model nobody has fixed, and "
                    f"disclosing it beside genuine period judgements makes both "
                    f"harder to read")
        if unmeasured:
            out += (f". **This extract is incomplete**: {len(unmeasured)} "
                    f"active overlay(s) have no measurement for this period. "
                    f"They are changing the number by an amount nobody "
                    f"recorded, and they are named here rather than left out — "
                    f"omitting them understates the judgement component, and "
                    f"including them at zero would be worse, because zero is a "
                    f"measurement")
        out += (". MAYA produces an extract and not a disclosure note: the "
                "figures are the register's, the words and the materiality "
                "judgement are the firm's")
        return out

    # ------------------------------------------------------------------ trend
    def trend(self, periods: Sequence[str]) -> Dict[str, Any]:
        """The judgement component across periods, in the order given.

        A rising overlay total across four quarters is the disclosure a reader
        actually wants and the one a period-at-a-time extract cannot give.
        """
        points = []
        for index, period in enumerate(periods):
            prior = periods[index - 1] if index else ""
            out = self.extract(period, prior=prior)
            points.append({
                "period": period, "overlays": out["count"],
                "magnitude": out["aggregate_magnitude"],
                "structural": len(out["structural"]),
                "unmeasured": len(out["unmeasured"]),
                "complete": out["complete"]})
        rising = (len(points) >= 3
                  and all(b["magnitude"] >= a["magnitude"]
                          for a, b in pairwise(points))
                  and points[-1]["magnitude"] > points[0]["magnitude"])
        return {
            "points": points, "periods": len(points),
            "monotonically_rising": rising,
            "any_incomplete": [p["period"] for p in points
                               if not p["complete"]],
            "detail": (
                f"{len(points)} period(s)"
                + (". The judgement component has risen in every one of them, "
                   "which is the shape a model that needs fixing makes: each "
                   "quarter's adjustment is defensible on its own and the "
                   "series is the finding"
                   if rising else "")
                + (f". {sum(1 for p in points if not p['complete'])} period(s) "
                   f"are incomplete, so the trend is over a moving definition "
                   f"of the total" if any(not p["complete"] for p in points)
                   else "")),
        }


def _movement_of(magnitude: float, prior: Optional[float]) -> str:
    if prior is None:
        return NEW
    if magnitude == 0.0 and prior != 0.0:
        return ENDED
    if abs(magnitude) > abs(prior):
        return GREW
    if abs(magnitude) < abs(prior):
        return SHRANK
    return UNCHANGED
