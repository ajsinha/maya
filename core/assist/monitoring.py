"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What the platform's own generative assistance is actually doing.

Almost none of this is new measurement. The generation log already records what
each draft claimed and what the grounding gate dropped; the spend ledger already
records what every call consumed and which ones bought nothing; the injection
scan already records what the register tried to say to a model. This joins them
and says what the numbers mean — which is the part that goes wrong.

**Citation accuracy is 1.0 by construction, and that is not good news.** The
grounding gate drops a claim citing something the platform does not hold *before
anybody reads it*, so measuring citation accuracy on the output measures the
gate and not the model. A dashboard showing 100% would be true and would tell a
reader the opposite of what it appears to. The number carrying the information is
the **rejection rate** — what the model tried to say and could not support — and
it is reported in its place with the reason.

**Toxicity and personal-data leakage are not measured, and are reported as not
measured.** MAYA has no classifier for either and will not ship a keyword list
dressed up as one: a dashboard showing zero toxicity because nothing looked would
be worse than a blank, because a blank prompts somebody to ask. What would have
to be true is named instead.

**Edit distance is the only number here that is not self-reported.** Everything
else is the platform grading its own homework. Edit distance is a human's
revision of what a model wrote, which is the one signal that comes from outside
the system — and it is therefore the one worth trending.

**A falling override rate is the alarm, not the goal.** The obvious reading is
that the capability is improving. The other reading is that a reviewer who has
approved forty correct drafts is not reviewing the forty-first, which is the
automation bias the review sample exists to catch — and the two look identical in
the number. So it is reported with both readings rather than with a green tick.
"""
from __future__ import annotations

import statistics
import time
from typing import Any, Dict, List, Optional

DAY = 86400.0

#: The metrics the requirement names, what each one is read from, and — for the
#: two this platform cannot measure — what would have to be true.
METRICS: Dict[str, Dict[str, str]] = {
    "groundedness": {
        "from": "the generation log's kept and rejected claims",
        "means": "the share of what a model claimed that the register could "
                 "support",
    },
    "citation_accuracy": {
        "from": "the grounding gate, by construction",
        "means": "1.0 always, because a claim citing something the platform "
                 "does not hold is dropped before a reader sees it. This "
                 "measures the gate and not the model, which is why the "
                 "rejection rate is the number to read",
    },
    "hallucination_rate": {
        "from": "the generation log's rejected claims",
        "means": "the share of claims the model could not support. The useful "
                 "half of citation accuracy",
    },
    "refusal_rate": {
        "from": "the spend ledger's outcomes",
        "means": "the share of calls that produced nothing — a capability "
                 "failing rather than one that is busy",
    },
    "injection_detections": {
        "from": "the injection scan recorded beside each generation",
        "means": "register content shaped like an instruction to a model. A "
                 "signal and never a gate",
    },
    "token_cost": {
        "from": "the spend ledger",
        "means": "what this has cost, per window",
    },
    "edit_distance": {
        "from": "what a reviewer changed at attestation",
        "means": "the only measure here that is not self-reported, and "
                 "therefore the one worth trending",
    },
    "override_rate": {
        "from": "generations rejected at attestation",
        "means": "how often a person disagreed. A FALLING rate is ambiguous "
                 "between a capability improving and a reviewer who has "
                 "stopped reading",
    },
    "toxicity": {
        "from": "not measured",
        "means": "MAYA has no classifier and will not ship a keyword list "
                 "dressed up as one. A dashboard showing zero because nothing "
                 "looked is worse than a blank, because a blank prompts "
                 "somebody to ask",
    },
    "personal_data_leakage": {
        "from": "not measured",
        "means": "the same. Detecting personal data in generated prose needs a "
                 "classifier this platform does not have, and the grounding "
                 "gate bounds the problem differently: a claim can only cite "
                 "evidence the register already holds",
    },
}

#: Reported as unmeasured rather than as zero, and named here so the API, the
#: screen and this module cannot drift about which is which.
NOT_MEASURED = ("toxicity", "personal_data_leakage")

#: The window a rate is computed over. Thirty days, matching the spend window,
#: so a cost figure and a refusal rate describe the same period.
DEFAULT_WINDOW_DAYS = 30.0

#: Below this many attested generations, an override rate is noise. Named
#: because a rate over four samples printed to two decimal places is a number
#: pretending to be a measurement.
MIN_FOR_A_RATE = 10


class AssistMonitoring:
    """Joins the generation log, the spend ledger and the injection scan."""

    def __init__(self, generations, capabilities, spend=None):
        self.generations, self.capabilities = generations, capabilities
        self.spend = spend

    # ------------------------------------------------------------ vocabulary
    @staticmethod
    def vocabulary() -> Dict[str, Any]:
        """Every metric, where it comes from, and the two that are not measured."""
        return {
            "metrics": [{"metric": k, **v} for k, v in METRICS.items()],
            "not_measured": list(NOT_MEASURED),
            "detail": (
                f"{len(METRICS) - len(NOT_MEASURED)} of {len(METRICS)} metrics "
                f"are computed from what the platform already records. "
                f"{', '.join(NOT_MEASURED)} are reported as NOT MEASURED rather "
                f"than as zero: a dashboard showing no toxicity because nothing "
                f"looked is worse than a blank, because a blank prompts "
                f"somebody to ask"),
        }

    # ------------------------------------------------------------ capability
    def of(self, capability_key: str, now: Optional[float] = None,
           window_days: float = DEFAULT_WINDOW_DAYS) -> Dict[str, Any]:
        """Every measurable metric for one capability."""
        capability = self.capabilities.require(capability_key)
        moment = now if now is not None else time.time()
        since = moment - window_days * DAY
        rows = [r for r in self.generations.generations.many(
            capability_id=capability["id"])
            if (r.get("created_at") or 0) >= since]

        kept = sum(len(r.get("claims") or []) for r in rows)
        dropped = sum(len(r.get("rejected_claims") or []) for r in rows)
        claims = kept + dropped
        attested = [r for r in rows if r["state"] == "attested"]
        rejected = [r for r in rows if r["state"] == "rejected"]
        decided = len(attested) + len(rejected)
        distances = [r["edit_distance"] for r in attested
                     if r.get("edit_distance") is not None]
        injections = sum((r.get("output") or {}).get("injection", {}).get(
            "count", 0) for r in rows)
        spend = self._spend(capability["id"], since)

        return {
            "capability_key": capability_key, "tier": capability.get("tier"),
            "window_days": window_days, "generations": len(rows),
            "claims": claims,
            "groundedness": round(kept / claims, 4) if claims else None,
            "hallucination_rate": (round(dropped / claims, 4) if claims
                                   else None),
            # 1.0 always, and reported with the reason rather than as a score.
            "citation_accuracy": 1.0 if kept else None,
            "citation_accuracy_means": METRICS["citation_accuracy"]["means"],
            "refusal_rate": spend["refusal_rate"],
            "injection_detections": injections,
            "token_cost": spend["cost"], "tokens": spend["tokens"],
            "calls": spend["calls"],
            "edit_distance": self._distribution(distances),
            "override_rate": self._override(len(rejected), decided),
            "not_measured": {name: METRICS[name]["means"]
                             for name in NOT_MEASURED},
            "detail": self._detail(capability_key, rows, claims, dropped,
                                   distances, len(rejected), decided, spend),
        }

    def _spend(self, capability_id: str, since: float) -> Dict[str, Any]:
        if self.spend is None:
            return {"calls": 0, "cost": None, "tokens": None,
                    "refusal_rate": None}
        rows = [r for r in self.spend.many(capability_id=capability_id)
                if (r.get("spent_at") or 0) >= since]
        wasted = sum(1 for r in rows if not r.get("generation_id"))
        return {
            "calls": len(rows),
            "cost": float(sum(r.get("cost") or 0.0 for r in rows)),
            "tokens": float(sum(r.get("tokens") or 0 for r in rows)),
            "refusal_rate": round(wasted / len(rows), 4) if rows else None,
        }

    @staticmethod
    def _override(rejected: int, decided: int) -> Dict[str, Any]:
        """How often a person disagreed, with both readings of a low number.

        The obvious reading is that the capability is improving. The other is
        that a reviewer who has approved forty correct drafts is not reviewing
        the forty-first — and the two look identical in the number.
        """
        if decided < MIN_FOR_A_RATE:
            return {
                "rate": None, "decided": decided,
                "means": (f"only {decided} generation(s) have been decided, "
                          f"and a rate over fewer than {MIN_FOR_A_RATE} is a "
                          f"number pretending to be a measurement"),
            }
        rate = rejected / decided
        return {
            "rate": round(rate, 4), "decided": decided, "rejected": rejected,
            "means": (
                "a reviewer is disagreeing regularly, which is what a review "
                "looks like when it is happening"
                if rate >= 0.05 else
                "almost nothing is being rejected. That reads two ways and "
                "they look identical in the number: the capability may be "
                "good, or the reviewer may have stopped reading. The "
                "automation-bias sample exists for exactly this, and a rate "
                "falling to zero is the alarm rather than the goal"),
        }

    @staticmethod
    def _distribution(values: List[float]) -> Dict[str, Any]:
        """Quantiles rather than a mean.

        A mean edit distance over drafts a reviewer either waved through or
        rewrote completely is a number describing neither.
        """
        if not values:
            return {"count": 0,
                    "detail": ("nothing has been attested, so the one measure "
                               "here that is not self-reported has no value "
                               "yet")}
        ordered = sorted(values)
        return {
            "count": len(ordered), "min": ordered[0], "max": ordered[-1],
            "median": statistics.median(ordered),
            "mean": statistics.fmean(ordered),
            "detail": ("quantiles rather than a mean: a mean over drafts a "
                       "reviewer either waved through or rewrote completely "
                       "describes neither"),
        }

    @staticmethod
    def _detail(key, rows, claims, dropped, distances, rejected, decided,
                spend) -> str:
        if not rows:
            if spend["calls"]:
                # The sharpest case there is, and the one the earlier wording
                # skipped: it WAS called, every call produced nothing, and a
                # generation-log-only view would have shown an empty capability
                # that looked idle.
                return (f"{key} was called {spend['calls']:.0f} time(s) in this "
                        f"window and produced nothing at all — "
                        f"{spend['refusal_rate']:.0%} of calls. That is a "
                        f"capability failing rather than one that is busy, and "
                        f"it costs exactly as much as one that works")
            return (f"{key} has produced nothing in this window, and was not "
                    f"called either — which is a different fact from its "
                    f"producing nothing useful")
        out = (f"{len(rows)} generation(s), {claims} claim(s), {dropped} of "
               f"which the register could not support")
        if spend["refusal_rate"]:
            out += (f". {spend['refusal_rate']:.0%} of calls produced nothing "
                    f"at all, which is a capability failing rather than one "
                    f"that is busy")
        if not distances:
            out += (". Nothing has been attested, so the one measure here that "
                    "is not self-reported has no value yet")
        return out

    # ---------------------------------------------------------------- estate
    def across_the_estate(self, now: Optional[float] = None,
                          window_days: float = DEFAULT_WINDOW_DAYS
                          ) -> Dict[str, Any]:
        """Every registered capability, measured."""
        rows = [self.of(c["capability_key"], now, window_days)
                for c in self.capabilities.list()]
        rows.sort(key=lambda r: -(r["hallucination_rate"] or 0.0))
        silent = [r for r in rows if not r["generations"]]
        unreviewed = [r for r in rows
                      if r["override_rate"]["rate"] == 0.0]
        return {
            "capabilities": rows, "count": len(rows),
            "generations": sum(r["generations"] for r in rows),
            "never_used": len(silent),
            "never_overridden": len(unreviewed),
            "not_measured": list(NOT_MEASURED),
            "detail": (
                f"{len(rows)} capabilit{'y' if len(rows) == 1 else 'ies'}, "
                f"{sum(r['generations'] for r in rows)} generation(s) in the "
                f"window"
                + (f"; {len(silent)} produced nothing at all, which is a "
                   f"different fact from producing nothing useful"
                   if silent else "")
                + (f"; {len(unreviewed)} have never had a draft rejected, "
                   f"which reads two ways and they look identical in the "
                   f"number" if unreviewed else "")),
        }
