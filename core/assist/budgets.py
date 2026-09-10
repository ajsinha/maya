"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a capability may spend, checked before it spends it.

`core/assist/providers/remote.py` names this gap in its own docstring — *cost
and rate limits, which are operational, and which is why they are named here
rather than discovered in production*. This is that, and the ordering is the
whole of it.

**A budget checked after the call is an invoice.** Everything about a generation
was already recorded — the prompt digest, the claims, what the oracle said, who
attested it — and every one of those is recorded *after* the provider answered.
A spend figure computed the same way tells you what happened. It does not stop
anything happening, and the requirement's phrase is *hard-enforced at the
gateway*.

**Three numbers, because they bound three different failures.** Tokens bound a
prompt that grew — a grounding set that quietly went from forty nodes to four
thousand. Cost bounds the invoice, which is the number somebody signs for.
**Steps bound a loop**, and that is the one worth having: a runaway agent is not
one enormous call, it is a large number of small ones, and it will pass a token
budget and a cost budget for a long time before either notices. A budget that
only counted size would let the shape that actually runs away run away.

**The overshoot is exactly one generation, and that is arithmetic rather than a
defect.** MAYA cannot know what a call will cost before making it — nobody can,
short of proxying the provider and metering the stream. What it can do is refuse
the *next* one, so a capability with a 100,000-token budget stops somewhere
between 100,000 and 100,000 plus one generation. Saying so is better than
implying a precision the arrangement does not have.

**A rolling window, never a lifetime cap.** A lifetime cap is reached once and
then the capability is dead forever, which is how budgets get raised to a number
that means nothing. Thirty days by default, and the window is per capability
because a document drafter and a probe generator do not run at the same rate.

**No budget declared is not unlimited.** A capability with none runs on the
default, and `across_the_estate` names which ones do — a number nobody chose is
a number nobody owns, and reporting it as though it were a decision is how a
default becomes permanent.

**Exhaustion refuses; it does not suspend.** The capability stays registered and
active, and the next window opens as it always would. Suspending is a governance
act somebody takes with a reason recorded, and a control that quietly retires a
capability because it was busy on Tuesday is one people work around.

**The spend ledger is a separate table from the generation log, and that is the
finding this requirement turned up.** A generation whose claims ground nothing is
never recorded — `GenerationLog.record` refuses it and writes no row. The
provider was still called and the tokens were still spent. Counting spend from
generation rows would therefore mean a capability whose output never grounds has
no measurable cost at all, which is exactly backwards: the capability failing
most often is the one burning the most. `ai_spend.generation_id` is null for
precisely those calls, and that null is the column worth reading — it is the
spend that bought nothing.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.assist.common import AssistError
from core.log import get_logger

logger = get_logger(__name__)

DAY = 86400.0

#: The three bounds, and what each one is for. Named as data because the
#: refusal, the estate view and the API all have to agree about them.
BUDGETS: Dict[str, str] = {
    "tokens": "the size of what is asked and answered — bounds a grounding set "
              "or a prompt that quietly grew",
    "cost": "the invoice, which is the number somebody signs for",
    "steps": "how many times — the one that bounds a loop, because a runaway "
             "agent is a large number of small calls and passes the other two "
             "for a long time first",
}

#: What a capability spends if nobody has said. Deliberately small: a default
#: large enough to be comfortable is a default nobody ever replaces.
DEFAULT_BUDGETS: Dict[str, float] = {
    "tokens": 200_000.0, "cost": 50.0, "steps": 500.0,
}

DEFAULT_WINDOW_DAYS = 30.0

#: The fraction of a budget at which the estate view starts saying so. Not a
#: refusal — the point of naming it early is that raising a budget is a decision
#: somebody should make before the work stops, not after.
WARN_AT = 0.8


class BudgetRegister:
    """Sets, checks and records what the platform's own AI may spend."""

    def __init__(self, capabilities, spend, evidence=None):
        self.capabilities, self.spend = capabilities, spend
        self.evidence = evidence

    # ------------------------------------------------------------------- set
    def set(self, capability_key: str, *, tokens: Optional[float] = None,
            cost: Optional[float] = None, steps: Optional[float] = None,
            window_days: Optional[float] = None,
            actor: str = "system") -> Dict[str, Any]:
        """Declare what this capability may spend per window."""
        capability = self.capabilities.require(capability_key)
        fields: Dict[str, Any] = {}
        for name, value in (("token_budget", tokens), ("cost_budget", cost),
                            ("step_budget", steps)):
            if value is None:
                continue
            if float(value) <= 0:
                raise AssistError(
                    "budget_not_positive",
                    f"a {name.split('_')[0]} budget of {value} would refuse "
                    f"every call, which is a suspension written as a number",
                    "suspend the capability instead, which records a reason")
            fields[name] = value
        if window_days is not None:
            if float(window_days) <= 0:
                raise AssistError(
                    "window_not_positive",
                    f"a budget window of {window_days} days is not a window",
                    "a window is how long the budget lasts before it refills")
            fields["budget_window_days"] = float(window_days)
        if not fields:
            raise AssistError(
                "nothing_to_set",
                "no budget was given, so this would record a decision nobody "
                "made",
                f"name at least one of {', '.join(BUDGETS)}, or a window")

        if self.evidence is not None:
            with self.evidence.recording():
                self.capabilities.capabilities.set(fields, id=capability["id"])
                self.evidence.append(
                    "ai_budget_set", "capability", capability["id"],
                    {"capability_key": capability_key, **fields}, actor=actor)
        else:
            self.capabilities.capabilities.set(fields, id=capability["id"])
        logger.info("budget for capability %s set by %s: %s",
                    capability_key, actor, fields)
        return self.of(capability_key)

    # ----------------------------------------------------------------- read
    def of(self, capability_key: str,
           now: Optional[float] = None) -> Dict[str, Any]:
        """This capability's budget, what it has spent, and what is left."""
        capability = self.capabilities.require(capability_key)
        return self._state(capability, now)

    def _state(self, capability: Dict[str, Any],
               now: Optional[float] = None) -> Dict[str, Any]:
        moment = now if now is not None else time.time()
        window = float(capability.get("budget_window_days")
                       or DEFAULT_WINDOW_DAYS)
        since = moment - window * DAY
        spent = self._spent(capability["id"], since)

        limits, defaulted = {}, []
        for name, column in (("tokens", "token_budget"), ("cost", "cost_budget"),
                             ("steps", "step_budget")):
            declared = capability.get(column)
            if declared is None:
                limits[name] = DEFAULT_BUDGETS[name]
                defaulted.append(name)
            else:
                limits[name] = float(declared)

        lines = []
        for name, limit in limits.items():
            used = spent[name]
            share = used / limit if limit else 1.0
            lines.append({
                "budget": name, "means": BUDGETS[name], "limit": limit,
                "spent": used, "remaining": max(0.0, limit - used),
                "share": round(share, 4),
                "declared": name not in defaulted,
                "exhausted": used >= limit, "near": WARN_AT <= share < 1.0,
            })
        exhausted: List[str] = [str(line["budget"]) for line in lines
                                if line["exhausted"]]
        return {
            "capability_key": capability.get("capability_key"),
            "window_days": window, "window_opened": since,
            "calls_in_window": spent["calls"],
            "calls_that_produced_nothing": spent["wasted"],
            "budgets": lines,
            "on_default": defaulted,
            "exhausted": exhausted, "within_budget": not exhausted,
            "detail": self._detail(capability, lines, exhausted, defaulted,
                                   window),
        }

    def _spent(self, capability_id: str, since: float) -> Dict[str, float]:
        """What this capability has consumed since a moment.

        Every call, not every generation. A draft the gate refused cost exactly
        as much to produce as one it accepted, and it left no generation row at
        all — so a budget read off the generation log would be one the least
        reliable capability could never exhaust.
        """
        rows = [r for r in self.spend.many(capability_id=capability_id)
                if (r.get("spent_at") or 0) >= since]
        return {
            "tokens": float(sum(r.get("tokens") or 0 for r in rows)),
            "cost": float(sum(r.get("cost") or 0.0 for r in rows)),
            "steps": float(sum(r.get("steps") or 0 for r in rows)),
            "calls": len(rows),
            # The spend that bought nothing. Named separately because it is the
            # number that says a capability is not working rather than busy.
            "wasted": sum(1 for r in rows if not r.get("generation_id")),
        }

    @staticmethod
    def _detail(capability: Dict[str, Any], lines: List[Dict[str, Any]],
                exhausted: List[str], defaulted: List[str],
                window: float) -> str:
        key = capability.get("capability_key")
        if exhausted:
            worst = next(line for line in lines
                         if line["budget"] == exhausted[0])
            return (f"{key} has spent its {exhausted[0]} budget for this "
                    f"{window:.0f}-day window — {worst['spent']:.0f} against "
                    f"{worst['limit']:.0f}. The next call is refused. The "
                    f"capability is not suspended: the window refills, and "
                    f"suspending is a decision somebody takes with a reason")
        near = [line["budget"] for line in lines if line["near"]]
        out = f"{key} is within budget"
        if near:
            out += (f", though {', '.join(near)} is past {WARN_AT:.0%} of the "
                    f"window — raising a budget is a decision better made "
                    f"before the work stops than after")
        if defaulted:
            out += (f". {', '.join(defaulted)} runs on the default rather than "
                    f"a number anybody chose")
        return out

    # ---------------------------------------------------------------- check
    def check(self, capability_key: str, *, steps: float = 1.0,
              now: Optional[float] = None) -> Dict[str, Any]:
        """Refuse before the call, or return the headroom.

        The gateway. Called before the provider is asked, which is the only
        position from which a budget is a control rather than a report.
        """
        state = self.of(capability_key, now)
        if state["exhausted"]:
            names = ", ".join(state["exhausted"])
            raise AssistError(
                "budget_exhausted",
                f"capability '{capability_key}' has spent its {names} budget "
                f"for this {state['window_days']:.0f}-day window, so this call "
                f"is refused before it is made. A budget checked after the "
                f"call is an invoice",
                f"raise the budget deliberately, or wait for the window — it "
                f"opened at {state['window_opened']:.0f} and refills as "
                f"calls age out of it")
        return state

    # --------------------------------------------------------------- charge
    def charge(self, capability_key: str, *, tokens: float = 0.0,
               cost: float = 0.0, steps: float = 1.0,
               generation_id: Optional[str] = None,
               outcome: str = "recorded", at: Optional[float] = None,
               actor: str = "system") -> Dict[str, Any]:
        """Record what one provider call consumed.

        Called whether or not anything survived the gate. `generation_id` is
        null when nothing did, and `outcome` says which refusal it was — a
        capability burning its budget on `oracle_failed` is a different problem
        from one burning it on `nothing_grounded`, and a single "wasted" count
        would not distinguish them.

        Zero is a real answer and is recorded as one. The mock provider returns
        no token count and says so rather than inventing a plausible number, and
        a budget fed invented figures would refuse real work for imaginary
        reasons.
        """
        capability = self.capabilities.require(capability_key)
        row = {"capability_id": capability["id"],
               "generation_id": generation_id,
               "tokens": int(tokens), "cost": float(cost), "steps": int(steps),
               "outcome": outcome,
               "spent_at": at if at is not None else time.time(),
               "spent_by": actor}
        return self.spend.add(row)

    # ---------------------------------------------------------------- estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every capability, what it may spend and what it has.

        The column worth reading is `on_default`. A capability nobody set a
        budget for is not unbudgeted — it runs on a number this module chose,
        and reporting that as though somebody decided it is how a default
        becomes permanent.
        """
        moment = now if now is not None else time.time()
        rows = [self._state(c, moment) for c in self.capabilities.list()]
        rows.sort(key=lambda r: -max((line["share"] for line in r["budgets"]),
                                     default=0.0))
        exhausted = [r for r in rows if r["exhausted"]]
        defaulted = [r for r in rows if r["on_default"]]
        return {
            "capabilities": rows, "count": len(rows),
            "exhausted": len(exhausted),
            "on_default": len(defaulted),
            "spent": {name: sum(line["spent"] for r in rows
                                for line in r["budgets"]
                                if line["budget"] == name)
                      for name in BUDGETS},
            "calls_that_produced_nothing": sum(
                r["calls_that_produced_nothing"] for r in rows),
            "detail": (
                f"{len(rows)} capabilit{'y' if len(rows) == 1 else 'ies'}, "
                f"{len(exhausted)} of them out of budget"
                + (f", {len(defaulted)} running on a number nobody chose"
                   if defaulted else "")),
        }
