"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a model of this class, at this tier, should be watched for.

Four monitor kinds existed and nothing said which of them any given model
needed, so every monitor in the estate was one somebody had thought to create.
That produces two failures and only one of them is visible: the model with no
monitors at all, which a coverage screen finds; and the model with three
monitors that could never have answered anything about it, which reads as
coverage and is worse.

The defaults are **derived from the fibre**, never declared here. `L-15` already
makes each trainability class say which questions it can answer — a T0 pricer
has no fitted relationship to lose, so performance and calibration are not
questions about it; a T5 generative assembly cannot be asked for a Brier score
over text. A second table of per-class defaults in this module would be a second
opinion about the same thing, and the two would disagree the first time either
moved. So this module contributes exactly two things the fibre does not know:
which *test* implements each kind, and how *often* to run it.

**Cadence and severity come from the tier, not the class.** How a model is
watched is a function of what it can be asked (its class) and how much rides on
it (its tier), and conflating them would mean a Tier 1 rulebook and a Tier 4 one
were monitored identically.

**Proposed, then seeded.** `propose()` returns what would be created and why,
including what it is *not* creating and the reason. Silently creating monitors
nobody asked for is how an estate acquires coverage it does not understand, and
the reasons are the half a reviewer needs: *this model has no performance
monitor because its class cannot answer that question* is a very different
sentence from *nobody got round to it*.
"""
from __future__ import annotations

from typing import Any, Dict, List

from core.monitoring.common import (CALIBRATION, INPUT_DRIFT, KINDS,
                                    LABEL_DEPENDENT, PERFORMANCE, SCORE_DRIFT,
                                    MonitorError)

#: The test that implements each kind by default. Every one of these is in
#: `ADMISSIBLE_TESTS` for its kind — the definition service checks that, and a
#: default that failed its own admissibility rule would be a fine joke.
#:
#: `discrimination.auc` for performance rather than one of the accuracy tests,
#: because the estate's models are predominantly classifiers; a regression model
#: overrides it, which is what `propose()` returning a proposal is for.
DEFAULT_TEST: Dict[str, str] = {
    INPUT_DRIFT: "stability.psi",
    SCORE_DRIFT: "stability.psi",
    PERFORMANCE: "discrimination.auc",
    CALIBRATION: "calibration.expected_vs_actual",
}

#: The threshold each default test breaches at. PSI above 0.25 is the
#: conventional "population has moved" line and 0.1 the "watch it" line; the
#: higher one is used because a monitor that breaches on every ordinary
#: fluctuation is a monitor somebody switches off.
DEFAULT_THRESHOLD: Dict[str, Dict[str, float]] = {
    "stability.psi": {"max": 0.25},
    "discrimination.auc": {"min": 0.65},
    "calibration.expected_vs_actual": {"max": 0.20},
}

#: How often, by tier. A Tier 1 model is looked at daily and a Tier 4 model
#: monthly, which is the same shape as the review cadence the tiering engine
#: already applies to whole-model review.
CADENCE_DAYS: Dict[int, float] = {1: 1.0, 2: 7.0, 3: 14.0, 4: 30.0}

#: How loudly a breach speaks, by tier.
SEVERITY: Dict[int, str] = {1: "High", 2: "High", 3: "Medium", 4: "Low"}

#: How many consecutive breaches before it escalates. A Tier 1 model escalates
#: on the second, because waiting for a third is a month of a material model
#: being wrong.
ESCALATE_AFTER: Dict[int, int] = {1: 2, 2: 2, 3: 3, 4: 3}

#: How long to wait for outcomes before a label-dependent monitor may report.
#: **This is the field the SDK's own docstring says people leave at zero and
#: should not** — a performance monitor evaluated over a cohort whose outcomes
#: have not matured measures the maturity of the cohort and not the model. A
#: default of zero would have shipped exactly that mistake as the default, so
#: the default is a quarter and the caller is told to set the real one.
DEFAULT_LABEL_DELAY_DAYS: float = 90.0


class MonitoringDefaults:
    """Proposes, and on request seeds, the monitor set a model's class admits."""

    def __init__(self, monitors, fibres, class_of, tier_of):
        self.monitors, self.fibres = monitors, fibres
        # Both passed as lookups rather than as registry references, so that
        # this module does not import the register it is describing — the same
        # discipline `core.monitoring.definitions` applies for the same reason.
        self.class_of, self.tier_of = class_of, tier_of

    # --------------------------------------------------------------- propose
    def propose(self, urn: str, model_id: str) -> Dict[str, Any]:
        """What this model should be watched for, and what it should not.

        The second half is the point. A model with no performance monitor
        because its class cannot answer that question, and a model with no
        performance monitor because nobody got round to it, look identical on
        every coverage screen ever built — and only one of them is a gap.
        """
        trainability = self.class_of(urn)
        if not trainability:
            raise MonitorError(
                "no_class",
                "this model has no version, so it has no trainability class "
                "and nothing can say which questions it can be asked",
                "register a version first; the class is derived from the "
                "kernel, not declared")
        fibre = self.fibres.get(trainability)
        if fibre is None:
            raise MonitorError(
                "no_fibre", f"no fibre is registered for class {trainability}",
                "a class without a fibre cannot say what it owes; see L-15")
        tier = self.tier_of(urn)
        if tier is None:
            raise MonitorError(
                "no_tier",
                "this model has no risk tier, so how often to watch it is "
                "undecided",
                "assess the model first — cadence and severity come from the "
                "tier, because how closely a model is watched depends on what "
                "rides on it and not only on what it is")

        existing = {(m["kind"], m["test_key"])
                    for m in self.monitors.for_model(model_id)}
        admitted, declined = [], []
        for kind in KINDS:
            test_key = DEFAULT_TEST[kind]
            if not fibre.admits_monitor(kind):
                declined.append({
                    "kind": kind,
                    "reason": f"a '{kind}' monitor cannot answer anything "
                              f"about a {trainability} model ({fibre.label}); "
                              f"what it can answer is: {fibre.answers}",
                    "is_a_gap": False})
                continue
            proposal = {
                "kind": kind, "test_key": test_key,
                "threshold": dict(DEFAULT_THRESHOLD[test_key]),
                "cadence_days": CADENCE_DAYS.get(tier, 14.0),
                "breach_severity": SEVERITY.get(tier, "Medium"),
                "escalate_after": ESCALATE_AFTER.get(tier, 3),
                "label_delay_days": (DEFAULT_LABEL_DELAY_DAYS
                                     if kind in LABEL_DEPENDENT else 0.0),
                "already_defined": (kind, test_key) in existing,
            }
            if kind in LABEL_DEPENDENT:
                proposal["note"] = (
                    "label_delay_days defaults to a quarter rather than to "
                    "zero. Evaluating this over a cohort whose outcomes have "
                    "not matured measures the maturity of the cohort and not "
                    "the model — set the delay this model's outcomes actually "
                    "take")
            admitted.append(proposal)

        missing = [p for p in admitted if not p["already_defined"]]
        return {
            "urn": urn, "trainability_class": trainability,
            "class_name": fibre.label, "tier": tier,
            "propose": admitted, "declined": declined,
            "already_defined": len(admitted) - len(missing),
            "would_create": len(missing),
            "detail": self._detail(fibre, tier, admitted, missing, declined),
        }

    # ------------------------------------------------------------------ seed
    def seed(self, urn: str, model_id: str, *, owner: str,
             actor: str = "system") -> Dict[str, Any]:
        """Create the proposed monitors that are not already there.

        Idempotent by (kind, test_key): seeding twice creates nothing the second
        time and says so, because a defaults helper that duplicated its own work
        would be a defaults helper nobody dared run on an estate.
        """
        plan = self.propose(urn, model_id)
        created = []
        for proposal in plan["propose"]:
            if proposal["already_defined"]:
                continue
            made = self.monitors.define(
                model_id,
                name=f"{proposal['kind']} ({proposal['test_key']})",
                kind=proposal["kind"], test_key=proposal["test_key"],
                threshold=proposal["threshold"], owner=owner,
                cadence_days=proposal["cadence_days"],
                label_delay_days=proposal["label_delay_days"],
                breach_severity=proposal["breach_severity"],
                escalate_after=proposal["escalate_after"], actor=actor)
            created.append(made)
        return {**plan, "created": created, "created_count": len(created)}

    # ---------------------------------------------------------------- shaping
    @staticmethod
    def _detail(fibre, tier: int, admitted: List[Dict[str, Any]],
                missing: List[Dict[str, Any]],
                declined: List[Dict[str, Any]]) -> str:
        head = (f"a {fibre.trainability_class} model at tier {tier} admits "
                f"{len(admitted)} of the {len(KINDS)} monitor kinds")
        if declined:
            head += (f"; the other {len(declined)} "
                     f"({', '.join(d['kind'] for d in declined)}) "
                     f"cannot answer anything about this class, which is a "
                     f"property of the model and not a gap in its coverage")
        if not missing:
            return f"{head}. All of them are already defined"
        return f"{head}. {len(missing)} of them are not yet defined"
