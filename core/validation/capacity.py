"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The validation queue, and the thing a backlog is actually a symptom of.

Every model risk function runs a backlog and almost none can say how big it is,
because the two halves of the answer live apart: what is *due* comes from the
register and what a team can *do* lives in somebody's head. This puts them side
by side, and the two are treated very differently.

**Workload is derived; capacity is declared.** MAYA counts open episodes and
computes what falls due, from triggers it already evaluates. It does not guess
how many validations a person can run in a quarter — a platform that did would
produce a forecast nobody could dispute, which is worse than no forecast because
it survives the meeting.

**The forecast states its own assumption.** Dividing work by capacity assumes
every validation costs the same, which is false and everyone knows it: a Tier 1
initial validation and a Tier 4 targeted one are not the same week. The number is
still worth having, and it is printed with the assumption attached, because a
forecast that hides its assumption is one people act on.

**The sort order is the finding.** If the work at the front of the queue is Tier
4 and Tier 1 models are behind it, the queue is inverted — and that is a
statement about how the function is being run, not about any one model. It is
computed and said, because it is invisible in a list sorted by due date, which
is how every backlog is sorted.

**And an overloaded validator is not a scheduling problem.** The commonest
response to a validation backlog is to let a model's own team review it, and the
second commonest is to conclude an episode without doing the work. Both are
independence failures that begin as capacity problems, so the overload is named
early and named as what it is.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.log import get_logger
from core.validation.common import ValidationError

logger = get_logger(__name__)

DAY = 86400.0
QUARTER_DAYS = 91.0

#: How far ahead a forecast reaches. A year, because the elapsed-time triggers
#: this counts against run to a year at the longest tier that has one.
HORIZON_DAYS = 365.0

#: Relative effort by tier. Published, and deliberately crude: this is the
#: assumption the forecast rests on, and it is better argued with than hidden.
#: A firm that disagrees should declare its own, which is why they are here as
#: data rather than in a divide.
EFFORT_BY_TIER: Dict[int, float] = {1: 3.0, 2: 2.0, 3: 1.0, 4: 0.5}
DEFAULT_EFFORT = 1.0


class ValidationCapacity:
    """What is queued, who is carrying it, and what the queue says about itself."""

    def __init__(self, capacities, registry, validation, plans=None,
                 evidence=None, effort: Optional[Dict[int, float]] = None):
        self.capacities, self.registry = capacities, registry
        self.validation, self.plans = validation, plans
        self.evidence = evidence
        self.effort = {**EFFORT_BY_TIER, **(effort or {})}

    # --------------------------------------------------------------- declare
    def declare(self, validator: str, episodes_per_quarter: float,
                note: str = "", actor: str = "system",
                now: Optional[float] = None) -> Dict[str, Any]:
        """Record what one validator can take on. Never inferred."""
        if not (validator or "").strip():
            raise ValidationError("a capacity has to belong to somebody")
        if episodes_per_quarter <= 0:
            raise ValidationError(
                "a capacity of zero or less is a statement that this person "
                "does no validation, which is better expressed by not "
                "declaring one — a zero here divides into an infinite forecast")
        moment = now if now is not None else time.time()
        held = self.capacities.one(validator=validator)
        row = {"validator": validator.strip(),
               "episodes_per_quarter": float(episodes_per_quarter),
               "note": note.strip(), "declared_by": actor,
               "declared_at": moment}
        if held:
            self.capacities.set(row, id=held["id"])
        else:
            self.capacities.add(row)
        if self.evidence is not None:
            self.evidence.append(
                "validator_capacity_declared", "principal", validator,
                {"validator": validator,
                 "episodes_per_quarter": float(episodes_per_quarter),
                 "was": held.get("episodes_per_quarter") if held else None},
                actor=actor)
        logger.info("%s declared capacity %.1f episodes/quarter for %s", actor,
                    episodes_per_quarter, validator)
        return self.capacities.one(validator=validator)

    def declared(self) -> List[Dict[str, Any]]:
        return list(self.capacities.many())

    # -------------------------------------------------------------- workload
    def by_validator(self, now: Optional[float] = None) -> Dict[str, Any]:
        """What each validator is carrying, against what they said they could."""
        moment = now if now is not None else time.time()
        capacities = {c["validator"]: c for c in self.capacities.many()}
        carrying: Dict[str, List[Dict[str, Any]]] = {}
        for episode in self.validation.validations.many():
            if episode.get("status") == "concluded" or episode.get("completed_at"):
                continue
            for validator in (episode.get("validators") or []):
                carrying.setdefault(validator, []).append(episode)

        rows = []
        for validator in sorted(set(capacities) | set(carrying)):
            open_episodes = carrying.get(validator, [])
            declared = capacities.get(validator)
            per_quarter = (declared["episodes_per_quarter"] if declared
                           else None)
            weighted = sum(self._effort(e) for e in open_episodes)
            rows.append({
                "validator": validator,
                "open_episodes": len(open_episodes),
                "weighted_effort": round(weighted, 2),
                "capacity_per_quarter": per_quarter,
                "capacity_declared": declared is not None,
                "utilisation": (round(weighted / per_quarter, 2)
                                if per_quarter else None),
                "oldest_open_days": round(
                    (moment - min((e.get("started_at") or moment)
                                  for e in open_episodes)) / DAY, 1)
                if open_episodes else 0.0,
                "overloaded": bool(per_quarter and weighted > per_quarter),
            })
        rows.sort(key=lambda r: -float(r["utilisation"] or 0.0))
        overloaded = [r for r in rows if r["overloaded"]]
        undeclared = [r["validator"] for r in rows if not r["capacity_declared"]]
        return {
            "validators": rows, "count": len(rows),
            "overloaded": [r["validator"] for r in overloaded],
            "capacity_not_declared": undeclared,
            "detail": self._workload_detail(rows, overloaded, undeclared),
        }

    def _effort(self, episode: Dict[str, Any]) -> float:
        tier = self._tier_of(episode)
        return self.effort.get(tier, DEFAULT_EFFORT) if tier else DEFAULT_EFFORT

    def _tier_of(self, episode: Dict[str, Any]) -> Optional[int]:
        model = self.registry.catalogue.by_id(episode.get("model_id"))
        tier = (model or {}).get("tier")
        return int(tier) if tier is not None else None

    @staticmethod
    def _workload_detail(rows, overloaded, undeclared) -> str:
        if not rows:
            return ("no validation episode is open and no capacity is declared, "
                    "so there is no queue to describe")
        out = (f"{sum(r['open_episodes'] for r in rows)} open episode(s) "
               f"across {len(rows)} validator(s)")
        if overloaded:
            out += (f". {len(overloaded)} are carrying more than they declared "
                    f"they could — and an overloaded validator is not a "
                    f"scheduling problem. The commonest response to a "
                    f"validation backlog is to let a model's own team review "
                    f"it, and the second commonest is to conclude an episode "
                    f"without doing the work; both are independence failures "
                    f"that begin here")
        if undeclared:
            out += (f". {len(undeclared)} carry work and have declared no "
                    f"capacity, so nothing can say whether they are "
                    f"overloaded — an absent capacity reads on every screen "
                    f"exactly like a generous one")
        return out

    # -------------------------------------------------------------- forecast
    def forecast(self, horizon_days: float = HORIZON_DAYS,
                 now: Optional[float] = None) -> Dict[str, Any]:
        """What falls due, against what the function said it could do."""
        moment = now if now is not None else time.time()
        due = self.due_within(horizon_days, now=moment)
        total_effort = sum(d["effort"] for d in due["models"])
        capacity = sum(c["episodes_per_quarter"] for c in self.capacities.many())
        quarters = horizon_days / QUARTER_DAYS
        available = capacity * quarters
        return {
            "horizon_days": horizon_days,
            "due": len(due["models"]), "effort_due": round(total_effort, 2),
            "capacity_per_quarter": capacity,
            "effort_available": round(available, 2),
            "shortfall": round(max(0.0, total_effort - available), 2),
            "validators_declaring": len(self.capacities.many()),
            "inverted_queue": due["inverted"],
            "assumes": ("effort is weighted by tier from a published table and "
                        "capacity is counted in episodes, so the two are "
                        "comparable only if a validator's quarter holds the "
                        "declared number of TIER 3 episodes. That is the "
                        "assumption, it is false in the ordinary case, and it "
                        "is printed here because a forecast that hides its "
                        "assumption is one people act on"),
            "detail": self._forecast_detail(total_effort, available, capacity,
                                            due, horizon_days),
        }

    @staticmethod
    def _forecast_detail(total, available, capacity, due, horizon) -> str:
        if not capacity:
            return (f"{due['count']} validation(s) fall due within "
                    f"{horizon:.0f} days and no validator has declared a "
                    f"capacity, so there is nothing to divide by. That is not a "
                    f"forecast of zero work: it is the absence of the half of "
                    f"the answer MAYA cannot derive")
        if total <= available:
            return (f"{due['count']} validation(s) due within {horizon:.0f} "
                    f"days at {total:.1f} units of weighted effort, against "
                    f"{available:.1f} declared — inside capacity, on an "
                    f"assumption stated beside this number")
        return (f"{due['count']} validation(s) due within {horizon:.0f} days at "
                f"{total:.1f} units of weighted effort against {available:.1f} "
                f"declared: a shortfall of {total - available:.1f}. What a firm "
                f"does with that is a decision; what it must not do is discover "
                f"it one model at a time")

    # ------------------------------------------------------------------ queue
    def due_within(self, horizon_days: float = HORIZON_DAYS,
                   now: Optional[float] = None) -> Dict[str, Any]:
        """Which models come due, worst risk first — and whether the queue is
        the wrong way round."""
        if self.plans is None:
            raise ValidationError(
                "this register was built without the validation plans, and "
                "every date in a forecast comes from a trigger they evaluate")
        moment = now if now is not None else time.time()
        rows = []
        for model in self.registry.list():
            verdict = self.plans.due(model["urn"], now=moment + horizon_days * DAY)
            already = self.plans.due(model["urn"], now=moment)
            if not verdict["due"]:
                continue
            tier = model.get("tier")
            rows.append({
                "urn": model["urn"], "tier": tier,
                "effort": self.effort.get(int(tier), DEFAULT_EFFORT)
                if tier is not None else DEFAULT_EFFORT,
                "already_due": bool(already["due"]),
                "last_validated": verdict.get("last_validated"),
                "triggers": [t["trigger"] for t in verdict["triggers"]
                             if t.get("fired")],
            })
        # By risk, and then by how long it has already been waiting. The two
        # orderings disagree, which is the point: a list sorted by due date puts
        # a Tier 4 model in front of a Tier 1 whenever the dates say so, and
        # nobody reading it notices.
        rows.sort(key=lambda r: (r["tier"] if r["tier"] is not None else 9,
                                 -(moment - (r["last_validated"] or 0))))
        return {"models": rows, "count": len(rows),
                "already_due": sum(1 for r in rows if r["already_due"]),
                "inverted": _inversion(rows),
                "detail": _queue_detail(rows, _inversion(rows), horizon_days)}


def _inversion(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Whether lower-risk work sits in front of higher-risk work by date.

    Invisible in a list sorted by due date, which is how every backlog is
    sorted — so it is computed rather than left to be noticed.
    """
    by_date = sorted(rows, key=lambda r: r.get("last_validated") or 0)
    ahead = []
    for index, row in enumerate(by_date):
        tier = row["tier"] if row["tier"] is not None else 9
        behind = [o for o in by_date[index + 1:]
                  if (o["tier"] if o["tier"] is not None else 9) < tier]
        if behind:
            ahead.append({"urn": row["urn"], "tier": row["tier"],
                          "in_front_of": [b["urn"] for b in behind[:3]],
                          "of_tier": min(b["tier"] for b in behind
                                         if b["tier"] is not None)})
    return {"inverted": bool(ahead), "cases": ahead[:10], "count": len(ahead)}


def _queue_detail(rows, inversion, horizon) -> str:
    if not rows:
        return (f"nothing falls due within {horizon:.0f} days. Worth reading "
                f"against the triggers rather than as a quiet quarter: a model "
                f"whose tier carries no elapsed-time trigger never appears here")
    out = (f"{len(rows)} model(s) due within {horizon:.0f} days, highest risk "
           f"first")
    if inversion["inverted"]:
        out += (f". Sorted by date instead, {inversion['count']} lower-risk "
                f"model(s) would sit in front of higher-risk ones — which is a "
                f"statement about how the function is being run rather than "
                f"about any one model, and it is invisible in a list sorted by "
                f"due date")
    return out
