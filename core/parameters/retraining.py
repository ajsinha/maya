"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

When a re-fit is due, and the standing approval that may accept one.

Two things are being asked for, and only one of them belongs in a register.

**MAYA does not retrain.** It says a re-fit is **due**, from triggers it already
computes — a monitor in breach, a drift observation past its threshold, an
adaptive excursion, a window elapsed. Nothing here starts anything: the fit
happens under a warrant somewhere else and comes back as a run and a parameter
set.

**The auto-promotion policy approves a procedure, never a result.** The
objection to automatic acceptance is obvious and mostly right — nobody looked at
this number — but the alternative in practice is not a committee reading every
recalibration. It is a recalibration that happens anyway, at the frequency the
business needs, with nobody's name on it. A standing policy is a person saying
in advance: *a re-fit of this model, on this trigger, whose diagnostics land
inside this tolerance, may be accepted without me* — and their name is on every
acceptance it produces.

That is only defensible with four things around it, and each is enforced rather
than documented:

  * **Tier 1 is never eligible.** Not configurable, not waivable. The first
    thing anybody asks of an auto-promotion policy is whether it can be widened,
    and a ceiling that can be raised is a ceiling that will be.
  * **Every policy expires.** A standing approval with no end is a permanent
    delegation of a judgement, and the person who gave it has usually moved on.
  * **The tolerance is declared and checked here.** A policy whose tolerance is
    evaluated by whatever produced the parameters is a model marking its own
    homework.
  * **The person who declares it may not approve it.** It is an approval like
    any other, and it is a larger one than most.

An acceptance the policy makes is recorded **attributed to the policy and to its
approver**, never to `system`. *Who approved this parameter set* must always have
a human answer, and *the automation did* is not one.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.log import get_logger
from core.parameters.common import ParameterError

logger = get_logger(__name__)

DAY = 86400.0

#: The tier that may never be accepted without a person. Not a default and not
#: a configuration key: a ceiling that can be raised is a ceiling that will be.
NEVER_AUTOMATIC_AT_OR_ABOVE = 1

#: The longest a standing approval may run before somebody renews it.
MAX_POLICY_DAYS = 365.0

ACTIVE, EXPIRED, REVOKED = "active", "expired", "revoked"

#: Conditions that make a re-fit due, each computed from something the platform
#: already evaluates. Held as data so a policy naming an unknown trigger is
#: refused when it is written rather than when it fires.
TRIGGERS: Dict[str, str] = {
    "monitor_breach": "a monitor on this model is in breach",
    "drift": "a drift monitor has passed its threshold",
    "adaptive_excursion": "a self-changing model has moved past its bound "
                          "since anybody last looked",
    "window_elapsed": "the parameter set in force was fitted over a window "
                      "that has passed",
    "upstream_change": "a feature view under this model changed schema or "
                       "materially changed volume",
}


class Retraining:
    """Says when a re-fit is due, and holds the standing approval for one."""

    def __init__(self, policies, registry, parameters, evidence,
                 monitoring=None, adaptive=None, pipeline=None):
        self.policies, self.registry = policies, registry
        self.parameters, self.evidence = parameters, evidence
        self.monitoring, self.adaptive = monitoring, adaptive
        self.pipeline = pipeline

    # ---------------------------------------------------------------- declare
    def declare(self, urn: str, *, triggers: Sequence[str],
                tolerance: Dict[str, Any], auto_accept: bool, rationale: str,
                expires_at: Optional[float] = None,
                now: Optional[float] = None,
                actor: str = "system") -> Dict[str, Any]:
        """Write the policy. Approval is a separate act by a different person."""
        model = self.registry.require(urn)
        unknown = [t for t in triggers if t not in TRIGGERS]
        if unknown:
            raise ParameterError(
                "unknown_trigger",
                f"{', '.join(unknown)} name(s) nothing the platform computes",
                f"the five are {', '.join(TRIGGERS)} — a trigger MAYA cannot "
                f"evaluate is a condition that silently never fires")
        if not triggers:
            raise ParameterError(
                "trigger_required",
                "a retraining policy with no trigger is a statement that this "
                "model is never re-fitted, which is better said by not having "
                "a policy", "name at least one")
        if not (rationale or "").strip():
            raise ParameterError(
                "rationale_required",
                "a standing approval needs a reason. It is delegating a "
                "judgement, and the person reading it in a year was not in the "
                "room", "say what it rests on")
        tier = model.get("tier")
        if auto_accept and (tier is None
                            or int(tier) <= NEVER_AUTOMATIC_AT_OR_ABOVE):
            raise ParameterError(
                "tier_not_eligible",
                (f"tier {tier} may never accept a parameter set without a "
                 f"person" if tier is not None else
                 "this model has no tier, and an untiered model takes the "
                 "strictest treatment — a model nobody has tiered is not a "
                 "safe model"),
                "declare the policy without auto_accept: the triggers still "
                "fire and the due-list still names it, which is most of the "
                "value and none of the delegation")
        if auto_accept and not tolerance:
            raise ParameterError(
                "tolerance_required",
                "automatic acceptance needs a declared tolerance, checked "
                "here. A policy whose tolerance is evaluated by whatever "
                "produced the parameters is a model marking its own homework",
                "declare the diagnostics and their bounds")
        moment = now if now is not None else time.time()
        ceiling = moment + MAX_POLICY_DAYS * DAY
        ends = min(expires_at or ceiling, ceiling)
        held = self.policies.one(model_id=model["id"])
        row = {"model_id": model["id"], "triggers": list(triggers),
               "tolerance": dict(tolerance or {}),
               "auto_accept": bool(auto_accept), "rationale": rationale.strip(),
               "declared_by": actor, "approved_by": None,
               "declared_at": moment, "expires_at": ends, "status": ACTIVE}
        with self.evidence.recording():
            if held:
                self.policies.set(row, id=held["id"])
                row["id"] = held["id"]
            else:
                self.policies.add(row)
            self.evidence.append(
                "retrain_policy_declared", "model", model["id"],
                {"triggers": list(triggers), "auto_accept": bool(auto_accept),
                 "tolerance": dict(tolerance or {}), "tier": tier,
                 "expires_at": ends, "rationale": rationale.strip()},
                actor=actor)
        logger.info("retraining policy for %s declared by %s (auto_accept=%s)",
                    urn, actor, auto_accept)
        return self.policy(urn, now=moment)

    def approve(self, urn: str, actor: str = "system",
                now: Optional[float] = None) -> Dict[str, Any]:
        """Approve the standing policy. Not by the person who wrote it."""
        model = self.registry.require(urn)
        policy = self._require(model)
        if policy["declared_by"] == actor:
            raise ParameterError(
                "author_may_not_approve",
                "the person who wrote a standing approval may not approve it. "
                "It delegates a judgement over every future re-fit of this "
                "model, which makes it a larger approval than most rather than "
                "a smaller one",
                "have somebody else approve it")
        moment = now if now is not None else time.time()
        with self.evidence.recording():
            self.policies.set({"approved_by": actor}, id=policy["id"])
            self.evidence.append(
                "retrain_policy_approved", "model", model["id"],
                {"approved_by": actor, "declared_by": policy["declared_by"],
                 "auto_accept": policy["auto_accept"],
                 "expires_at": policy["expires_at"]}, actor=actor)
        return self.policy(urn, now=moment)

    def revoke(self, urn: str, reason: str, actor: str = "system",
               now: Optional[float] = None) -> Dict[str, Any]:
        model = self.registry.require(urn)
        policy = self._require(model)
        moment = now if now is not None else time.time()
        with self.evidence.recording():
            self.policies.set({"status": REVOKED}, id=policy["id"])
            self.evidence.append(
                "retrain_policy_revoked", "model", model["id"],
                {"reason": reason, "was_auto_accept": policy["auto_accept"]},
                actor=actor)
        return self.policy(urn, now=moment)

    # ------------------------------------------------------------------- due
    def due(self, urn: str, now: Optional[float] = None) -> Dict[str, Any]:
        """Whether a re-fit is due, and on what. MAYA starts nothing."""
        model = self.registry.require(urn)
        moment = now if now is not None else time.time()
        policy = self.policies.one(model_id=model["id"])
        wanted = set((policy or {}).get("triggers") or TRIGGERS)
        fired = [t for t in self._evaluate(model, moment)
                 if t["trigger"] in wanted and t["fired"]]
        checked = [t for t in self._evaluate(model, moment)
                   if t["trigger"] in wanted]
        return {
            "urn": urn, "tier": model.get("tier"),
            "triggers": checked, "due": bool(fired),
            "fired": [t["trigger"] for t in fired],
            "policy": self.policy(urn, now=moment)["policy"],
            "starts_anything": False,
            "detail": (
                (f"a re-fit is due: {', '.join(t['trigger'] for t in fired)}. "
                 f"MAYA does not start one — the fit happens under a warrant "
                 f"elsewhere and comes back as a run and a parameter set"
                 if fired else
                 "nothing has fired, so there is no reason to re-fit this "
                 "model. That is a decision rather than an omission")
                + ("" if policy else
                   ". No policy is declared, so every trigger the platform "
                   "computes was evaluated — a model with no policy is "
                   "watched more widely rather than less")),
        }

    def _evaluate(self, model: Dict[str, Any],
                  moment: float) -> List[Dict[str, Any]]:
        """Each trigger, from something the platform already computes."""
        out = [{"trigger": "monitor_breach",
                "fired": bool(self.monitoring
                              and self.monitoring.breaches.open_for(
                                  model["id"])),
                "from": "the breach register"},
               {"trigger": "drift",
                "fired": bool(self.monitoring and any(
                    b["severity"] in ("Critical", "High")
                    for b in self.monitoring.breaches.open_for(model["id"]))),
                "from": "drift monitors in breach"}]
        excursion = False
        if self.adaptive is not None:
            sweep = self.adaptive.sweep(now=moment)
            excursion = model["urn"] in {r.get("urn") for r
                                         in sweep.get("excursions", [])}
        out.append({"trigger": "adaptive_excursion", "fired": excursion,
                    "from": "the adaptive trajectory"})
        out.append({"trigger": "window_elapsed",
                    "fired": self._window_elapsed(model, moment),
                    "from": "the window the parameter set in force was fitted "
                            "over"})
        out.append({"trigger": "upstream_change", "fired": False,
                    "from": "feature view history — evaluated by "
                            "`pipelines.check`, and reported there rather than "
                            "duplicated here"})
        return out

    def _window_elapsed(self, model: Dict[str, Any], moment: float) -> bool:
        if self.parameters is None:
            return False
        rows = [p for p in self.parameters.parameters.many(model_id=model["id"])
                if p.get("state") == "approved" and p.get("window_to")]
        if not rows:
            return False
        newest = max(rows, key=lambda p: p["window_to"])
        span = (newest["window_to"] - (newest.get("window_from")
                                       or newest["window_to"]))
        return span > 0 and (moment - newest["window_to"]) > span

    # ---------------------------------------------------------------- accept
    def may_accept(self, urn: str, diagnostics: Dict[str, Any],
                   now: Optional[float] = None) -> Dict[str, Any]:
        """Whether the standing policy covers a parameter set. Checked here.

        Returns a decision and never performs one: accepting is an act on the
        parameter register, attributed to the policy's approver rather than to
        `system`, because *who approved this* must always have a human answer.
        """
        # `require` rather than `get`: a decision about a model the register
        # does not hold is a decision about nothing, and returning False for it
        # would read as a refusal rather than as a mistyped urn.
        self.registry.require(urn)
        moment = now if now is not None else time.time()
        state = self.policy(urn, now=moment)
        policy = state["policy"]
        if not policy or state["status"] != ACTIVE:
            return {"may_accept": False, "attributed_to": None,
                    "reason": ("no standing approval is in force for this "
                               "model, so a person accepts this set")}
        if not policy["auto_accept"]:
            return {"may_accept": False, "attributed_to": None,
                    "reason": "this policy names triggers and does not "
                              "delegate acceptance"}
        if not policy.get("approved_by"):
            return {"may_accept": False, "attributed_to": None,
                    "reason": ("the policy is declared and not approved, and "
                               "an unapproved standing approval is a draft")}
        breaches = self._outside(policy["tolerance"], diagnostics)
        if breaches:
            return {"may_accept": False, "attributed_to": None,
                    "outside_tolerance": breaches,
                    "reason": (f"{len(breaches)} diagnostic(s) fall outside the "
                               f"declared tolerance: "
                               + "; ".join(breaches)
                               + ". The tolerance is checked here rather than "
                                 "by whatever produced the parameters, which "
                                 "would be a model marking its own homework")}
        return {
            "may_accept": True, "attributed_to": policy["approved_by"],
            "policy_declared_by": policy["declared_by"],
            "expires_at": policy["expires_at"],
            "reason": (f"every declared diagnostic is inside tolerance and a "
                       f"standing approval by {policy['approved_by']} covers "
                       f"this. The acceptance is attributed to them and never "
                       f"to `system`: *who approved this parameter set* must "
                       f"have a human answer, and *the automation did* is not "
                       f"one"),
        }

    @staticmethod
    def _outside(tolerance: Dict[str, Any],
                 diagnostics: Dict[str, Any]) -> List[str]:
        out = []
        for key, bound in (tolerance or {}).items():
            held = diagnostics.get(key)
            if held is None:
                # An absent diagnostic is outside tolerance. Treating it as
                # inside would let a fit that stopped reporting a number pass
                # the check that number existed for.
                out.append(f"{key} was not reported")
                continue
            if "min" in bound and held < bound["min"]:
                out.append(f"{key} {held:.6g} below {bound['min']:.6g}")
            if "max" in bound and held > bound["max"]:
                out.append(f"{key} {held:.6g} above {bound['max']:.6g}")
        return out

    # ----------------------------------------------------------------- policy
    def policy(self, urn: str, now: Optional[float] = None) -> Dict[str, Any]:
        model = self.registry.require(urn)
        moment = now if now is not None else time.time()
        row = self.policies.one(model_id=model["id"])
        if not row:
            return {"urn": urn, "policy": None, "status": None,
                    "detail": "no retraining policy is declared for this model"}
        status = row["status"]
        if status == ACTIVE and row.get("expires_at") \
                and moment > row["expires_at"]:
            status = EXPIRED
        return {
            "urn": urn, "policy": row, "status": status,
            "days_left": (round((row["expires_at"] - moment) / DAY, 1)
                          if row.get("expires_at") else None),
            "detail": (
                f"declared by {row['declared_by']}"
                + (f", approved by {row['approved_by']}"
                   if row.get("approved_by") else ", and NOT approved — an "
                   "unapproved standing approval is a draft")
                + (f", accepting re-fits inside tolerance until "
                   f"{_when(row['expires_at'])}" if row["auto_accept"]
                   else ", naming triggers and delegating no acceptance")
                + (". It has expired, so acceptance falls back to a person, "
                   "which is the state a standing approval should decay into"
                   if status == EXPIRED else "")),
        }

    def _require(self, model: Dict[str, Any]) -> Dict[str, Any]:
        row = self.policies.one(model_id=model["id"])
        if not row:
            raise ParameterError(
                "no_policy", f"no retraining policy for {model['urn']}",
                "declare one")
        return row

    # ----------------------------------------------------------------- estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        moment = now if now is not None else time.time()
        rows = []
        for model in self.registry.list():
            state = self.policy(model["urn"], now=moment)
            rows.append({**state, "due": self.due(model["urn"], now=moment)})
        rows.sort(key=lambda r: (not r["due"]["due"], r["urn"]))
        due = [r for r in rows if r["due"]["due"]]
        automatic = [r for r in rows if r["policy"]
                     and r["policy"]["auto_accept"] and r["status"] == ACTIVE]
        expired = [r for r in rows if r["status"] == EXPIRED]
        return {
            "models": rows, "count": len(rows),
            "due": [r["urn"] for r in due],
            "automatic": [r["urn"] for r in automatic],
            "expired_policies": [r["urn"] for r in expired],
            "retrains_anything": False,
            "detail": (
                f"{len(due)} model(s) have a re-fit trigger firing and "
                f"{len(automatic)} carry a standing approval that would accept "
                f"one inside tolerance. MAYA retrains nothing: the fit happens "
                f"elsewhere under a warrant and comes back as a run"
                + (f". {len(expired)} standing approval(s) have expired and "
                   f"acceptance has fallen back to a person, which is the "
                   f"state one should decay into" if expired else "")),
        }

    @staticmethod
    def triggers() -> Dict[str, Any]:
        return {
            "triggers": [{"trigger": k, "fires_when": v}
                         for k, v in TRIGGERS.items()],
            "never_automatic_at_or_above_tier": NEVER_AUTOMATIC_AT_OR_ABOVE,
            "max_policy_days": MAX_POLICY_DAYS,
            "retrains_anything": False,
            "detail": ("the policy approves a PROCEDURE and never a result. "
                       "Tier 1 is never eligible and it is not configurable — "
                       "the first thing anybody asks of an auto-promotion "
                       "policy is whether it can be widened, and a ceiling that "
                       "can be raised is a ceiling that will be"),
        }


def _when(stamp: Optional[float]) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(stamp)) if stamp else "unknown"
