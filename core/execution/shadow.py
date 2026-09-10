"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

An answer that must not be used, and what a register can actually do about it.

Shadow traffic — mirroring a share of production calls to a challenger without
letting its answer affect anything — is a genuinely good practice and it happens
in the router. **MAYA is not in the serving path**, so it does not mirror, does
not sample, and cannot observe the share. A platform claiming to enforce a
canary percentage by *watching* would be claiming something it has no way to
check, which is the same objection this codebase already makes about compute
residency.

What a register can do is three things, and each is a real control:

**It can authorise the mirror as what it is.** A shadow grant is an ordinary
grant with `advisory` marked on it, and the descriptor it resolves says
`authoritative: false`. Every invocation under it is recorded as an advisory
call. A firm that never marked its shadow traffic has a challenger's answers in
the same log as its champion's, and *did this number reach a decision* becomes
unanswerable a year later.

**It can refuse the shape that lets a shadow answer escape.** A shadow grant
whose `declared_use` matches a use the model is *approved for in production* is
refused by name. That is precisely how a shadow answer reaches a decision: not
by somebody deciding to use it, but by a grant that is indistinguishable from a
production one at the point of use. The declared use must be its own.

**And it can notice a shadow that never ends.** Shadow mode is a temporary state
by definition — it exists to decide something. One running past its declared
window is a second production model nobody approved, running on production
traffic, with no owner, no validation and no monitoring plan; that is reported
as an excursion and it is the failure this module is most likely to catch in a
real estate.

The declared share is recorded and labelled an **attestation**, not a
measurement. Where MAYA has invocation telemetry it computes the observed share
and reports the gap — which is an observation about *authorised* calls and still
not about the router, and the answer says so.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.execution.errors import WarrantError
from core.log import get_logger

logger = get_logger(__name__)

DAY = 86400.0

ADVISORY = "advisory"

#: How long a shadow may run before it is an excursion. Shadow mode exists to
#: decide something; one that has not decided in a quarter has stopped being an
#: experiment.
MAX_SHADOW_DAYS = 90.0

#: How far the observed share may sit from the declared one before the gap is
#: worth reporting. Wide, because the observed figure counts authorised calls
#: and not routed ones, and a tight bound over the wrong denominator would fire
#: constantly and be muted.
SHARE_TOLERANCE = 0.25


class ShadowTraffic:
    """Authorises a mirror, refuses the shape that lets its answer escape."""

    def __init__(self, registry, warrants, grants, uses=None, invocations=None,
                 findings=None):
        self.registry, self.warrants, self.grants = registry, warrants, grants
        self.uses, self.invocations = uses, invocations
        self.findings = findings

    # ------------------------------------------------------------------ grant
    def authorise(self, urn: str, environment: str, principal: str, *,
                  declared_use: str, mirrors: str, share: float,
                  until: Optional[float] = None,
                  now: Optional[float] = None,
                  actor: str = "system") -> Dict[str, Any]:
        """Issue an advisory grant for a challenger running beside a champion."""
        model = self.registry.require(urn)
        if not (0.0 < share <= 1.0):
            raise WarrantError(
                "share_out_of_range",
                f"a mirrored share of {share} is not between 0 and 1",
                "declare the fraction of production traffic the router will "
                "mirror — MAYA cannot see the router, so this is an "
                "attestation and its value is that somebody stated it")
        if not (mirrors or "").strip():
            raise WarrantError(
                "mirrors_required",
                "a shadow grant must name the production use it mirrors, or "
                "nothing can tell whether it is shadowing anything",
                "name the declared use whose traffic is being copied")
        self._refuse_a_production_use(model, environment, declared_use)
        moment = now if now is not None else time.time()
        ends = until or (moment + MAX_SHADOW_DAYS * DAY)
        grant = self.grants.issue(urn, environment, principal, declared_use,
                                  flavour=ADVISORY, actor=actor)
        logger.info("advisory grant for %s issued to %s mirroring %s at %.0f%% "
                    "until %s", urn, principal, mirrors, 100 * share,
                    _when(ends))
        return {
            "grant": grant, "urn": urn, "environment": environment,
            "principal": principal, "declared_use": declared_use,
            "mirrors": mirrors, "declared_share": share,
            "authoritative": False, "until": ends,
            "share_is_measured": False,
            "detail": (
                f"an advisory grant: every answer under it is non-authoritative "
                f"and every invocation is recorded as such. The {share:.0%} "
                f"share is an **attestation** — MAYA is not in the serving path "
                f"and cannot see the router, and claiming to enforce a canary "
                f"percentage by watching would be claiming something it has no "
                f"way to check. It expires {_when(ends)}: shadow mode exists to "
                f"decide something, and one that has not decided is a second "
                f"production model nobody approved"),
        }

    def _refuse_a_production_use(self, model: Dict[str, Any],
                                 environment: str, declared_use: str) -> None:
        """The refusal that stops a shadow answer reaching a decision.

        Not by somebody deciding to use it — by a grant indistinguishable from
        a production one at the point of use.
        """
        if self.uses is None:
            return
        reading = self.uses.for_model(model["urn"])
        approved = {u.get("declared_use") for u in reading.get("uses", [])
                    if not u.get("retired_at")}
        if declared_use in approved:
            raise WarrantError(
                "shadow_use_is_a_production_use",
                f"'{declared_use}' is an approved use of {model['urn']}, so a "
                f"shadow grant under it would be indistinguishable from a "
                f"production one at the point of use",
                "give the shadow its own declared use. That is how a shadow "
                "answer reaches a decision — not by anybody deciding to use "
                "it, but by nothing being able to tell the two apart")

    # ----------------------------------------------------------------- status
    def status(self, urn: str, environment: str = "",
               now: Optional[float] = None) -> Dict[str, Any]:
        """Advisory grants on a model, and whether any has outstayed itself."""
        model = self.registry.require(urn)
        moment = now if now is not None else time.time()
        rows = [g for g in self.grants.of_model(urn)
                if g.get("flavour") == ADVISORY
                and (not environment or g["environment"] == environment)]
        out = []
        for grant in rows:
            age = (moment - grant["created_at"]) / DAY
            out.append({
                **grant, "age_days": round(age, 1),
                "overstayed": age > MAX_SHADOW_DAYS and not grant["revoked"],
                "observed_share": self._observed(model, grant, moment),
            })
        overstayed = [g for g in out if g["overstayed"]]
        return {
            "urn": urn, "advisory_grants": out, "count": len(out),
            "overstayed": [g["id"] for g in overstayed],
            "in_the_serving_path": False,
            "detail": self._detail(out, overstayed),
        }

    def _observed(self, model: Dict[str, Any], grant: Dict[str, Any],
                  moment: float) -> Optional[Dict[str, Any]]:
        """The share of AUTHORISED calls, which is not the share of routed ones.

        Reported with that caveat attached rather than presented as the canary
        percentage: MAYA sees the calls that asked it for a warrant, and a
        router that mirrors without resolving is invisible here.
        """
        if self.invocations is None:
            return None
        rows = self.invocations.for_model(model["id"])["invocations"]
        if not rows:
            return None
        advisory = sum(1 for r in rows if r.get("warrant_id") == grant["id"])
        return {"advisory_calls": advisory, "total_calls": len(rows),
                "share_of_authorised": round(advisory / len(rows), 3),
                "is_the_routed_share": False,
                "caveat": ("this is the share of calls that asked MAYA for a "
                           "warrant, not the share the router mirrored. A "
                           "router that copies traffic without resolving is "
                           "invisible here, and no arrangement of this platform "
                           "would make it visible")}

    @staticmethod
    def _detail(rows: List[Dict[str, Any]],
                overstayed: List[Dict[str, Any]]) -> str:
        if not rows:
            return ("no advisory grant on this model. A firm running shadow "
                    "traffic without one has a challenger's answers in the same "
                    "log as its champion's, and *did this number reach a "
                    "decision* becomes unanswerable a year later")
        out = (f"{len(rows)} advisory grant(s). Every answer under one is "
               f"non-authoritative and MAYA is not in the serving path")
        if overstayed:
            out += (f". {len(overstayed)} have run past {MAX_SHADOW_DAYS:.0f} "
                    f"days — a shadow that never ends is a second production "
                    f"model nobody approved, on production traffic, with no "
                    f"owner and no monitoring plan")
        return out

    # ----------------------------------------------------------------- estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        moment = now if now is not None else time.time()
        rows = [self.status(m["urn"], now=moment) for m in self.registry.list()]
        rows = [r for r in rows if r["count"]]
        rows.sort(key=lambda r: -len(r["overstayed"]))
        overstayed = [r["urn"] for r in rows if r["overstayed"]]
        return {
            "models": rows, "count": len(rows),
            "advisory_grants": sum(r["count"] for r in rows),
            "overstayed": overstayed,
            "in_the_serving_path": False, "mirrors_traffic": False,
            "detail": (
                f"{sum(r['count'] for r in rows)} advisory grant(s) across "
                f"{len(rows)} model(s)"
                + (f", {len(overstayed)} of which have outstayed the "
                   f"{MAX_SHADOW_DAYS:.0f}-day window and are running as "
                   f"unapproved production models" if overstayed else "")
                if rows else
                "no advisory grant anywhere. That is either a firm doing no "
                "shadow testing or one doing it unmarked, and the register "
                "cannot tell the two apart — which is itself worth knowing"),
        }

    @staticmethod
    def describe() -> Dict[str, Any]:
        return {
            "flavour": ADVISORY,
            "max_shadow_days": MAX_SHADOW_DAYS,
            "share_tolerance": SHARE_TOLERANCE,
            "mirrors_traffic": False, "measures_the_share": False,
            "in_the_serving_path": False,
            "detail": ("MAYA does not mirror traffic and cannot see the router. "
                       "What it does is authorise the mirror as advisory, refuse "
                       "a shadow grant whose declared use is a production use — "
                       "which is how a shadow answer reaches a decision — and "
                       "notice a shadow that never ends"),
        }


def _when(stamp: Optional[float]) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(stamp)) if stamp else "unknown"
