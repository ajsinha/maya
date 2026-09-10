"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What one grant may spend, checked before the descriptor is signed.

**Three limits, and they are not three sizes of the same thing.** A rate limit
bounds calls per minute and protects the **downstream system** from a loop. A
quota bounds calls per window and protects the **authorisation** from being used
more than anybody intended — a grant issued for a nightly batch and exercised
forty thousand times a day is being used for something nobody approved, and no
rate limit would notice because none of it is fast. A cost budget bounds money
and is the only one whose unit is not calls, which is exactly why it is the one
that matters for a token-metered generative model: ten calls can cost more than
ten thousand.

**The limit is on the grant, not on the caller.** That is what *per grant*
means and it is the right unit. A service account holding four grants should not
have one runaway use exhaust the other three, and a limit on the principal does
precisely that — it turns an incident in one product into an outage in three
unrelated ones.

**A refused call must not count against the quota.** Otherwise a caller in a
retry loop can never recover: the retries consume the allowance the retries are
waiting for, and the grant is dead until the window rolls even though it was
never used successfully. Refusals are still *recorded* — the invocation log
keeps them, which is what makes *who is hammering this* answerable — they simply
do not spend anything.

**The rate window slides.** A fixed one-minute bucket permits twice the limit
across a boundary: sixty calls at 11:59:59 and sixty more at 12:00:01 is a
hundred and twenty calls in two seconds under a limit of sixty a minute. The
whole point of a rate limit is the burst, so measuring it in a way that misses
the burst is measuring nothing.

**Nothing here is a default.** A grant with no limits set is unlimited on every
axis, and the estate view reports how many of those there are rather than
treating it as the normal state. Inventing a limit would refuse work nobody
agreed to refuse; pretending an absent limit is a decision would be worse.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.execution.errors import WarrantError
from core.log import get_logger

logger = get_logger(__name__)

MINUTE = 60.0
HOUR = 3600.0

#: The three limits, and what each one protects. Named as data because the
#: refusal, the estate view and the API all have to agree about them.
LIMITS: Dict[str, str] = {
    "rate": "calls per minute — protects the downstream system from a loop",
    "quota": "calls per window — protects the authorisation from being used "
             "more than anybody intended, which no rate limit would notice "
             "because none of it is fast",
    "cost": "money per window — the only one whose unit is not calls, and "
            "therefore the one that matters for a token-metered model, where "
            "ten calls can cost more than ten thousand",
}

#: The share of a limit at which the estate view starts saying so. Not a
#: refusal: raising a limit is a decision better made before the work stops.
WARN_AT = 0.8


class GrantQuotas:
    """Sets and enforces what a single warrant grant may spend."""

    def __init__(self, warrants, invocations, evidence=None):
        self.warrants, self.invocations = warrants, invocations
        self.evidence = evidence

    # ------------------------------------------------------------------- set
    def set(self, warrant_id: str, *, rate: Optional[int] = None,
            quota: Optional[int] = None, cost: Optional[float] = None,
            window_hours: Optional[float] = None,
            actor: str = "system") -> Dict[str, Any]:
        """Declare what this grant may spend."""
        grant = self._grant(warrant_id)
        fields: Dict[str, Any] = {}
        for name, column, value in (("rate", "rate_per_minute", rate),
                                    ("quota", "quota", quota),
                                    ("cost", "cost_budget", cost)):
            if value is None:
                continue
            if float(value) <= 0:
                raise WarrantError(
                    "limit_not_positive",
                    f"a {name} limit of {value} would refuse every call, which "
                    f"is a revocation written as a number",
                    "revoke the grant instead, which records a reason and "
                    "shows on every screen as what it is")
            fields[column] = value
        if window_hours is not None:
            if float(window_hours) <= 0:
                raise WarrantError(
                    "window_not_positive",
                    f"a quota window of {window_hours} hours is not a window",
                    "a window is how long the quota lasts before it refills")
            fields["quota_window_hours"] = float(window_hours)
        if not fields:
            raise WarrantError(
                "nothing_to_set",
                "no limit was given, so this would record a decision nobody "
                "made",
                f"name at least one of {', '.join(LIMITS)}, or a window")

        if self.evidence is not None:
            with self.evidence.recording():
                self.warrants.grants.repo.set(fields, id=warrant_id)
                self.evidence.append(
                    "warrant_limits_set", "warrant", warrant_id,
                    {"principal": grant.get("principal"),
                     "declared_use": grant.get("declared_use"), **fields},
                    actor=actor)
        else:
            self.warrants.grants.repo.set(fields, id=warrant_id)
        logger.info("limits on grant %s set by %s: %s", warrant_id, actor,
                    fields)
        return self.of(warrant_id)

    # ------------------------------------------------------------------ read
    def of(self, warrant_id: str,
           now: Optional[float] = None) -> Dict[str, Any]:
        """This grant's limits, what it has spent, and what is left."""
        return self._state(self._grant(warrant_id), now)

    def _state(self, grant: Dict[str, Any],
               now: Optional[float] = None) -> Dict[str, Any]:
        moment = now if now is not None else time.time()
        window = float(grant.get("quota_window_hours") or 24.0)
        spent = self._spent(grant["id"], moment, window)

        lines = []
        for name, column, used, unit in (
                ("rate", "rate_per_minute", spent["in_the_last_minute"], "per minute"),
                ("quota", "quota", spent["calls"], f"per {window:.0f}h"),
                ("cost", "cost_budget", spent["cost"], f"per {window:.0f}h")):
            limit = grant.get(column)
            lines.append({
                "limit": name, "protects": LIMITS[name], "unit": unit,
                "ceiling": limit, "spent": used,
                "remaining": None if limit is None else max(0.0, limit - used),
                "share": None if limit is None else round(used / limit, 4),
                "set": limit is not None,
                "exhausted": limit is not None and used >= limit,
                "near": (limit is not None
                         and WARN_AT <= used / limit < 1.0),
            })
        exhausted = [line["limit"] for line in lines if line["exhausted"]]
        unlimited = [line["limit"] for line in lines if not line["set"]]
        return {
            "warrant_id": grant["id"], "model_id": grant.get("model_id"),
            "principal": grant.get("principal"),
            "declared_use": grant.get("declared_use"),
            "window_hours": window, "limits": lines,
            "unlimited": unlimited, "exhausted": exhausted,
            "within_limits": not exhausted,
            "calls_in_window": spent["calls"],
            "refused_in_window": spent["refused"],
            "detail": self._detail(grant, lines, exhausted, unlimited, window,
                                   spent),
        }

    def _spent(self, warrant_id: str, moment: float,
               window_hours: float) -> Dict[str, float]:
        """What this grant has actually consumed.

        Refusals are counted for reporting and **excluded from the spend**. A
        caller in a retry loop whose retries consumed the allowance the retries
        were waiting for could never recover, and the grant would be dead until
        the window rolled despite never having been used successfully.
        """
        rows = self.invocations.repo.many(warrant_id=warrant_id)
        since = moment - window_hours * HOUR
        recent = [r for r in rows if (r.get("at") or 0) >= since]
        spent = [r for r in recent if r.get("outcome") != "refused"]
        minute_ago = moment - MINUTE
        return {
            "calls": float(len(spent)),
            "refused": float(len(recent) - len(spent)),
            "cost": float(sum(r.get("cost") or 0.0 for r in spent)),
            "in_the_last_minute": float(sum(
                1 for r in spent if (r.get("at") or 0) >= minute_ago)),
        }

    @staticmethod
    def _detail(grant, lines, exhausted, unlimited, window, spent) -> str:
        who = f"{grant.get('principal')} for {grant.get('declared_use')}"
        if exhausted:
            worst = next(line for line in lines
                         if line["limit"] == exhausted[0])
            return (f"{who} has reached its {exhausted[0]} limit — "
                    f"{worst['spent']:.0f} against {worst['ceiling']:.0f} "
                    f"{worst['unit']}. Further calls are refused, and the "
                    f"refusals do not count against it, so a retry loop cannot "
                    f"keep it exhausted")
        out = f"{who} is within its limits"
        near = [line["limit"] for line in lines if line["near"]]
        if near:
            out += (f", though {', '.join(near)} is past {WARN_AT:.0%} — "
                    f"raising a limit is a decision better made before the "
                    f"work stops than after")
        if unlimited:
            out += (f". {', '.join(unlimited)} is unlimited on this grant, "
                    f"which is a decision nobody has taken rather than one "
                    f"they have")
        if spent["refused"]:
            out += (f". {spent['refused']:.0f} call(s) in this window were "
                    f"refused, which is worth reading on its own")
        return out

    # ---------------------------------------------------------------- check
    def check(self, warrant_id: str,
              now: Optional[float] = None) -> Dict[str, Any]:
        """Refuse before the descriptor is signed, or return the headroom.

        Before, because a signed descriptor is an authorisation: handing one
        out and then declining to honour it would mean the caller holds a
        warrant the platform does not intend to let it use, which is exactly
        the confusion the whole warrant design exists to remove.
        """
        state = self.of(warrant_id, now)
        if not state["exhausted"]:
            return state
        which = state["exhausted"][0]
        worst = next(line for line in state["limits"]
                     if line["limit"] == which)
        detail = (f"this grant has reached its {which} limit of "
                  f"{worst['ceiling']:.0f} {worst['unit']}. {LIMITS[which]}")
        remediation = ("wait for the window, or have the limit raised "
                       "deliberately — the refusal is recorded and does not "
                       "itself count against the limit, so a retry loop cannot "
                       "keep the grant exhausted")
        # Three raise sites with three literal codes rather than one assembled
        # from `which`. A code built with an f-string or a lookup is a code
        # nobody can grep for — and the discipline test that reconciles this
        # taxonomy against the route layer's status map cannot see one either,
        # so the mapping would silently degrade to a bare 400.
        if which == "rate":
            raise WarrantError("rate_limit_reached", detail, remediation)
        if which == "quota":
            raise WarrantError("quota_limit_reached", detail, remediation)
        raise WarrantError("cost_limit_reached", detail, remediation)

    # ---------------------------------------------------------------- estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every live grant, and how close it is to its limits."""
        moment = now if now is not None else time.time()
        rows: List[Dict[str, Any]] = []
        for grant in self.warrants.grants.repo.many():
            if grant.get("revoked"):
                continue
            rows.append(self._state(grant, moment))
        rows.sort(key=lambda r: -max(
            (line["share"] or 0.0) for line in r["limits"]))
        exhausted = [r for r in rows if r["exhausted"]]
        wholly_unlimited = [r for r in rows if len(r["unlimited"]) == len(LIMITS)]
        return {
            "grants": rows, "count": len(rows),
            "exhausted": len(exhausted),
            "unlimited": len(wholly_unlimited),
            "refused_in_window": sum(r["refused_in_window"] for r in rows),
            "detail": (
                f"{len(rows)} live grant(s), {len(exhausted)} at a limit"
                + (f", {len(wholly_unlimited)} with no limit of any kind — "
                   f"which is a decision nobody has taken rather than one they "
                   f"have" if wholly_unlimited else "")),
        }

    # -------------------------------------------------------------- shaping
    def _grant(self, warrant_id: str) -> Dict[str, Any]:
        row = self.warrants.grants.repo.one(id=warrant_id)
        if not row:
            raise WarrantError("no_grant", f"no warrant grant '{warrant_id}'",
                               "grants are listed against the model they name")
        return row
