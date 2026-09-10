"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a validation must cover for this model, and when the next one is due.

Two requirements that are one subject. A validation episode declared its scope
and its plan as free text, which meant every episode was scoped by whoever
opened it — and the thing a scope most needs to be is *the same for two models
of the same kind*, because otherwise "validated" means something different in
each report and nobody can compare them.

**The scope is derived, not written.** `L-15` already makes each trainability
class say what it owes, in exactly the three areas SR 26-2 asks a validation to
cover: `soundness` is conceptual soundness, `outcomes` is outcomes analysis, and
`answers` is what ongoing monitoring can actually establish for this class. A
catalogue of plans keyed by class would be a second copy of that, and the two
would disagree the first time either moved. So the class supplies *what*, the
tier supplies *how deeply*, and this module is the join.

Asking a T0 pricer for out-of-sample discrimination is not rigour. It is a
category error that wastes a review cycle and teaches everybody that the
checklist is noise — which is the real cost, because the next thing on the
checklist was load-bearing.

**Scheduling has triggers, not a calendar.** SR 26-2 removed the fixed annual
rule, and the usual response is to keep the annual rule anyway because it is the
only thing anybody knows how to administer. A trigger-based schedule needs
something to trigger on, and by now the register has plenty: a material change
to the version, a monitor in breach, a tier that rose, an immaterial model whose
escalation conditions tripped. Each is already computed elsewhere and each is a
better reason to revalidate than a date.

**"No fixed cadence" is supported explicitly and is the point of the clause.** A
tier 4 model has no elapsed-time trigger at all — it is revalidated when
something happens to it and not otherwise. Making the low-tier path a *shorter*
version of the high-tier one is how proportionality gets quietly discarded, and
this returns no due date rather than a distant one, so nobody can mistake the
second for the first.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

DAY = 86400.0

#: The three areas SR 26-2 asks a validation to cover, and the fibre field that
#: says what each one means for a given class. The mapping is the whole reason
#: a plan can be derived rather than written.
AREAS: Dict[str, str] = {
    "conceptual_soundness": "soundness",
    "outcomes_analysis": "outcomes",
    "ongoing_monitoring": "answers",
}

#: How deeply, by tier. This is what the tier contributes that the class cannot:
#: two models of one class at different tiers owe the same QUESTIONS and a
#: different amount of independence in answering them.
DEPTH: Dict[int, str] = {
    1: "independent_recode",
    2: "independent_review",
    3: "peer_review",
    4: "owner_attestation",
}

DEPTH_MEANING: Dict[str, str] = {
    "independent_recode": "a validator implements the model independently from "
                          "the documentation and compares outputs. The strongest "
                          "form, and the only one that catches a specification "
                          "the code does not implement",
    "independent_review": "a validator who did not build it examines the "
                          "evidence and challenges the conclusions",
    "peer_review": "somebody other than the builder reads it against the "
                   "framework",
    "owner_attestation": "the owner states that it still does what it says. "
                         "Proportionate, and honest about being the lightest "
                         "thing that is still a control",
}

#: How long a validation stands before elapsed time alone is a reason to look
#: again — and **None for tier 4**, which is the requirement's "no fixed
#: cadence" and not an oversight.
ELAPSED_DAYS: Dict[int, Optional[float]] = {
    1: 365.0, 2: 2 * 365.0, 3: 3 * 365.0, 4: None,
}


class ValidationPlans:
    """Derives a validation's scope from the class and its depth from the tier."""

    def __init__(self, registry, fibres, validation=None, monitoring=None,
                 changes=None):
        self.registry, self.fibres = registry, fibres
        self.validation, self.monitoring = validation, monitoring
        self.changes = changes

    # ----------------------------------------------------------------- scope
    def propose(self, urn: str, semver: str) -> Dict[str, Any]:
        """What a validation of this version must cover, and how deeply."""
        from core.validation.common import ValidationError

        model = self.registry.require(urn)
        version = self.registry.version_service.require(urn, semver)
        trainability = version.get("trainability_class")
        fibre = self.fibres.get(trainability) if trainability else None
        if fibre is None:
            raise ValidationError(
                f"no fibre is registered for class {trainability!r}, so "
                f"nothing can say what a validation of this version owes")
        tier = model.get("tier")
        if tier is None:
            raise ValidationError(
                "this model has no risk tier, so how deeply it must be "
                "validated is undecided. Assess it first — the class says what "
                "the questions are and the tier says how much independence "
                "answering them takes")

        depth = DEPTH.get(int(tier), "peer_review")
        areas = [{
            "area": area,
            "what_this_class_owes": getattr(fibre, field),
            "because": f"{trainability} ({fibre.label})",
        } for area, field in AREAS.items()]
        return {
            "urn": urn, "semver": semver, "trainability_class": trainability,
            "tier": tier, "depth": depth, "depth_means": DEPTH_MEANING[depth],
            "areas": areas,
            "elapsed_days": ELAPSED_DAYS.get(int(tier)),
            "detail": (f"a {trainability} model at tier {tier}: three areas, "
                       f"each scoped by what the class can actually be asked, "
                       f"answered to {depth.replace('_', ' ')} depth"),
        }

    def check(self, urn: str, semver: str,
              scope: List[str]) -> Dict[str, Any]:
        """Whether a declared scope covers what the class owes.

        The control this module contributes. An episode may narrow its scope —
        a targeted revalidation is a real thing — but it must say which areas
        it is not covering, because *validated* meaning three areas in one
        report and one area in another is how a portfolio of validations stops
        being comparable.
        """
        planned = self.propose(urn, semver)
        declared = set(scope or ())
        missing = [a["area"] for a in planned["areas"]
                   if a["area"] not in declared]
        return {
            **planned, "declared_scope": sorted(declared),
            "not_covered": missing, "complete": not missing,
            "detail": (planned["detail"] if not missing else
                       f"this scope omits {', '.join(missing)}. A targeted "
                       f"revalidation is a real thing and this is not a "
                       f"refusal — but the omission has to be visible, or "
                       f"'validated' means something different in every "
                       f"report"),
        }

    # -------------------------------------------------------------- schedule
    def due(self, urn: str, now: Optional[float] = None) -> Dict[str, Any]:
        """Why this model is due for validation, if it is.

        Triggers rather than a calendar. SR 26-2 removed the fixed annual rule
        and the usual response is to keep it anyway, because a date is the only
        thing anybody knows how to administer. Every trigger here is computed
        elsewhere in the register already, and each is a better reason to look
        again than the earth having gone round the sun.
        """
        model = self.registry.require(urn)
        moment = now if now is not None else time.time()
        tier = model.get("tier")
        triggers: List[Dict[str, Any]] = []

        last = self._last_validation(urn)
        window = ELAPSED_DAYS.get(int(tier)) if tier is not None else None
        if window is None:
            triggers.append({
                "trigger": "elapsed", "fired": False,
                "why": ("this model has no elapsed-time trigger at all — it is "
                        "revalidated when something happens to it and not "
                        "otherwise. That is the proportionality clause being "
                        "used rather than quietly discarded, and it is why "
                        "there is no due date here rather than a distant one"),
            })
        elif last is None:
            triggers.append({
                "trigger": "elapsed", "fired": True,
                "why": "this model has never been validated"})
        else:
            age = (moment - last) / DAY
            triggers.append({
                "trigger": "elapsed", "fired": age >= window,
                "observed_days": round(age, 1), "window_days": window,
                "why": f"a tier {tier} validation stands for {window:.0f} days"})

        triggers.append(self._breaching(model))
        fired = [t for t in triggers if t.get("fired")]
        return {
            "urn": urn, "tier": tier, "last_validated": last,
            "triggers": triggers, "due": bool(fired),
            "detail": (f"due: {', '.join(t['trigger'] for t in fired)}"
                       if fired else
                       "nothing has happened to this model and no window has "
                       "elapsed, so there is no reason to validate it again "
                       "yet — which is a decision rather than an omission"),
        }

    def _last_validation(self, urn: str) -> Optional[float]:
        if self.validation is None:
            return None
        episodes = [e for e in self.validation.for_model(urn)
                    if e.get("completed_at")]
        return max((e["completed_at"] for e in episodes), default=None)

    def _breaching(self, model: Dict[str, Any]) -> Dict[str, Any]:
        if self.monitoring is None:
            return {"trigger": "monitoring", "fired": False,
                    "why": "no monitoring service is wired into this instance"}
        status = self.monitoring.status(model["id"]) or {}
        breaching = status.get("breaching") or status.get("in_breach") or 0
        return {
            "trigger": "monitoring", "fired": bool(breaching),
            "observed": breaching,
            "why": ("a model whose monitors are in breach has told you "
                    "something changed, which is a better reason to revalidate "
                    "than a date"),
        }
