"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The path for a model that does not matter much, and the condition that would
mean it does.

Every framework has a proportionality clause and almost every framework then
fails to use it. What happens instead is that four hundred immaterial models are
put through the same validation, documentation and monitoring the tier 1 models
get; none of it is done properly because there is not enough of anybody to do
it; and the tier 1 models end up governed to the average standard of the whole
estate. Proportionality is not a discount. It is what makes the expensive
controls affordable where they are needed.

So this path is two things and, as the requirement says, **no more**:
identification, and a watch for the condition that would make the model
material. The "no more" half is written down here, because the failure this
prevents is not somebody doing too little for a small model — it is somebody
doing a bit of everything for all of them.

**What a tier 4 model owes.** That it is in the register, with an owner. That
something is watching for it to stop being immaterial. That is the whole list,
and it is the tier lattice's own `CONTROLS[4]` rather than a second opinion.

**What it does not owe, said out loud.** No independent validation, no annual
review cycle, no monthly monitoring, no committee. Naming these is the point:
an unwritten exemption is one that erodes the first time somebody senior asks
why a model has no validation report.

**The conditions, and why these three.** Materiality was assessed from what
somebody declared, and a declaration goes stale quietly. What the register can
observe without being told is *usage*, *dependence* and *age* — a model called
fifty thousand times a month is not immaterial whatever its exposure field says;
a model that three others now read has become a common dependency; and an
assessment nobody has revisited in years is a fact about the assessment rather
than the model. None of these escalates anything automatically. They raise a
finding that says *look at this again*, because materiality is a judgement and
the register's job is to make sure somebody makes it rather than to make it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

DAY = 86400.0

#: The tier this path is for. Named rather than inlined, because "immaterial"
#: and "tier 4" are the same thing said two ways and the code should only have
#: to be told once.
IMMATERIAL_TIER = 4

#: Invocations in the window past which a model is not immaterial by usage,
#: whatever its exposure field says. A model called this often is one whose
#: failure somebody notices.
USAGE_THRESHOLD = 10_000

#: How many downstream models make this a common dependency rather than a
#: leaf. Two, because one downstream consumer is a pair and two is a pattern.
DEPENDENCY_THRESHOLD = 2

#: How long an assessment may stand before its age is itself the finding. The
#: tier 4 review cadence is three years, so this is that plus a quarter's
#: grace — a review that is late is a different conversation from one nobody
#: has scheduled.
STALE_DAYS = 3 * 365 + 90


class ImmaterialPath:
    """What an immaterial model owes, and what would stop it being immaterial."""

    def __init__(self, registry, tiering, invocations=None, composition=None,
                 risk_repo=None, findings=None):
        self.registry, self.tiering = registry, tiering
        self.invocations, self.composition = invocations, composition
        self.risk_repo, self.findings = risk_repo, findings

    # ------------------------------------------------------------------ read
    def for_model(self, urn: str, now: Optional[float] = None) -> Dict[str, Any]:
        """Whether this model is on the immaterial path, and what that means."""
        import time

        model = self.registry.require(urn)
        moment = now if now is not None else time.time()
        tier = model.get("tier")
        if tier != IMMATERIAL_TIER:
            return {
                "urn": urn, "tier": tier, "on_the_immaterial_path": False,
                "detail": (f"this model is tier {tier}, so the proportionality "
                           f"path does not apply to it" if tier else
                           "this model has no tier, so nothing can say whether "
                           "it is immaterial — an unassessed model is the top "
                           "of the lattice, not the bottom"),
            }

        owes = list(self.tiering.required_controls(
            IMMATERIAL_TIER, model.get("designations")))
        heavier = sorted({c for t in (1, 2, 3)
                          for c in self.tiering.required_controls(t)}
                         - set(owes))
        conditions = self._conditions(model, moment)
        tripped = [c for c in conditions if c["tripped"]]
        return {
            "urn": urn, "tier": tier, "on_the_immaterial_path": True,
            "owes": owes,
            # Named rather than left implicit. An unwritten exemption is one
            # that erodes the first time somebody senior asks why a model has
            # no validation report.
            "does_not_owe": heavier,
            "conditions": conditions,
            "still_immaterial": not tripped,
            "detail": self._detail(owes, heavier, tripped),
        }

    def _conditions(self, model: Dict[str, Any],
                    moment: float) -> List[Dict[str, Any]]:
        """The three the register can observe without being told."""
        out = [self._usage(model), self._dependence(model),
               self._staleness(model, moment)]
        return [c for c in out if c]

    def _usage(self, model: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self.invocations is None:
            return None
        calls = self.invocations.for_model(model["id"])["total"]
        return {
            "condition": "usage", "observed": calls,
            "threshold": USAGE_THRESHOLD,
            "tripped": calls >= USAGE_THRESHOLD,
            "why": ("a model called this often is one whose failure somebody "
                    "notices, whatever its exposure field says. Exposure was "
                    "declared once; this is observed continuously"),
        }

    def _dependence(self, model: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self.composition is None:
            return None
        radius = self.composition.blast_radius(model["urn"])
        count = radius.get("count") or 0
        return {
            "condition": "dependence", "observed": count,
            "threshold": DEPENDENCY_THRESHOLD,
            "tripped": count >= DEPENDENCY_THRESHOLD,
            "why": ("a model several others read has become a common "
                    "dependency, and a common dependency's materiality is not "
                    "its own — it is the sum of what rests on it"),
        }

    def _staleness(self, model: Dict[str, Any],
                   moment: float) -> Optional[Dict[str, Any]]:
        if self.risk_repo is None:
            return None
        rows = sorted(self.risk_repo.many(model_id=model["id"]),
                      key=lambda r: r.get("assessed_at") or 0)
        if not rows:
            return {"condition": "staleness", "observed": None,
                    "threshold": STALE_DAYS, "tripped": False,
                    "why": "no assessment is recorded, which the approval gate "
                           "refuses on for a better reason than this one"}
        age = (moment - (rows[-1].get("assessed_at") or 0)) / DAY
        return {
            "condition": "staleness", "observed": round(age, 1),
            "threshold": STALE_DAYS, "tripped": age >= STALE_DAYS,
            "why": ("materiality was assessed from what somebody declared, and "
                    "a declaration goes stale quietly. An assessment nobody has "
                    "revisited in years is a fact about the assessment rather "
                    "than about the model"),
        }

    # ----------------------------------------------------------------- sweep
    def sweep(self, now: Optional[float] = None,
              actor: str = "system") -> Dict[str, Any]:
        """Every immaterial model, and a finding where one may have stopped being one.

        Nothing is escalated automatically. Materiality is a judgement, and the
        register's job is to make sure somebody makes it rather than to make it
        — a platform that silently re-tiered a model would be one whose tiers
        nobody could account for.
        """
        looked, raised = 0, []
        for model in self.registry.list(tier=IMMATERIAL_TIER):
            looked += 1
            report = self.for_model(model["urn"], now=now)
            tripped = [c for c in report.get("conditions", []) if c["tripped"]]
            if tripped and self._raise(model, tripped):
                raised.append(model["urn"])
        return {"models": looked, "raised": raised, "count": len(raised),
                "detail": (f"{looked} immaterial model(s) checked; "
                           + (f"{len(raised)} may no longer be immaterial"
                              if raised else
                              "none has tripped an escalation condition"))}

    def _raise(self, model: Dict[str, Any],
               tripped: List[Dict[str, Any]]) -> bool:
        if self.findings is None:
            return False
        title = "Immaterial model may have stopped being immaterial"
        if any(f.get("title") == title
               for f in self.findings.open_for(model["id"])):
            return False
        self.findings.raise_finding(
            model["id"], "Medium", title=title,
            owner=model.get("owner") or "person/unknown",
            description=(
                "This model is on the proportionality path, which means it "
                "carries identification and condition monitoring and no more. "
                + " ".join(f"Its {c['condition']} condition has tripped: "
                           f"{c['observed']} against a threshold of "
                           f"{c['threshold']} — {c['why']}."
                           for c in tripped)
                + " Nothing has been re-tiered: materiality is a judgement, and "
                  "this finding exists so that somebody makes it rather than so "
                  "that the platform makes it for them."),
            category="tiering", source="self_identified", blocking=False)
        return True

    @staticmethod
    def _detail(owes: List[str], heavier: List[str],
                tripped: List[Dict[str, Any]]) -> str:
        head = (f"on the proportionality path: {len(owes)} control(s) — "
                f"{', '.join(owes)} — and explicitly not the "
                f"{len(heavier)} a higher tier would carry")
        if not tripped:
            return f"{head}. No escalation condition has tripped"
        return (f"{head}. {len(tripped)} escalation condition(s) have tripped "
                f"({', '.join(c['condition'] for c in tripped)}), so somebody "
                f"should look at the materiality again — nothing has been "
                f"re-tiered automatically")
