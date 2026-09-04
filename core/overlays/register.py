"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The overlay register.

Four rules are enforced here rather than trusted to process, and each exists
because of a way overlays actually go wrong.

**An overlay must be time-boxed.** An adjustment with no end date is a model
change nobody versioned, and it will still be running when the people who
approved it have left.

**The proposer may not approve.** An adjustment one person can both propose and
approve is not a control, it is a preference.

**Renewal requires a measurement.** You may not extend an adjustment whose size
you have not measured this period. "We still need the overlay" and "the overlay
is £40m" are different statements, and only the second can be challenged.

**Persistent overlays raise findings.** Past the renewal limit, the register
raises a finding against the model — because at that point the overlay has
stopped being a temporary adjustment and become an unversioned model change.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.authz.common import same_person
from core.evidence import EvidenceEngine
from core.overlays import analysis
from core.overlays.common import (DAY, DEFAULT_MAX_DAYS, DEFAULT_RENEWAL_LIMIT,
                                  DIRECTIONS, KINDS, OverlayError)
from core.log import get_logger
from db import MeasurementRepository, OverlayRepository

logger = get_logger(__name__)


class OverlayRegister:
    """Proposes, approves, measures, renews and retires post-model adjustments."""

    def __init__(self, overlays: OverlayRepository,
                 measurements: MeasurementRepository, evidence: EvidenceEngine,
                 findings=None, max_days: int = DEFAULT_MAX_DAYS,
                 renewal_limit: int = DEFAULT_RENEWAL_LIMIT):
        self.overlays, self.measurements = overlays, measurements
        self.evidence, self.findings = evidence, findings
        self.max_days, self.renewal_limit = max_days, renewal_limit

    # -------------------------------------------------------------- propose
    def propose(self, model_id: str, name: str, kind: str, rationale: str,
                owner: str, direction: str = "increase",
                basis: Optional[Dict[str, Any]] = None,
                model_version_id: Optional[str] = None,
                days: Optional[int] = None, actor: str = "system") -> Dict[str, Any]:
        if kind not in KINDS:
            raise OverlayError("unknown_kind", f"unknown overlay kind '{kind}'",
                               f"expected one of {', '.join(KINDS)}")
        if direction not in DIRECTIONS:
            raise OverlayError("unknown_direction",
                               f"unknown direction '{direction}'",
                               f"expected one of {', '.join(DIRECTIONS)}")
        if not rationale.strip():
            raise OverlayError(
                "rationale_required",
                "an overlay must say what the model is getting wrong and why this "
                "corrects it",
                "supply a rationale; it is what a validator will challenge")
        window = days or self.max_days
        if window > self.max_days:
            raise OverlayError(
                "window_too_long",
                f"{window} days exceeds the {self.max_days}-day limit for a single "
                "overlay period",
                "propose a shorter period and renew it, so the adjustment is "
                "re-examined rather than forgotten")
        row = {"model_id": model_id, "model_version_id": model_version_id,
               "reference": self._reference(model_id), "name": name, "kind": kind,
               "direction": direction, "rationale": rationale, "basis": basis or {},
               "owner": owner, "proposed_by": actor, "approved_by": None,
               "status": "proposed", "effective_from": None, "expires_at": None,
               "renewals": 0, "finding_id": None, "created_at": time.time(),
               "closed_at": None, "closure_reason": None}
        self.overlays.add(row)
        self.evidence.append("overlay_proposed", "model", model_id,
                             {"overlay_id": row["id"], "reference": row["reference"],
                              "kind": kind, "rationale": rationale}, actor=actor)
        return self.overlays.one(id=row["id"])

    def _reference(self, model_id: str) -> str:
        return f"OVL-{len(self.overlays.many(model_id=model_id)) + 1:03d}"

    # -------------------------------------------------------------- approve
    def approve(self, overlay_id: str, actor: str,
                days: Optional[int] = None) -> Dict[str, Any]:
        """Approve and start the clock. The proposer may not do this."""
        row = self.require(overlay_id)
        if row["status"] != "proposed":
            raise OverlayError("not_proposed",
                               f"this overlay is '{row['status']}', not proposed", "")
        if same_person(actor, row["proposed_by"]):
            raise OverlayError(
                "self_approval",
                f"{actor} proposed this overlay and cannot also approve it",
                "an adjustment one person can both propose and approve is a "
                "preference, not a control")
        now = time.time()
        window = days or self.max_days
        self.overlays.set({"status": "active", "approved_by": actor,
                           "effective_from": now,
                           "expires_at": now + window * DAY}, id=overlay_id)
        self.evidence.append("overlay_approved", "model", row["model_id"],
                             {"overlay_id": overlay_id, "reference": row["reference"],
                              "days": window}, actor=actor)
        return self.overlays.one(id=overlay_id)

    # -------------------------------------------------------------- measure
    def measure(self, overlay_id: str, period: str, base_value: float,
                adjusted_value: float, actor: str = "system") -> Dict[str, Any]:
        """Record how large the adjustment actually was this period.

        Magnitude relative to the model's own output is the number that makes an
        overlay challengeable. "We still need it" cannot be argued with;
        "it is 18% of the provision" can.
        """
        row = self.require(overlay_id)
        if self.measurements.one(overlay_id=overlay_id, period=period):
            raise OverlayError("already_measured",
                               f"{overlay_id} is already measured for {period}",
                               "one measurement per period")
        magnitude = adjusted_value - base_value
        measurement = {"overlay_id": overlay_id, "period": period,
                       "base_value": base_value, "adjusted_value": adjusted_value,
                       "magnitude": magnitude,
                       "pct_of_base": (magnitude / base_value) if base_value else None,
                       "measured_by": actor, "measured_at": time.time()}
        self.measurements.add(measurement)
        self.evidence.append("overlay_measured", "model", row["model_id"],
                             {"overlay_id": overlay_id, "period": period,
                              "magnitude": magnitude,
                              "pct_of_base": measurement["pct_of_base"]}, actor=actor)
        return self.measurements.one(id=measurement["id"])

    # --------------------------------------------------------------- renew
    def renew(self, overlay_id: str, actor: str, days: Optional[int] = None,
              period: Optional[str] = None) -> Dict[str, Any]:
        """Extend an overlay. Refused unless its size has been measured."""
        row = self.require(overlay_id)
        if row["status"] != "active":
            raise OverlayError("not_active",
                               f"this overlay is '{row['status']}', not active", "")
        # An owner is written `person/j.okafor` and authenticated as
        # `j.okafor`, so `==` here compared two spellings of the same human and
        # found them different. The renewal control -- the moment somebody
        # independent asks whether the model should be fixed instead of adjusted
        # -- was inert over HTTP for as long as it has existed.
        if same_person(actor, row["owner"]):
            raise OverlayError(
                "self_renewal",
                f"{actor} owns this overlay and cannot also renew it",
                "renewal is the point at which somebody independent asks whether "
                "the model should be fixed instead")
        measurements = self.measurements_for(overlay_id)
        if not measurements:
            raise OverlayError(
                "unmeasured",
                "this overlay has never been measured, so there is nothing to "
                "renew on the basis of",
                "record a magnitude for the current period first")
        if period and not self.measurements.one(overlay_id=overlay_id, period=period):
            raise OverlayError("period_unmeasured",
                               f"no measurement recorded for {period}",
                               "measure the current period before renewing")

        now, window = time.time(), days or self.max_days
        renewals = row["renewals"] + 1
        self.overlays.set({"renewals": renewals, "expires_at": now + window * DAY},
                          id=overlay_id)
        self.evidence.append("overlay_renewed", "model", row["model_id"],
                             {"overlay_id": overlay_id, "renewals": renewals,
                              "days": window}, actor=actor)

        fresh = self.overlays.one(id=overlay_id)
        self._escalate_if_persistent(fresh, measurements, actor)
        return self.overlays.one(id=overlay_id)

    def _escalate_if_persistent(self, overlay: Dict[str, Any],
                                measurements: List[Dict[str, Any]],
                                actor: str) -> None:
        """Past the renewal limit, this is a model defect. Say so, once."""
        reading = analysis.assess(overlay, measurements, self.renewal_limit)
        if not reading["escalate"] or overlay.get("finding_id") or not self.findings:
            return
        finding = self.findings.raise_finding(
            overlay["model_id"], "High",
            title=f"Persistent overlay: {overlay['name']} ({overlay['reference']})",
            owner=overlay["owner"],
            description=("; ".join(reading["reasons"]) +
                         ". A persistent overlay is an unversioned model change: "
                         "either the model should be corrected, or the adjustment "
                         "should be built into it and validated."),
            category="overlay", source="self_identified",
            model_version_id=overlay.get("model_version_id"), actor=actor)
        self.overlays.set({"finding_id": finding["id"]}, id=overlay["id"])
        logger.warning("overlay %s escalated after %d renewals",
                       overlay["reference"], overlay["renewals"])

    # ---------------------------------------------------------------- close
    def close(self, overlay_id: str, status: str, reason: str,
              actor: str = "system") -> Dict[str, Any]:
        """Withdraw an overlay, or absorb it into the model.

        `absorbed` is the outcome that should be aimed at: the adjustment stopped
        being an overlay because the model now does it.
        """
        if status not in ("withdrawn", "absorbed", "expired"):
            raise OverlayError("unknown_closure", f"cannot close as '{status}'",
                               "close as withdrawn, absorbed or expired")
        if not reason.strip():
            raise OverlayError("reason_required", "closing an overlay needs a reason", "")
        row = self.require(overlay_id)
        self.overlays.set({"status": status, "closed_at": time.time(),
                           "closure_reason": reason}, id=overlay_id)
        self.evidence.append(f"overlay_{status}", "model", row["model_id"],
                             {"overlay_id": overlay_id,
                              "reference": row["reference"], "reason": reason},
                             actor=actor)
        return self.overlays.one(id=overlay_id)

    def sweep_expired(self, model_id: str, now: Optional[float] = None,
                      actor: str = "system") -> List[Dict[str, Any]]:
        """Close overlays whose window has passed.

        Expiry is already computed, so this only makes the stored status agree
        with the computed one — nothing depends on the sweep having run.
        """
        closed = []
        for row in self.overlays.many(model_id=model_id, status="active"):
            if analysis.is_expired(row, now):
                closed.append(self.close(row["id"], "expired",
                                         "the approved window elapsed", actor))
        return closed

    # ----------------------------------------------------------------- query
    def get(self, overlay_id: str) -> Optional[Dict[str, Any]]:
        return self.overlays.one(id=overlay_id)

    def require(self, overlay_id: str) -> Dict[str, Any]:
        row = self.get(overlay_id)
        if row is None:
            raise OverlayError("no_overlay", f"no overlay {overlay_id}", "")
        return row

    def for_model(self, model_id: str) -> List[Dict[str, Any]]:
        return self.overlays.many(model_id=model_id)

    def measurements_for(self, overlay_id: str) -> List[Dict[str, Any]]:
        return self.measurements.many(overlay_id=overlay_id)

    def reading(self, overlay_id: str, now: Optional[float] = None) -> Dict[str, Any]:
        overlay = self.require(overlay_id)
        return {**overlay, "measurements": self.measurements_for(overlay_id),
                "assessment": analysis.assess(
                    overlay, self.measurements_for(overlay_id),
                    self.renewal_limit, now=now)}

    def status(self, model_id: str, now: Optional[float] = None) -> Dict[str, Any]:
        """What a risk committee actually asks: how much of this is the model,
        and how much is us."""
        overlays = self.for_model(model_id)
        by_overlay = {o["id"]: self.measurements_for(o["id"]) for o in overlays}
        return {**analysis.portfolio(overlays, by_overlay, now),
                "detail_rows": [
                    {**o, "assessment": analysis.assess(o, by_overlay[o["id"]],
                                                        self.renewal_limit, now=now)}
                    for o in overlays]}
