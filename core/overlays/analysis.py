"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Reading an overlay register.

The interesting question is never "what overlays exist" — a list answers that,
and every bank has the list. It is **which of these have stopped being
temporary**, and the answer is a function of three things the register already
holds: how many times an overlay has been renewed, how large it is relative to
the model's own output, and how long it has been running.

The judgement encoded here is deliberately simple and deliberately stated in the
open: an overlay that has been renewed past its limit is a **model defect**, and
should be raised as one. The alternative — leaving it to somebody to notice —
is how a "temporary" management adjustment reaches its fourth year.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.overlays.common import DAY, DEFAULT_MATERIAL_PCT, DEFAULT_RENEWAL_LIMIT


def age_days(overlay: Dict[str, Any], now: Optional[float] = None) -> float:
    start = overlay.get("effective_from") or overlay["created_at"]
    return ((now if now is not None else time.time()) - start) / DAY


def is_expired(overlay: Dict[str, Any], now: Optional[float] = None) -> bool:
    """Expiry is computed, not swept. An overlay past its date is expired
    whether or not anything has run to notice."""
    if overlay["status"] not in ("active", "proposed") or not overlay.get("expires_at"):
        return False
    return (now if now is not None else time.time()) > overlay["expires_at"]


def latest_magnitude(measurements: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return measurements[-1] if measurements else None


def persistence(overlay: Dict[str, Any],
                renewal_limit: int = DEFAULT_RENEWAL_LIMIT) -> Dict[str, Any]:
    """Has this overlay stopped being temporary?

    Renewals rather than age, because age alone punishes an overlay that was
    correctly given a long window, while a short overlay renewed five times is
    the one that has quietly become part of the model.
    """
    # `continuations` when the register has computed it: the count across every
    # row this adjustment has occupied, not just the current one. Renewal
    # counting was per ROW, so letting an overlay lapse and PROPOSING it again
    # reset the counter to zero — and the platform's own expiry job was what
    # performed the reset. Four consecutive 90-day overlays read as
    # `persistent: false` throughout.
    renewals = overlay.get("continuations")
    if renewals is None:
        renewals = overlay.get("renewals", 0)
    over = renewals > renewal_limit
    return {
        "renewals": renewals, "limit": renewal_limit, "persistent": over,
        "detail": (f"renewed {renewals} times against a limit of {renewal_limit}; "
                   "an overlay that keeps being renewed is evidence the model is "
                   "wrong, not that the overlay is needed" if over
                   else f"renewed {renewals} times, within the limit of {renewal_limit}"),
    }


def materiality(measurements: Sequence[Dict[str, Any]],
                material_pct: float = DEFAULT_MATERIAL_PCT) -> Dict[str, Any]:
    """How large is this adjustment relative to what the model itself produced?"""
    latest = latest_magnitude(measurements)
    if latest is None:
        return {"measured": False, "material": False,
                "detail": "no magnitude has been measured"}
    pct = latest.get("pct_of_base")
    return {
        "measured": True, "period": latest["period"],
        "magnitude": latest["magnitude"], "pct_of_base": pct,
        "material": pct is not None and abs(pct) >= material_pct,
        "detail": (f"{latest['magnitude']:,.2f} in {latest['period']}"
                   + (f", {pct:.1%} of the model's own output" if pct is not None else "")),
    }


def trend(measurements: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Is the adjustment growing? A shrinking overlay is a model catching up;
    a growing one is a model falling further behind."""
    if len(measurements) < 2:
        return {"known": False, "detail": "not enough periods to establish a trend"}
    first, last = measurements[0]["magnitude"], measurements[-1]["magnitude"]
    direction = "growing" if abs(last) > abs(first) else (
        "shrinking" if abs(last) < abs(first) else "flat")
    return {"known": True, "direction": direction,
            "from": first, "to": last, "periods": len(measurements),
            "detail": (f"{direction} across {len(measurements)} periods "
                       f"({first:,.2f} to {last:,.2f})"
                       + (" — the model is falling further behind"
                          if direction == "growing" else ""))}


def assess(overlay: Dict[str, Any], measurements: Sequence[Dict[str, Any]],
           renewal_limit: int = DEFAULT_RENEWAL_LIMIT,
           material_pct: float = DEFAULT_MATERIAL_PCT,
           now: Optional[float] = None) -> Dict[str, Any]:
    """The whole reading of one overlay, and whether it should be escalated."""
    persist = persistence(overlay, renewal_limit)
    size = materiality(measurements, material_pct)
    movement = trend(measurements)
    reasons = []
    if persist["persistent"]:
        reasons.append(persist["detail"])
    if size["material"]:
        reasons.append(f"material at {size['detail']}")
    if movement.get("direction") == "growing" and size.get("measured"):
        reasons.append(movement["detail"])
    return {
        "overlay_id": overlay["id"], "reference": overlay["reference"],
        "age_days": round(age_days(overlay, now), 1),
        "expired": is_expired(overlay, now),
        "persistence": persist, "materiality": size, "trend": movement,
        "escalate": bool(persist["persistent"]),
        "reasons": reasons,
    }


def portfolio(overlays: List[Dict[str, Any]],
              measurements_by_overlay: Dict[str, List[Dict[str, Any]]],
              now: Optional[float] = None) -> Dict[str, Any]:
    """What the register says about a model as a whole.

    Aggregate magnitude is the number a risk committee actually asks for and
    almost never gets: not "how many overlays", but "how much of this number is
    the model and how much is us".
    """
    active = [o for o in overlays if o["status"] == "active"]
    total = 0.0
    for o in active:
        latest = latest_magnitude(measurements_by_overlay.get(o["id"], []))
        if latest:
            total += latest["magnitude"]
    persistent = [o for o in active
                  if persistence(o)["persistent"]]
    return {
        "overlays": len(overlays), "active": len(active),
        "persistent": len(persistent),
        "expired_but_open": sum(1 for o in active if is_expired(o, now)),
        "aggregate_magnitude": round(total, 2),
        "unmeasured": sum(1 for o in active
                          if not measurements_by_overlay.get(o["id"])),
        "detail": (f"{len(active)} active overlay(s) adjusting this model by "
                   f"{total:,.2f} in aggregate"
                   + (f"; {len(persistent)} have outlived their renewal limit"
                      if persistent else "")),
    }
